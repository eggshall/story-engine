"""N1 E2E：空产出必须走 `event: error`，不能静默变成 `done` + 空正文。

覆盖链路（真实 HTTP → FastAPI → 路由 → SSE 层）：
    POST /api/generate/chapter
      → _stream_chapter 先生成大纲（假 router.chat 返回合法 JSON 大纲）
      → router.chat_stream 抛 LLMStreamError（模拟"思考模式吃掉 max_tokens、零 token"）
      → api/sse.py event_stream 必须转成 error 事件，且**不得**再补 done

这个用例是"静默空正文"这个真实故障的回归防线：旧行为下前端会收到 done + 空正文，
并把它当成一次成功的生成。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.llm.base import LLMRequest, LLMResponse, LLMStreamError

client = TestClient(app)

FAKE_OUTLINE = {
    "chapter_number": 1,
    "title": "试炼",
    "summary": "主角进入试炼场",
    "beats": ["入场", "冲突", "转折"],
    "key_scenes": ["擂台"],
    "word_estimate": 1200,
}


@pytest.fixture(autouse=True)
def setup_test_env(test_config, reset_router):
    """用临时最小配置（无 security.api_key）→ 否则鉴权中间件会 401。

    与 tests/test_writer/test_api.py 一致（统一 conftest fixture）。
    """
    yield


@pytest.fixture
def router_empty_stream(monkeypatch):
    """假 router：大纲调用正常返回，正文流式返回"零 token"（抛 LLMStreamError）"""
    router = MagicMock()
    seen: dict = {}

    async def _chat(request: LLMRequest, model_name: str | None = None) -> LLMResponse:
        seen.setdefault("tasks", []).append(request.task)
        return LLMResponse(
            content=f"```json\n{json.dumps(FAKE_OUTLINE, ensure_ascii=False)}\n```",
            model="fake",
            provider="fake",
        )

    async def _chat_stream(request: LLMRequest, model_name: str | None = None):
        seen["stream_task"] = request.task
        raise LLMStreamError("模型返回空产出（流式零 token）")
        yield ""  # pragma: no cover  —— 使其成为异步生成器

    router.chat = _chat
    router.chat_stream = _chat_stream
    monkeypatch.setattr("story_engine.api.routes.generate._router", router)
    return router, seen


def test_chapter_stream_empty_output_emits_error_not_done(router_empty_stream):
    _router, seen = router_empty_stream

    resp = client.post(
        "/api/generate/chapter",
        params={"chapter_number": 1, "chapter_title": "试炼"},
    )

    assert resp.status_code == 200
    body = resp.text
    assert "event: error" in body, f"空产出必须以 error 事件暴露，实际响应:\n{body[:800]}"
    assert "event: done" not in body, f"空产出时不得再补 done（会被前端当成功）:\n{body[:800]}"

    # 事件体是 JSON（中文被转义为 \uXXXX），解析后断言内容而不是匹配原始文本
    payloads = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    assert payloads, f"SSE 响应没有 data 行:\n{body[:800]}"
    errors = " ".join(str(p.get("error", "")) for p in payloads)
    assert "空产出" in errors, f"error 事件未携带失败原因: {payloads}"

    # 契约：正文流式请求必须显式关闭思考（task=generate）；大纲 JSON 走 extract
    assert seen.get("stream_task") == "generate"
    assert seen.get("tasks") == ["extract"]


def test_chapter_stream_success_path_still_streams_content(router_empty_stream, monkeypatch):
    """对照：有 token 时正常下发 content，并带 done（证明上面的 error 不是"总是失败"）"""
    router, _seen = router_empty_stream

    async def _ok_stream(request: LLMRequest, model_name: str | None = None):
        yield "第一段"
        yield "第二段"

    router.chat_stream = _ok_stream

    resp = client.post("/api/generate/chapter", params={"chapter_number": 1, "chapter_title": "试炼"})

    body = resp.text
    assert "第一段" in body and "第二段" in body
    assert "event: error" not in body
