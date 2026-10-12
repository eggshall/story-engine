"""N9 E2E（真实 HTTP）：伏笔账本跨层闭环。

按 §9.3：改了**文件落盘**与**HTTP 接口**就必须有真 HTTP E2E（`TestClient` 只算单测）。
本文件用真 socket(uvicorn) + 鉴权中间件 + 假上游，覆盖三件事：

1. 账本经接口落盘到 `<小说目录>/`，并**活过**一次真实生成（v2 保存章节会重建镜像目录 —— 这是坑）；
2. 未回收伏笔**真的进了 prompt**（不只看 manifest 自述，还要看假上游收到的请求体）；
3. 悬空伏笔 / 回收章不存在能被校验接口报出，而**没有账本的书报告形状不变**。
"""

from __future__ import annotations

import json

import httpx
import pytest

from story_engine.core.models import Chapter, Novel
from story_engine.tools.novel_storage import save_novel
from tests.e2e.fake_upstream import FakeUpstream, parse_sse_events, real_http_stack, write_config

pytestmark = pytest.mark.e2e

API_KEY = "e2e-n9-key"
THREAD_TITLE = "怀表的来历"
THREAD_NOTE = "第 30 章揭晓"

CLEAN_TEXT = "\n\n".join(
    [
        "我推开门，我听见风。突然，灯灭了。",
        "我站住，我没敢回头。",
    ]
)


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    upstream = FakeUpstream()
    upstream.set_mode("ok")
    cfg = write_config(tmp_path_factory.mktemp("e2e-n9"), upstream.base_url, API_KEY)

    with real_http_stack(cfg) as base:
        yield base, upstream

    upstream.close()


@pytest.fixture
def novels_root(tmp_path, monkeypatch):
    root = tmp_path / "novels"
    root.mkdir()
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", root)
    return root


def _headers() -> dict:
    return {"X-API-Key": API_KEY}


def _make_novel(novel_id: str) -> None:
    novel = Novel(title="人类大进步")
    novel.chapters = [Chapter(chapter_number=1, title="第一次发射", content="舷窗外的地球。")]
    save_novel(novel, novel_id)


def _create_thread(base: str, novel_id: str, **kw) -> dict:
    body = {"id": "t1", "title": THREAD_TITLE, "planted_chapter": 1, "strength": 4,
            "note": THREAD_NOTE}
    body.update(kw)
    resp = httpx.post(f"{base}/api/novel/{novel_id}/threads", json=body,
                      headers=_headers(), timeout=30)
    assert resp.status_code == 200, resp.text[:400]
    return resp.json()


def _generate(base: str, novel_id: str, chapter_number: int = 2) -> dict:
    resp = httpx.post(
        f"{base}/api/generate/chapter/v2",
        json={"novel_id": novel_id, "chapter_number": chapter_number, "chapter_title": "试炼"},
        headers=_headers(),
        timeout=60,
    )
    assert resp.status_code == 200, resp.status_code
    events = parse_sse_events(resp.text)
    assert [ev for ev, _p in events][-1] == "done", resp.text[:400]
    return [p for ev, p in events if ev == "done"][0]


class TestAuth:
    def test_requires_api_key(self, stack, novels_root):
        base, _up = stack
        _make_novel("n9-auth")

        resp = httpx.get(f"{base}/api/novel/n9-auth/threads", timeout=30)

        assert resp.status_code == 401


class TestLedgerOverHttp:
    def test_crud_lands_on_disk(self, stack, novels_root):
        base, _up = stack
        _make_novel("n9-crud")

        assert _create_thread(base, "n9-crud")["success"] is True

        # 落盘：真源在 novel.json，可见镜像在 threads/
        novel_dir = novels_root / "n9-crud"
        raw = json.loads((novel_dir / "novel.json").read_text(encoding="utf-8"))
        assert raw["threads"]["t1"]["title"] == THREAD_TITLE
        assert (novel_dir / "threads" / "t1.json").is_file()

        # 接口回读
        listed = httpx.get(f"{base}/api/novel/n9-crud/threads", headers=_headers(), timeout=30)
        assert listed.json()["data"]["ids"] == ["t1"]

    def test_thread_survives_real_generation(self, stack, novels_root):
        """核心陷阱：生成并保存章节会重建镜像目录，账本必须活下来。"""
        base, upstream = stack
        _make_novel("n9-survive")
        _create_thread(base, "n9-survive")
        upstream.clear()

        _generate(base, "n9-survive")          # 真实生成 → 保存章节 → 触发 _write_files

        listed = httpx.get(f"{base}/api/novel/n9-survive/threads", headers=_headers(), timeout=30)
        assert listed.json()["data"]["ids"] == ["t1"], "保存章节后伏笔丢了 —— 实现绕过了模型"
        assert (novels_root / "n9-survive" / "threads" / "t1.json").is_file()

    def test_duplicate_is_explicit_failure(self, stack, novels_root):
        base, _up = stack
        _make_novel("n9-dup")
        _create_thread(base, "n9-dup")

        again = _create_thread(base, "n9-dup", title="偷偷改掉")

        assert again["success"] is False


class TestInjectionVisible:
    def test_open_thread_reaches_the_real_prompt(self, stack, novels_root):
        """manifest 说注入了不算数 —— 假上游收到的 prompt 里必须真有这一条。"""
        base, upstream = stack
        _make_novel("n9-inject")
        _create_thread(base, "n9-inject")
        upstream.clear()

        payload = _generate(base, "n9-inject")

        sources = [e["source"] for e in payload["context_manifest"]["entries"]]
        assert "thread:t1" in sources

        calls = upstream.stream_requests()
        assert len(calls) == 1
        prompt = "\n".join(str(m.get("content", "")) for m in calls[0]["body"]["messages"])
        assert THREAD_TITLE in prompt, "manifest 声称注入，但 prompt 里没有"
        assert THREAD_NOTE in prompt

    def test_resolved_thread_is_not_injected(self, stack, novels_root):
        base, upstream = stack
        _make_novel("n9-resolved")
        _create_thread(base, "n9-resolved")
        httpx.post(
            f"{base}/api/novel/n9-resolved/threads/t1/advance",
            json={"status": "paid_off", "chapter_number": 2},
            headers=_headers(),
            timeout=30,
        )
        upstream.clear()

        payload = _generate(base, "n9-resolved")

        sources = [e["source"] for e in payload["context_manifest"]["entries"]]
        assert "thread:t1" not in sources

    def test_manifest_endpoint_exposes_thread_source(self, stack, novels_root):
        """§9.1.1 验收 2 点名的 `GET /api/check/manifest` 也要能看到伏笔来源。

        评审 P2-4：原来只断言了 SSE done 载荷里的 manifest，没有验证**落盘后再读回**这条路
        —— 而作者事后复查靠的正是这个端点。
        """
        base, upstream = stack
        _make_novel("n9-manifest")
        _create_thread(base, "n9-manifest")
        upstream.clear()

        _generate(base, "n9-manifest")

        resp = httpx.get(
            f"{base}/api/check/manifest",
            params={"novel_id": "n9-manifest", "chapter_number": 2},
            headers=_headers(),
            timeout=30,
        )

        assert resp.status_code == 200, resp.status_code
        body = resp.json()
        assert body["success"] is True, body.get("message")
        sources = [e["source"] for e in body["data"]["entries"]]
        assert "thread:t1" in sources, "落盘的注入清单里看不到伏笔来源"


class TestCheckRulesOverHttp:
    def test_dangling_and_unknown_payoff_are_reported(self, stack, novels_root):
        base, _up = stack
        _make_novel("n9-check")
        _create_thread(base, "n9-check", planted_chapter=1)
        _create_thread(base, "n9-check", id="t2", title="指向不存在的回收章",
                       status="paid_off", payoff_chapter=99)

        resp = httpx.post(
            f"{base}/api/check/chapter",
            json={"novel_id": "n9-check", "chapter_number": 100, "text": CLEAN_TEXT},
            headers=_headers(),
            timeout=30,
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "dangling_threads" in data["by_rule"]
        assert "unknown_payoff" in data["by_rule"]
        assert data["level"] == "alert"
        dangling = [f for f in data["findings"] if f["rule_id"] == "dangling_threads"][0]
        assert THREAD_TITLE in dangling["suggestion"]

    def test_book_without_ledger_keeps_legacy_report_shape(self, stack, novels_root):
        """最小影响不变量：没账本的书，报告里不能凭空多出伏笔规则。"""
        base, _up = stack
        _make_novel("n9-legacy")

        resp = httpx.post(
            f"{base}/api/check/chapter",
            json={"novel_id": "n9-legacy", "chapter_number": 2, "text": CLEAN_TEXT},
            headers=_headers(),
            timeout=30,
        )

        data = resp.json()["data"]
        assert set(data["by_rule"]) <= {
            "chapter_hook", "dialogue_ratio", "paragraph_length", "pov_consistency", "ai_flavor"
        }
        assert set(data["rules_run"]) == {
            "chapter_hook", "dialogue_ratio", "paragraph_length", "pov_consistency", "ai_flavor"
        }
