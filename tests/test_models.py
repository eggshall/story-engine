"""测试：模型管理 API"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.core.config import get_config


@pytest.fixture(autouse=True)
def setup_test_env(make_config):
    """建立测试配置：3 个模型（含禁用 + 含 api_key）（统一 conftest fixture）"""
    make_config({
        "llm": {
            "default_model": "pro-model",
            "models": [
                {
                    "name": "pro-model",
                    "provider": "deepseek",
                    "model_id": "deepseek-chat",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "sk-test-pro-key",
                    "enabled": True,
                    "temperature": 0.7,
                    "max_tokens": 8192,
                },
                {
                    "name": "flash-model",
                    "provider": "deepseek",
                    "model_id": "deepseek-chat",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "",
                    "enabled": True,
                    "temperature": 0.8,
                    "max_tokens": 4096,
                },
                {
                    "name": "local-model",
                    "provider": "local",
                    "model_id": "qwen3.5:9b-q6-fixed",
                    "base_url": "http://localhost:11434",
                    "api_key": "ollama",
                    "enabled": False,
                    "temperature": 0.8,
                    "max_tokens": 8192,
                    "read_timeout": 300,
                },
            ]
        }
    })
    yield


client = TestClient(app)


class TestListModels:
    """GET /api/models/ — 列出模型"""

    def test_returns_all_models(self):
        resp = client.get("/api/models/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        models = data["data"]
        assert len(models) == 3

    def test_returns_correct_fields(self):
        resp = client.get("/api/models/")
        models = resp.json()["data"]
        pro = next(m for m in models if m["name"] == "pro-model")
        assert pro["provider"] == "deepseek"
        assert pro["model_id"] == "deepseek-chat"
        assert pro["enabled"] is True
        assert pro["temperature"] == 0.7
        assert pro["max_tokens"] == 8192

    def test_masks_api_key_in_response(self):
        """api_key 应部分掩码，但保留 base_url"""
        resp = client.get("/api/models/")
        models = resp.json()["data"]
        pro = next(m for m in models if m["name"] == "pro-model")
        assert pro["base_url"] == "https://api.deepseek.com/v1"
        # api_key should be masked — show only last 4 chars
        assert "api_key" in pro
        assert pro["api_key"].endswith("key")
        assert pro["api_key"] != "sk-test-pro-key"

    def test_returns_disabled_model(self):
        resp = client.get("/api/models/")
        models = resp.json()["data"]
        local = next(m for m in models if m["name"] == "local-model")
        assert local["enabled"] is False

    def test_default_model(self):
        resp = client.get("/api/models/default")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["default_model"] == "pro-model"


class TestUpdateModel:
    """PATCH /api/models/{name} — 更新模型配置"""

    def test_update_enabled(self):
        resp = client.patch("/api/models/local-model", json={"enabled": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["enabled"] is True

        # 验证持久化
        cfg = get_config()
        models = cfg.get("llm.models", [])
        updated = next(m for m in models if m["name"] == "local-model")
        assert updated["enabled"] is True

    def test_update_temperature(self):
        resp = client.patch("/api/models/pro-model", json={"temperature": 0.5})
        assert resp.status_code == 200
        assert resp.json()["data"]["temperature"] == 0.5

        cfg = get_config()
        models = cfg.get("llm.models", [])
        updated = next(m for m in models if m["name"] == "pro-model")
        assert updated["temperature"] == 0.5

    def test_update_api_key(self):
        resp = client.patch("/api/models/pro-model", json={"api_key": "sk-new-secret-key"})
        assert resp.status_code == 200
        # response should have masked key
        assert resp.json()["data"]["api_key"].endswith("key")
        assert resp.json()["data"]["api_key"] != "sk-new-secret-key"

        # but config file should have full key
        cfg = get_config()
        models = cfg.get("llm.models", [])
        updated = next(m for m in models if m["name"] == "pro-model")
        assert updated["api_key"] == "sk-new-secret-key"

    def test_update_base_url(self):
        resp = client.patch(
            "/api/models/flash-model",
            json={"base_url": "https://custom.api.com/v1"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["base_url"] == "https://custom.api.com/v1"

        cfg = get_config()
        models = cfg.get("llm.models", [])
        updated = next(m for m in models if m["name"] == "flash-model")
        assert updated["base_url"] == "https://custom.api.com/v1"

    def test_update_max_tokens(self):
        resp = client.patch("/api/models/pro-model", json={"max_tokens": 16384})
        assert resp.status_code == 200
        assert resp.json()["data"]["max_tokens"] == 16384

    def test_partial_update_only_changes_specified_fields(self):
        """只更新指定字段，其他保持不变"""
        resp = client.patch("/api/models/pro-model", json={"enabled": False})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["enabled"] is False
        assert data["temperature"] == 0.7  # unchanged
        assert data["max_tokens"] == 8192  # unchanged

        # 改回来
        client.patch("/api/models/pro-model", json={"enabled": True})

    def test_returns_404_for_nonexistent_model(self):
        resp = client.patch("/api/models/non-existent", json={"enabled": True})
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    def test_returns_422_for_invalid_temperature(self):
        resp = client.patch(
            "/api/models/pro-model",
            json={"temperature": -1},
        )
        assert resp.status_code == 422

    def test_returns_422_for_invalid_max_tokens(self):
        resp = client.patch(
            "/api/models/pro-model",
            json={"max_tokens": 0},
        )
        assert resp.status_code == 422

    def test_update_multiple_fields_at_once(self):
        resp = client.patch(
            "/api/models/flash-model",
            json={
                "enabled": False,
                "temperature": 0.3,
                "max_tokens": 2048,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["enabled"] is False
        assert data["temperature"] == 0.3
        assert data["max_tokens"] == 2048


class TestTestConnection:
    """POST /api/models/{name}/test — 测试连接"""

    def test_successful_connection(self, monkeypatch):
        """模拟 HTTP 返回 200"""
        async def mock_get(*args, **kwargs):
            mock = MagicMock()
            mock.status_code = 200
            mock.text = "OK"
            return mock

        monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
        resp = client.post("/api/models/pro-model/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "ok"

    def test_failed_connection(self, monkeypatch):
        """模拟 HTTP 抛出异常 — 错误信息不泄露内部细节"""
        async def mock_get(*args, **kwargs):
            raise Exception("Connection refused")

        monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
        resp = client.post("/api/models/pro-model/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True  # 测试本身没挂
        assert data["data"]["status"] == "error"
        assert "Connection refused" not in data["data"]["message"]


class TestSsrProtection:
    """SSRF 防护：内网/元数据/非 https 地址被拒"""

    def _set_models(self, models, monkeypatch):
        cfg = get_config()
        cfg.set("llm.models", models)
        cfg.save()
        import story_engine.core.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config_instance", None)

    @pytest.mark.parametrize("bad_url", [
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/api",
        "http://192.168.1.1",
        "http://172.16.0.9",
        "file:///etc/passwd",
        "ftp://example.com/file",
    ])
    def test_probe_rejects_internal_url(self, bad_url, monkeypatch):
        self._set_models([{
            "name": "evil", "provider": "openai", "model_id": "x",
            "base_url": bad_url, "api_key": "", "enabled": True,
        }], monkeypatch)
        resp = client.post("/api/models/evil/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["data"]["status"] == "error"

    def test_probe_rejects_public_http(self, monkeypatch):
        self._set_models([{
            "name": "http-only", "provider": "openai", "model_id": "x",
            "base_url": "http://api.example.com/v1", "api_key": "", "enabled": True,
        }], monkeypatch)
        resp = client.post("/api/models/http-only/test")
        assert resp.json()["data"]["status"] == "error"

    def test_probe_allows_localhost_local_model(self, monkeypatch):
        self._set_models([{
            "name": "local", "provider": "local", "model_id": "qwen",
            "base_url": "http://localhost:11434", "api_key": "ollama", "enabled": True,
        }], monkeypatch)

        async def mock_get(*args, **kwargs):
            mock = MagicMock()
            mock.status_code = 200
            return mock

        monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
        resp = client.post("/api/models/local/test")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "ok"

    def test_probe_allows_public_https(self, monkeypatch):
        self._set_models([{
            "name": "pub", "provider": "openai", "model_id": "x",
            "base_url": "https://1.1.1.1/v1", "api_key": "", "enabled": True,
        }], monkeypatch)

        async def mock_get(*args, **kwargs):
            mock = MagicMock()
            mock.status_code = 200
            return mock

        monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
        resp = client.post("/api/models/pub/test")
        assert resp.json()["data"]["status"] == "ok"

    def test_probe_uses_api_tags_for_ollama(self, monkeypatch):
        """ollama provider 应探测 /api/tags"""
        self._set_models([{
            "name": "ollama", "provider": "ollama", "model_id": "qwen",
            "base_url": "http://localhost:11434", "api_key": "ollama", "enabled": True,
        }], monkeypatch)

        captured = {}

        async def mock_get(client, url, **kwargs):
            captured["url"] = url
            mock = MagicMock()
            mock.status_code = 200
            return mock

        monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
        resp = client.post("/api/models/ollama/test")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "ok"
        assert captured["url"].endswith("/api/tags")

    def test_probe_5xx_returns_error(self, monkeypatch):
        """服务端 5xx 应返回 error 状态"""
        async def mock_get(*args, **kwargs):
            mock = MagicMock()
            mock.status_code = 500
            return mock

        monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
        resp = client.post("/api/models/pro-model/test")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "error"

    def test_probe_3xx_redirect_counts_ok(self, monkeypatch):
        """非 5xx 的 HTTP 状态（如 200/404/3xx）按连接成功处理"""
        async def mock_get(*args, **kwargs):
            mock = MagicMock()
            mock.status_code = 404
            return mock

        monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
        resp = client.post("/api/models/pro-model/test")
        assert resp.json()["data"]["status"] == "ok"

    def test_timeout_connection(self, monkeypatch):
        """模拟超时"""
        async def mock_get(*args, **kwargs):
            raise TimeoutError("timeout")

        monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
        resp = client.post("/api/models/pro-model/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["status"] == "error"

    def test_returns_404_for_nonexistent_model(self):
        resp = client.post("/api/models/non-existent/test")
        assert resp.status_code == 404

    def test_returns_error_for_model_without_base_url(self, monkeypatch):
        """没有 base_url 的模型应直接返回错误"""
        cfg = get_config()
        models = cfg.get("llm.models", [])
        for m in models:
            if m["name"] == "local-model":
                m["base_url"] = ""
        cfg.save()

        # 重设配置
        import story_engine.core.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_config_instance", None)

        resp = client.post("/api/models/local-model/test")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "error"
