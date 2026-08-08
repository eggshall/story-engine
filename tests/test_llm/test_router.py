"""测试：ModelRouter — fallback 诊断 / 前缀标记 / 流式 fallback"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from story_engine.llm.api_client import AnthropicClient, OpenAIClient
from story_engine.llm.base import BaseLLM, LLMRequest, LLMResponse, LLMStreamError
from story_engine.llm.local_client import LocalLLMClient
from story_engine.llm.router import ModelRouter


class _FakeClient(BaseLLM):
    """可编程假客户端：按 name 决定成功/失败/流式行为"""

    def __init__(self, config, *, succeed: bool = True,
                 stream_chunks: list[str] | None = None,
                 raise_stream: bool = False,
                 raise_generic: bool = False) -> None:
        super().__init__(config)
        self.succeed = succeed
        self.stream_chunks = stream_chunks or ["块1", "块2"]
        self.raise_stream = raise_stream
        self.raise_generic = raise_generic
        self.chat_calls = 0

    async def chat(self, request: LLMRequest) -> LLMResponse:
        self.chat_calls += 1
        if self.succeed:
            return LLMResponse(content="好内容", model=self.name, provider=self.provider)
        return LLMResponse(success=False, error=f"{self.name}挂了", provider=self.provider)

    async def chat_stream(self, request: LLMRequest):
        if self.raise_stream:
            raise LLMStreamError(f"{self.name}流式失败")
        if self.raise_generic:
            raise RuntimeError(f"{self.name}内部错误")
        for c in self.stream_chunks:
            yield c

    async def close(self) -> None:
        return None


def _router(clients: list[_FakeClient], default: str = "") -> ModelRouter:
    r = ModelRouter([], default_model=default)
    r._clients = {c.name: c for c in clients}
    return r


class TestChatFallback:
    def test_success_no_prefix(self):
        a = _FakeClient({"name": "a", "provider": "p"})
        r = _router([a], default="a")
        result = asyncio.run(r.chat(LLMRequest(messages=[]), model_name="a"))
        assert result.success is True
        assert result.content == "好内容"
        assert "Fallback" not in result.content

    def test_fallback_success_adds_prefix(self):
        a = _FakeClient({"name": "a", "provider": "p"}, succeed=False)
        b = _FakeClient({"name": "b", "provider": "p"})
        r = _router([a, b], default="a")
        result = asyncio.run(r.chat(LLMRequest(messages=[]), model_name="a"))
        assert result.success is True
        assert result.content.startswith("[Fallback → b]")

    def test_all_fail_aggregates_errors(self):
        a = _FakeClient({"name": "a", "provider": "p"}, succeed=False)
        b = _FakeClient({"name": "b", "provider": "p"}, succeed=False)
        r = _router([a, b], default="a")
        result = asyncio.run(r.chat(LLMRequest(messages=[]), model_name="a"))
        assert result.success is False
        assert "a: a挂了" in result.error
        assert "b: b挂了" in result.error

    def test_named_model_not_in_clients_no_prefix(self):
        """指定了不存在模型时使用默认/首个，不应加 fallback 前缀"""
        b = _FakeClient({"name": "b", "provider": "p"})
        r = _router([b], default="b")
        result = asyncio.run(r.chat(LLMRequest(messages=[]), model_name="ghost"))
        assert result.success is True
        assert "Fallback" not in result.content

    def test_default_model_used_when_no_model_name(self):
        """未指定模型时使用 default_model"""
        a = _FakeClient({"name": "a", "provider": "p"})
        b = _FakeClient({"name": "b", "provider": "p"})
        r = _router([a, b], default="b")
        result = asyncio.run(r.chat(LLMRequest(messages=[])))
        assert result.success is True
        assert b.chat_calls == 1
        assert a.chat_calls == 0

    def test_fallback_disabled_returns_failed_result(self):
        """fallback=False 时应直接返回目标模型的失败结果，不尝试其他模型"""
        a = _FakeClient({"name": "a", "provider": "p"}, succeed=False)
        b = _FakeClient({"name": "b", "provider": "p"})
        r = _router([a, b], default="a")
        result = asyncio.run(r.chat(LLMRequest(messages=[]), model_name="a", fallback=False))
        assert result.success is False
        assert b.chat_calls == 0

    def test_no_models_returns_clear_error(self):
        """无任何模型时返回明确的错误信息"""
        r = _router([], default="")
        result = asyncio.run(r.chat(LLMRequest(messages=[])))
        assert result.success is False
        assert "未找到可用模型" in result.error

    def test_no_error_passthrough(self):
        """目标失败但无 error 信息时，聚合 detail 使用默认提示"""
        class _SilentFail(_FakeClient):
            async def chat(self, request: LLMRequest) -> LLMResponse:
                return LLMResponse(success=False, provider=self.provider)  # 无 error 字段

        a = _SilentFail({"name": "a", "provider": "p"})
        r = _router([a], default="a")
        result = asyncio.run(r.chat(LLMRequest(messages=[])))
        assert result.success is False
        assert "未找到可用模型" in result.error


class TestChatStream:
    def test_stream_success(self):
        a = _FakeClient({"name": "a", "provider": "p"})
        r = _router([a], default="a")
        async def _collect():
            out = []
            async for chunk in r.chat_stream(LLMRequest(messages=[]), model_name="a"):
                out.append(chunk)
            return "".join(out)
        assert asyncio.run(_collect()) == "块1块2"

    def test_stream_fallback_on_error(self):
        a = _FakeClient({"name": "a", "provider": "p"}, raise_stream=True)
        b = _FakeClient({"name": "b", "provider": "p"})
        r = _router([a, b], default="a")
        async def _collect():
            out = []
            async for chunk in r.chat_stream(LLMRequest(messages=[]), model_name="a"):
                out.append(chunk)
            return "".join(out)
        text = asyncio.run(_collect())
        assert text.startswith("[Fallback → b]")
        assert "块1" in text

    def test_stream_all_fail_raises(self):
        a = _FakeClient({"name": "a", "provider": "p"}, raise_stream=True)
        b = _FakeClient({"name": "b", "provider": "p"}, raise_stream=True)
        r = _router([a, b], default="a")
        async def _collect():
            out = []
            async for chunk in r.chat_stream(LLMRequest(messages=[]), model_name="a"):
                out.append(chunk)
            return out
        with pytest.raises(LLMStreamError) as ei:
            asyncio.run(_collect())
        assert "a: a流式失败" in str(ei.value)
        assert "b: b流式失败" in str(ei.value)

    def test_stream_no_error_text_in_body(self):
        """流式失败不应把 [Error: ...] 混入正文"""
        a = _FakeClient({"name": "a", "provider": "p"}, raise_stream=True)
        r = _router([a], default="a")
        async def _collect():
            out = []
            async for chunk in r.chat_stream(LLMRequest(messages=[]), model_name="a"):
                out.append(chunk)
            return out
        with pytest.raises(LLMStreamError):
            asyncio.run(_collect())

    def test_stream_mismatched_model_adds_prefix(self):
        """指定模型不在列表、落到默认模型时流式应标 [Fallback → 默认] 前缀"""
        a = _FakeClient({"name": "a", "provider": "p"})
        r = _router([a], default="a")
        async def _collect():
            out = []
            async for chunk in r.chat_stream(LLMRequest(messages=[]), model_name="ghost"):
                out.append(chunk)
            return "".join(out)
        text = asyncio.run(_collect())
        assert text.startswith("[Fallback → a]")
        assert "块1" in text

    def test_stream_fallback_over_generic_exception(self):
        """目标抛非 LLMStreamError 的泛异常也应触发 fallback"""
        a = _FakeClient({"name": "a", "provider": "p"}, raise_generic=True)
        b = _FakeClient({"name": "b", "provider": "p"})
        r = _router([a, b], default="a")
        async def _collect():
            out = []
            async for chunk in r.chat_stream(LLMRequest(messages=[]), model_name="a"):
                out.append(chunk)
            return "".join(out)
        text = asyncio.run(_collect())
        assert text.startswith("[Fallback → b]")

    def test_stream_all_generic_fail_aggregates(self):
        """所有模型抛泛异常时聚合错误并抛 LLMStreamError"""
        a = _FakeClient({"name": "a", "provider": "p"}, raise_generic=True)
        b = _FakeClient({"name": "b", "provider": "p"}, raise_generic=True)
        r = _router([a, b], default="a")
        async def _collect():
            out = []
            async for chunk in r.chat_stream(LLMRequest(messages=[]), model_name="a"):
                out.append(chunk)
            return out
        with pytest.raises(LLMStreamError) as ei:
            asyncio.run(_collect())
        assert "a内部错误" in str(ei.value)
        assert "b内部错误" in str(ei.value)

    def test_stream_no_models_raises(self):
        """无模型时流式抛 LLMStreamError"""
        r = _router([], default="")
        async def _collect():
            out = []
            async for chunk in r.chat_stream(LLMRequest(messages=[])):
                out.append(chunk)
            return out
        with pytest.raises(LLMStreamError) as ei:
            asyncio.run(_collect())
        assert "未找到可用模型" in str(ei.value)


class TestCloseAll:
    def test_close_all_swallows_client_errors(self):
        """单个 client close 抛异常不应中断其他 client 的关闭"""
        closed = []

        class _FailingClose(_FakeClient):
            async def close(self) -> None:
                closed.append(self.name)
                raise RuntimeError("close 失败")

        a = _FailingClose({"name": "a", "provider": "p"})
        b = _FakeClient({"name": "b", "provider": "p"})
        b.close = AsyncMock(side_effect=lambda: closed.append("b"))  # type: ignore[method-assign]
        r = _router([a, b], default="a")

        async def _close():
            await r.close_all()

        asyncio.run(_close())  # 不应抛异常
        assert closed == ["a", "b"]  # 两个 client 均被尝试关闭

    def test_list_models(self):
        a = _FakeClient({"name": "a", "provider": "p"})
        b = _FakeClient({"name": "b", "provider": "p"})
        r = _router([a, b], default="a")
        assert r.list_models() == ["a", "b"]


class TestClientCreation:
    def test_provider_mapping(self):
        """provider → 客户端类型映射"""
        cfg = [
            {"name": "o", "provider": "openai", "enabled": True},
            {"name": "d", "provider": "deepseek", "enabled": True},
            {"name": "a", "provider": "anthropic", "enabled": True},
            {"name": "l", "provider": "local", "enabled": True},
            {"name": "x", "provider": "unknown", "enabled": True},
            {"name": "dis", "provider": "openai", "enabled": False},
        ]
        r = ModelRouter(cfg)
        assert isinstance(r.get_client("o"), OpenAIClient)
        assert isinstance(r.get_client("d"), OpenAIClient)
        assert isinstance(r.get_client("a"), AnthropicClient)
        assert isinstance(r.get_client("l"), LocalLLMClient)
        assert r.get_client("x") is None
        assert r.get_client("dis") is None
