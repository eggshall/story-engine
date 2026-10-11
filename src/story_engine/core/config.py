"""核心配置管理 — 加载 YAML 配置，提供全局配置对象"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

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

# 配置路径覆盖开关（N2）：`STORY_CONFIG_PATH=<path>` 时优先使用该文件。
# 用途：浏览器 E2E / 多环境部署（如把模型指向本地假上游跑真 UI 链路），
# 避免为了测试去改项目的 config/config.yaml。
CONFIG_PATH_ENV = "STORY_CONFIG_PATH"

DEFAULT_CONFIG_PATH = (
    Path(os.environ[CONFIG_PATH_ENV])
    if os.environ.get(CONFIG_PATH_ENV)
    else config_dir() / "config.yaml"
)

# P2-6（N2 评审）：显式覆盖却指到不存在的文件时，`Config._load` 会静默回退成空配置
# （security.api_key 变空 → 鉴权中间件退化为"仅回环"，服务表现为不可用）。
# 这是"显式设置却无效"的典型静默故障，导入时就告警，别等运行时才发现。
if os.environ.get(CONFIG_PATH_ENV) and not DEFAULT_CONFIG_PATH.exists():
    logger.warning(
        "%s 指向的配置文件不存在: %s（将回退为空配置，鉴权/模型设置都会失效）",
        CONFIG_PATH_ENV,
        DEFAULT_CONFIG_PATH,
    )


class _LLMModelConfig(BaseModel):
    """llm.models 单条模型配置（N3：白名单 = 真实使用的字段全集）。

    两条硬规则：
    - **已知字段一个都不许丢**（此前 `weight` / `read_timeout` / `connect_timeout` 被静默剥离，
      其中本地模型的 `read_timeout: 300` 被丢后一律退回全局 120s，长文生成会被无提示掐断）；
    - **未知字段保留并告警**（`extra="allow"` + `_validate_models` 里的告警），
      键名拼错时必须能看见，而不是悄悄少一个配置项。
    """

    # 未知字段保留（N3 C2）；不设 allow 会把未来的新字段全部静默吃掉
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    provider: str = ""
    model_id: str = ""
    base_url: str = ""
    api_key: str = ""
    enabled: bool = True
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1)
    # ── 既有但此前被剥离的字段 ──
    # weight: 放行它是为了"配置不丢字段"（评审 P2-3 指出当前 `router.py::_pick_target`
    # 并不读它，只按 名字/默认/首个 选目标）—— 预留语义：模型权重，供后续离线调度/优先级使用。
    weight: float = Field(default=1, ge=0)
    connect_timeout: Optional[float] = Field(default=None, gt=0)
    read_timeout: Optional[float] = Field(default=None, gt=0)
    timeout: Optional[float] = Field(default=None, gt=0)  # 旧字段，api_client 仍兼容读取
    # ── N3 新增：config 驱动的调用契约入口 ──
    # task: 模型级默认任务；请求未显式指定时生效（见 llm/api_client.py 的优先级说明）
    task: Optional[str] = None
    # thinking: 显式覆盖（如 {"type": "disabled"}），优先于按 task 推导的默认
    thinking: Optional[Dict[str, Any]] = None

    @field_validator("task", mode="before")
    @classmethod
    def _validate_task(cls, v: Any) -> Optional[str]:
        """task 任何非法形态 → 降级为"未设置"并告警。

        评审 P1-2：之前用「类型约束 + after 校验」，非字符串（`5`/`True`/`["plan"]`）
        会在类型校验阶段就失败 → **整条模型配置被过滤**，与"不连坐整条配置"的承诺相反。
        这里改用 before 校验，先把任意类型收敛成"合法字符串 or None"。
        也不静默当成 generate —— 那正是 N1 要消灭的"静默退回思考模式"。
        """
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            logger.warning("llm.models 的 task=%r 不是字符串，该字段会被忽略（模型条目保留）", v)
            return None
        from story_engine.llm.base import VALID_TASKS

        if v not in VALID_TASKS:
            logger.warning(
                "llm.models 的 task=%r 非法（允许值: %s），该字段会被忽略", v, sorted(VALID_TASKS)
            )
            return None
        return v

    @field_validator("thinking", mode="before")
    @classmethod
    def _validate_thinking(cls, v: Any) -> Optional[Dict[str, Any]]:
        """thinking 必须是 `{"type": "enabled"|"disabled"}`；否则丢弃并告警。

        评审 P2-1：之前是 `Optional[Dict[str, Any]]`，`{"type": "xxx"}` 会一路原样发给
        上游（可能 400）。宁可不发、让下游按 task 推导，也不发未知字段。
        """
        if v is None:
            return None
        if not isinstance(v, dict):
            logger.warning(
                "llm.models 的 thinking=%r 不是对象（形如 {\"type\": \"disabled\"}），该字段会被忽略", v
            )
            return None
        t = v.get("type")
        if t not in ("enabled", "disabled"):
            logger.warning(
                "llm.models 的 thinking.type=%r 非法（只能 enabled/disabled），该字段会被忽略", t
            )
            return None
        return {"type": t}


def _validate_models(models: Any) -> List[Dict[str, Any]]:
    """Pydantic 校验 llm.models 列表；非法条目过滤并告警，返回合法条目。

    `exclude_none=True`：未设置的可选字段（timeouts/task/thinking）不会以 None 出现，
    保持"没写就是不写"的语义（api_client 用"缺省→回退全局值"判断）。
    注意（评审 P2-4）：显式写 `read_timeout: null` 与"不写"等价 —— 之后会被
    `generate.py::_build_router_locked` 注入全局值；想覆盖全局请写具体数值。
    """
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
        extra = sorted(parsed.model_extra or {})
        if extra:
            # C2：不静默剥离，但要让写错的键名现形
            logger.warning(
                "llm.models[%s] 含未知字段 %s：已原样保留，请核对键名拼写", parsed.name, extra
            )
        dumped = parsed.model_dump(exclude_none=True)
        _warn_task_fields_on_unsupported_provider(dumped)
        valid.append(dumped)
    return valid


def _warn_task_fields_on_unsupported_provider(model: Dict[str, Any]) -> None:
    """评审 P2-2：`task`/`thinking` 只有 OpenAI 兼容客户端会消费。

    本地（Ollama）与 Anthropic 客户端都不读这两个字段 —— 若不告警，作者会以为
    "配置生效了"，实际是静默空操作（真实配置的 default_model 恰是本地 qwen）。
    """
    if not (model.get("task") or model.get("thinking")):
        return
    from story_engine.llm.api_client import _THINKING_CAPABLE_PROVIDERS

    provider = model.get("provider", "")
    if provider not in _THINKING_CAPABLE_PROVIDERS:
        logger.warning(
            "llm.models[%s] 配了 task/thinking，但 provider=%r 的客户端不支持这两个字段"
            "（只有 %s 生效）→ 该配置不会生效，请改用支持思考控制的模型或忽略此项",
            model.get("name"),
            provider,
            sorted(_THINKING_CAPABLE_PROVIDERS),
        )


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
        """保存回文件。

        评审 P2-5：未知/拼错的字段（`model_extra`）会被一并写回 config.yaml。
        保留写回是刻意的（作者能看见自己写了什么），但这里再告警一次，
        避免"一次 typo 被持久化且无人知晓"。
        """
        models = self.get("llm.models") or []
        known = set(_LLMModelConfig.model_fields)
        for m in models:
            extra = sorted(set(m) - known)
            if extra:
                logger.warning("保存配置：llm.models[%s] 仍含未知字段 %s（将原样写入文件）", m.get("name"), extra)
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
