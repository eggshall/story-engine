"""测试：LLM 模型层"""
from story_engine.llm.base import BaseLLM, LLMRequest, LLMResponse
from story_engine.llm.router import ModelRouter


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
        class TestClient(BaseLLM):
            async def chat(self, request): pass
            async def chat_stream(self, request):
                yield ""

        client = TestClient({"name": "test", "model_id": "m", "provider": "p"})
        msgs = client.format_messages("系统提示", [{"role": "user", "content": "你好"}])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "系统提示"


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
