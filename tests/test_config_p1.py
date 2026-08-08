"""测试：P1 配置健壮性 — YAML 加载容错 / llm.models 校验 / _get_router 不污染共享配置"""

import asyncio
import builtins
import copy
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import yaml

from story_engine.core.config import Config, _validate_models, reload_config


def _write_cfg(data, monkeypatch) -> Path:
    tmp = Path(tempfile.mktemp(suffix=".yaml"))
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", tmp)
    return tmp


class TestConfigLoad:
    def test_missing_file_empty(self, monkeypatch):
        tmp = Path(tempfile.mktemp(suffix=".yaml"))
        monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", tmp)
        cfg = Config()
        assert cfg.all() == {}

    def test_invalid_yaml_falls_back(self, monkeypatch, tmp_path):
        tmp = tmp_path / "bad.yaml"
        tmp.write_text("llm: [unclosed\n  - bad", encoding="utf-8")
        monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", tmp)
        cfg = Config()
        assert cfg.all() == {}  # 回退为空配置而非崩溃

    def test_non_dict_yaml_falls_back(self, monkeypatch, tmp_path):
        tmp = tmp_path / "list.yaml"
        tmp.write_text("- a\n- b\n", encoding="utf-8")
        monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", tmp)
        cfg = Config()
        assert cfg.all() == {}

    def test_invalid_models_filtered(self, monkeypatch, tmp_path):
        _write_cfg({
            "llm": {
                "models": [
                    {"name": "ok", "provider": "deepseek", "temperature": 0.7},
                    {"name": "bad", "temperature": 3.5},   # temperature 越界
                    {"name": "", "provider": "x"},          # name 为空
                    "not-a-dict",                            # 非 dict
                ]
            }
        }, monkeypatch)
        cfg = Config()
        models = cfg.get("llm.models", [])
        assert len(models) == 1
        assert models[0]["name"] == "ok"

    def test_validate_models_none_and_non_list(self):
        """_validate_models 直接调用：None / 非列表 返回空列表"""
        assert _validate_models(None) == []
        assert _validate_models("not-a-list") == []
        assert _validate_models({"name": "x"}) == []

    def test_validate_models_defaults_filled(self):
        """合法条目应填充默认字段（model_dump）"""
        parsed = _validate_models([{"name": "m", "provider": "local"}])
        assert parsed == [{
            "name": "m", "provider": "local", "model_id": "", "base_url": "",
            "api_key": "", "enabled": True, "temperature": 0.7, "max_tokens": 4096,
        }]

    def test_oserror_load_falls_back(self, monkeypatch, tmp_path):
        """读取失败（路径为目录）回退为空配置而非崩溃"""
        dir_path = tmp_path / "adir"
        dir_path.mkdir()
        monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", dir_path)
        cfg = Config()
        assert cfg.all() == {}

    def test_get_with_non_dict_intermediate(self, monkeypatch):
        """get 路径中途遇到非 dict 应返回 default"""
        _write_cfg({"llm": {"models": [1, 2]}}, monkeypatch)
        cfg = Config()
        assert cfg.get("llm.models.name", "dflt") == "dflt"

    def test_valid_config_unchanged(self, monkeypatch, tmp_path):
        data = {
            "llm": {
                "default_model": "m",
                "models": [{"name": "m", "provider": "local", "enabled": True}],
            },
            "security": {"api_key": "k"},
        }
        _write_cfg(data, monkeypatch)
        cfg = Config()
        assert cfg.get("llm.default_model") == "m"
        assert cfg.get("security.api_key") == "k"


class TestRouterNoPollution:
    def test_get_router_does_not_mutate_shared_config(self, monkeypatch):
        """_get_router 注入超时不应持久化到共享配置（深拷贝）"""
        models = [{"name": "m", "provider": "openai", "model_id": "x",
                   "base_url": "https://api.example.com/v1", "api_key": "k",
                   "enabled": True}]
        _write_cfg({
            "llm": {
                "default_model": "m",
                "connect_timeout": 10,
                "read_timeout": 60,
                "models": copy.deepcopy(models),
            }
        }, monkeypatch)
        monkeypatch.setattr("story_engine.core.config._config_instance", None)
        # 重新加载
        cfg = reload_config()
        models_snapshot = cfg.get("llm.models")

        from story_engine.api.routes.generate import _get_router
        router = _get_router()
        assert router is not None
        assert "m" in router.list_models()

        # 共享配置不应被注入超时
        assert "connect_timeout" not in models_snapshot[0]
        assert "read_timeout" not in models_snapshot[0]
        # 重置全局 router
        monkeypatch.setattr("story_engine.api.routes.generate._router", None)

    def test_reload_config_rebuilds_router(self, monkeypatch):
        """reload_config() 后 router 重建（清空触发下次懒加载）"""
        _write_cfg({"llm": {"models": []}}, monkeypatch)
        monkeypatch.setattr("story_engine.core.config._config_instance", None)
        monkeypatch.setattr("story_engine.api.routes.generate._router", None)
        reload_config()
        # 不抛异常即通过；router 重建钩子被触发

    def test_reload_config_without_loop_clears_router(self, monkeypatch):
        """无运行中事件循环时 reload_config 直接清空 router 引用"""
        import story_engine.api.routes.generate as gen_mod
        _write_cfg({"llm": {"models": []}}, monkeypatch)
        monkeypatch.setattr("story_engine.core.config._config_instance", None)
        monkeypatch.setattr(gen_mod, "_router", object())  # 非 None 哨兵
        reload_config()
        assert gen_mod._router is None

    def test_reload_config_in_running_loop_schedules_close(self, monkeypatch):
        """运行中事件循环内 reload_config 应调度 close_router 关闭旧 router"""
        import story_engine.api.routes.generate as gen_mod
        _write_cfg({"llm": {"models": []}}, monkeypatch)
        monkeypatch.setattr("story_engine.core.config._config_instance", None)
        fake_router = AsyncMock()
        fake_router.close_all = AsyncMock()
        monkeypatch.setattr(gen_mod, "_router", fake_router)

        async def _go():
            cfg = reload_config()
            await asyncio.sleep(0)  # 让被调度的 close_router 任务执行
            return cfg

        cfg = asyncio.run(_go())
        assert cfg.all() == {"llm": {"models": []}}
        fake_router.close_all.assert_awaited()
        assert gen_mod._router is None

    def test_reload_config_import_error_ignored(self, monkeypatch):
        """reload_config 中 import generate 失败应静默忽略，仍返回配置"""
        real_import = builtins.__import__

        def _blocked(name, *args, **kwargs):
            if name == "story_engine.api.routes.generate":
                raise ImportError("blocked")
            return real_import(name, *args, **kwargs)

        _write_cfg({"llm": {"models": []}}, monkeypatch)
        monkeypatch.setattr("story_engine.core.config._config_instance", None)
        monkeypatch.setattr(builtins, "__import__", _blocked)
        cfg = reload_config()
        assert cfg.all() == {"llm": {"models": []}}
