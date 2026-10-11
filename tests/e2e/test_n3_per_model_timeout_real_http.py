"""N3 E2E（真实 HTTP）：模型级 `read_timeout` 真的落到了 HTTP 层。

背景：`config.yaml` 里本地模型写的是 `read_timeout: 300`，但 N3 之前这个字段被
`_LLMModelConfig` 白名单**静默剥离**，运行时一律用全局 `llm.read_timeout`（120s）：

- 本地模型长文生成会在 120s 被掐断（且没有任何"配置没生效"的提示）；
- 反过来，把 300 写小了也不生效。

这属于跨层行为（config → Router → OpenAIClient → httpx 超时），所以按要求用**真实
HTTP** 验证，而不是只断言字典里有这个键：让本地假上游故意慢（延迟 3s），
再把模型的 read_timeout 设成 1s / 10s，看真实链路是"快速失败"还是"等够再成功"。

若内核用的是全局 120s，第一个用例不可能在 6s 内结束（会一直等到上游响应）。
"""

from __future__ import annotations

import time
from contextlib import contextmanager

import httpx
import pytest

from tests.e2e.fake_upstream import FakeUpstream, real_http_stack, write_config

pytestmark = pytest.mark.e2e

API_KEY = "e2e-n3-key"
UPSTREAM_DELAY = 3.0


@pytest.fixture(scope="module")
def upstream():
    up = FakeUpstream()
    up.set_mode("ok")
    up.set_delay(UPSTREAM_DELAY)
    yield up
    up.close()


@contextmanager
def _stack_with_timeout(tmp_path, upstream: FakeUpstream, read_timeout: float):
    """起一个只有单个模型的真实栈；模型带指定 read_timeout（无 fallback 目标，隔离变量）。"""
    cfg = write_config(
        tmp_path,
        upstream.base_url,
        API_KEY,
        models=[{"name": "m", "read_timeout": read_timeout}],
    )
    with real_http_stack(cfg) as base:
        yield base


def _call_outline(base: str) -> tuple[str, float]:
    start = time.monotonic()
    resp = httpx.post(
        f"{base}/api/generate/outline",
        params={"chapter_number": 1},
        headers={"X-API-Key": API_KEY},
        timeout=60,
    )
    elapsed = time.monotonic() - start
    assert resp.status_code == 200, resp.status_code
    return resp.text, elapsed


def test_per_model_read_timeout_is_applied(tmp_path, upstream):
    """read_timeout=1s + 上游慢 3s → 必须快速失败（而不是等全局 120s 或等上游成功）。"""
    with _stack_with_timeout(tmp_path, upstream, 1) as base:
        body, elapsed = _call_outline(base)

    assert "event: error" in body, body[:400]
    assert "event: done" not in body, body[:400]
    # 关键断言：耗时接近"模型级 1s（含最多 1 次重试）" —— 评审 P2-7 建议收紧到 2s
    assert elapsed < 2.0, f"耗时 {elapsed:.2f}s，说明用的不是模型级的 1s 超时"


def test_larger_per_model_read_timeout_waits_and_succeeds(tmp_path, upstream):
    """对照：read_timeout=10s → 等得上游的 3s，正常拿到 done（证明上面不是"永远失败"）。"""
    with _stack_with_timeout(tmp_path, upstream, 10) as base:
        body, elapsed = _call_outline(base)

    assert "event: done" in body, body[:400]
    assert "outline" in body
    # 确实等过了上游延迟（排除了"没真的发请求/被缓存"的可能）
    assert elapsed >= UPSTREAM_DELAY * 0.8, f"耗时只有 {elapsed:.2f}s，不像等过上游"
    assert elapsed < 30


@contextmanager
def _stack_with_model_task(tmp_path, upstream: FakeUpstream, task: str):
    """单模型栈：模型**自带** `task`（用来验证"配置的默认 task 不会污染正文端点"）。"""
    cfg = write_config(
        tmp_path,
        upstream.base_url,
        API_KEY,
        models=[{"name": "m", "task": task}],
    )
    with real_http_stack(cfg) as base:
        yield base


def test_prose_endpoints_force_thinking_off_even_if_model_task_is_plan(tmp_path, upstream):
    """评审 P1-1 的硬断言：模型配置 `task: plan` 时，**正文类端点仍必须关思考**。

    这些端点（对话/章节/去 AI 味/带文风写作）在 N3 之前没显式传 task，会继承模型配置的
    `task: plan` → 开启思考且不发 temperature（reasoning 吃满 max_tokens → 静默空产出）。
    这里在真实 HTTP 链路上断言"上游实际收到的请求体"，而不是只看单测里的 payload。
    """
    upstream.set_delay(0)
    with _stack_with_model_task(tmp_path, upstream, "plan") as base:
        upstream.clear()
        headers = {"X-API-Key": API_KEY}

        # 1) 自由对话（流式）
        httpx.post(
            f"{base}/api/generate/chat",
            headers=headers,
            json={"messages": [{"role": "user", "content": "写一句开场"}], "stream": True},
            timeout=30,
        )
        # 2) 章节生成（流式；内部先走一次非流式大纲）
        httpx.post(
            f"{base}/api/generate/chapter",
            params={"chapter_number": 1},
            headers=headers,
            timeout=60,
        )
        # 3) 去 AI 味（流式）
        httpx.post(
            f"{base}/api/generate/depolish",
            params={"text": "他感到非常非常的高兴。"},
            headers=headers,
            timeout=30,
        )
        # 4) 带文风写作（流式）
        httpx.post(
            f"{base}/api/style/generate",
            headers=headers,
            json={"chapter_number": 1, "style_prompt": "冷峻克制", "stream": True},
            timeout=30,
        )

        stream_calls = upstream.stream_requests()

    assert len(stream_calls) >= 4, f"应有 4 个正文类流式请求，实际 {len(stream_calls)}"
    for call in stream_calls:
        payload = call["body"]
        assert payload["thinking"] == {"type": "disabled"}, payload.get("thinking")
        # 关思考后 temperature 才有效 → 必须发出去（否则等于默认值静默生效）
        assert "temperature" in payload, payload.keys()
        assert "reasoning_effort" not in payload

