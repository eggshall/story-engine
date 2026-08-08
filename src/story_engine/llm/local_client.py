"""本地模型客户端 — Ollama / llama.cpp 的 OpenAI 兼容 API 接口"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator, Dict

import httpx

from story_engine.llm.base import BaseLLM, LLMRequest, LLMResponse, LLMStreamError

# 健康探测结果缓存 TTL（秒）
_HEALTH_TTL = 30


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
        self._client_read_timeout: float | None = None
        self._health: tuple[bool, str] | None = None
        self._health_at: float = 0.0
        self._lock = asyncio.Lock()

    def _close_client(self) -> None:
        if self._client is not None:
            self._client = None
        self._client_read_timeout = None

    def _get_client(self, read_timeout: float | None = None) -> httpx.AsyncClient:
        """按当前配置（或显式传入）的超时构建持久客户端，超时变化时重建。"""
        effective_timeout = read_timeout or self.read_timeout
        timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=effective_timeout,
            write=self.connect_timeout,
            pool=self.connect_timeout,
        )
        if self._client is None or self._client_read_timeout != effective_timeout:
            self._close_client()
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
            self._client_read_timeout = effective_timeout
        return self._client

    async def _check_server(self) -> tuple[bool, str]:
        """检查本地模型服务器是否在运行（结果缓存 _HEALTH_TTL 秒）"""
        now = time.monotonic()
        if self._health is not None and (now - self._health_at) < _HEALTH_TTL:
            return self._health
        # 探测用临时客户端，不复用持久 client，避免 10s 超时污染
        endpoints = ["/api/tags", "/health", "/"]
        timeout = httpx.Timeout(connect=5, read=5, write=5, pool=5)
        result: tuple[bool, str] = (False, "")
        for ep in endpoints:
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url, timeout=timeout,
                    headers={"Content-Type": "application/json"},
                ) as client:
                    resp = await client.get(ep)
                    if resp.status_code < 500:
                        result = (True, ep)
                        break
            except Exception:
                continue
        self._health = result
        self._health_at = now
        return result

    async def _warm_up(self) -> bool:
        """预热：发送一次最小请求，让模型加载到 GPU（临时客户端 + 长超时）"""
        if self._warmed:
            return True
        payload = {
            "model": self.model_id or "local",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(connect=self.connect_timeout, read=120,
                                       write=30, pool=10),
                headers={"Content-Type": "application/json"},
            ) as client:
                resp = await client.post("/v1/chat/completions", json=payload)
                resp.raise_for_status()
                self._warmed = True
                return True
        except Exception:
            return False

    async def _ensure_ready(self) -> str:
        """探测 + 预热（加锁串行化，消除 _warmed 竞态）。失败返回错误信息，成功返回空串。"""
        async with self._lock:
            alive, _ep = await self._check_server()
            if not alive:
                return f"本地模型服务器 {self.base_url} 未启动"
            if not self._warmed:
                warmed = await self._warm_up()
                if not warmed:
                    return "本地模型预热失败（首次加载超时）"
        return ""

    async def chat(self, request: LLMRequest) -> LLMResponse:
        err = await self._ensure_ready()
        if err:
            return LLMResponse(success=False, error=err, provider=self.provider)

        payload = {
            "model": self.model_id or "local",
            "messages": self.format_messages(request.system_prompt, request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stop": request.stop,
            "stream": False,
        }

        effective_timeout = request.timeout or self.read_timeout
        try:
            client = self._get_client(read_timeout=effective_timeout)
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0].get("message", {})
            content = msg.get("content") or msg.get("reasoning_content", "") or ""
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
                error=f"本地模型请求超时（{effective_timeout}s）",
                provider=self.provider,
            )
        except Exception as e:
            return LLMResponse(success=False, error=str(e), provider=self.provider)

    async def chat_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        err = await self._ensure_ready()
        if err:
            raise LLMStreamError(err)

        payload = {
            "model": self.model_id or "local",
            "messages": self.format_messages(request.system_prompt, request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }

        effective_timeout = request.timeout or self.read_timeout
        try:
            client = self._get_client(read_timeout=effective_timeout)
            async with client.stream("POST", "/v1/chat/completions", json=payload) as resp:
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
                            # 兼容带推理块的模型 (Qwen3.5 等): 思考阶段 content 为空,
                            # 内容在 reasoning 字段; content 恢复后正常输出
                            c = delta.get("content", "") or delta.get("reasoning", "")
                            if c:
                                yield c
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            raise LLMStreamError(str(e)) from e

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
