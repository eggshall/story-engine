"""N8 E2E（真实 HTTP）：世界观**按书绑定**的跨层闭环。

按 §9.3：改了**注入组装**与**文件落盘**就必须有真 HTTP E2E（`TestClient` 只算单测）。
本文件走真 socket(uvicorn) + 鉴权中间件 + 假上游，钉死四件事：

1. **这本书**的设定集在前一章正文里命中 → 进 v2 的注入清单，且**假上游实际收到的 prompt 里真的有**
   （manifest 只是自述，不能单独作为注入发生的证据）；
2. **书间隔离** —— 别的书的设定集不许漏进来。这是 N8 的立身之本：改之前世界观是全局
   `data/lore/`，A 书的修仙设定会注入到 B 书的都市故事里；
3. 没有触发源（第一章）或没命中 → 槽位进 `skipped`（"没注成必须可见"），且**整条流不报错** ——
   作者刚建书就是这个状态；
4. 真源在 `novel.json` 的 `lorebooks`、镜像是 `lore/<设定集名>.json`，且**删除后的残影会被清掉**
   （`_write_files` 先清空再重建；N9 期间核过 lore 曾是三个镜像目录里唯一"只写不清空"的例外）。
"""

from __future__ import annotations

import json

import httpx
import pytest

from story_engine.core.models import Chapter, LoreBook, LorebookEntry, Novel
from story_engine.tools.novel_storage import load_novel, save_novel
from tests.e2e.fake_upstream import FakeUpstream, parse_sse_events, real_http_stack, write_config

pytestmark = pytest.mark.e2e

API_KEY = "e2e-n8-key"

# 两本书用**同一个触发词**，各自的设定内容不同 —— 这样"注入的是哪本书的设定"才有判别力，
# 用不同触发词就分不清"隔离生效"和"本来就没命中"。
TRIGGER = "筑基"
A_BOOK = "天玄大陆"
A_ENTRY = "A书设定：筑基是修仙第一步，共九层。"
B_BOOK = "现代都市"
B_ENTRY = "B书设定：这里是都市，筑基只是楼盘名。"


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    upstream = FakeUpstream()
    upstream.set_mode("ok")
    cfg = write_config(tmp_path_factory.mktemp("e2e-n8"), upstream.base_url, API_KEY)

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


def _book(name: str, content: str) -> LoreBook:
    return LoreBook(
        name=name,
        entries={name + "-e1": LorebookEntry(keys=[TRIGGER], content=content, priority=80)},
    )


def _make_novel(
    novel_id: str, *, books: dict | None = None, chapter_one: str | None = None
) -> None:
    """建书：`books` 给定时写进 `lorebooks`（真源），`chapter_one` 给定时写第一章正文。

    第一章正文是**触发源**（世界观只按"紧邻上一章"触发），所以想验命中就必须给。
    """
    novel = Novel(title="人类大进步")
    if books:
        novel.lorebooks = books
    if chapter_one is not None:
        novel.chapters = [Chapter(chapter_number=1, title="第一次发射", content=chapter_one)]
    save_novel(novel, novel_id)


def _generate(base: str, novel_id: str, chapter_number: int = 2) -> tuple[str, list, dict]:
    resp = httpx.post(
        f"{base}/api/generate/chapter/v2",
        json={"novel_id": novel_id, "chapter_number": chapter_number, "chapter_title": "试炼"},
        headers=_headers(),
        timeout=60,
    )
    assert resp.status_code == 200, resp.status_code
    events = parse_sse_events(resp.text)
    assert [ev for ev, _p in events][-1] == "done", resp.text[:400]
    return resp.text, events, [p for ev, p in events if ev == "done"][0]


def _prompt_of(upstream: FakeUpstream) -> str:
    """假上游**实际收到**的请求体拼成的 prompt（证据链的另一半）。"""
    calls = upstream.stream_requests()
    assert len(calls) == 1, f"期望 1 次流式调用，实际 {len(calls)}"
    return "\n".join(str(m.get("content", "")) for m in calls[0]["body"]["messages"])


class TestLoreInjectedOverHttp:
    def test_book_lore_reaches_manifest_and_real_prompt(self, stack, novels_root):
        """命中 → 清单有来源可溯的条目，且上游收到的 prompt 里真的有这段设定。"""
        base, upstream = stack
        _make_novel(
            "n8-hit", books={A_BOOK: _book(A_BOOK, A_ENTRY)}, chapter_one=f"他盘膝坐下，运转{TRIGGER}。"
        )
        upstream.clear()

        _body, _events, payload = _generate(base, "n8-hit")
        manifest = payload["context_manifest"]
        sources = [e["source"] for e in manifest["entries"]]

        # 1) 清单：来源精确到「书:条目」，作者能据此知道这段设定从哪来
        assert f"lore:{A_BOOK}:{A_BOOK}-e1" in sources, sources
        # 2) 槽位不能被当成"没注成"
        assert "lore" not in {s["slot_id"] for s in manifest["skipped"]}
        # 3) 上游实际收到的 prompt —— 含内容，也含"[书名] 触发词"标签（模型才知道属于哪个世界）
        prompt = _prompt_of(upstream)
        assert A_ENTRY in prompt, "manifest 说注入了，但 prompt 里没有 —— 注入没真发生"
        assert f"[{A_BOOK}] {TRIGGER}" in prompt, prompt[:600]

    def test_other_book_lore_never_leaks(self, stack, novels_root):
        """书间隔离：两本书同一个触发词，各自只许看到自己的设定。"""
        base, upstream = stack
        _make_novel(
            "n8-iso-a", books={A_BOOK: _book(A_BOOK, A_ENTRY)}, chapter_one=f"他运转{TRIGGER}。"
        )
        _make_novel(
            "n8-iso-b", books={B_BOOK: _book(B_BOOK, B_ENTRY)}, chapter_one=f"他在{TRIGGER}站下车。"
        )

        upstream.clear()
        _body, _events, payload_a = _generate(base, "n8-iso-a")
        prompt_a = _prompt_of(upstream)
        sources_a = [e["source"] for e in payload_a["context_manifest"]["entries"]]

        assert A_ENTRY in prompt_a
        assert B_ENTRY not in prompt_a, "B 书的设定漏进了 A 书 —— 世界观又变回全局了"
        assert not any(s.startswith(f"lore:{B_BOOK}") for s in sources_a), sources_a

        upstream.clear()
        _body, _events, payload_b = _generate(base, "n8-iso-b")
        prompt_b = _prompt_of(upstream)
        sources_b = [e["source"] for e in payload_b["context_manifest"]["entries"]]

        assert B_ENTRY in prompt_b
        assert A_ENTRY not in prompt_b, "A 书的设定漏进了 B 书 —— 世界观又变回全局了"
        assert not any(s.startswith(f"lore:{A_BOOK}") for s in sources_b), sources_b


class TestNoTriggerSource:
    def test_first_chapter_skips_lore_without_failing(self, stack, novels_root):
        """第一章没有"上一章"当触发源：槽位进 skipped，流照常收尾。"""
        base, _upstream = stack
        _make_novel("n8-first", books={A_BOOK: _book(A_BOOK, A_ENTRY)}, chapter_one=None)

        body, events, payload = _generate(base, "n8-first", chapter_number=1)

        skipped = {s["slot_id"]: s["reason"] for s in payload["context_manifest"]["skipped"]}
        assert skipped.get("lore") == "empty", skipped
        assert [ev for ev, _p in events][-1] == "done"
        assert "error" not in [ev for ev, _p in events], body[:300]

    def test_no_keyword_hit_skips_lore(self, stack, novels_root):
        """有设定集但前一章没提到触发词 → 同样 skipped，不是"注入了空串"。"""
        base, _upstream = stack
        _make_novel(
            "n8-nohit", books={A_BOOK: _book(A_BOOK, A_ENTRY)}, chapter_one="他抬头看了看天，没说话。"
        )

        _body, _events, payload = _generate(base, "n8-nohit")

        skipped = {s["slot_id"]: s["reason"] for s in payload["context_manifest"]["skipped"]}
        assert skipped.get("lore") == "empty", skipped
        assert not any(
            e["source"].startswith("lore:")
            for e in payload["context_manifest"]["entries"]
        )


class TestLoreMirrorOnDisk:
    def test_source_of_truth_and_mirror_land_on_disk(self, stack, novels_root):
        """真源 `novel.json` + 人类可读镜像 `lore/<名>.json`（与角色卡/伏笔同构）。"""
        base, _upstream = stack
        _make_novel(
            "n8-mirror", books={A_BOOK: _book(A_BOOK, A_ENTRY)}, chapter_one=f"他运转{TRIGGER}。"
        )

        novel_dir = novels_root / "n8-mirror"
        raw = json.loads((novel_dir / "novel.json").read_text(encoding="utf-8"))
        assert raw["lorebooks"][A_BOOK]["entries"][f"{A_BOOK}-e1"]["content"] == A_ENTRY
        mirror = novel_dir / "lore" / f"{A_BOOK}.json"
        assert mirror.is_file(), "镜像目录里没有设定集 —— 作者看不到人可读副本"

    def test_deleted_lorebook_mirror_is_cleared_by_real_generation(self, stack, novels_root):
        """删除 + 残影都必须被真实生成路径清掉（`_write_files` 先清空再重建）。

        这条守的是 N8 修掉的那个缺口：lore 原来是"只写不清空"，作者删掉设定集后
        目录里留残影 —— 界面显示"删了还在"。
        """
        base, _upstream = stack
        _make_novel(
            "n8-clear", books={A_BOOK: _book(A_BOOK, A_ENTRY)}, chapter_one=f"他运转{TRIGGER}。"
        )

        novel_dir = novels_root / "n8-clear"
        lore_dir = novel_dir / "lore"
        # 造一个"残影"：不在真源里、却躺在镜像目录里的文件
        stale = lore_dir / "残影.json"
        stale.write_text("{}", encoding="utf-8")
        assert stale.is_file()

        # 经模型删除设定集（绕过模型直接删镜像文件是另一种坑，不在这里验）
        novel = load_novel("n8-clear")
        assert novel is not None
        del novel.lorebooks[A_BOOK]
        save_novel(novel, "n8-clear")
        assert not (lore_dir / f"{A_BOOK}.json").exists(), "保存时没清空镜像目录"

        # 再来一次真实生成（保存章节会重建镜像目录）→ 残影必须消失
        stale.write_text("{}", encoding="utf-8")
        _generate(base, "n8-clear")

        assert not stale.exists(), "残影文件还在 —— lore 镜像又变回「只写不清空」了"
        assert not (lore_dir / f"{A_BOOK}.json").exists(), "已删除的设定集在生成后复活了"
        raw = json.loads((novel_dir / "novel.json").read_text(encoding="utf-8"))
        assert raw["lorebooks"] == {}
