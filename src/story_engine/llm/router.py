"""模型路由器 — 远程/本地自动切换 + 负载分配"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from story_engine.llm.base import BaseLLM, LLMRequest, LLMResponse
from story_engine.llm.api_client import AnthropicClient, OpenAIClient
from story_engine.llm.local_client import LocalLLMClient


class ModelRouter:
    """模型路由器 — 根据配置自动创建并调度模型"""

    def __init__(self, models_config: List[Dict[str, Any]]) -> None:
        self._clients: Dict[str, BaseLLM] = {}
        self._init_clients(models_config)

    def _init_clients(self, models_config: List[Dict[str, Any]]) -> None:
        for cfg in models_config:
            if not cfg.get("enabled", True):
                continue
            client = self._create_client(cfg)
            if client:
                self._clients[cfg["name"]] = client

    def _create_client(self, cfg: Dict[str, Any]) -> Optional[BaseLLM]:
        provider = cfg.get("provider", "")
        if provider == "deepseek":
            return OpenAIClient(cfg)
        elif provider == "openai":
            return OpenAIClient(cfg)
        elif provider == "anthropic":
            return AnthropicClient(cfg)
        elif provider == "local":
            return LocalLLMClient(cfg)
        return None

    def get_client(self, name: str) -> Optional[BaseLLM]:
        return self._clients.get(name)

    def list_models(self) -> List[str]:
        return list(self._clients.keys())

    async def chat(
        self,
        request: LLMRequest,
        model_name: Optional[str] = None,
        fallback: bool = True,
    ) -> LLMResponse:
        """发送请求到指定模型，失败时可 fallback 到下一个可用模型"""
        if model_name and model_name in self._clients:
            client = self._clients[model_name]
            result = await client.chat(request)
            if result.success or not fallback:
                return result

        # Fallback: 遍历所有模型
        for name, client in self._clients.items():
            if name == model_name:
                continue  # 已经试过了
            result = await client.chat(request)
            if result.success:
                result.content = f"[Fallback → {name}]\n" + result.content
                return result

        return LLMResponse(success=False, error="所有模型均不可用")

    async def chat_stream(
        self,
        request: LLMRequest,
        model_name: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        if model_name and model_name in self._clients:
            async for chunk in self._clients[model_name].chat_stream(request):
                yield chunk
        else:
            yield "[Error: 未找到可用模型]"

    async def close_all(self) -> None:
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
