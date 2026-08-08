"""测试：P1 L9 统一错误处理 — 未捕获异常脱敏 / 业务错误 400 / lifespan 资源释放"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from story_engine.api.main import BusinessError, app

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch):
    """隔离 API 配置，避免本地 config.yaml 触发鉴权"""
    tmp_cfg = Path(tempfile.mktemp(suffix=".yaml"))
    with open(tmp_cfg, "w", encoding="utf-8") as f:
        yaml.dump({"llm": {"default_model": "test-model", "models": []}}, f)
    monkeypatch.setattr("story_engine.core.config._config_instance", None)
    monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", tmp_cfg)
    yield


class TestGlobalExceptionHandler:
    def test_unhandled_exception_masked(self):
        """未捕获异常返回 500 且不泄露内部细节"""

        async def _boom():
            raise RuntimeError("secret path /etc/passwd leaked")

        app.add_api_route("/api/_boom", _boom, methods=["GET"])

        try:
            resp = client.get("/api/_boom")
            assert resp.status_code == 500
            detail = resp.json()["detail"]
            assert "/etc/passwd" not in detail
            assert "secret" not in detail
        finally:
            # 清理测试路由，避免污染其他测试
            routes = [r for r in app.routes if getattr(r, "path", None) == "/api/_boom"]
            for r in routes:
                app.routes.remove(r)

    def test_http_exception_preserved(self):
        """HTTPException 保留原始状态码与 detail"""
        resp = client.get("/api/novel/不存在/map")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    def test_import_bad_json_masked(self):
        """导入非法 JSON 不泄露解析细节"""
        resp = client.post("/api/import/json", json={"json_data": "{bad json"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "Expecting" not in resp.json()["message"]

    def test_business_error_returns_400(self):
        """业务错误 BusinessError 统一转 HTTPException(400)"""
        async def _business_fail():
            raise BusinessError("章节内容不能为空")

        app.add_api_route("/api/_business", _business_fail, methods=["GET"])

        try:
            resp = client.get("/api/_business")
            assert resp.status_code == 400
            assert resp.json()["detail"] == "章节内容不能为空"
        finally:
            routes = [r for r in app.routes if getattr(r, "path", None) == "/api/_business"]
            for r in routes:
                app.routes.remove(r)


class TestLifespan:
    def test_shutdown_closes_router(self):
        """应用 shutdown 时应调用 close_router 释放 LLM 连接池"""
        with patch("story_engine.api.routes.generate.close_router",
                   new=AsyncMock(return_value=None)) as mock_close:
            with TestClient(app) as tc:
                # 启动阶段触发 lifespan；进程内正常请求
                assert tc.get("/api/health").status_code == 200
            # 退出 with 块触发 shutdown → close_router 被调用
            mock_close.assert_awaited()

    def test_shutdown_close_failure_is_swallowed(self):
        """close_router 抛异常时 shutdown 不应崩溃"""
        async def _boom():
            raise RuntimeError("close 失败")

        with patch("story_engine.api.routes.generate.close_router", new=_boom):
            with TestClient(app) as tc:
                assert tc.get("/api/health").status_code == 200
            # 不抛异常即通过
