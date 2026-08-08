"""测试：本地模型客户端 — 超时配置生效 / 探测与持久 client 分离"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from story_engine.llm.base import LLMRequest, LLMResponse, LLMStreamError
from story_engine.llm.local_client import LocalLLMClient


@pytest.fixture
def local_client() -> LocalLLMClient:
    return LocalLLMClient({
        "name": "local",
        "provider": "local",
        "model_id": "qwen3.5:9b",
        "base_url": "http://127.0.0.1:11434",
        "read_timeout": 300,
        "connect_timeout": 10,
    })


class TestTimeout:
    def test_chat_uses_read_timeout_from_config(self, local_client):
        """chat 应通过持久 client 走配置的 read_timeout(300s)"""
        client_mock = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json.return_value = {
            "choices": [{"message": {"content": "你好"}}],
            "model": "qwen3.5:9b",
        }
        client_mock.post = AsyncMock(return_value=resp)

        with patch.object(local_client, "_ensure_ready", new=AsyncMock(return_value="")), \
             patch.object(local_client, "_get_client", return_value=client_mock) as mock_get:
            result = asyncio.run(local_client.chat(LLMRequest(messages=[{"role": "user", "content": "hi"}])))
            assert result.success is True
            assert result.content == "你好"
            # chat 显式传 read_timeout=self.read_timeout
            assert mock_get.call_args.kwargs.get("read_timeout") == 300

    def test_get_client_rebuilds_on_timeout_change(self, local_client):
        """持久 client 超时变化时应重建，而不是复用旧 client"""
        instances = []
        with patch("httpx.AsyncClient", side_effect=lambda **kw: instances.append(MagicMock()) or instances[-1]):
            c1 = local_client._get_client(read_timeout=300)
            c2 = local_client._get_client(read_timeout=300)
            assert c1 is c2  # 超时未变 → 复用
            assert len(instances) == 1

            c3 = local_client._get_client(read_timeout=10)
            assert c3 is not c1  # 超时变化 → 重建
            assert len(instances) == 2

    def test_chat_uses_request_timeout_override(self, local_client):
        """请求级 timeout 覆盖应传给 _get_client（L2 语义在本地客户端同样生效）"""
        client_mock = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = lambda: None
        resp.json.return_value = {
            "choices": [{"message": {"content": "你好"}}],
            "model": "qwen",
        }
        client_mock.post = AsyncMock(return_value=resp)

        with patch.object(local_client, "_ensure_ready", new=AsyncMock(return_value="")), \
             patch.object(local_client, "_get_client", return_value=client_mock) as mock_get:
            req = LLMRequest(messages=[{"role": "user", "content": "hi"}], timeout=42)
            result = asyncio.run(local_client.chat(req))
            assert result.success is True
            assert mock_get.call_args.kwargs.get("read_timeout") == 42  # 覆盖配置的 300

    def test_probe_uses_temp_client_not_persistent(self, local_client):
        """探测应使用短超时临时 client，不能污染持久 client 的超时配置"""
        instances = []
        with patch("httpx.AsyncClient", side_effect=lambda **kw: instances.append(MagicMock()) or instances[-1]):
            # 先构造持久 client
            local_client._get_client(read_timeout=300)
            assert len(instances) == 1

            async def _probe():
                return await local_client._check_server()

            # 探测不应复用持久 client
            result = asyncio.run(_probe())
            assert result == (False, "")
            # 探测创建的是临时 client（数量增加）
            assert len(instances) >= 2
            # 持久 client 超时配置未被探测污染
            assert local_client._client_read_timeout == 300


class TestHealthCache:
    def test_health_cached_within_ttl(self, local_client):
        """健康状态在 TTL 内应缓存，不重复探测"""
        instances = []
        with patch("httpx.AsyncClient", side_effect=lambda **kw: instances.append(MagicMock()) or instances[-1]):
            async def _probe():
                return await local_client._check_server()

            asyncio.run(_probe())
            calls_before = len(instances)
            asyncio.run(_probe())
            # 第二次应命中缓存（TTL 30s），不再创建 client
            assert len(instances) == calls_before

    def test_warm_up_uses_temp_client(self, local_client):
        """预热应使用独立临时 client（长超时），不复用持久 client"""
        instances = []

        def _new_instance(**kw):
            inst = MagicMock()
            inst.post = AsyncMock(side_effect=httpx.ConnectError("conn refused"))
            inst.__aenter__ = AsyncMock(return_value=inst)
            inst.__aexit__ = AsyncMock(return_value=False)
            instances.append(inst)
            return inst

        with patch("httpx.AsyncClient", side_effect=_new_instance):
            local_client._get_client(read_timeout=300)
            calls_before = len(instances)

            async def _warm():
                return await local_client._warm_up()

            result = asyncio.run(_warm())
            assert result is False
            # 预热创建了新的临时 client
            assert len(instances) > calls_before
            assert local_client._client_read_timeout == 300  # 持久 client 不受影响


class TestEnsureReady:
    def test_ensure_ready_serialized_by_lock(self, local_client):
        """探测/预热应通过 Lock 串行化，消除 _warmed 竞态"""
        # _ensure_ready 内部使用 self._lock，正常路径下调用不抛错
        with patch.object(local_client, "_check_server", new=AsyncMock(return_value=(True, "/health"))), \
             patch.object(local_client, "_warm_up", new=AsyncMock(return_value=True)):
            async def _go():
                return await local_client._ensure_ready()

            err = asyncio.run(_go())
            assert err == ""

    def test_ensure_ready_reports_server_down(self, local_client):
        with patch.object(local_client, "_check_server", new=AsyncMock(return_value=(False, ""))):
            async def _go():
                return await local_client._ensure_ready()

            err = asyncio.run(_go())
            assert "未启动" in err

    def test_ensure_ready_reports_warm_fail(self, local_client):
        """探测通过但预热失败 → 返回预热错误"""
        with patch.object(local_client, "_check_server", new=AsyncMock(return_value=(True, "/api/tags"))), \
             patch.object(local_client, "_warm_up", new=AsyncMock(return_value=False)):
            async def _go():
                return await local_client._ensure_ready()

            err = asyncio.run(_go())
            assert "预热失败" in err

    def test_warm_up_cache_short_circuit(self, local_client):
        """_warmed=True 时预热直接返回，不再创建任何 client"""
        local_client._warmed = True
        with patch("httpx.AsyncClient", side_effect=AssertionError("不应创建 client")):
            async def _warm():
                return await local_client._warm_up()

            assert asyncio.run(_warm()) is True

    def test_warm_up_success_sets_flag(self, local_client):
        """预热成功应置 _warmed=True 并返回 True"""
        local_client._warmed = False
        instances = []

        def _new_instance(**kw):
            inst = MagicMock()
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = lambda: None
            inst.post = AsyncMock(return_value=resp)
            inst.__aenter__ = AsyncMock(return_value=inst)
            inst.__aexit__ = AsyncMock(return_value=False)
            instances.append(inst)
            return inst

        with patch("httpx.AsyncClient", side_effect=_new_instance):
            assert asyncio.run(local_client._warm_up()) is True
            assert local_client._warmed is True
            assert len(instances) == 1

    def test_check_server_success_status(self, local_client):
        """探测任一端点返回 <500 视为服务器存活，并缓存结果"""
        local_client._health = None
        local_client._health_at = 0.0

        def _new_instance(**kw):
            inst = MagicMock()
            resp = MagicMock()
            resp.status_code = 404
            inst.get = AsyncMock(return_value=resp)
            inst.__aenter__ = AsyncMock(return_value=inst)
            inst.__aexit__ = AsyncMock(return_value=False)
            return inst

        with patch("httpx.AsyncClient", side_effect=_new_instance):
            async def _probe():
                return await local_client._check_server()

            result = asyncio.run(_probe())
            assert result == (True, "/api/tags")  # 首个端点 404(<500) 即存活
            # 结果已缓存，TTL 内复用
            assert local_client._health == (True, "/api/tags")


class TestChatErrors:
    def test_chat_server_not_ready(self, local_client):
        """服务器未就绪时 chat 返回结构化错误而非抛异常"""
        with patch.object(local_client, "_ensure_ready", new=AsyncMock(return_value="本地模型服务器未启动")):
            result = asyncio.run(local_client.chat(LLMRequest(messages=[])))
            assert isinstance(result, LLMResponse)
            assert result.success is False
            assert "未启动" in result.error

    def test_chat_timeout_error(self, local_client):
        """超时返回结构化错误，携带生效的 read_timeout"""
        with patch.object(local_client, "_ensure_ready", new=AsyncMock(return_value="")):
            client_mock = MagicMock()
            client_mock.post = AsyncMock(side_effect=httpx.ReadTimeout("read timed out"))
            with patch.object(local_client, "_get_client", return_value=client_mock):
                result = asyncio.run(local_client.chat(LLMRequest(messages=[])))
                assert result.success is False
                assert "超时" in result.error
                assert "300s" in result.error

    def test_chat_request_timeout_in_error(self, local_client):
        """请求级覆盖的超时出现在错误信息中"""
        with patch.object(local_client, "_ensure_ready", new=AsyncMock(return_value="")):
            client_mock = MagicMock()
            client_mock.post = AsyncMock(side_effect=httpx.ConnectTimeout("connect timed out"))
            with patch.object(local_client, "_get_client", return_value=client_mock):
                req = LLMRequest(messages=[], timeout=8)
                result = asyncio.run(local_client.chat(req))
                assert result.success is False
                assert "8s" in result.error

    def test_chat_generic_exception(self, local_client):
        """未知异常返回结构化错误，不抛异常"""
        with patch.object(local_client, "_ensure_ready", new=AsyncMock(return_value="")):
            client_mock = MagicMock()
            client_mock.post = AsyncMock(side_effect=ValueError("boom"))
            with patch.object(local_client, "_get_client", return_value=client_mock):
                result = asyncio.run(local_client.chat(LLMRequest(messages=[])))
                assert result.success is False
                assert "boom" in result.error


class TestStreamErrors:
    def test_stream_server_not_ready_raises(self, local_client):
        """流式模式下服务器未就绪应抛 LLMStreamError，而非混入正文"""
        with patch.object(local_client, "_ensure_ready", new=AsyncMock(return_value="未启动")):
            async def _collect():
                out = []
                async for token in local_client.chat_stream(LLMRequest(messages=[])):
                    out.append(token)
                return out

            with pytest.raises(LLMStreamError) as ei:
                asyncio.run(_collect())
            assert "未启动" in str(ei.value)

    def test_stream_skips_malformed_json(self, local_client):
        """流式解析容错：坏 JSON 行跳过，后续 token 正常输出"""
        with patch.object(local_client, "_ensure_ready", new=AsyncMock(return_value="")):
            client_mock = MagicMock()

            async def _aiter_lines():
                yield ''                          # 空行跳过
                yield ': keep-alive comment'      # 注释行跳过
                yield 'data: {bad json'
                yield 'data: ' + json.dumps({"choices": [{"delta": {"content": "好"}}]})
                yield 'data: ' + json.dumps({"choices": [{"delta": {"reasoning": "思"}}]})
                yield 'data: [DONE]'

            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = lambda: None
            resp.aiter_lines.return_value = _aiter_lines()
            stream_ctx = MagicMock()
            stream_ctx.__aenter__ = AsyncMock(return_value=resp)
            stream_ctx.__aexit__ = AsyncMock(return_value=False)
            client_mock.stream = MagicMock(return_value=stream_ctx)
            with patch.object(local_client, "_get_client", return_value=client_mock):
                async def _collect():
                    out = []
                    async for token in local_client.chat_stream(LLMRequest(messages=[])):
                        out.append(token)
                    return "".join(out)

                text = asyncio.run(_collect())
                assert text == "好思"

    def test_stream_exception_raises(self, local_client):
        """流式底层异常应转为 LLMStreamError 抛出"""
        with patch.object(local_client, "_ensure_ready", new=AsyncMock(return_value="")):
            client_mock = MagicMock()
            resp = MagicMock()
            resp.raise_for_status = lambda: None

            async def _aiter_lines():
                raise httpx.ReadTimeout("stream timeout")
                yield  # pragma: no cover

            resp.aiter_lines = lambda: _aiter_lines()
            stream_ctx = MagicMock()
            stream_ctx.__aenter__ = AsyncMock(return_value=resp)
            stream_ctx.__aexit__ = AsyncMock(return_value=False)
            client_mock.stream = MagicMock(return_value=stream_ctx)
            with patch.object(local_client, "_get_client", return_value=client_mock):
                async def _collect():
                    out = []
                    async for token in local_client.chat_stream(LLMRequest(messages=[])):
                        out.append(token)
                    return out

                with pytest.raises(LLMStreamError) as ei:
                    asyncio.run(_collect())
                assert "stream timeout" in str(ei.value)


class TestClose:
    def test_close_releases_client(self, local_client):
        """close() 应 aclose 底层 client 并清空引用"""
        client_mock = MagicMock()
        client_mock.aclose = AsyncMock(return_value=None)
        local_client._client = client_mock

        async def _close():
            await local_client.close()

        asyncio.run(_close())
        client_mock.aclose.assert_awaited()
        assert local_client._client is None

    def test_close_idempotent_no_client(self, local_client):
        """无 client 时 close() 安全"""
        local_client._client = None
        async def _close():
            await local_client.close()
        asyncio.run(_close())


class TestStreamErrorFormat:
    def test_chat_stream_errors_as_text(self, local_client):
        """流式错误应混入正文（兼容旧协议）；内容解析从 delta.content/reasoning 取"""
        with patch.object(local_client, "_ensure_ready", new=AsyncMock(return_value="")):
            client_mock = MagicMock()

            async def _aiter_lines():
                yield 'data: ' + json.dumps({"choices": [{"delta": {"content": "前"}}]})
                yield 'data: ' + json.dumps({"choices": [{"delta": {"reasoning": "思"}}]})
                yield 'data: [DONE]'

            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = lambda: None
            resp.aiter_lines.return_value = _aiter_lines()

            stream_ctx = MagicMock()
            stream_ctx.__aenter__ = AsyncMock(return_value=resp)
            stream_ctx.__aexit__ = AsyncMock(return_value=False)
            client_mock.stream = MagicMock(return_value=stream_ctx)
            with patch.object(local_client, "_get_client", return_value=client_mock):
                async def _collect():
                    out = []
                    async for token in local_client.chat_stream(LLMRequest(messages=[])):
                        out.append(token)
                    return "".join(out)

                text = asyncio.run(_collect())
                # content + reasoning 均被消费；空 content 时回退 reasoning
                assert "前" in text
                assert "思" in text
