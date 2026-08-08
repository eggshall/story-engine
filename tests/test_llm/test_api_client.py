"""测试：远程 API 客户端 — 超时配置注入 / reasoning 回退 / 错误处理"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from story_engine.llm.api_client import AnthropicClient, OpenAIClient
from story_engine.llm.base import LLMRequest, LLMResponse, LLMStreamError


@pytest.fixture
def openai_client() -> OpenAIClient:
    return OpenAIClient({
        "name": "deepseek",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-test",
        "read_timeout": 60,
        "connect_timeout": 10,
    })


class TestTimeoutInjection:
    def test_chat_uses_request_timeout_override(self, openai_client):
        """注入的请求级超时应被 chat() 消费"""
        client_mock = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json.return_value = {"choices": [{"message": {"content": "ok"}}], "model": "deepseek-chat"}
        client_mock.post = AsyncMock(return_value=resp)
        openai_client._client = client_mock

        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], timeout=30)
        result = asyncio.run(openai_client.chat(req))
        assert result.success is True
        post_kwargs = client_mock.post.call_args.kwargs
        assert post_kwargs["timeout"].read == 30  # 请求级覆盖生效

    def test_chat_defaults_to_config_timeout(self, openai_client):
        """未注入时使用配置的 read_timeout"""
        client_mock = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json.return_value = {"choices": [{"message": {"content": "ok"}}], "model": "m"}
        client_mock.post = AsyncMock(return_value=resp)
        openai_client._client = client_mock

        req = LLMRequest(messages=[{"role": "user", "content": "hi"}])
        result = asyncio.run(openai_client.chat(req))
        assert result.success is True
        assert client_mock.post.call_args.kwargs["timeout"].read == 60

    def test_chat_stream_uses_request_timeout(self, openai_client):
        """chat_stream 也应消费注入的超时"""
        client_mock = MagicMock()

        async def _aiter_lines():
            yield 'data: ' + json.dumps({"choices": [{"delta": {"content": "块"}}]})
            yield 'data: [DONE]'

        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.aiter_lines.return_value = _aiter_lines()
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        client_mock.stream = MagicMock(return_value=stream_ctx)
        openai_client._client = client_mock

        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], timeout=5)
        async def _collect():
            out = []
            async for token in openai_client.chat_stream(req):
                out.append(token)
            return "".join(out)

        text = asyncio.run(_collect())
        assert "块" in text
        assert client_mock.stream.call_args.kwargs["timeout"].read == 5


class TestReasoningFallback:
    def test_chat_content_falls_back_to_reasoning(self, openai_client):
        """content 为空时回退 reasoning_content（推理模型）"""
        client_mock = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json.return_value = {
            "choices": [{"message": {"content": None, "reasoning_content": "思考过程"}}],
            "model": "m",
        }
        client_mock.post = AsyncMock(return_value=resp)
        openai_client._client = client_mock

        result = asyncio.run(openai_client.chat(LLMRequest(messages=[{"role": "user", "content": "hi"}])))
        assert result.success is True
        assert result.content == "思考过程"

    def test_chat_content_empty_string(self, openai_client):
        """content 为空串时同样回退 reasoning"""
        client_mock = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json.return_value = {
            "choices": [{"message": {"content": "", "reasoning_content": "推理内容"}}],
            "model": "m",
        }
        client_mock.post = AsyncMock(return_value=resp)
        openai_client._client = client_mock

        result = asyncio.run(openai_client.chat(LLMRequest(messages=[])))
        assert result.content == "推理内容"


class TestPayload:
    def test_chat_sends_stop(self, openai_client):
        """request.stop 应写入请求体"""
        client_mock = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json.return_value = {"choices": [{"message": {"content": "ok"}}], "model": "m"}
        client_mock.post = AsyncMock(return_value=resp)
        openai_client._client = client_mock

        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], stop=["\n\n", "###"])
        result = asyncio.run(openai_client.chat(req))
        assert result.success is True
        assert client_mock.post.call_args.kwargs["json"]["stop"] == ["\n\n", "###"]

    def test_chat_api_key_header(self):
        """api_key 配置应写入 Authorization 头"""
        client = OpenAIClient({
            "name": "m", "provider": "openai", "model_id": "x",
            "base_url": "https://api.example.com/v1", "api_key": "sk-secret",
        })
        with patch("httpx.AsyncClient", return_value=MagicMock()) as mock_cls:
            client._get_client()
            _, kwargs = mock_cls.call_args
            assert kwargs["headers"]["Authorization"] == "Bearer sk-secret"


class TestStreamTolerance:
    def test_stream_skips_blank_and_comment_lines(self, openai_client):
        """流式应跳过空行/注释行，坏 JSON 行忽略，异常转 LLMStreamError"""
        client_mock = MagicMock()

        async def _aiter_lines():
            yield ''
            yield ': keep-alive'
            yield 'data: {broken json'
            yield 'data: ' + json.dumps({"choices": [{"delta": {"content": "块"}}]})
            yield 'data: [DONE]'

        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.aiter_lines = _aiter_lines
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        client_mock.stream = MagicMock(return_value=stream_ctx)
        openai_client._client = client_mock

        async def _collect():
            out = []
            async for token in openai_client.chat_stream(LLMRequest(messages=[])):
                out.append(token)
            return "".join(out)

        assert asyncio.run(_collect()) == "块"

    def test_stream_error_raises_llm_stream_error(self, openai_client):
        """流式底层异常应以 LLMStreamError 抛出，不再混入 [Error: ...]"""
        client_mock = MagicMock()

        async def _aiter_lines():
            raise httpx.ReadTimeout("upstream timeout")
            yield  # pragma: no cover

        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.aiter_lines = lambda: _aiter_lines()
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        client_mock.stream = MagicMock(return_value=stream_ctx)
        openai_client._client = client_mock

        async def _collect():
            out = []
            async for token in openai_client.chat_stream(LLMRequest(messages=[])):
                out.append(token)
            return out

        with pytest.raises(LLMStreamError) as ei:
            asyncio.run(_collect())
        assert "upstream timeout" in str(ei.value)

    def test_close_releases_client(self, openai_client):
        """close() 应 aclose 底层 client 并清空引用"""
        client_mock = MagicMock()
        client_mock.aclose = AsyncMock(return_value=None)
        openai_client._client = client_mock

        async def _close():
            await openai_client.close()

        asyncio.run(_close())
        client_mock.aclose.assert_awaited()
        assert openai_client._client is None


class TestErrorHandling:
    def test_http_error_masked(self, openai_client):
        """HTTP 错误返回结构化 error，不抛异常"""
        client_mock = MagicMock()
        resp = MagicMock()
        resp.status_code = 429
        resp.text = "rate limit"
        resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
            "429", request=MagicMock(), response=resp))
        client_mock.post = AsyncMock(return_value=resp)
        openai_client._client = client_mock

        result = asyncio.run(openai_client.chat(LLMRequest(messages=[])))
        assert result.success is False
        assert "429" in result.error

    def test_chat_generic_exception(self, openai_client):
        """未知异常返回结构化错误，不抛异常"""
        client_mock = MagicMock()
        client_mock.post = AsyncMock(side_effect=httpx.ConnectError("conn refused"))
        openai_client._client = client_mock

        result = asyncio.run(openai_client.chat(LLMRequest(messages=[])))
        assert result.success is False
        assert "conn refused" in result.error

    def test_anthropic_timeout_injected(self):
        """Anthropic 客户端同样消费请求级超时"""
        client = AnthropicClient({
            "name": "claude", "provider": "anthropic",
            "model_id": "claude-x", "base_url": "https://api.anthropic.com/v1",
            "api_key": "k", "read_timeout": 120,
        })
        client_mock = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json.return_value = {"content": [{"type": "text", "text": "你好"}]}
        client_mock.post = AsyncMock(return_value=resp)
        client._client = client_mock

        result = asyncio.run(client.chat(LLMRequest(messages=[{"role": "user", "content": "hi"}], timeout=45)))
        assert result.success is True
        assert client_mock.post.call_args.kwargs["timeout"].read == 45


@pytest.fixture
def anthropic_client() -> AnthropicClient:
    return AnthropicClient({
        "name": "claude", "provider": "anthropic",
        "model_id": "claude-x", "base_url": "https://api.anthropic.com/v1",
        "api_key": "k-anthropic", "read_timeout": 120, "connect_timeout": 8,
    })


class TestAnthropic:
    def test_get_client_headers(self, anthropic_client):
        """Anthropic 请求头应包含 api key 与版本"""
        with patch("httpx.AsyncClient", return_value=MagicMock()) as mock_cls:
            anthropic_client._get_client()
            _, kwargs = mock_cls.call_args
            assert kwargs["headers"]["x-api-key"] == "k-anthropic"
            assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
            assert kwargs["timeout"].read == 120

    def test_chat_with_system_prompt(self, anthropic_client):
        """system_prompt 应写入 payload.system，多段 text 拼接"""
        client_mock = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json.return_value = {
            "content": [
                {"type": "text", "text": "第"},
                {"type": "text", "text": "一段"},
                {"type": "tool_use", "text": "忽略"},
            ],
            "model": "claude-x",
        }
        client_mock.post = AsyncMock(return_value=resp)
        anthropic_client._client = client_mock

        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], system_prompt="你是一位编辑")
        result = asyncio.run(anthropic_client.chat(req))
        assert result.success is True
        assert result.content == "第一段"
        assert client_mock.post.call_args.kwargs["json"]["system"] == "你是一位编辑"

    def test_chat_error_masked(self, anthropic_client):
        """Anthropic 未知异常返回结构化错误"""
        client_mock = MagicMock()
        client_mock.post = AsyncMock(side_effect=httpx.ConnectError("conn refused"))
        anthropic_client._client = client_mock

        result = asyncio.run(anthropic_client.chat(LLMRequest(messages=[])))
        assert isinstance(result, LLMResponse)
        assert result.success is False
        assert "conn refused" in result.error

    def test_chat_stream_content_block_delta(self, anthropic_client):
        """Anthropic 流式解析 content_block_delta 并消费请求级超时"""
        client_mock = MagicMock()

        async def _aiter_lines():
            yield 'event: message_start'
            yield 'data: ' + json.dumps({"type": "content_block_delta", "delta": {"text": "流"}})
            yield 'data: {bad'
            yield 'data: ' + json.dumps({"type": "content_block_delta", "delta": {"text": "式"}})
            yield 'data: [DONE]'

        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.aiter_lines = _aiter_lines
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        client_mock.stream = MagicMock(return_value=stream_ctx)
        anthropic_client._client = client_mock

        async def _collect():
            out = []
            async for token in anthropic_client.chat_stream(
                    LLMRequest(messages=[], timeout=7, system_prompt="系统提示")):
                out.append(token)
            return "".join(out)

        text = asyncio.run(_collect())
        assert text == "流式"
        assert client_mock.stream.call_args.kwargs["timeout"].read == 7
        assert client_mock.stream.call_args.kwargs["json"]["system"] == "系统提示"

    def test_chat_stream_error_raises(self, anthropic_client):
        """Anthropic 流式异常以 LLMStreamError 抛出"""
        client_mock = MagicMock()

        async def _aiter_lines():
            raise httpx.ReadTimeout("anthropic timeout")
            yield  # pragma: no cover

        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.aiter_lines = lambda: _aiter_lines()
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        client_mock.stream = MagicMock(return_value=stream_ctx)
        anthropic_client._client = client_mock

        async def _collect():
            out = []
            async for token in anthropic_client.chat_stream(LLMRequest(messages=[])):
                out.append(token)
            return out

        with pytest.raises(LLMStreamError) as ei:
            asyncio.run(_collect())
        assert "anthropic timeout" in str(ei.value)

    def test_close_releases_client(self, anthropic_client):
        client_mock = MagicMock()
        client_mock.aclose = AsyncMock(return_value=None)
        anthropic_client._client = client_mock

        async def _close():
            await anthropic_client.close()

        asyncio.run(_close())
        client_mock.aclose.assert_awaited()
        assert anthropic_client._client is None
