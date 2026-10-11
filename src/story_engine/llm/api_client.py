"""远程 API 客户端 — DeepSeek / Anthropic Claude / OpenAI 兼容接口"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from story_engine.llm.base import (
    BaseLLM,
    LLMEmptyOutputError,
    LLMRequest,
    LLMResponse,
    LLMStreamError,
)

# 任务类型 → 思考模式策略（N1 调用契约）
# 实测（2026-10）：DeepSeek 思考模式默认开启（effort=high），reasoning_tokens 会吃掉 max_tokens
# （max_tokens=8000 时 content 仍为空字符串，HTTP 却是 200），且思考模式下 temperature 被静默忽略。
# 因此创作/抽取类任务显式关闭思考，规划类任务保留思考。
_NO_THINKING_TASKS = {"generate", "extract"}

# 只有这些 provider 的接口接受 DeepSeek 风格的 `thinking` 字段（评审 P2-1）。
# 其他 OpenAI 兼容服务（DashScope 用 enable_thinking、部分第三方直接拒未知字段）**不发**该字段，
# 否则可能是 400 —— 乱发比不发更危险。temperature 语义与 provider 无关，照常发。
_THINKING_CAPABLE_PROVIDERS = {"deepseek"}


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

    def _build_payload(self, request: LLMRequest, stream: bool = False) -> Dict[str, Any]:
        """按任务类型构建请求体（N1 调用契约）。

        - generate/extract：关闭思考 + 发送 temperature（思考模式下 temperature 无效）
        - plan：开启思考，且**不**发送 temperature（发了也不生效，避免误导）
        - `thinking` 仅发给支持该字段的 provider（见 _THINKING_CAPABLE_PROVIDERS）
        - 一律不发送 reasoning_effort（与 disabled 共存会被 API 拒绝）
        """
        payload: Dict[str, Any] = {
            "model": self.model_id,
            "messages": self.format_messages(request.system_prompt, request.messages),
            "max_tokens": request.max_tokens,
        }
        thinking_capable = self.provider in _THINKING_CAPABLE_PROVIDERS
        if request.task in _NO_THINKING_TASKS:
            if thinking_capable:
                payload["thinking"] = {"type": "disabled"}
            payload["temperature"] = request.temperature
        elif thinking_capable:
            payload["thinking"] = {"type": "enabled"}
        if request.stop:
            payload["stop"] = request.stop
        if stream:
            payload["stream"] = True
        return payload

    async def chat(self, request: LLMRequest) -> LLMResponse:
        client = self._get_client()
        payload = self._build_payload(request)

        try:
            resp = await client.post("/chat/completions", json=payload, timeout=self._timeout(request))
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0].get("message", {})
            usage = data.get("usage")
            model = data.get("model", self.model_id)
            content = (msg.get("content") or "").strip()
            if not content:
                # 不再回退 reasoning_content：推理过程不是交付内容。
                # 实测该情形=思考模式耗尽 max_tokens，必须显式失败而不是静默返回空。
                reasoning = (msg.get("reasoning_content") or "").strip()
                hint = (
                    "；reasoning_tokens 占满了 max_tokens（思考模式），请提高 max_tokens 或使用 task='generate'"
                    if reasoning
                    else ""
                )
                return LLMResponse(
                    success=False,
                    provider=self.provider,
                    model=model,
                    usage=usage,
                    empty_output=True,
                    error=f"模型返回空产出（content 为空）{hint}",
                )
            return LLMResponse(
                content=content,
                model=model,
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
        payload = self._build_payload(request, stream=True)
        yielded_chars = 0
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
                                # 只算非空白字符：纯空白 token 不算正文（评审 P2-3）
                                yielded_chars += len(content.strip())
                                yield content
                        except json.JSONDecodeError:
                            continue
        except LLMStreamError:
            raise
        except Exception as e:
            raise LLMStreamError(str(e)) from e

        if yielded_chars == 0:
            # 流式零 token：思考模式耗尽预算或上游异常，必须显式失败
            # （否则 router 会把空流当成功，SSE 层还会发 done，前端拿到空正文）
            raise LLMEmptyOutputError(
                "模型返回空产出（流式零 token）：reasoning_tokens 可能占满了 max_tokens，"
                "请提高 max_tokens 或使用 task='generate' 关闭思考"
            )

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
