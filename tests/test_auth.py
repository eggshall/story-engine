"""测试：API 鉴权中间件（X-API-Key / 本机回环）"""

import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from story_engine.api.main import app

client = TestClient(app)


def _write_config(monkeypatch, data: dict) -> None:
    tmp_cfg = Path(tempfile.mktemp(suffix=".yaml"))
    with open(tmp_cfg, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    monkeypatch.setattr("story_engine.core.config._config_instance", None)
    monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", tmp_cfg)


@pytest.fixture
def config_with_key(monkeypatch):
    _write_config(monkeypatch, {
        "security": {"api_key": "test-secret-key"},
        "llm": {"default_model": "m", "models": []},
    })


@pytest.fixture
def config_no_key(monkeypatch):
    _write_config(monkeypatch, {
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
