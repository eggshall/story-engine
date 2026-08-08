"""测试：LLM 模型层"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from story_engine.llm.base import BaseLLM, LLMRequest, LLMResponse
from story_engine.llm.router import ModelRouter


class _MinimalClient(BaseLLM):
    """最小可用实现（测试 format_messages/__repr__/close 约定用）。"""

    def __init__(self, config=None):
        super().__init__(config or {})
        self._closed = False

    async def chat(self, request):
        return LLMResponse(content="ok")

    async def chat_stream(self, request):
        yield "ok"

    async def close(self):
        self._closed = True


class TestLLMBase:
    def test_llm_request(self):
        req = LLMRequest(
            system_prompt="You are helpful",
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0.5,
        )
        assert req.system_prompt == "You are helpful"
        assert len(req.messages) == 1

    def test_llm_response(self):
        resp = LLMResponse(content="Hello!", model="test-model", provider="test")
        assert resp.success
        assert resp.content == "Hello!"

    def test_llm_response_error(self):
        resp = LLMResponse(success=False, error="API Error")
        assert not resp.success

    def test_format_messages(self):
        """测试 system + user 消息拼接"""
        client = _MinimalClient({"name": "test", "model_id": "m", "provider": "p"})
        msgs = client.format_messages("系统提示", [{"role": "user", "content": "你好"}])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "系统提示"

    def test_repr(self):
        client = _MinimalClient({"name": "测试模型", "model_id": "test-id", "provider": "openai"})
        r = repr(client)
        assert "测试模型" in r
        assert "test-id" in r

    def test_close_is_abstract(self):
        """close() 为抽象方法：未实现子类无法实例化"""
        class _NoClose(BaseLLM):
            async def chat(self, request):
                return LLMResponse()

            async def chat_stream(self, request):
                yield ""

        with pytest.raises(TypeError):
            _NoClose({})

    def test_close_implemented_and_callable(self):
        client = _MinimalClient({})
        async def _run():
            await client.close()
        asyncio.run(_run())
        assert client._closed is True


class TestModelRouter:
    def test_empty_router(self):
        router = ModelRouter([])
        assert router.list_models() == []

    def test_router_init_with_config(self):
        models = [
            {"name": "test-model", "provider": "openai", "model_id": "test",
             "base_url": "http://localhost:8080", "api_key": "test", "enabled": True},
        ]
        router = ModelRouter(models)
        assert "test-model" in router.list_models()

    def test_disabled_model(self):
        models = [
            {"name": "disabled", "provider": "openai", "enabled": False},
        ]
        router = ModelRouter(models)
        assert router.list_models() == []

    def test_get_client(self):
        models = [
            {"name": "m1", "provider": "openai", "model_id": "m", "base_url": "http://localhost:8080", "api_key": "k", "enabled": True},
        ]
        router = ModelRouter(models)
        client = router.get_client("m1")
        assert client is not None
        assert client.name == "m1"


class TestCloseAll:
    def test_close_all_idempotent(self):
        """close_all() 应可多次安全调用（幂等），并逐个关闭 client"""
        models = [
            {"name": "m1", "provider": "openai", "model_id": "m",
             "base_url": "http://localhost:8080", "api_key": "k", "enabled": True},
            {"name": "m2", "provider": "openai", "model_id": "m2",
             "base_url": "http://localhost:8080", "api_key": "k", "enabled": True},
        ]
        router = ModelRouter(models)
        client_mocks = []
        for name in ("m1", "m2"):
            m = AsyncMock()
            router.get_client(name)._client = m
            client_mocks.append(m)

        async def _close_twice():
            await router.close_all()
            await router.close_all()

        asyncio.run(_close_twice())  # 不应抛异常
        # 每个 client 的 close 被调用
        for m in client_mocks:
            m.aclose.assert_called()

    def test_close_all_empty_router(self):
        """空 router 的 close_all() 应安全"""
        router = ModelRouter([])
        async def _close():
            await router.close_all()
        asyncio.run(_close())
