"""统一测试 fixture — P2-E2.2：收敛各测试文件重复的 tempfile config + monkeypatch 复制。

提供：
- ``make_config``：工厂 fixture，把配置写入临时 YAML 并让全局 Config 指向它
- ``test_config``：统一最小配置（默认单模型），覆盖多数 API 测试
- ``reset_router``：重设 API 路由中的全局 router，避免跨测试复用
- ``novels_root``：隔离的小说存储目录（同时覆盖 storage 与 export 模块）
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict

import pytest
import yaml

# 最小测试配置：单个本地模型，满足 API 路由/生成器对模型的依赖
DEFAULT_TEST_MODELS: list[dict] = [
    {
        "name": "test-model",
        "provider": "openai",
        "model_id": "test",
        "base_url": "http://localhost:8080",
        "api_key": "test",
        "enabled": True,
    }
]

DEFAULT_TEST_CONFIG: Dict = {
    "llm": {
        "default_model": "test-model",
        "models": DEFAULT_TEST_MODELS,
    }
}


@pytest.fixture
def make_config(monkeypatch, tmp_path) -> Callable[[Dict], Path]:
    """工厂 fixture：把配置写入临时 YAML 并让全局 Config 指向它。

    返回 callable：``make_config(data: dict) -> Path``。
    """

    def _make(data: Dict) -> Path:
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        import story_engine.core.config as cfg_mod

        monkeypatch.setattr(cfg_mod, "_config_instance", None)
        monkeypatch.setattr(cfg_mod, "DEFAULT_CONFIG_PATH", cfg_path)
        return cfg_path

    return _make


@pytest.fixture
def test_config(make_config) -> Path:
    """统一最小配置：默认单个模型。"""
    return make_config(DEFAULT_TEST_CONFIG)


@pytest.fixture
def reset_router(monkeypatch):
    """重设 API 路由中的全局 router，避免跨测试复用/污染。"""
    import story_engine.api.routes.generate as gen_mod

    monkeypatch.setattr(gen_mod, "_router", None)


@pytest.fixture
def novels_root(monkeypatch, tmp_path) -> Path:
    """隔离的小说存储目录，同时覆盖 storage 与 export 模块。"""
    import story_engine.api.routes.export as export_mod
    import story_engine.tools.novel_storage as ns

    root = tmp_path / "novels"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ns, "NOVELS_ROOT", root)
    monkeypatch.setattr(export_mod, "NOVELS_ROOT", root)
    return root
