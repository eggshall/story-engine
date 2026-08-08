"""核心配置管理 — 加载 YAML 配置，提供全局配置对象"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("story_engine.config")

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


class _LLMModelConfig(BaseModel):
    """llm.models 单条模型配置的最小校验（L6.1）"""

    name: str = Field(min_length=1)
    provider: str = ""
    model_id: str = ""
    base_url: str = ""
    api_key: str = ""
    enabled: bool = True
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1)


def _validate_models(models: Any) -> List[Dict[str, Any]]:
    """Pydantic 校验 llm.models 列表；非法条目过滤并告警，返回合法条目。"""
    if models is None:
        return []
    if not isinstance(models, list):
        logger.warning("config llm.models 不是列表，已忽略")
        return []
    valid: List[Dict[str, Any]] = []
    for item in models:
        try:
            parsed = _LLMModelConfig.model_validate(item)
        except (ValidationError, TypeError) as e:
            logger.warning("llm.models 条目非法已跳过: %s", e)
            continue
        valid.append(parsed.model_dump())
    return valid


class Config:
    """全局配置管理器，从 YAML 加载"""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or DEFAULT_CONFIG_PATH
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            logger.error("配置文件 %s 解析失败: %s（回退为空配置）", self.path, e)
            self._data = {}
        except OSError as e:
            logger.error("配置文件 %s 读取失败: %s（回退为空配置）", self.path, e)
            self._data = {}
        # 空配置回退 + llm.models 校验（L6.1）
        if not isinstance(self._data, dict):
            logger.warning("配置内容非对象，回退为空配置")
            self._data = {}
        models = self._data.get("llm", {}).get("models")
        if models is not None:
            self._data.setdefault("llm", {})["models"] = _validate_models(models)

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
    """重载配置；若全局 router 已存在，触发其重建（清空以便下次懒加载）。"""
    global _config_instance
    _config_instance = Config()
    try:
        import story_engine.api.routes.generate as gen_mod
        if gen_mod._router is not None:
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                loop.create_task(gen_mod.close_router())
            except RuntimeError:
                # 无运行中事件循环：直接清空，连接池由进程退出回收
                gen_mod._router = None
    except ImportError:
        pass
    return _config_instance
