"""测试：系统设置 API（默认写作参数）"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import yaml

from story_engine.api.main import app


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """建立测试配置"""
    tmp_cfg = Path(tempfile.mktemp(suffix=".yaml"))
    config_data = {
        "llm": {
            "default_model": "deepseek-v4-pro",
            "models": [
                {"name": "deepseek-v4-pro", "provider": "deepseek",
                 "model_id": "deepseek-chat", "enabled": True},
            ],
        },
        "writing": {
            "temperature": 0.7,
            "max_tokens": 4096,
        },
    }
    with open(tmp_cfg, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    monkeypatch.setattr("story_engine.core.config._config_instance", None)
    monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", tmp_cfg)
    monkeypatch.setattr("story_engine.api.routes.generate._router", None)
    yield


client = TestClient(app)


class TestGetSettings:
    """GET /api/settings — 获取默认写作参数"""

    def test_returns_default_settings(self):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        settings = data["data"]
        assert settings["default_model"] == "deepseek-v4-pro"
        assert settings["temperature"] == 0.7
        assert settings["max_tokens"] == 4096

    def test_returns_correct_types(self):
        resp = client.get("/api/settings")
        settings = resp.json()["data"]
        assert isinstance(settings["temperature"], float)
        assert isinstance(settings["max_tokens"], int)
        assert isinstance(settings["default_model"], str)

    def test_returns_defaults_when_config_missing(self, monkeypatch):
        """配置中没有 writing 段时返回合理默认值"""
        tmp_cfg = Path(tempfile.mktemp(suffix=".yaml"))
        with open(tmp_cfg, "w", encoding="utf-8") as f:
            yaml.dump({"llm": {"default_model": "test"}}, f)
        monkeypatch.setattr("story_engine.core.config._config_instance", None)
        monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", tmp_cfg)

        resp = client.get("/api/settings")
        assert resp.status_code == 200
        settings = resp.json()["data"]
        assert settings["default_model"] == "test"
        # defaults for missing writing section
        assert settings["temperature"] == 0.7
        assert settings["max_tokens"] == 4096


class TestUpdateSettings:
    """POST /api/settings — 保存默认写作参数"""

    def test_update_temperature(self):
        resp = client.post("/api/settings", json={"temperature": 0.5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["temperature"] == 0.5
        assert data["data"]["max_tokens"] == 4096  # unchanged

        # 验证持久化
        from story_engine.core.config import get_config
        cfg = get_config()
        assert cfg.get("writing.temperature") == 0.5

    def test_update_max_tokens(self):
        resp = client.post("/api/settings", json={"max_tokens": 8192})
        assert resp.status_code == 200
        assert resp.json()["data"]["max_tokens"] == 8192

    def test_update_default_model(self):
        resp = client.post("/api/settings", json={"default_model": "local-model"})
        assert resp.status_code == 200
        assert resp.json()["data"]["default_model"] == "local-model"

    def test_partial_update(self):
        """只更新一个字段，其他保持不变"""
        resp = client.post("/api/settings", json={"default_model": "other-model"})
        data = resp.json()["data"]
        assert data["default_model"] == "other-model"
        assert data["temperature"] == 0.7  # unchanged
        assert data["max_tokens"] == 4096  # unchanged

    def test_update_all_fields(self):
        resp = client.post("/api/settings", json={
            "default_model": "new-model",
            "temperature": 0.3,
            "max_tokens": 2048,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["default_model"] == "new-model"
        assert data["temperature"] == 0.3
        assert data["max_tokens"] == 2048

    def test_returns_422_for_invalid_temperature(self):
        resp = client.post("/api/settings", json={"temperature": -1})
        assert resp.status_code == 422

    def test_returns_422_for_invalid_max_tokens(self):
        resp = client.post("/api/settings", json={"max_tokens": 0})
        assert resp.status_code == 422
