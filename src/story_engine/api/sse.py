"""SSE (Server-Sent Events) 工具 — 流式输出支持"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Any


def format_sse(data: Any, event: str = "message") -> str:
    """格式化 SSE 消息"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def event_stream(generator: AsyncGenerator[str, None]) -> AsyncGenerator[dict, None]:
    """将异步生成器包装为 SSE 事件流（返回 dict 供 EventSourceResponse 使用）"""
    try:
        async for token in generator:
            yield {"event": "token", "data": json.dumps({"token": token}, ensure_ascii=False)}
        yield {"event": "done", "data": json.dumps({"done": True})}
    except Exception as e:
        yield {"event": "error", "data": json.dumps({"error": str(e)})}


def format_sse_done() -> str:
    return format_sse({"done": True}, event="done")


def format_sse_error(msg: str) -> str:
    return format_sse({"error": msg}, event="error")
