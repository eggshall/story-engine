"""N9 契约测试：伏笔账本 CRUD（按小说绑定，走模型保存）。

设计依据：`docs/design/P7-MVP-PLAN.md` §9.1.1。

关键约束（写测试时就钉死，与 N8 角色卡同源）：
账本的真源是 `<小说目录>/novel.json` 的 `threads` 字典，镜像在 `<小说目录>/threads/`。
实现必须走 `load_novel → 改模型 → save_novel`；绕过模型直接写镜像目录，
会在下一次保存章节时被整目录清空。
"""

from __future__ import annotations

import pytest

from story_engine.core.models import Novel, PlotThread
from story_engine.threads.manager import (
    NovelNotFound,
    advance_thread,
    delete_thread,
    list_threads,
    load_thread,
    save_thread,
    select_open_threads,
)
from story_engine.tools.novel_storage import _novel_dir, save_novel


@pytest.fixture(autouse=True)
def _tmp_roots(tmp_path, monkeypatch):
    """把小说根指到 tmp，别碰真实 data/。"""
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
    return tmp_path


def _make_novel(novel_id: str, title: str = "人类大进步") -> None:
    save_novel(Novel(title=title), novel_id)


def _thread(tid: str, **kw) -> PlotThread:
    base = dict(id=tid, title=f"线索 {tid}", status="planted", planted_chapter=1)
    base.update(kw)
    return PlotThread(**base)


class TestThreadCRUD:
    def test_save_then_list_and_load(self):
        _make_novel("novel_a")

        assert save_thread("novel_a", _thread("t1")) is True

        assert list_threads("novel_a") == ["t1"]
        t = load_thread("novel_a", "t1")
        assert t is not None and t.id == "t1" and t.status == "planted"

    def test_thread_lands_in_this_novel_dir(self):
        _make_novel("novel_a")
        save_thread("novel_a", _thread("t1"))

        mirror = _novel_dir("novel_a") / "threads" / "t1.json"
        assert mirror.is_file(), "伏笔账本必须落在本书目录（human-readable 镜像）"

    def test_duplicate_without_overwrite_returns_false(self):
        _make_novel("novel_a")
        assert save_thread("novel_a", _thread("t1")) is True
        assert save_thread("novel_a", _thread("t1", title="改了标题")) is False
        assert load_thread("novel_a", "t1").title == "线索 t1", "非覆盖写入不能改到已有条目"

    def test_overwrite_updates(self):
        _make_novel("novel_a")
        save_thread("novel_a", _thread("t1"))
        assert save_thread("novel_a", _thread("t1", title="新标题"), overwrite=True) is True
        assert load_thread("novel_a", "t1").title == "新标题"

    def test_load_missing_returns_none(self):
        _make_novel("novel_a")
        assert load_thread("novel_a", "nope") is None

    def test_delete(self):
        _make_novel("novel_a")
        save_thread("novel_a", _thread("t1"))
        assert delete_thread("novel_a", "t1") is True
        assert list_threads("novel_a") == []
        assert delete_thread("novel_a", "t1") is False

    def test_unknown_novel_raises(self):
        with pytest.raises(NovelNotFound):
            list_threads("no_such_novel")


class TestIsolation:
    def test_threads_do_not_leak_between_novels(self):
        _make_novel("novel_a")
        _make_novel("novel_b")
        save_thread("novel_a", _thread("t1"))

        assert list_threads("novel_a") == ["t1"]
        assert list_threads("novel_b") == [], "A 书的伏笔绝不能出现在 B 书"


class TestAdvance:
    def test_advance_to_developed_without_payoff(self):
        _make_novel("novel_a")
        save_thread("novel_a", _thread("t1", planted_chapter=1))

        t = advance_thread("novel_a", "t1", "developed", chapter_number=5)
        assert t is not None and t.status == "developed"
        assert t.payoff_chapter is None, "推进不等于回收，payoff_chapter 不能顺手写上"

    def test_advance_to_paid_off_records_payoff_chapter(self):
        _make_novel("novel_a")
        save_thread("novel_a", _thread("t1", planted_chapter=1))

        t = advance_thread("novel_a", "t1", "paid_off", chapter_number=9)
        assert t is not None and t.status == "paid_off"
        assert t.payoff_chapter == 9, "回收必须记下回收章（马良三段式的双向指针）"

    def test_advance_missing_returns_none(self):
        _make_novel("novel_a")
        assert advance_thread("novel_a", "nope", "developed", chapter_number=3) is None

    def test_invalid_status_rejected(self):
        _make_novel("novel_a")
        save_thread("novel_a", _thread("t1"))
        with pytest.raises(ValueError):
            advance_thread("novel_a", "t1", "done", chapter_number=3)


class TestSelectOpenThreads:
    """注入用的筛选（最小版是**规则过滤**，不是检索）。"""

    def _seed(self):
        _make_novel("novel_a")
        save_thread("novel_a", _thread("old", planted_chapter=1))
        save_thread("novel_a", _thread("recent", planted_chapter=40))
        save_thread("novel_a", _thread("future", planted_chapter=99))
        save_thread("novel_a", _thread("done", planted_chapter=1, status="paid_off",
                                       payoff_chapter=30))
        save_thread("novel_a", _thread("dropped", planted_chapter=1, status="abandoned"))

    def test_only_unresolved_and_already_planted(self):
        self._seed()
        ids = [t.id for t in select_open_threads("novel_a", chapter_number=50)]
        assert set(ids) == {"old", "recent"}, "只注入未回收 + 已埋设的"

    def test_sorted_by_staleness_desc(self):
        self._seed()
        ids = [t.id for t in select_open_threads("novel_a", chapter_number=50)]
        assert ids == ["old", "recent"], "越久没推进的越靠前"

    def test_empty_ledger_returns_empty(self):
        _make_novel("novel_a")
        assert select_open_threads("novel_a", chapter_number=10) == []
