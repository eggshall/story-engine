"""N2 E2E（真实 HTTP）：SSE **单一 done + done 载荷** 契约。

对应 P0-3 的验收：改了跨进程行为（SSE 帧）就必须用真 HTTP 验证，
而不是只看 `sse.py` 的单元测试。

链路：真实 socket(uvicorn) ←httpx→ 鉴权中间件 → 路由 → Router → OpenAIClient
      → 本地假上游（`tests/e2e/fake_upstream.py`）

断言的是"前端能拿到什么"：done 的**数量**与 done 的**载荷字段**。
"""

from __future__ import annotations

import json

import httpx
import pytest

from tests.e2e.fake_upstream import FakeUpstream, parse_sse_events, real_http_stack, write_config

pytestmark = pytest.mark.e2e

API_KEY = "e2e-n2-key"


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    upstream = FakeUpstream()
    upstream.set_mode("ok")
    cfg_path = write_config(tmp_path_factory.mktemp("e2e-n2"), upstream.base_url, API_KEY)

    with real_http_stack(cfg_path) as base:
        yield base, upstream

    upstream.close()


def _headers() -> dict:
    return {"X-API-Key": API_KEY}


def _events_of(body: str, event: str) -> list:
    return [p for ev, p in parse_sse_events(body) if ev == event]


def test_chapter_stream_has_exactly_one_done_with_chapter_payload(stack):
    """章节生成：全流**只有一个** done，且载荷里有完整章节记录。"""
    base, upstream = stack
    upstream.set_mode("ok")

    resp = httpx.post(
        f"{base}/api/generate/chapter",
        params={"chapter_number": 1},
        headers=_headers(),
        timeout=60,
    )
    assert resp.status_code == 200

    events = parse_sse_events(resp.text)
    names = [ev for ev, _p in events]

    # 1) 单一 done（历史 bug：生成器自己 yield done + 包装层补 done = 两个）
    assert names.count("done") == 1, names
    # 2) done 必须是最后一个事件（其后不得再有 token/error/done）
    assert names[-1] == "done", names
    # 3) 正文仍然逐 token 下发
    tokens = [p["token"] for p in _events_of(resp.text, "token")]
    assert "".join(tokens) == "擂台之上", tokens

    # 4) 载荷字段：前端靠它拿到标题/字数（以及后续的注入清单）
    payload = _events_of(resp.text, "done")[0]
    assert payload["done"] is True
    chapter = payload["chapter"]
    assert chapter["chapter_number"] == 1
    assert chapter["title"] == "试炼"
    assert chapter["content"].strip() == "擂台之上"
    assert chapter["word_count"] == 4

    # 5) done 载荷必须是合法 JSON 对象（前端 JSON.parse 后直接读字段）
    assert isinstance(json.loads(json.dumps(chapter)), dict)


def test_outline_stream_payload_rides_on_done(stack):
    """大纲：结果走 done 载荷（不再是"藏在 token 里的结构体"），且仍是单一 done。"""
    base, _upstream = stack

    resp = httpx.post(
        f"{base}/api/generate/outline",
        params={"chapter_number": 1},
        headers=_headers(),
        timeout=60,
    )
    assert resp.status_code == 200

    events = parse_sse_events(resp.text)
    names = [ev for ev, _p in events]
    assert names.count("done") == 1, names

    payload = _events_of(resp.text, "done")[0]
    outline = payload["outline"]
    assert outline["title"] == "试炼"
    assert outline["chapter_number"] == 1
    # 旧形状（结构体当 token 发）不得回归：token 事件里不该再出现流水线结构
    for tok in _events_of(resp.text, "token"):
        assert "outline" not in tok, tok


def test_chat_stream_has_exactly_one_done(stack):
    """自由对话：同样只有一次 done（空载荷），错误路径不在此列。"""
    base, upstream = stack
    upstream.set_mode("ok")

    resp = httpx.post(
        f"{base}/api/generate/chat",
        headers=_headers(),
        json={
            "messages": [{"role": "user", "content": "写一句开场"}],
            "stream": True,
        },
        timeout=60,
    )
    assert resp.status_code == 200

    events = parse_sse_events(resp.text)
    names = [ev for ev, _p in events]
    assert names.count("done") == 1, names
    assert names[-1] == "done", names
    assert "error" not in names, names


def test_done_count_is_at_most_one_across_streams(stack):
    """回归兜底：跨流式接口统一断言"done 至多一次"（防止新接口又补第二个）。"""
    base, _upstream = stack

    first = httpx.post(
        f"{base}/api/generate/chapter",
        params={"chapter_number": 2},
        headers=_headers(),
        timeout=60,
    )
    second = httpx.post(
        f"{base}/api/generate/outline",
        params={"chapter_number": 2},
        headers=_headers(),
        timeout=60,
    )

    for path, resp in (("/api/generate/chapter", first), ("/api/generate/outline", second)):
        names = [ev for ev, _p in parse_sse_events(resp.text)]
        # 评审 P2-2：兜底用例也要断言"恰好 1 个"（<=1 会把"一个 done 都没发"放过去）
        assert names.count("done") == 1, (path, names)
