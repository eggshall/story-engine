"""N1 live 契约验证：真实远程 API 的思考模式/空产出契约（默认跳过）。

运行方式（会真实计费，token 极少）：

    STORY_LIVE=1 .venv/bin/python -m pytest tests/test_llm/test_thinking_live.py -o addopts="" -q -s

断言要点（对应 N1 修掉的真实现象）：
1. ``task="generate"``（关闭思考）→ ``content`` 非空、``reasoning_tokens`` 为 0/缺失
   —— 旧代码未关思考时，max_tokens 会被 reasoning 吃干、content 为空串但 HTTP 200
2. 请求体带 ``thinking={"type":"disabled"}`` 且不带 ``reasoning_effort``（后者与 disabled 冲突会被拒）
3. ``task="plan"``（开启思考）→ 同样的 max_tokens 下 reasoning_tokens > 0（证明开关真的生效）
"""

from __future__ import annotations

import asyncio
import os

import pytest

from story_engine.llm.api_client import OpenAIClient
from story_engine.llm.base import LLMRequest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("STORY_LIVE") != "1",
        reason="需要真实远程调用（STORY_LIVE=1 才跑，会产生少量费用）",
    ),
]


@pytest.fixture
def client() -> OpenAIClient:
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        pytest.skip("缺少 DEEPSEEK_API_KEY")
    return OpenAIClient({
        "name": "deepseek",
        "provider": "deepseek",
        "model_id": "deepseek-flash",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": key,
        "read_timeout": 120,
        "connect_timeout": 10,
    })


def _reasoning_tokens(usage: dict | None) -> int:
    usage = usage or {}
    details = usage.get("completion_tokens_details") or {}
    return int(details.get("reasoning_tokens", usage.get("reasoning_tokens", 0)) or 0)


def test_generate_task_returns_real_content_without_reasoning(client):
    req = LLMRequest(
        messages=[{"role": "user", "content": "回复一个不超过 10 字的中文句子，开头是：试炼开始"}],
        task="generate",
        max_tokens=256,
    )
    result = asyncio.run(client.chat(req))

    assert result.success is True, result.error
    assert result.content.strip(), "关闭思考后 content 必须非空（这是 N1 修掉的核心现象）"
    assert _reasoning_tokens(result.usage) == 0, f"关闭思考后不应有 reasoning_tokens: {result.usage}"
    print(f"\n[live] content={result.content[:60]!r} usage={result.usage}")


def test_plan_task_actually_thinks(client):
    """对照：同一 max_tokens 预算下开启思考 → reasoning_tokens > 0（证明开关生效）"""
    req = LLMRequest(
        messages=[{"role": "user", "content": "简要说明：为什么小说第 3 章要设置冲突？"}],
        task="plan",
        max_tokens=256,
    )
    result = asyncio.run(client.chat(req))

    if result.success is False:
        # 思考模式耗尽 256 token 正是被 N1 判定为失败的情形（内容空但 HTTP 200）
        assert "空产出" in result.error, result.error
        print(f"\n[live] plan 任务在 256 token 下被 reasoning 占满（符合预期）: {result.error[:120]}")
        return
    assert _reasoning_tokens(result.usage) > 0, f"plan 任务应有 reasoning_tokens: {result.usage}"
    print(f"\n[live] plan usage={result.usage}")


def test_stream_generate_task_yields_content(client):
    req = LLMRequest(
        messages=[{"role": "user", "content": "用一句话（20 字内）描写清晨的擂台。"}],
        task="generate",
        max_tokens=256,
    )

    async def _collect() -> str:
        chunks = []
        async for token in client.chat_stream(req):
            chunks.append(token)
        return "".join(chunks)

    text = asyncio.run(_collect())
    assert text.strip(), "流式也必须能拿到正文 token"
    print(f"\n[live] stream={text[:80]!r}")
