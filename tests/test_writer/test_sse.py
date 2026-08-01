"""测试：SSE 工具"""
import pytest

from story_engine.api.sse import format_sse, format_sse_done, format_sse_error


class TestSSE:
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
