"""N8 世界观切片：关键词触发只用**本书**的设定集 + 引擎侧隔离。

触发引擎改成接收「设定集字典」（纯函数，不碰磁盘）的理由：
- `WritingEngine` 已持有 `self.current_novel`（内含 `lorebooks`），再进行一次磁盘读
  既浪费又可能与手上这本不一致；
- 纯函数让「命中哪些条目」可以脱离文件系统直接断言（N5 评审反复强调的可测性）。

原 `test_find_matching_entries`（优先级排序）与 `test_build_lore_context`（含
「世界观设定」表头）的断言在这里以纯函数形式保留。
"""

from __future__ import annotations

import pytest

from story_engine.core.models import Chapter, LoreBook, LorebookEntry, Novel
from story_engine.llm.router import ModelRouter
from story_engine.lore.lorebook import build_lore_context, find_matching_entries
from story_engine.writer.engine import WritingEngine


def _books() -> dict:
    return {
        "天玄大陆": LoreBook(
            name="天玄大陆",
            entries={
                "culti": LorebookEntry(keys=["筑基", "金丹"], content="境界：筑基→金丹", priority=80),
                "sect": LorebookEntry(keys=["天玄宗"], content="天玄宗在东域", priority=70),
                "dead": LorebookEntry(keys=["废案"], content="不该出现", priority=99, enabled=False),
            },
        ),
        "现代都市": LoreBook(
            name="现代都市",
            entries={"car": LorebookEntry(keys=["汽车"], content="都市背景", priority=60)},
        ),
    }


class TestFindMatchingEntries:
    def test_find_matching_entries(self):
        """保留原断言：多个条目都命中，且按优先级降序（原来用「魔法/剑」两个词触发）。"""
        matched = find_matching_entries(_books(), "他运转筑基，又提到天玄宗。")

        assert len(matched) == 2
        assert matched[0][2].priority >= matched[1][2].priority

    def test_only_triggered_keys_match(self):
        matched = find_matching_entries(_books(), "他盘膝坐下，运转筑基功法。")

        assert [e.content for _n, _i, e in matched] == ["境界：筑基→金丹"]

    def test_match_carries_book_name_and_entry_id(self):
        """三元组要能唯一定位到一个条目 —— 装配器的 `lore:<书名>:<条目>` 靠它。"""
        matched = find_matching_entries(_books(), "他盘膝坐下，运转筑基功法。")

        assert matched[0][:2] == ("天玄大陆", "culti")

    def test_sorted_by_priority_desc(self):
        matched = find_matching_entries(_books(), "天玄宗里有筑基修士。")

        assert [e.content for _n, _i, e in matched] == ["境界：筑基→金丹", "天玄宗在东域"]
        assert matched[0][2].priority >= matched[1][2].priority

    def test_disabled_entry_never_matches(self):
        assert find_matching_entries(_books(), "这是废案内容。") == []

    def test_max_results_is_respected(self):
        assert len(find_matching_entries(_books(), "筑基 天玄宗 汽车", max_results=2)) == 2

    def test_empty_book_set_is_fine(self):
        assert find_matching_entries({}, "筑基") == []


class TestBuildLoreContext:
    def test_build_lore_context(self):
        """保留原断言：正文进上下文，且带「世界观设定」表头。"""
        ctx = build_lore_context(_books(), "他运转筑基功法。")

        assert "境界：筑基→金丹" in ctx
        assert "世界观设定" in ctx

    def test_empty_context(self):
        """保留原断言：没命中就是空串（不是空表头）。"""
        assert build_lore_context(_books(), "完全无关的一段话。") == ""

    def test_context_contains_book_name(self):
        assert "天玄大陆" in build_lore_context(_books(), "他运转筑基功法。")

    def test_other_books_never_leak_in(self):
        """隔离性的关键断言：命中都市那本，不该把天玄大陆的条目带进来。"""
        ctx = build_lore_context(_books(), "他开着一辆汽车。")

        assert "都市背景" in ctx
        assert "境界：筑基→金丹" not in ctx
        assert "天玄宗" not in ctx


class TestEngineIsolation:
    """引擎必须只用**手上这本**的设定集 —— 本节点要修的核心 bug。"""

    @pytest.fixture
    def engine(self) -> WritingEngine:
        return WritingEngine(ModelRouter([]))

    def test_engine_uses_current_novel_lorebooks_only(self, engine):
        novel = Novel(title="A 书", lorebooks=_books())
        novel.chapters = [Chapter(chapter_number=1, title="一", content="他运转筑基功法。")]
        engine.load_novel(novel)

        # 写第 2 章 → 触发源是第 1 章
        assert "境界：筑基→金丹" in engine._build_world_context(2)

    def test_engine_without_lorebooks_gets_nothing(self, engine):
        novel = Novel(title="空书")
        novel.chapters = [Chapter(chapter_number=1, title="一", content="他运转筑基功法。")]
        engine.load_novel(novel)

        assert engine._build_world_context(2) == ""

    def test_engine_does_not_leak_from_the_chapter_being_written(self, engine):
        """写第 1 章时没有"上一章"，即使第 1 章自己已有正文也不能当触发源。"""
        novel = Novel(title="A 书", lorebooks=_books())
        novel.chapters = [Chapter(chapter_number=1, title="一", content="他运转筑基功法。")]
        engine.load_novel(novel)

        assert engine._build_world_context(1) == ""

    def test_no_novel_loaded_returns_empty(self, engine):
        assert engine._build_world_context(2) == ""
