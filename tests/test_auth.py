"""测试：API 鉴权中间件（X-API-Key / 本机回环）"""

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app

client = TestClient(app)


@pytest.fixture
def config_with_key(make_config):
    make_config({
        "security": {"api_key": "test-secret-key"},
        "llm": {"default_model": "m", "models": []},
    })


@pytest.fixture
def config_no_key(make_config):
    make_config({
        "llm": {"default_model": "m", "models": []},
    })


def test_health_no_auth_needed(config_no_key):
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_root_no_auth_needed(config_no_key):
    resp = client.get("/")
    assert resp.status_code == 200


def test_no_key_rejected(config_with_key):
    resp = client.get("/api/models/")
    assert resp.status_code == 401


def test_wrong_key_rejected(config_with_key):
    resp = client.get("/api/models/", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


def test_correct_key_accepted(config_with_key):
    resp = client.get("/api/models/", headers={"X-API-Key": "test-secret-key"})
    assert resp.status_code == 200


def test_localhost_allowed_without_key(config_no_key):
    resp = client.get("/api/models/")
    assert resp.status_code == 200


def test_non_loopback_rejected_without_key(config_no_key):
    """未配置 api_key 时，非回环来源应被拒 403（S5.1）"""
    import asyncio

    from starlette.requests import Request

    from story_engine.api.main import api_auth_middleware

    async def _call_next(request):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=200, content={"ok": True})

    async def _run():
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/models/",
            "headers": [(b"host", b"evil.example.com")],
            "query_string": b"",
            "client": ("203.0.113.7", 12345),
            "scheme": "http",
        }
        req = Request(scope)
        resp = await api_auth_middleware(req, _call_next)
        return resp

    resp = asyncio.run(_run())
    assert resp.status_code == 403


def test_loopback_without_key_passes_middleware(config_no_key):
    """回环来源未配置 key 时应放行"""
    import asyncio

    from starlette.requests import Request

    from story_engine.api.main import api_auth_middleware

    async def _call_next(request):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=200, content={"ok": True})

    async def _run():
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/models/",
            "headers": [(b"host", b"localhost")],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
        }
        req = Request(scope)
        resp = await api_auth_middleware(req, _call_next)
        return resp

    resp = asyncio.run(_run())
    assert resp.status_code == 200


def test_health_skips_auth_with_key(config_with_key):
    """配置 key 时 /api/health 仍免鉴权"""
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_cors_whitelist_origin_allowed(config_no_key):
    """白名单 Origin 应返回对应 CORS 头"""
    resp = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_unknown_origin_not_echoed(config_no_key):
    """非白名单 Origin 不应被回显在 allow-origin 头"""
    resp = client.get("/api/health", headers={"Origin": "http://evil.example.com"})
    assert resp.status_code == 200
    acao = resp.headers.get("access-control-allow-origin")
    assert acao != "http://evil.example.com"
