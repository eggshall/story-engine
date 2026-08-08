"""核心配置管理 — 加载 YAML 配置，提供全局配置对象"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# 项目根目录（自动探测 — 从 src/story_engine/core/ 向上找 pyproject.toml）
_PROJECT_ROOT: Optional[Path] = None


def _find_project_root() -> Path:
    """从当前文件位置向上查找 pyproject.toml，确定项目根目录"""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    # fallback: 环境变量或 CWD
    return Path(os.getcwd())


def project_root() -> Path:
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = _find_project_root()
    return _PROJECT_ROOT


def data_dir() -> Path:
    return project_root() / "data"


def config_dir() -> Path:
    return project_root() / "config"


# ── 配置加载 ──────────────────────────────────────────────

DEFAULT_CONFIG_PATH = config_dir() / "config.yaml"


class Config:
    """全局配置管理器，从 YAML 加载"""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or DEFAULT_CONFIG_PATH
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        else:
            self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        """点号分隔的键值访问，如 config.get('llm.deepseek.api_key')"""
        parts = key.split(".")
        value: Any = self._data
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """设置一个点号分隔的配置值"""
        parts = key.split(".")
        data = self._data
        for part in parts[:-1]:
            if part not in data or not isinstance(data[part], dict):
                data[part] = {}
            data = data[part]
        data[parts[-1]] = value

    def save(self) -> None:
        """保存回文件"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, allow_unicode=True, default_flow_style=False)

    def all(self) -> Dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return f"Config({self.path})"


# 全局单例
_config_instance: Optional[Config] = None


def get_config() -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


def reload_config() -> Config:
    global _config_instance
    _config_instance = Config()
    return _config_instance
