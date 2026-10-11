"""N4b E2E（真实 HTTP）：`POST /api/generate/chapter/v2` 的**注入可见性**闭环。

这是架构里"作者必须能看到这次注入了什么"的硬证据，必须跨层验证（§9.3）：改了 SSE 帧、
prompt 组装与落盘，就不能只跑单测。

链路：真实 socket(uvicorn) ←httpx→ 鉴权中间件 → 路由 → **装配器** → Router
      → OpenAIClient → 本地假上游（记录收到的请求体）

两条断言缺一不可：

1. **拿得到**：SSE 的 done 载荷里带 `context_manifest`（字段齐、来源可溯、预算/裁剪信息在）；
2. **对得上**：假上游**实际收到**的 prompt 里确实包含 manifest 声称注入的内容
   —— 否则 manifest 只是"自述"，不能证明注入真的发生了。
"""

from __future__ import annotations

import httpx
import pytest

from story_engine.core.models import Chapter, Novel
from story_engine.tools.novel_storage import save_novel
from tests.e2e.fake_upstream import FakeUpstream, parse_sse_events, real_http_stack, write_config

pytestmark = pytest.mark.e2e

API_KEY = "e2e-n4b-key"
MAINLINE = "主线：人类第一次走出太阳系，代价是失去地球。"
RECAP_LINE = "第一章：发射失败，主角背下全部责任。"
BEAT = "本章节拍：舱内失重，主角必须在返航与继续之间做选择。"
PREV_TAIL = "上一章结尾：舷窗外的地球缩成一个句号。"


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    upstream = FakeUpstream()
    upstream.set_mode("ok")
    cfg = write_config(tmp_path_factory.mktemp("e2e-n4b"), upstream.base_url, API_KEY)

    with real_http_stack(cfg) as base:
        yield base, upstream

    upstream.close()


@pytest.fixture
def novels_root(tmp_path, monkeypatch):
    """隔离两个全局目录：小说根目录 + 角色卡目录。

    评审 P1-1：路由会无条件加载 `data/characters` 里的全局角色卡，本机有卡 → 断言会
    随"仓库里有没有大卡"漂移。这里把两个目录都指到临时目录，让"有卡/无卡"两种情形都受控。
    """
    root = tmp_path / "novels"
    root.mkdir()
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", root)
    monkeypatch.setattr("story_engine.characters.manager.CHARACTERS_DIR", tmp_path / "characters")
    return root


def _make_novel(root, novel_id: str, *, with_materials: bool) -> None:
    d = root / novel_id
    d.mkdir(parents=True, exist_ok=True)
    novel = Novel(title="人类大进步")
    novel.chapters = [
        Chapter(chapter_number=1, title="第一次发射", content=PREV_TAIL, word_count=len(PREV_TAIL))
    ]
    save_novel(novel, novel_id)

    if with_materials:
        (d / "beats").mkdir(exist_ok=True)
        (d / "mainline.md").write_text(MAINLINE, encoding="utf-8")
        (d / "recap.md").write_text(RECAP_LINE, encoding="utf-8")
        (d / "beats" / "ch_0002.md").write_text(BEAT, encoding="utf-8")


def _call_v2(base: str, novel_id: str, chapter_number: int = 2) -> tuple[str, list]:
    # 评审 P2-4：手写文本走请求体（不走 query string，避免撞 URL 长度上限）
    resp = httpx.post(
        f"{base}/api/generate/chapter/v2",
        json={"novel_id": novel_id, "chapter_number": chapter_number, "chapter_title": "试炼"},
        headers={"X-API-Key": API_KEY},
        timeout=60,
    )
    assert resp.status_code == 200, resp.status_code
    events = parse_sse_events(resp.text)
    return resp.text, events


def test_manifest_is_delivered_and_matches_injected_prompt(stack, novels_root):
    """有手写件时：done 载荷带 manifest，且上游收到的 prompt 与 manifest 一致。"""
    base, upstream = stack
    _make_novel(novels_root, "n4b-full", with_materials=True)
    upstream.clear()

    body, events = _call_v2(base, "n4b-full")

    names = [ev for ev, _p in events]
    assert names.count("done") == 1, names                  # N2 契约在 v2 上同样成立
    assert names[-1] == "done", names
    assert "error" not in names, body[:400]

    payload = [p for ev, p in events if ev == "done"][0]
    manifest = payload["context_manifest"]
    sources = [e["source"] for e in manifest["entries"]]

    # 1) 手写件确实进了注入清单
    assert "mainline" in sources
    assert "beat:ch_0002" in sources
    assert "recap:1" in sources
    assert "chapter_tail:ch_0001" in sources
    # 2) 预算与口径信息可核
    assert manifest["budget_tokens"] == 40000
    assert manifest["token_estimate"] is True
    assert manifest["total_tokens"] > 0
    assert manifest["over_budget"] is False
    assert manifest["dropped"] == []
    # 没有风格块（未传 profile_id）、角色卡目录已隔离为空 → 两者都必须显式列在 skipped
    skipped_slots = {s["slot_id"] for s in manifest["skipped"]}
    assert {"style", "characters"} <= skipped_slots
    # 「不静默消失」的通用不变量：标准槽位必须**要么注入、要么被裁、要么记 skipped**
    standard = {"mainline", "style", "beat", "recap", "chapter_tail", "characters"}
    visible = (
        {e["slot_id"] for e in manifest["entries"]}
        | skipped_slots
        | {d["slot_id"] for d in manifest["dropped"]}
    )
    assert standard <= visible, standard - visible

    # 3) 上游**实际收到**的 prompt 里必须有 manifest 声称注入的内容（同一条证据链的另一半）
    stream_calls = upstream.stream_requests()
    assert len(stream_calls) == 1, len(stream_calls)
    # 注意：OpenAIClient 会把 system_prompt 作为 messages[0] 一起发，这里合并全部消息看
    prompt = "\n".join(
        str(m.get("content", "")) for m in stream_calls[0]["body"]["messages"]
    )
    for chunk in (MAINLINE, BEAT, RECAP_LINE, PREV_TAIL):
        assert chunk in prompt, f"prompt 里缺少注入内容：{chunk!r}"

    # 4) manifest 自述的字符数与真实 prompt 内的注入量一致（允许装配器加的分隔符）
    injected_chars = sum(e["chars"] for e in manifest["entries"])
    assert injected_chars <= len(prompt)
    assert injected_chars >= len(MAINLINE) + len(BEAT) + len(RECAP_LINE) + len(PREV_TAIL)

    # 5) 章节按 v2 的标题落盘
    chapter = payload["chapter"]
    assert chapter["chapter_number"] == 2
    assert chapter["title"] == "试炼"
    assert chapter["content"].strip() == "擂台之上"      # 假上游固定产出
    assert chapter["word_count"] == 4


def test_manifest_reports_missing_materials_without_failing(stack, novels_root):
    """还没有手写件时（作者刚建书就是这个状态）：不能报错，且必须明说缺了什么。"""
    base, upstream = stack
    _make_novel(novels_root, "n4b-empty", with_materials=False)
    upstream.clear()

    body, events = _call_v2(base, "n4b-empty")

    payload = [p for ev, p in events if ev == "done"][0]
    manifest = payload["context_manifest"]
    skipped = {s["slot_id"]: s["reason"] for s in manifest["skipped"]}

    # 没写主线/节拍/前情 → skipped 里点名，作者一眼看到"该补什么"
    assert set(skipped) >= {"mainline", "beat", "recap"}
    assert all(reason == "empty" for reason in skipped.values()), skipped
    # 上一章结尾仍然注入了（第一章有内容）→ 说明它不依赖手写件
    assert "chapter_tail:ch_0001" in [e["source"] for e in manifest["entries"]]
    # 缺料不是错误：流正常收尾
    assert [ev for ev, _p in events][-1] == "done"


def test_v2_requires_api_key(stack, novels_root):
    """鉴权不能被 v2 绕开。"""
    base, _upstream = stack
    _make_novel(novels_root, "n4b-auth", with_materials=True)

    resp = httpx.post(
        f"{base}/api/generate/chapter/v2",
        params={"novel_id": "n4b-auth", "chapter_number": 2},
        timeout=30,
    )

    assert resp.status_code == 401


def test_v2_unknown_novel_returns_message(stack, novels_root):
    """未知小说 → 明确报错（不是空流，也不是 HTML 错误页）。"""
    base, _upstream = stack

    resp = httpx.post(
        f"{base}/api/generate/chapter/v2",
        json={"novel_id": "definitely-missing", "chapter_number": 1},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )

    # 评审 P2-7：断言收紧为"必须是 JSON 且 success=false 且给出原因"，避免被 HTML/空体蒙混
    assert resp.status_code == 200, resp.status_code
    assert "application/json" in resp.headers.get("content-type", "")
    payload = resp.json()
    assert payload.get("success") is False
    assert "不存在" in (payload.get("message") or "")
    assert "event:" not in resp.text
