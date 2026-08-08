"""远程 API 客户端 — DeepSeek / Anthropic Claude / OpenAI 兼容接口"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from story_engine.llm.base import BaseLLM, LLMRequest, LLMResponse, LLMStreamError


class OpenAIClient(BaseLLM):
    """兼容 OpenAI API 格式的远程客户端（DeepSeek / Qwen / Kimi 等）"""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url", "https://api.deepseek.com/v1")
        # API Key: 优先配置项，其次环境变量（DEEPSEEK_API_KEY / OPENAI_API_KEY）
        self.api_key = config.get("api_key", "") or os.environ.get(
            f"{config.get('provider', '').upper()}_API_KEY", ""
        )
        # 统一读取 read_timeout / connect_timeout（兼容旧 timeout 字段）
        self.read_timeout = config.get("read_timeout") or config.get("timeout", 60)
        self.connect_timeout = config.get("connect_timeout", 10)
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: Dict[str, str] = {
                "Content-Type": "application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    connect=self.connect_timeout,
                    read=self.read_timeout,
                    write=self.connect_timeout,
                    pool=self.connect_timeout,
                ),
                headers=headers,
            )
        return self._client

    def _timeout(self, request: LLMRequest) -> httpx.Timeout:
        """按请求级覆盖（或配置默认值）构建超时。"""
        read = request.timeout or self.read_timeout
        return httpx.Timeout(
            connect=self.connect_timeout,
            read=read,
            write=self.connect_timeout,
            pool=self.connect_timeout,
        )

    async def chat(self, request: LLMRequest) -> LLMResponse:
        client = self._get_client()
        payload = {
            "model": self.model_id,
            "messages": self.format_messages(request.system_prompt, request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.stop:
            payload["stop"] = request.stop

        try:
            resp = await client.post("/chat/completions", json=payload, timeout=self._timeout(request))
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0].get("message", {})
            # 推理模型 content 可能为空/缺失，回退 reasoning_content
            content = msg.get("content") or msg.get("reasoning_content", "") or ""
            usage = data.get("usage")
            return LLMResponse(
                content=content,
                model=data.get("model", self.model_id),
                provider=self.provider,
                usage=usage,
            )
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500]
            return LLMResponse(
                success=False,
                error=f"HTTP {e.response.status_code}: {body}",
                provider=self.provider,
            )
        except Exception as e:
            return LLMResponse(success=False, error=str(e), provider=self.provider)

    async def chat_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        client = self._get_client()
        payload = {
            "model": self.model_id,
            "messages": self.format_messages(request.system_prompt, request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        try:
            async with client.stream("POST", "/chat/completions", json=payload,
                                     timeout=self._timeout(request)) as resp:
                resp.raise_for_status()
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
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            raise LLMStreamError(str(e)) from e

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


class AnthropicClient(BaseLLM):
    """Anthropic Claude API 客户端"""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url", "https://api.anthropic.com/v1")
        self.api_key = config.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
        # 统一读取 read_timeout / connect_timeout（兼容旧 timeout 字段）
        self.read_timeout = config.get("read_timeout") or config.get("timeout", 120)
        self.connect_timeout = config.get("connect_timeout", 10)
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: Dict[str, str] = {
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            if self.api_key:
                headers["x-api-key"] = self.api_key
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    connect=self.connect_timeout,
                    read=self.read_timeout,
                    write=self.connect_timeout,
                    pool=self.connect_timeout,
                ),
                headers=headers,
            )
        return self._client

    def _timeout(self, request: LLMRequest) -> httpx.Timeout:
        """按请求级覆盖（或配置默认值）构建超时。"""
        read = request.timeout or self.read_timeout
        return httpx.Timeout(
            connect=self.connect_timeout,
            read=read,
            write=self.connect_timeout,
            pool=self.connect_timeout,
        )

    async def chat(self, request: LLMRequest) -> LLMResponse:
        client = self._get_client()
        messages = request.messages
        system = request.system_prompt

        payload: Dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system:
            payload["system"] = system

        try:
            resp = await client.post("/messages", json=payload, timeout=self._timeout(request))
            resp.raise_for_status()
            data = resp.json()
            content = "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
            usage = data.get("usage")
            return LLMResponse(
                content=content,
                model=data.get("model", self.model_id),
                provider=self.provider,
                usage=usage,
            )
        except Exception as e:
            return LLMResponse(success=False, error=str(e), provider=self.provider)

    async def chat_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        client = self._get_client()
        messages = request.messages
        system = request.system_prompt
        payload: Dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }
        if system:
            payload["system"] = system

        try:
            async with client.stream("POST", "/messages", json=payload,
                                     timeout=self._timeout(request)) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        if chunk.get("type") == "content_block_delta":
                            delta = chunk.get("delta", {})
                            text = delta.get("text", "")
                            if text:
                                yield text
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            raise LLMStreamError(str(e)) from e

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
