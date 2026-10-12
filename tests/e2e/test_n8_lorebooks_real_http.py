"""N8 E2E（真实 HTTP）：设定集接口 → 落盘 → **真的进入下一次生成的 prompt**。

按 §9.3：新增 HTTP 接口 + 文件落盘就必须有真 HTTP E2E。这条链是「作者录入设定 → 下次生成
真的用上」的完整证据，缺任何一段都只是自述：

    真实 socket(uvicorn) ←httpx→ 鉴权中间件
        → POST /api/novel/{id}/lorebooks            （落盘 novel.json + lore/ 镜像）
        → POST /api/generate/chapter/v2             （装配器 lore 槽位）
        → 假上游（记录**实际收到**的请求体）

同时钉住那个坑：生成并保存章节会**重建**镜像目录，设定集必须活下来。
"""

from __future__ import annotations

import json

import httpx
import pytest

from story_engine.core.models import Chapter, Novel
from story_engine.tools.novel_storage import save_novel
from tests.e2e.fake_upstream import FakeUpstream, parse_sse_events, real_http_stack, write_config

pytestmark = pytest.mark.e2e

API_KEY = "e2e-n8-lorebooks-key"

BOOK = "天玄大陆"
ENTRY_CONTENT = "境界：筑基→金丹，共九重。"
TRIGGER = "筑基"


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    upstream = FakeUpstream()
    upstream.set_mode("ok")
    cfg = write_config(tmp_path_factory.mktemp("e2e-n8-lorebooks"), upstream.base_url, API_KEY)

    with real_http_stack(cfg) as base:
        yield base, upstream

    upstream.close()


@pytest.fixture
def novels_root(tmp_path, monkeypatch):
    """隔离小说根**与世界观素材库根**（后者不隔离会写进真实 data/library/lore/）。"""
    root = tmp_path / "novels"
    root.mkdir()
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", root)
    monkeypatch.setattr("story_engine.lore.library.LIBRARY_DIR", tmp_path / "library" / "lore")
    return root


def _headers() -> dict:
    return {"X-API-Key": API_KEY}


def _make_novel(novel_id: str, chapter_one: str = f"他盘膝坐下，运转{TRIGGER}。") -> None:
    novel = Novel(title="人类大进步")
    novel.chapters = [Chapter(chapter_number=1, title="第一次发射", content=chapter_one)]
    save_novel(novel, novel_id)


def _book_body(name: str = BOOK, content: str = ENTRY_CONTENT) -> dict:
    return {
        "name": name,
        "description": "东域修仙体系",
        "entries": {"culti": {"keys": [TRIGGER], "content": content, "priority": 80}},
    }


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


def _prompt_of(upstream: FakeUpstream) -> str:
    calls = upstream.stream_requests()
    assert len(calls) == 1, f"期望 1 次流式调用，实际 {len(calls)}"
    return "\n".join(str(m.get("content", "")) for m in calls[0]["body"]["messages"])


class TestAuth:
    def test_requires_api_key(self, stack, novels_root):
        base, _up = stack
        _make_novel("n8lb-auth")

        resp = httpx.get(f"{base}/api/novel/n8lb-auth/lorebooks", timeout=30)

        assert resp.status_code == 401


class TestEndToEndChain:
    def test_created_over_http_lands_on_disk_and_reaches_the_real_prompt(self, stack, novels_root):
        """录入 → 落盘（真源 + 镜像）→ 存活过一次真实生成 → 进下一次生成的 prompt。"""
        base, upstream = stack
        _make_novel("n8lb-chain")

        created = httpx.post(
            f"{base}/api/novel/n8lb-chain/lorebooks", json=_book_body(), headers=_headers(), timeout=30
        )
        assert created.json()["success"] is True, created.text[:300]

        # 1) 落盘：真源在 novel.json，镜像在 lore/
        novel_dir = novels_root / "n8lb-chain"
        raw = json.loads((novel_dir / "novel.json").read_text(encoding="utf-8"))
        assert raw["lorebooks"][BOOK]["entries"]["culti"]["content"] == ENTRY_CONTENT
        assert (novel_dir / "lore" / f"{BOOK}.json").is_file()

        # 2) 生成 → 保存章节会重建镜像目录，设定集必须活下来（坑）
        upstream.clear()
        payload = _generate(base, "n8lb-chain")
        listed = httpx.get(
            f"{base}/api/novel/n8lb-chain/lorebooks", headers=_headers(), timeout=30
        ).json()
        assert listed["data"]["names"] == [BOOK], "保存章节后设定集丢了 —— 实现绕过了模型"

        # 3) 注入清单有来源可溯的条目，并且**上游真的收到了**这段设定
        sources = [e["source"] for e in payload["context_manifest"]["entries"]]
        assert f"lore:{BOOK}:culti" in sources, sources
        prompt = _prompt_of(upstream)
        assert ENTRY_CONTENT in prompt
        assert f"[{BOOK}] {TRIGGER}" in prompt

    def test_other_book_lore_never_leaks_over_http(self, stack, novels_root):
        """接口层同样要有书间隔离：A 书录入的设定，B 书的 prompt 里不许出现。"""
        base, upstream = stack
        _make_novel("n8lb-iso-a")
        _make_novel("n8lb-iso-b", chapter_one="他在筑基站下车。")

        httpx.post(
            f"{base}/api/novel/n8lb-iso-a/lorebooks", json=_book_body(), headers=_headers(), timeout=30
        )

        upstream.clear()
        _generate(base, "n8lb-iso-b")

        prompt = _prompt_of(upstream)
        assert ENTRY_CONTENT not in prompt, "A 书的设定漏进了 B 书"


class TestLibraryOverHttp:
    def test_export_then_import_across_books(self, stack, novels_root):
        base, _up = stack
        _make_novel("n8lb-lib-a")
        _make_novel("n8lb-lib-b")

        assert httpx.post(
            f"{base}/api/novel/n8lb-lib-a/lorebooks", json=_book_body(), headers=_headers(), timeout=30
        ).json()["success"] is True
        assert httpx.post(
            f"{base}/api/novel/n8lb-lib-a/lorebooks/{BOOK}/to-library", headers=_headers(), timeout=30
        ).json()["success"] is True

        lib = httpx.get(f"{base}/api/library/lorebooks", headers=_headers(), timeout=30).json()
        assert lib["data"]["names"] == [BOOK]

        imported = httpx.post(
            f"{base}/api/novel/n8lb-lib-b/lorebooks/import",
            json={"source": "library", "name": BOOK},
            headers=_headers(),
            timeout=30,
        )
        assert imported.json()["success"] is True, imported.text[:300]

        names = httpx.get(
            f"{base}/api/novel/n8lb-lib-b/lorebooks", headers=_headers(), timeout=30
        ).json()["data"]["names"]
        assert names == [BOOK]
        # 副本真的进了 B 书的落盘（不是只回了个 success）
        raw = json.loads((novels_root / "n8lb-lib-b" / "novel.json").read_text(encoding="utf-8"))
        assert raw["lorebooks"][BOOK]["entries"]["culti"]["content"] == ENTRY_CONTENT
