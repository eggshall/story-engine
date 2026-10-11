"""N2 契约测试：SSE 事件流必须"有且只有一个 done，且载荷原样承载"。

为什么要有这组测试（对应 P0-3）：

- 现状 `sse.py::event_stream` 在生成器自然结束后**无条件补发**一个
  `{"done": true}`；而 `generate.py::_stream_chapter` 自己已经 yield 了
  `{"done": True, "chapter": {...}}` → 一条流里出现**两个 done**。
- 前端 `readSSE` 读到第一个 `done` 就 return，且 `onDone()` 不带参
  → 载荷（章节记录 / 后续的注入清单）**永久丢失**，前端也看不到。
- 因此"单一 done + 载荷"必须是一等契约，由后端保证、由测试锁死。

契约（N2 起生效）：

  R1 一条 SSE 流最多一个 `done`；生成器不 yield done 时由包装层补一个。
  R2 生成器 yield 的 done **载荷字段原样保留**（`chapter`、后续的
     `injection_manifest` 等）。
  R3 `done` 之后不再下发任何事件（token/error/done），重复的 done 被去重。
  R4 出现 `error` 事件的流**不得**再有 `done`（错误不是成功）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List

from story_engine.api.sse import event_stream
from story_engine.llm.base import LLMStreamError


def _collect(gen: AsyncGenerator[Dict[str, str], None]) -> List[Dict[str, str]]:
    async def _run() -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        async for item in gen:
            out.append(item)
        return out

    return asyncio.run(_run())


def _names(events: List[Dict[str, str]]) -> List[str]:
    return [e["event"] for e in events]


def _data(events: List[Dict[str, str]], event: str) -> List[Any]:
    return [json.loads(e["data"]) for e in events if e["event"] == event]


class TestSingleDone:
    def test_generator_done_is_not_duplicated(self):
        """R1/R2：生成器自己 yield done（带 chapter 载荷）→ 只出现一次且载荷完整。"""

        async def _gen():
            yield "擂台之上"
            yield {"done": True, "chapter": {"chapter_number": 1, "title": "试炼", "word_count": 4}}

        events = _collect(event_stream(_gen()))

        assert _names(events) == ["token", "done"], _names(events)
        payload = _data(events, "done")[0]
        assert payload["done"] is True
        assert payload["chapter"]["title"] == "试炼"
        assert payload["chapter"]["word_count"] == 4

    def test_plain_generator_still_gets_one_done(self):
        """R1：生成器不 yield done → 包装层补一个（且只有一个）。"""

        async def _gen():
            yield "甲"
            yield "乙"

        events = _collect(event_stream(_gen()))

        assert _names(events) == ["token", "token", "done"], _names(events)
        assert _data(events, "done") == [{"done": True}]

    def test_duplicate_done_is_deduped(self):
        """R1/R3：生成器违规 yield 两次 done → 只下发第一个。"""

        async def _gen():
            yield "文"
            yield {"done": True, "chapter": {"chapter_number": 1}}
            yield {"done": True, "chapter": {"chapter_number": 1}}

        events = _collect(event_stream(_gen()))

        assert _names(events) == ["token", "done"], _names(events)

    def test_no_events_after_done(self):
        """R3：done 之后的 token/error 一律不下发（客户端已经收尾）。"""

        async def _gen():
            yield "正文"
            yield {"done": True, "chapter": {"chapter_number": 1}}
            yield "这条不该出现"
            yield {"error": "也不该出现"}

        events = _collect(event_stream(_gen()))

        assert _names(events) == ["token", "done"], _names(events)
        blob = json.dumps(events, ensure_ascii=False)
        assert "不该出现" not in blob

    def test_done_then_exception_keeps_single_done(self):
        """R3/R4 边界：done 之后底层再抛异常 → 不补第二个 done，也不改发 error。"""

        async def _gen():
            yield {"done": True, "chapter": {"chapter_number": 1}}
            raise LLMStreamError("done 之后才炸")

        events = _collect(event_stream(_gen()))

        assert _names(events) == ["done"], _names(events)


class TestErrorExcludesDone:
    def test_error_has_no_done(self):
        """R4：error 流不得有 done。"""

        async def _gen():
            yield "半截"
            raise LLMStreamError("模型返回空产出（流式零 token）")

        events = _collect(event_stream(_gen()))

        assert _names(events) == ["token", "error"], _names(events)

    def test_error_dict_has_no_done(self):
        """R4：生成器主动 yield error dict（如"大纲生成失败"）→ 无 done。"""

        async def _gen():
            yield {"error": "大纲生成失败"}

        events = _collect(event_stream(_gen()))

        assert _names(events) == ["error"], _names(events)
        assert _data(events, "error")[0]["error"] == "大纲生成失败"

    def test_error_after_done_is_suppressed(self):
        """R3 优先于 R4：done 已发出，后续 error 不下发（前端已按完成处理）。"""

        async def _gen():
            yield {"done": True}
            yield {"error": "迟到的错误"}

        events = _collect(event_stream(_gen()))

        assert _names(events) == ["done"], _names(events)

    def test_error_then_done_is_suppressed(self):
        """R4（评审 P1-1）：error→done 顺序下 done 也必须被丢弃（顺序无关）。"""

        async def _gen():
            yield {"error": "先出错"}
            yield {"done": True, "chapter": {"chapter_number": 1}}

        events = _collect(event_stream(_gen()))

        assert _names(events) == ["error"], _names(events)

    def test_tokens_after_error_are_dropped(self):
        """R4（评审 P2-1）：error 之后不再下发 token（否则前端拿不到的半截正文会漏出去）。"""

        async def _gen():
            yield "前半截"
            yield {"error": "模型返回空产出（流式零 token）"}
            yield "这半截不该出现"

        events = _collect(event_stream(_gen()))

        assert _names(events) == ["token", "error"], _names(events)
        assert "不该出现" not in json.dumps(events, ensure_ascii=False)

    def test_unknown_exception_keeps_masking(self):
        """回归：未知异常仍脱敏成 error，且不出现 done。"""

        async def _gen():
            yield "x"
            raise RuntimeError("secret /etc/passwd")

        gen = _gen()
        events = _collect(event_stream(gen))

        assert _names(events) == ["token", "error"], _names(events)
        err = _data(events, "error")[0]["error"]
        assert "secret" not in err and "/etc/passwd" not in err
        asyncio.run(gen.aclose())
