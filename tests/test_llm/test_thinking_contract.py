"""N1 节点测试：远程模型调用契约（思考模式 / 温度 / 空产出）

背景（实测，2026-10）：
- DeepSeek 思考模式**默认开启**（effort=high），`reasoning_tokens` 会吃掉 `max_tokens`：
  实测 `deepseek-v4-pro` 在 max_tokens=8000 时 reasoning 全占、`content` 为空字符串，
  而 HTTP 仍是 200 → 前端收到"静默空正文"。
- 思考模式下 `temperature` 会被**静默忽略**（官方文档：设置不报错也不生效）。
- 本地 Ollama Qwen 的 reasoning 回退语义保留在 local_client，不属于本契约范围。

契约（本节点定义）：
- `task in {"generate", "extract"}` → 关闭思考（`thinking: {"type": "disabled"}`）+ 发送 temperature
- `task == "plan"` → 开启思考（`thinking: {"type": "enabled"}`）+ 不发送 temperature（无意义）
- 不发送 `reasoning_effort`（与 disabled 冲突会被 API 拒绝）
- 非流式 content 为空 → `success=False`（不再回退 reasoning_content）
- 流式零 token → 抛 `LLMStreamError`，由 SSE 层转 `event: error`
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from story_engine.llm.api_client import OpenAIClient
from story_engine.llm.base import LLMRequest, LLMStreamError
from story_engine.llm.router import ModelRouter


@pytest.fixture
def client() -> OpenAIClient:
    return OpenAIClient({
        "name": "deepseek",
        "provider": "deepseek",
        "model_id": "deepseek-flash",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-test",
        "read_timeout": 60,
        "connect_timeout": 10,
    })


def _mock_chat(client: OpenAIClient, message: dict) -> MagicMock:
    http = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.json.return_value = {"choices": [{"message": message}], "model": "m"}
    http.post = AsyncMock(return_value=resp)
    client._client = http
    return http


def _mock_stream(client: OpenAIClient, lines: list[str]) -> MagicMock:
    http = MagicMock()

    async def _aiter_lines():
        for line in lines:
            yield line

    resp = MagicMock()
    resp.raise_for_status = lambda: None
    resp.aiter_lines.return_value = _aiter_lines()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    http.stream = MagicMock(return_value=ctx)
    client._client = http
    return http


def _delta(content: str = "", reasoning: str = "") -> str:
    d: dict = {}
    if content:
        d["content"] = content
    if reasoning:
        d["reasoning_content"] = reasoning
    return "data: " + json.dumps({"choices": [{"delta": d}]})


class TestThinkingContract:
    def test_generate_disables_thinking_and_keeps_temperature(self, client):
        http = _mock_chat(client, {"content": "正文"})

        req = LLMRequest(messages=[{"role": "user", "content": "写"}], temperature=0.8)
        assert req.task == "generate"
        result = asyncio.run(client.chat(req))

        payload = http.post.call_args.kwargs["json"]
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["temperature"] == 0.8
        assert "reasoning_effort" not in payload
        assert result.success is True

    def test_extract_disables_thinking(self, client):
        http = _mock_chat(client, {"content": "{}"})

        asyncio.run(client.chat(LLMRequest(messages=[], task="extract")))

        assert http.post.call_args.kwargs["json"]["thinking"] == {"type": "disabled"}

    def test_plan_enables_thinking_without_temperature(self, client):
        http = _mock_chat(client, {"content": "计划"})

        asyncio.run(client.chat(LLMRequest(messages=[], task="plan", temperature=0.7)))

        payload = http.post.call_args.kwargs["json"]
        assert payload["thinking"] == {"type": "enabled"}
        assert "temperature" not in payload  # 思考模式下无意义，明确不发

    def test_stream_payload_follows_same_contract(self, client):
        http = _mock_stream(client, [_delta(content="块"), "data: [DONE]"])

        async def _collect():
            out = []
            async for token in client.chat_stream(LLMRequest(messages=[], task="generate")):
                out.append(token)
            return out

        assert asyncio.run(_collect()) == ["块"]
        payload = http.stream.call_args.kwargs["json"]
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["stream"] is True


class TestEmptyOutputIsFailure:
    def test_chat_reasoning_only_is_failure(self, client):
        """实测场景：content 为空、reasoning 占满 → 必须判定为失败，不能当成功"""
        _mock_chat(client, {"content": "", "reasoning_content": "思考过程…"})

        result = asyncio.run(client.chat(LLMRequest(messages=[])))

        assert result.success is False
        assert "空产出" in result.error

    def test_chat_content_none_is_failure(self, client):
        _mock_chat(client, {"content": None, "reasoning_content": "推理"})

        result = asyncio.run(client.chat(LLMRequest(messages=[])))

        assert result.success is False
        assert "空产出" in result.error

    def test_chat_stream_zero_content_tokens_raises(self, client):
        """流式只回 reasoning、零 content → 抛 LLMStreamError（供 SSE 转 error 事件）"""
        _mock_stream(client, [_delta(reasoning="思考1"), _delta(reasoning="思考2"), "data: [DONE]"])

        async def _collect():
            async for _ in client.chat_stream(LLMRequest(messages=[])):
                pass

        with pytest.raises(LLMStreamError) as exc:
            asyncio.run(_collect())
        assert "空产出" in exc.value.message

    def test_chat_stream_with_content_does_not_raise(self, client):
        _mock_stream(client, [_delta(content="正"), _delta(content="文"), "data: [DONE]"])

        async def _collect():
            out = []
            async for token in client.chat_stream(LLMRequest(messages=[])):
                out.append(token)
            return out

        assert asyncio.run(_collect()) == ["正", "文"]


class TestRouterPropagatesEmptyStream:
    def test_single_client_empty_stream_raises(self, client):
        _mock_stream(client, [_delta(reasoning="只思考"), "data: [DONE]"])
        router = ModelRouter([{**client.config, "name": "deepseek"}])
        router._clients["deepseek"] = client

        async def _drain():
            async for _ in router.chat_stream(LLMRequest(messages=[]), model_name="deepseek"):
                pass

        with pytest.raises(LLMStreamError) as exc:
            asyncio.run(_drain())
        assert "空产出" in exc.value.message

    def test_fallback_to_healthy_client_still_works(self, client):
        """空产出应触发 fallback（LLMStreamError 被 router 捕获后尝试下一个模型）"""
        _mock_stream(client, [_delta(reasoning="只思考"), "data: [DONE]"])
        healthy = OpenAIClient({**client.config, "name": "backup"})
        _mock_stream(healthy, [_delta(content="备"), "data: [DONE]"])

        router = ModelRouter([{**client.config, "name": "deepseek"}, {**client.config, "name": "backup"}])
        router._clients["deepseek"] = client
        router._clients["backup"] = healthy

        async def _collect():
            out = []
            async for token in router.chat_stream(LLMRequest(messages=[]), model_name="deepseek"):
                out.append(token)
            return out

        text = "".join(asyncio.run(_collect()))
        assert "备" in text
        assert "Fallback" in text
