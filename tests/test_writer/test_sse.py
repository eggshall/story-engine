"""测试：SSE 工具 — 统一事件协议 / 断开中断 / 错误事件"""

import asyncio
import json

from story_engine.api.sse import (
    event_stream,
    format_sse,
    format_sse_done,
    format_sse_error,
)
from story_engine.llm.base import LLMStreamError


class TestSSEFormat:
    def test_format_sse_message(self):
        msg = format_sse({"token": "你好"}, event="token")
        assert msg.startswith("event: token")
        assert 'data: {"token": "你好"}' in msg

    def test_format_sse_done(self):
        msg = format_sse_done()
        assert "done" in msg
        assert "true" in msg

    def test_format_sse_error(self):
        msg = format_sse_error("出错了")
        assert "error" in msg
        assert "出错了" in msg


class TestEventStream:
    async def _collect(self, gen):
        out = []
        async for item in gen:
            out.append(item)
        return out

    def test_plain_text_tokens(self):
        async def _gen():
            yield "第"
            yield "一章"

        events = asyncio.run(self._collect(event_stream(_gen())))
        assert len(events) == 3
        assert events[0]["event"] == "token"
        assert json.loads(events[0]["data"]) == {"token": "第"}
        assert events[1]["event"] == "token"
        # 最后一个是 done
        assert events[2]["event"] == "done"
        assert json.loads(events[2]["data"]) == {"done": True}

    def test_structured_dict_token(self):
        async def _gen():
            yield {"kind": "outline", "title": "第一章"}

        events = asyncio.run(self._collect(event_stream(_gen())))
        # 无 done/error 键的 dict 作为 token
        assert events[0]["event"] == "token"
        assert json.loads(events[0]["data"])["token"] == {"kind": "outline", "title": "第一章"}

    def test_done_dict_event(self):
        async def _gen():
            yield {"done": True, "chapter": {"n": 1}}

        events = asyncio.run(self._collect(event_stream(_gen())))
        assert events[0]["event"] == "done"
        assert json.loads(events[0]["data"])["done"] is True

    def test_error_dict_event(self):
        async def _gen():
            yield {"error": "大纲生成失败"}

        events = asyncio.run(self._collect(event_stream(_gen())))
        assert events[0]["event"] == "error"
        assert json.loads(events[0]["data"])["error"] == "大纲生成失败"

    def test_llm_stream_error_becomes_error_event(self):
        async def _gen():
            yield "前"
            raise LLMStreamError("模型挂了")

        events = asyncio.run(self._collect(event_stream(_gen())))
        assert events[0]["event"] == "token"
        assert events[1]["event"] == "error"
        assert json.loads(events[1]["data"])["error"] == "模型挂了"
        # 不再有 done
        assert all(e["event"] != "done" for e in events)

    def test_unknown_exception_masked(self):
        """内部生成器抛未知异常 → 转 error 事件且脱敏"""
        async def _gen():
            yield "部分"
            raise RuntimeError("secret internal path /etc/passwd")

        gen = _gen()
        events = asyncio.run(self._collect(event_stream(gen)))
        assert events[0]["event"] == "token"
        assert events[-1]["event"] == "error"
        err = json.loads(events[-1]["data"])["error"]
        assert "/etc/passwd" not in err  # 脱敏
        assert "secret" not in err
        asyncio.run(gen.aclose())  # 显式关闭，避免悬挂生成器告警

    def test_disconnect_cleanup(self):
        """客户端断开时生成器会被 aclose，finally 清理执行"""
        closed = []

        async def _gen():
            try:
                yield "a"
                await asyncio.sleep(3600)  # 模拟长连接
            finally:
                closed.append(True)

        gen = _gen()

        async def _collect_one():
            async for item in event_stream(gen):
                return item  # 只取第一个 token 就返回（模拟断开）

        ev = asyncio.run(_collect_one())
        assert ev["event"] == "token"
        # 显式关闭生成器（等价于客户端断开），触发 finally 清理
        asyncio.run(gen.aclose())
        assert closed == [True]
