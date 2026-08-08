"""SSE (Server-Sent Events) 工具 — 流式输出支持

统一事件协议（L8.1）：
  - 内部生成器只 yield 纯文本 token 或结构化对象（dict）
  - 外层 `event_stream` 统一包装为 SSE 事件，杜绝双重 JSON 编码
  - 错误统一转 `event: error`，不再把 `[Error: ...]` 混入正文

事件类型：
  - `event: token`  data: {"token": <str|dict>}
  - `event: done`   data: {"done": true}
  - `event: error`  data: {"error": <msg>}
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict

from story_engine.llm.base import LLMStreamError


def format_sse(data: Any, event: str = "message") -> str:
    """格式化 SSE 消息"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def event_stream(
    generator: AsyncGenerator[Any, None],
) -> AsyncGenerator[Dict[str, str], None]:
    """将内部生成器包装为 SSE 事件流。

    内部生成器可 yield：
      - str            → token 事件（纯文本）
      - dict 含 done   → done 事件
      - dict 含 error  → error 事件
      - 其他 dict/对象 → token 事件（序列化后）
    抛出 LLMStreamError 或其它异常 → error 事件。
    """
    try:
        async for item in generator:
            if isinstance(item, dict):
                if "done" in item:
                    yield {"event": "done", "data": json.dumps(item, ensure_ascii=False)}
                elif "error" in item:
                    yield {"event": "error", "data": json.dumps(item, ensure_ascii=False)}
                else:
                    yield {
                        "event": "token",
                        "data": json.dumps({"token": item}, ensure_ascii=False),
                    }
            else:
                yield {
                    "event": "token",
                    "data": json.dumps({"token": str(item)}, ensure_ascii=False),
                }
        yield {"event": "done", "data": json.dumps({"done": True})}
    except LLMStreamError as e:
        yield {"event": "error", "data": json.dumps({"error": e.message})}
    except Exception:
        # 统一脱敏：不把底层异常细节直接回显给前端
        logger = __import__("logging").getLogger("story_engine.api")
        logger.exception("SSE 生成异常")
        yield {"event": "error", "data": json.dumps({"error": "生成失败，请稍后重试"})}


def format_sse_done() -> str:
    return format_sse({"done": True}, event="done")


def format_sse_error(msg: str) -> str:
    return format_sse({"error": msg}, event="error")
