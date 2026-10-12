"""N9 注入契约：伏笔进入装配器（走既有 extra_providers 口子，不改签名）。

设计（§9.1.1）：
- 新增槽位 `Slot("threads", priority=SUMMARIES, provider="threads", renderer="bullets")`
- 只注入未回收（planted/developed）且已埋设（planted_chapter ≤ 本章）的
- 无账本 → 返回空 → 自动进 `manifest.skipped`（`empty`），不给假内容
"""

from __future__ import annotations

import pytest

from story_engine.core.models import Novel, PlotThread
from story_engine.threads.manager import save_thread
from story_engine.tools.novel_storage import save_novel
from story_engine.writer.context_builder import SUMMARIES
from story_engine.writer.context_sources import build_novel_builder, default_slots


@pytest.fixture(autouse=True)
def _tmp_roots(tmp_path, monkeypatch):
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
    return tmp_path


class TestSlotRegistration:
    def test_threads_slot_registered(self):
        slots = {s.slot_id: s for s in default_slots()}
        assert "threads" in slots, "default_slots() 必须登记伏笔槽位"
        slot = slots["threads"]
        assert slot.provider == "threads"
        assert slot.renderer == "bullets"
        assert slot.priority == SUMMARIES, "账本属记忆类：可被预算裁，不是 PINNED"

    def test_slot_order_between_beat_and_recap(self):
        ids = [s.slot_id for s in default_slots()]
        assert ids.index("beat") < ids.index("threads") < ids.index("recap"), \
            "伏笔回答「本章该推进什么」，与节拍同级紧邻"


class TestInjection:
    def _seed(self, novel_id: str = "novel_a") -> Novel:
        save_novel(Novel(title="人类大进步"), novel_id)
        save_thread(novel_id, PlotThread(id="old", title="怀表的来历", planted_chapter=1))
        save_thread(novel_id, PlotThread(id="done", title="已经揭晓", planted_chapter=1,
                                         status="paid_off", payoff_chapter=20))
        save_thread(novel_id, PlotThread(id="future", title="还没埋", planted_chapter=99))
        from story_engine.tools.novel_storage import load_novel

        loaded = load_novel(novel_id)
        assert loaded is not None
        return loaded

    def test_open_thread_injected_with_source(self):
        novel = self._seed()
        ctx = build_novel_builder(novel, "novel_a", chapter_number=50).build({})

        sources = [e.source for e in ctx.manifest.entries]
        assert "thread:old" in sources
        assert "thread:done" not in sources, "已回收的不能再注入"
        assert "thread:future" not in sources, "还没埋设的不能注入"
        assert "怀表的来历" in ctx.text

    def test_no_ledger_is_skipped_not_silent(self):
        save_novel(Novel(title="人类大进步"), "novel_b")
        from story_engine.tools.novel_storage import load_novel

        novel = load_novel("novel_b")
        assert novel is not None
        ctx = build_novel_builder(novel, "novel_b", chapter_number=3).build({})

        reasons = {s.slot_id: s.reason for s in ctx.manifest.skipped}
        assert reasons.get("threads") == "empty", "没账本要留痕为 empty，不能静默消失"

    def test_slot_budget_marks_truncated(self):
        """超过槽位预算时按片段截断，并在 manifest 里自报 truncated。"""
        save_novel(Novel(title="人类大进步"), "novel_a")
        for i in range(60):
            save_thread("novel_a", PlotThread(
                id=f"t{i:02d}", title=f"线索{i}：" + "很长的说明" * 30, planted_chapter=1))
        from story_engine.tools.novel_storage import load_novel

        novel = load_novel("novel_a")
        ctx = build_novel_builder(novel, "novel_a", chapter_number=50).build({})

        thread_entries = [e for e in ctx.manifest.entries if e.slot_id == "threads"]
        assert thread_entries, "至少注入一条"
        assert any(e.truncated for e in thread_entries), "超出槽位预算必须留痕"
