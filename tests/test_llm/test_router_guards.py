"""N1 评审修复的回归测试（P1-2 / P1-3 / P1-4 / P2-1 / P2-3）

- P1-2 未知/拼错 task 必须立刻抛错，不能静默退回"开思考 + 丢温度"
- P1-3 空产出守卫下沉到 router（本地客户端没有自己的守卫，而它是默认模型）
- P1-4 空产出在同一模型上重试 1 次，再次空产出才 fallback（PLAN §1.2）
- P2-1 只有支持 `thinking` 字段的 provider 才发该字段
- P2-3 纯空白 token 不算正文
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from story_engine.llm.api_client import OpenAIClient
from story_engine.llm.base import (
    LLMEmptyOutputError,
    LLMRequest,
    LLMResponse,
    LLMStreamError,
)
from story_engine.llm.router import ModelRouter

# ── 工具 ────────────────────────────────────────────────


def make_router(clients: dict) -> ModelRouter:
    router = ModelRouter([])
    router._clients = clients
    return router


def stream_client(chunks_by_call):
    """每调用一次 chat_stream 就产出一组 token；chunks_by_call 是 list[list[str]]"""
    client = MagicMock()
    state = {"n": 0}

    def _factory(request, model_name=None):
        idx = state["n"]
        state["n"] += 1
        chunks = chunks_by_call[idx] if idx < len(chunks_by_call) else []

        async def _gen():
            for c in chunks:
                yield c

        return _gen()

    client.chat_stream = _factory
    client.state = state
    return client


async def drain(router, **kwargs) -> str:
    out = []
    async for token in router.chat_stream(LLMRequest(messages=[{"role": "user", "content": "x"}]), **kwargs):
        out.append(token)
    return "".join(out)


# ── P1-2 task 白名单 ────────────────────────────────────


class TestTaskWhitelist:
    def test_unknown_task_raises_immediately(self):
        with pytest.raises(ValueError) as exc:
            LLMRequest(messages=[], task="geneate")  # 拼错
        assert "geneate" in str(exc.value)
        assert "generate" in str(exc.value)  # 文案里列出允许值

    @pytest.mark.parametrize("task", ["generate", "extract", "plan"])
    def test_valid_tasks_accepted(self, task):
        assert LLMRequest(messages=[], task=task).task == task


# ── P1-3 router 层空产出守卫（覆盖本地客户端）──────────


class TestRouterEmptyGuards:
    def test_local_client_zero_token_stream_is_treated_as_empty(self):
        """本地客户端零 token 时正常结束 → router 必须判定为空产出"""
        client = stream_client([[]])  # 第一次空，第二次也空
        router = make_router({"qwen-local": client})

        with pytest.raises(LLMStreamError) as exc:
            asyncio.run(drain(router, model_name="qwen-local"))

        assert "空产出" in exc.value.message
        # 已重试 1 次 → 共调用 2 次
        assert client.state["n"] == 2

    def test_whitespace_only_stream_is_empty(self):
        client = stream_client([[" "], ["\n", "\t"]])
        router = make_router({"local": client})

        with pytest.raises(LLMStreamError) as exc:
            asyncio.run(drain(router, model_name="local"))

        assert "空产出" in exc.value.message

    def test_chat_success_with_blank_content_is_empty(self):
        client = MagicMock()
        client.chat = AsyncMock(
            side_effect=[
                LLMResponse(content="   \n", model="m", provider="local"),
                LLMResponse(content="  ", model="m", provider="local"),
            ]
        )
        router = make_router({"local": client})

        result = asyncio.run(router.chat(LLMRequest(messages=[]), model_name="local"))

        assert result.success is False
        # 无其他模型可 fallback → 聚合失败信息，但仍须暴露"空产出"这一原因
        assert "空产出" in result.error
        assert client.chat.await_count == 2  # 重试 1 次


# ── P1-4 空产出重试 1 次 ────────────────────────────────


class TestEmptyOutputRetry:
    def test_stream_retries_same_model_once_then_succeeds(self):
        """第一次空产出 → 同模型重试 → 第二次拿到正文（不触发 fallback）"""
        client = stream_client([[], ["正文", "继续"]])
        router = make_router({"m1": client})

        text = asyncio.run(drain(router, model_name="m1"))

        assert text == "正文继续"
        assert client.state["n"] == 2
        assert "Fallback" not in text

    def test_stream_falls_back_after_retry_exhausted(self):
        """目标模型两次都空 → fallback 到健康模型，且目标模型确实被调 2 次"""
        bad = stream_client([[], []])
        good = stream_client([["备"], ["用"]])
        router = make_router({"bad": bad, "good": good})

        text = asyncio.run(drain(router, model_name="bad"))

        assert text == "[Fallback → good]\n备"
        assert "Fallback" in text
        assert bad.state["n"] == 2
        assert good.state["n"] == 1

    def test_chat_retries_once_then_succeeds(self):
        client = MagicMock()
        client.chat = AsyncMock(
            side_effect=[
                LLMResponse(success=False, empty_output=True, error="模型返回空产出（content 为空）"),
                LLMResponse(content="第二次成功", model="m", provider="deepseek"),
            ]
        )
        router = make_router({"m1": client})

        result = asyncio.run(router.chat(LLMRequest(messages=[]), model_name="m1"))

        assert result.success is True
        assert result.content == "第二次成功"
        assert client.chat.await_count == 2

    def test_chat_fallback_after_retry_exhausted(self):
        bad = MagicMock()
        bad.chat = AsyncMock(
            return_value=LLMResponse(success=False, empty_output=True, error="模型返回空产出（content 为空）")
        )
        good = MagicMock()
        good.chat = AsyncMock(return_value=LLMResponse(content="备份正文", model="m", provider="deepseek"))
        router = make_router({"bad": bad, "good": good})

        result = asyncio.run(router.chat(LLMRequest(messages=[]), model_name="bad"))

        assert result.success is True
        assert result.content.startswith("[Fallback → good]")
        assert bad.chat.await_count == 2
        assert good.chat.await_count == 1

    def test_non_empty_error_does_not_retry(self):
        """上游网络错误不该重试同模型（只有空产出才重试）"""
        bad = MagicMock()
        bad.chat = AsyncMock(return_value=LLMResponse(success=False, error="HTTP 500: boom"))
        router = make_router({"bad": bad})

        result = asyncio.run(router.chat(LLMRequest(messages=[]), model_name="bad", fallback=False))

        assert result.success is False
        assert bad.chat.await_count == 1


# ── P2-1 provider 门控 ──────────────────────────────────


class TestThinkingProviderGate:
    def _payload(self, provider: str, task: str = "generate") -> dict:
        client = OpenAIClient({
            "name": provider,
            "provider": provider,
            "model_id": "m",
            "base_url": "https://example.com/v1",
            "api_key": "k",
        })
        return client._build_payload(LLMRequest(messages=[], task=task, temperature=0.5))

    def test_deepseek_gets_thinking_field(self):
        payload = self._payload("deepseek")
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["temperature"] == 0.5

    def test_other_openai_compatible_provider_omits_thinking(self):
        """DashScope 等第三方字段名不同/拒绝未知字段 → 不发 thinking，但温度照发"""
        payload = self._payload("openai")
        assert "thinking" not in payload
        assert payload["temperature"] == 0.5

    def test_plan_task_on_non_thinking_provider_omits_both(self):
        payload = self._payload("openai", task="plan")
        assert "thinking" not in payload
        assert "temperature" not in payload


def test_empty_output_error_is_a_stream_error():
    """SSE 层只认 LLMStreamError，空产出必须仍是它的子类（否则 error 事件发不出去）"""
    assert issubclass(LLMEmptyOutputError, LLMStreamError)
