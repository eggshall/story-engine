"""LLM 模型抽象接口 — 所有模型提供者需实现此接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

# 任务类型白名单（N1 调用契约；见 llm/api_client.py）
TASK_GENERATE = "generate"
TASK_EXTRACT = "extract"
TASK_PLAN = "plan"
VALID_TASKS = frozenset({TASK_GENERATE, TASK_EXTRACT, TASK_PLAN})


@dataclass
class LLMRequest:
    """统一请求格式"""
    messages: List[Dict[str, str]] = field(default_factory=list)
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    stop: Optional[List[str]] = None
    timeout: Optional[float] = None  # 请求级超时覆盖（秒），None 时用客户端配置
    # 任务类型 —— 决定思考模式与温度语义（见 llm/api_client.py 的调用契约）:
    #   generate 创作 / extract 结构化抽取 → 关闭思考 + 显式 temperature
    #   plan 规划推理 → 开启思考（此时 temperature 无意义，不发送）
    #   空串 "" = **未指定**：由模型配置的 task 决定，最后才回退 "generate"（N3 优先级）
    task: str = ""

    def __post_init__(self) -> None:
        # 白名单校验：拼错/未知的 task 必须立刻炸，否则会静默退回"开思考 + 丢温度"
        # —— 那正是 N1 要消灭的行为（评审 P1-2）。
        # 空串是合法状态（"未指定"，交给模型配置/默认值解析），不在此列。
        if self.task and self.task not in VALID_TASKS:
            raise ValueError(
                f"未知 task={self.task!r}，允许值: {sorted(VALID_TASKS)}"
                "（不接受静默退回思考模式）"
            )


@dataclass
class LLMResponse:
    """统一响应格式"""
    content: str = ""
    model: str = ""
    provider: str = ""
    usage: Optional[Dict[str, int]] = None
    success: bool = True
    error: str = ""
    # 空产出标记：模型"成功返回"但无正文（N1）。router 据此决定"重试 1 次"，
    # 而不是靠匹配错误文案（评审 P1-4 需要机器可读的信号）。
    empty_output: bool = False


class LLMStreamError(Exception):
    """流式生成过程中的模型级错误。

    由客户端在无法继续流式输出时抛出，供 router 做模型级 fallback 或
    由 SSE 层包装为结构化 error 事件（不再混入正文）。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMEmptyOutputError(LLMStreamError):
    """空产出：模型"正常返回"但没有任何正文内容/token。

    单独成类，让 router 能区分空产出与其他错误 ——
    空产出可以**重试 1 次**（多为思考模式耗尽 max_tokens 的瞬时问题），
    网络/上游错误则直接 fallback（见 docs/design/P7-MVP-PLAN.md §1.2）。
    """


class BaseLLM(ABC):
    """所有模型提供者的基类"""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.name: str = config.get("name", "unknown")
        self.model_id: str = config.get("model_id", "")
        self.provider: str = config.get("provider", "")

    @abstractmethod
    async def chat(self, request: LLMRequest) -> LLMResponse:
        """发送聊天请求，返回响应"""
        ...

    @abstractmethod
    async def chat_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """流式聊天，yield 文本块"""
        # 抽象异步生成器：body 需含 yield 才被 mypy 识别为异步生成器（子类必须实现）
        yield ""  # pragma: no cover

    @abstractmethod
    async def close(self) -> None:
        """释放底层资源（连接池等），所有子类必须实现。

        每次构建持久 httpx client 时，close() 负责 aclose 底层连接池，
        防止连接池泄漏（见 L3）。
        """
        ...

    def format_messages(self, system_prompt: str, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """将 system_prompt + 消息列表拼接为标准 messages 格式"""
        result: List[Dict[str, str]] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        result.extend(messages)
        return result

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, model={self.model_id})"
