"""SSE (Server-Sent Events) 工具 — 流式输出支持

统一事件协议（L8.1 + N2 契约）：
  - 内部生成器只 yield 纯文本 token 或结构化对象（dict）
  - 外层 `event_stream` 统一包装为 SSE 事件，杜绝双重 JSON 编码
  - 错误统一转 `event: error`，不再把 `[Error: ...]` 混入正文

事件类型：
  - `event: token`  data: {"token": <str|dict>}
  - `event: done`   data: {"done": true, <载荷字段…>}
  - `event: error`  data: {"error": <msg>}

**单一 done 契约（N2）** —— 这是前端 `readSSE` 能拿到结果的前提：

  R1 一条流**最多一个** `done`。生成器自己 yield 了 done（如章节生成携带
     `chapter`），包装层就**不再补发**；生成器没 yield，包装层补一个
     `{"done": true}`。
  R2 生成器 yield 的 done **载荷字段原样保留**（`chapter`、`injection_manifest` 等），
     包装层只负责转发，不裁剪。
  R3 `done` 之后不再下发任何事件（重复 done / token / error 一律丢弃并告警）。
     理由：前端读到第一个 done 就收尾，之后的事件没有任何接收方，只会掩盖
     后端生成器的顺序 bug（历史上 `_stream_chapter` 因此拿到两个 done）。
  R4 出现 `error` 的流**不再有** `done`，也不再下发后续 token（错误不是成功，
     前端据此回滚空章节）。顺序无关：done→error 与 error→done 都只留先到的那个。

为什么载荷必须寄在 done 上而不是单独一个 token 事件：前端 `readSSE` 在 done
处 return，token 事件之后的内容不可达；且 done 是唯一"结果已完整"的信号点。
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Dict

from story_engine.llm.base import LLMStreamError

logger = logging.getLogger("story_engine.api")


def format_sse(data: Any, event: str = "message") -> str:
    """格式化 SSE 消息"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def done_payload(**fields: Any) -> Dict[str, Any]:
    """构造 done 事件载荷：`{"done": true, **fields}`（R2 的写入侧入口）。

    路由层用它统一写 done，避免手写 `{"done": True, ...}` 时漏字段或写错键名。
    """
    return {"done": True, **fields}


def error_payload(message: str) -> Dict[str, Any]:
    """构造 error 事件载荷（便于路由层与测试共用同一形状）。"""
    return {"error": message}


async def event_stream(
    generator: AsyncGenerator[Any, None],
) -> AsyncGenerator[Dict[str, str], None]:
    """将内部生成器包装为 SSE 事件流（协议见模块 docstring 的 R1–R4）。

    内部生成器可 yield：
      - str            → token 事件（纯文本）
      - dict 含 done   → done 事件（载荷原样转发，且此后不再有事件）
      - dict 含 error  → error 事件（此后不再有 done，也不再有 token）
      - 其他 dict/对象 → token 事件（序列化后）
    抛出 LLMStreamError 或其它异常 → error 事件（done 未发出时）。

    实现要点：用**一个** `finished` 标志同时覆盖"已 done"和"已 error"两种收尾
    （评审 P1-1/P2-1：此前只在 done 分支判断，导致 error→done、error→token
    这两种顺序能漏出去，与 docstring 宣称的 R3/R4 不符）。
    """
    done_sent = False
    error_sent = False
    finished = False
    try:
        async for item in generator:
            if finished:
                # R3/R4：任何收尾信号之后的事件都是生成器的顺序 bug，丢弃并留痕。
                # 只记类型/长度，不记内容 —— 否则 done 后混入的整段正文会被写进日志（P2-7）。
                logger.warning(
                    "SSE 协议违规：%s 之后仍产出事件，已丢弃 | type=%s len=%s",
                    "done" if done_sent else "error",
                    type(item).__name__,
                    len(item) if hasattr(item, "__len__") else "-",
                )
                continue
            if isinstance(item, dict):
                if "error" in item:
                    # 先判 error：error→done 顺序下 done 必须被丢弃（R4）
                    error_sent = True
                    finished = True
                    yield {"event": "error", "data": json.dumps(item, ensure_ascii=False)}
                elif "done" in item:
                    done_sent = True
                    finished = True
                    yield {"event": "done", "data": json.dumps(item, ensure_ascii=False)}
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
        # R1：生成器没给 done 才补（给了就转发过了，不再补第二个）
        if not done_sent and not error_sent:
            yield {"event": "done", "data": json.dumps({"done": True})}
    except LLMStreamError as e:
        if done_sent:
            # R3：流已收尾，迟到的错误只留痕，不改写已发出的结果
            logger.warning("SSE 生成异常（done 之后）：%s", e.message)
        else:
            yield {"event": "error", "data": json.dumps({"error": e.message})}
    except Exception:
        # 统一脱敏：不把底层异常细节直接回显给前端
        logger.exception("SSE 生成异常")
        if not done_sent:
            yield {"event": "error", "data": json.dumps({"error": "生成失败，请稍后重试"})}


def format_sse_done() -> str:
    """（deprecated）旧的 done 拼装：**不带载荷**，仅保留兼容既有单测。

    新代码请用 `done_payload(...)` 经 `event_stream` 下发（N2 契约要求 done 承载结果字段）。
    """
    return format_sse({"done": True}, event="done")


def format_sse_error(msg: str) -> str:
    """（deprecated）旧的 error 拼装：新代码请用 `error_payload(msg)`。"""
    return format_sse({"error": msg}, event="error")
