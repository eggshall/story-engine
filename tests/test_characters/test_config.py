"""测试：配置管理"""
import tempfile
from pathlib import Path

from story_engine.core.config import Config


class TestConfig:
    def test_empty_config(self):
        tmp = Path(tempfile.mktemp(suffix=".yaml"))
        cfg = Config(tmp)
        assert cfg.all() == {}

    def test_get_default(self):
        cfg = Config(Path("/nonexistent/config.yaml"))
        assert cfg.get("llm.default_model", "fallback") == "fallback"

    def test_set_and_get(self):
        tmp = Path(tempfile.mktemp(suffix=".yaml"))
        cfg = Config(tmp)
        cfg.set("llm.default_model", "test-model")
        assert cfg.get("llm.default_model") == "test-model"

    def test_save_and_reload(self):
        tmp = Path(tempfile.mktemp(suffix=".yaml"))
        cfg = Config(tmp)
        cfg.set("llm.default_model", "saved-model")
        cfg.save()

        cfg2 = Config(tmp)
        assert cfg2.get("llm.default_model") == "saved-model"

    def test_nested_get(self):
        tmp = Path(tempfile.mktemp(suffix=".yaml"))
        cfg = Config(tmp)
        cfg.set("llm.models.0.name", "model-a")
        cfg.set("llm.models.0.enabled", True)
        assert cfg.get("llm.models.0.name") == "model-a"
        assert cfg.get("llm.models.0.enabled") is True

    def test_nonexistent_nested(self):
        cfg = Config(Path("/nonexistent.yaml"))
        assert cfg.get("a.b.c.d") is None
