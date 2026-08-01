"""本地模型客户端 — Ollama / llama.cpp 的 OpenAI 兼容 API 接口"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict

import httpx

from story_engine.llm.base import BaseLLM, LLMRequest, LLMResponse


class LocalLLMClient(BaseLLM):
    """本地模型客户端（Ollama / llama.cpp）

    使用 OpenAI 兼容 API 格式，自动适配 Ollama 和 llama.cpp。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url", "http://127.0.0.1:8080")
        self.read_timeout = config.get("read_timeout", 300)   # 首次加载模型可能需 60s+
        self.connect_timeout = config.get("connect_timeout", 10)
        self._warmed = False
        self._client: httpx.AsyncClient | None = None

    def _get_client(self, read_timeout: int | None = None) -> httpx.AsyncClient:
        timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=read_timeout or self.read_timeout,
            write=self.connect_timeout,
            pool=self.connect_timeout,
        )
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def _check_server(self) -> tuple[bool, str]:
        """检查本地模型服务器是否在运行"""
        # Ollama 使用 /api/tags，llama.cpp 使用 /health
        endpoints = ["/api/tags", "/health", "/"]
        for ep in endpoints:
            try:
                client = self._get_client(read_timeout=10)
                resp = await client.get(ep, timeout=httpx.Timeout(connect=5, read=5, write=5, pool=5))
                if resp.status_code < 500:
                    return True, ep
            except Exception:
                continue
        return False, ""

    async def _warm_up(self) -> bool:
        """预热：发送一次最小请求，让模型加载到 GPU"""
        if self._warmed:
            return True
        payload = {
            "model": self.model_id or "local",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        try:
            client = self._get_client(read_timeout=120)  # 预热用长超时
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            self._warmed = True
            return True
        except Exception:
            return False

    async def chat(self, request: LLMRequest) -> LLMResponse:
        alive, ep = await self._check_server()
        if not alive:
            return LLMResponse(
                success=False,
                error=f"本地模型服务器 {self.base_url} 未启动",
                provider=self.provider,
            )

        # 首次请求自动预热
        if not self._warmed:
            warmed = await self._warm_up()
            if not warmed:
                return LLMResponse(
                    success=False,
                    error="本地模型预热失败（首次加载超时）",
                    provider=self.provider,
                )

        payload = {
            "model": self.model_id or "local",
            "messages": self.format_messages(request.system_prompt, request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stop": request.stop,
            "stream": False,
        }

        try:
            client = self._get_client()
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage")
            return LLMResponse(
                content=content,
                model=f"local:{data.get('model', 'unknown')}",
                provider=self.provider,
                usage=usage,
            )
        except httpx.TimeoutException:
            return LLMResponse(
                success=False,
                error=f"本地模型请求超时（{self.read_timeout}s）",
                provider=self.provider,
            )
        except Exception as e:
            return LLMResponse(success=False, error=str(e), provider=self.provider)

    async def chat_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        alive, ep = await self._check_server()
        if not alive:
            yield f"\n[Error: 本地模型服务器 {self.base_url} 未启动]"
            return

        if not self._warmed:
            warmed = await self._warm_up()
            if not warmed:
                yield "\n[Error: 本地模型预热失败]"
                return

        payload = {
            "model": self.model_id or "local",
            "messages": self.format_messages(request.system_prompt, request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }

        try:
            client = self._get_client()
            async with client.stream("POST", "/v1/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                import json
                async for line in resp.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            c = delta.get("content", "")
                            if c:
                                yield c
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield f"\n[Error: {e}]"

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
