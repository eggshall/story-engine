"""LLM 模型抽象接口 — 所有模型提供者需实现此接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional


@dataclass
class LLMRequest:
    """统一请求格式"""
    messages: List[Dict[str, str]] = field(default_factory=list)
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    stop: Optional[List[str]] = None
    stream: bool = False
    timeout: Optional[float] = None  # 请求级超时覆盖（秒），None 时用客户端配置


@dataclass
class LLMResponse:
    """统一响应格式"""
    content: str = ""
    model: str = ""
    provider: str = ""
    usage: Optional[Dict[str, int]] = None
    success: bool = True
    error: str = ""


class LLMStreamError(Exception):
    """流式生成过程中的模型级错误。

    由客户端在无法继续流式输出时抛出，供 router 做模型级 fallback 或
    由 SSE 层包装为结构化 error 事件（不再混入正文）。
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


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
        ...
        if False:  # pragma: no cover
            yield ""

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
