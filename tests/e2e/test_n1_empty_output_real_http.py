"""N1 E2E（真实 HTTP + 真实鉴权）：空产出走 error 事件、且请求体确实关闭思考。

评审 P1-5 指出原来的 TestClient 用例不达 §9.3 的 E2E 标准，本文件补齐：

    真实 socket(uvicorn) ←httpx→ FastAPI 中间件(校验 X-API-Key) → 路由 → Router
      → 真实 OpenAIClient → **本地假上游**(OpenAI 兼容 HTTP server)

因此覆盖了：鉴权头、真实 HTTP 传输、SSE 解析、以及"线上真正发出去的请求体"。
假上游只做协议层（不调真模型、不花钱、不依赖网络）。共享实现见
`tests/e2e/fake_upstream.py`（N2 起抽出，N1/N2 共用同一套工具）。
"""

from __future__ import annotations

import json

import httpx
import pytest

from tests.e2e.fake_upstream import FakeUpstream, parse_sse_events, real_http_stack, write_config

pytestmark = pytest.mark.e2e

API_KEY = "e2e-test-key"


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    """真实 uvicorn(真实 socket) + 假上游 + 临时配置（含 security.api_key）"""
    upstream = FakeUpstream()
    cfg_path = write_config(tmp_path_factory.mktemp("e2e"), upstream.base_url, API_KEY)

    with real_http_stack(cfg_path) as base:
        yield base, upstream

    upstream.close()


def test_requires_api_key_over_real_http(stack):
    """真实 HTTP + 鉴权：无 X-API-Key 必须 401（否则这套 E2E 没有测到鉴权链路）"""
    base, _upstream = stack

    resp = httpx.post(f"{base}/api/generate/chapter", params={"chapter_number": 1}, timeout=30)

    assert resp.status_code == 401


def test_empty_stream_returns_error_event_and_no_done(stack):
    """空产出：真实 HTTP 下必须 event: error（含原因）且没有 event: done"""
    base, upstream = stack
    upstream.set_mode("empty")
    upstream.clear()

    resp = httpx.post(
        f"{base}/api/generate/chapter",
        params={"chapter_number": 1},
        headers={"X-API-Key": API_KEY},
        timeout=60,
    )

    assert resp.status_code == 200
    body = resp.text
    assert "event: error" in body, body[:800]
    assert "event: done" not in body, body[:800]

    # 事件体是 JSON（中文转义为 \uXXXX），解析后再断言
    payloads = [p for _ev, p in parse_sse_events(body)]
    errors = " ".join(str(p.get("error", "")) for p in payloads)
    assert "空产出" in errors, payloads

    # 线上真正发出去的请求体：必须关闭思考（否则 reasoning 会吃掉 max_tokens）
    stream_calls = upstream.stream_requests()
    assert stream_calls, "假上游没有收到流式请求"
    assert stream_calls[-1]["body"]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in stream_calls[-1]["body"]
    # P1-4：空产出确实在真实链路上重试了 1 次（上游收到 2 次流式请求）
    assert len(stream_calls) == 2, [r["body"].get("stream") for r in upstream.requests]


def test_success_stream_returns_tokens_and_done(stack):
    """对照：有 token 时正常下发并补 done（证明上面的 error 不是"永远失败"）"""
    base, upstream = stack
    upstream.set_mode("ok")

    resp = httpx.post(
        f"{base}/api/generate/chapter",
        params={"chapter_number": 1},
        headers={"X-API-Key": API_KEY},
        timeout=60,
    )

    body = resp.text
    assert "event: error" not in body, body[:800]
    assert "擂台" in body and "之上" in body
    assert "event: done" in body

    # N2 契约初查（细节断言在 test_n2_sse_done_real_http.py）：有正文时正文必须落进 done 载荷
    dones = [p for ev, p in parse_sse_events(body) if ev == "done"]
    assert len(dones) == 1, dones
    assert dones[0].get("chapter", {}).get("content", "").strip() == "擂台之上", json.dumps(
        dones, ensure_ascii=False
    )
