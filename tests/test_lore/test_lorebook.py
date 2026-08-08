"""测试：Lorebook + 关键词触发"""
import tempfile
from pathlib import Path

import pytest

from story_engine.core.models import LoreBook, LorebookEntry
from story_engine.lore.lorebook import (
    build_lore_context,
    create_example_lorebook,
    delete_lorebook,
    find_matching_entries,
    list_lorebooks,
    load_lorebook,
    save_lorebook,
)


class TestLorebook:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        self.tmp_dir = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.lore.lorebook.LOREB_DIR", self.tmp_dir)
        yield

    def test_save_and_list(self):
        book = LoreBook(name="test_book")
        assert save_lorebook(book)
        assert "test_book" in list_lorebooks()

    def test_load(self):
        book = LoreBook(name="book1", description="测试")
        save_lorebook(book)
        loaded = load_lorebook("book1")
        assert loaded is not None
        assert loaded.name == "book1"

    def test_delete(self):
        save_lorebook(LoreBook(name="del_book"))
        assert delete_lorebook("del_book")
        assert "del_book" not in list_lorebooks()

    def test_find_matching_entries(self):
        book = LoreBook(name="world")
        book.entries["e1"] = LorebookEntry(keys=["魔法", "法力"], content="魔法设定", priority=80)
        book.entries["e2"] = LorebookEntry(keys=["剑"], content="剑法设定", priority=50)
        save_lorebook(book)

        matches = find_matching_entries("他施展魔法，手中剑光一闪")
        assert len(matches) == 2
        # 按优先级排序，魔法应在剑前面
        assert matches[0][1].priority >= matches[1][1].priority

    def test_build_lore_context(self):
        book = LoreBook(name="world")
        book.entries["e1"] = LorebookEntry(keys=["魔法"], content="魔法设定")
        save_lorebook(book)

        ctx = build_lore_context("他使用了魔法")
        assert "魔法设定" in ctx
        assert "世界观设定" in ctx

    def test_empty_context(self):
        ctx = build_lore_context("无关内容")
        assert ctx == ""

    def test_create_example(self):
        book = create_example_lorebook()
        assert book.name == "天玄大陆"
        assert len(book.entries) >= 4
