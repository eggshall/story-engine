"""LLM 模型抽象接口 — 所有模型提供者需实现此接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMRequest:
    """统一请求格式"""
    messages: List[Dict[str, str]] = field(default_factory=list)
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    stop: Optional[List[str]] = None
    stream: bool = False


@dataclass
class LLMResponse:
    """统一响应格式"""
    content: str = ""
    model: str = ""
    provider: str = ""
    usage: Optional[Dict[str, int]] = None
    success: bool = True
    error: str = ""


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
    async def chat_stream(self, request: LLMRequest):
        """流式聊天，yield 文本块"""
        ...
        yield  # pragma: no cover

    def format_messages(self, system_prompt: str, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """将 system_prompt + 消息列表拼接为标准 messages 格式"""
        result: List[Dict[str, str]] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        result.extend(messages)
        return result

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, model={self.model_id})"
