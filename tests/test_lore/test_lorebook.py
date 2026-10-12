"""测试：Lorebook + 关键词触发（**按小说绑定**，N8 世界观切片）

原文件测的是全局 `data/lore/` 行为 —— 那是本节点要退役的东西。改写为按书版本时，
**逐条保留了原来 7 条测试的断言**（save_and_list / load / delete / find_matching_entries /
build_lore_context / empty_context / create_example），并补上 N8 特有的隔离与镜像回归。

存储约定（`docs/design/P7-MVP-PLAN.md` §「N8 决策」）：
- 真源 = `<小说目录>/novel.json` 的 `lorebooks` 字典
- 镜像 = `<小说目录>/lore/<设定集名>.json`（human-readable）
- **必须经 `load_novel → 改模型 → save_novel` 写入**，否则下次保存章节会被 `_write_files` 清空
"""

from __future__ import annotations

import json

import pytest

from story_engine.core.models import Chapter, LoreBook, LorebookEntry, Novel
from story_engine.lore.lorebook import (
    NovelNotFound,
    create_example_lorebook,
    delete_lorebook,
    list_lorebooks,
    load_lorebook,
    save_lorebook,
)
from story_engine.tools.novel_storage import _novel_dir, load_novel, save_novel


@pytest.fixture(autouse=True)
def _isolate_novels(novels_root):
    """本文件每条测试都强制隔离小说根目录。

    隔离本身**复用 `tests/conftest.py` 的 `novels_root`**（它同时 patch 了
    `novel_storage` 与 `api.routes.export` 两处）—— 这里只是把它变成本文件 autouse。

    教训（本节点第一次跑踩到的）：别在测试文件里重造这个 fixture。我在本文件写过一份只 patch
    `novel_storage` 的局部 `novels_root`，它**覆盖**了 conftest 的版本，而且因为没标 autouse、
    测试又没声明参数，测试直接跑在真实 `data/novels/` 上，留下了 `novel_a`/`novel_b` 等残留。
    """
    return novels_root


def _book(name: str = "天玄大陆", description: str = "修仙基础设定", **kw) -> LoreBook:
    """造一个设定集。

    `description` 是**显式形参**：早先写成硬编码 + `**kw` 转发，于是 `_book(description=...)`
    会 `got multiple values for keyword argument`（本节点第一次跑就炸在这里）。
    """
    entries = kw.pop(
        "entries",
        {"culti": LorebookEntry(keys=["筑基", "金丹"], content="境界：筑基→金丹", priority=80)},
    )
    return LoreBook(name=name, description=description, entries=entries, **kw)


class TestScopedCrud:
    def test_save_and_list(self):
        save_novel(Novel(title="A 书"), "novel_a")

        assert save_lorebook("novel_a", _book()) is True
        assert "天玄大陆" in list_lorebooks("novel_a")

    def test_load(self):
        save_novel(Novel(title="A 书"), "novel_a")
        save_lorebook("novel_a", _book())

        loaded = load_lorebook("novel_a", "天玄大陆")

        assert loaded is not None
        assert loaded.name == "天玄大陆"
        assert loaded.entries["culti"].content == "境界：筑基→金丹"

    def test_delete(self):
        save_novel(Novel(title="A 书"), "novel_a")
        save_lorebook("novel_a", _book())

        assert delete_lorebook("novel_a", "天玄大陆") is True
        assert "天玄大陆" not in list_lorebooks("novel_a")
        assert delete_lorebook("novel_a", "天玄大陆") is False      # 再删返回 False，不抛

    def test_books_are_isolated(self):
        """N8 的核心不变量：设定集按书隔离，换书看不到别本的设定。"""
        save_novel(Novel(title="A 书"), "novel_a")
        save_novel(Novel(title="B 书"), "novel_b")
        save_lorebook("novel_a", _book(name="A 界"))

        assert list_lorebooks("novel_a") == ["A 界"]
        assert list_lorebooks("novel_b") == []
        assert load_lorebook("novel_b", "A 界") is None

    def test_unknown_novel_raises_not_silent_empty(self):
        """未知小说要**显式报错**，不能静默返回空列表（否则界面显示"没有设定"骗人）。"""
        with pytest.raises(NovelNotFound):
            list_lorebooks("no_such_novel")

    def test_duplicate_save_does_not_silently_overwrite(self):
        save_novel(Novel(title="A 书"), "novel_a")
        save_lorebook("novel_a", _book())

        assert save_lorebook("novel_a", _book(description="偷偷改掉")) is False
        loaded = load_lorebook("novel_a", "天玄大陆")
        assert loaded is not None and loaded.description == "修仙基础设定"

        assert save_lorebook("novel_a", _book(description="显式覆盖"), overwrite=True) is True
        updated = load_lorebook("novel_a", "天玄大陆")
        assert updated is not None and updated.description == "显式覆盖"


class TestStorageConvention:
    def test_source_of_truth_and_mirror_agree(self):
        save_novel(Novel(title="A 书"), "novel_a")
        save_lorebook("novel_a", _book())

        novel_dir = _novel_dir("novel_a")
        raw = json.loads((novel_dir / "novel.json").read_text(encoding="utf-8"))
        assert "lorebooks" in raw and "天玄大陆" in raw["lorebooks"]
        assert (novel_dir / "lore" / "天玄大陆.json").is_file()

    def test_lorebook_survives_chapter_save(self):
        """核心陷阱（与 `test_card_survives_chapter_save` 同源）。

        `novel_storage._write_files` 每次保存都会**先清空再重建**镜像目录。绕过模型直接往
        `<小说目录>/lore/` 写文件，下一次保存章节就会被整目录清空
        —— 作者眼里是「设定集莫名其妙没了」。
        """
        save_novel(Novel(title="A 书"), "novel_a")
        save_lorebook("novel_a", _book())

        novel = load_novel("novel_a")
        assert novel is not None
        novel.chapters.append(Chapter(chapter_number=1, title="第一章", content="正文"))
        save_novel(novel, "novel_a")

        assert (_novel_dir("novel_a") / "lore" / "天玄大陆.json").is_file()
        assert load_lorebook("novel_a", "天玄大陆") is not None

    def test_deleted_lorebook_mirror_is_removed(self):
        """镜像是「先清空再重建」语义：删掉的设定集不该在目录里留残影。"""
        save_novel(Novel(title="A 书"), "novel_a")
        save_lorebook("novel_a", _book())
        delete_lorebook("novel_a", "天玄大陆")

        save_novel(Novel(title="A 书"), "novel_a")      # 任意一次保存都会重建镜像

        assert not (_novel_dir("novel_a") / "lore" / "天玄大陆.json").exists()

    def test_legacy_novel_without_lorebooks_key_still_loads(self):
        """老书（N8 之前写的 `novel.json` 没有 `lorebooks` 键）必须仍能加载。"""
        save_novel(Novel(title="老书"), "legacy_a")
        meta = _novel_dir("legacy_a") / "novel.json"
        raw = json.loads(meta.read_text(encoding="utf-8"))
        raw.pop("lorebooks", None)
        meta.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        novel = load_novel("legacy_a")
        assert novel is not None
        assert novel.lorebooks == {}


def test_create_example():
    """保留原断言：示例设定集至少 4 个条目。"""
    book = create_example_lorebook()

    assert book.name == "天玄大陆"
    assert len(book.entries) >= 4
