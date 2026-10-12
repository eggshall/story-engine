"""N9 陷阱回归：伏笔镜像必须能活过「保存章节」。

与 N8 角色卡同源的坑：`novel_storage._write_files` 每次保存都会按模型里的字典
**重建**镜像目录（先 unlink 所有 *.json 再写）。如果伏笔账本绕过模型直接写
`<小说目录>/threads/`，下一次保存章节时就会被整目录清空 —— 作者眼里是「伏笔莫名其妙没了」。

所以实现必须：① 真源放 `novel.json` 的 `threads`；② 镜像写进 `_write_files`。
"""

from __future__ import annotations

import json

import pytest

from story_engine.core.models import Chapter, Novel, PlotThread
from story_engine.threads.manager import (
    delete_thread,
    list_threads,
    load_thread,
    save_thread,
)
from story_engine.tools.novel_storage import _novel_dir, load_novel, save_novel


@pytest.fixture(autouse=True)
def _tmp_roots(tmp_path, monkeypatch):
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
    return tmp_path


def test_thread_mirror_survives_chapter_save():
    save_novel(Novel(title="人类大进步"), "novel_a")
    save_thread("novel_a", PlotThread(id="t1", title="怀表的来历", planted_chapter=1))

    # 模拟作者保存一章：走模型（load → append → save），这正是会重建镜像目录的路径
    novel = load_novel("novel_a")
    assert novel is not None
    novel.chapters.append(Chapter(chapter_number=1, title="第一章", content="正文" * 50))
    save_novel(novel, "novel_a")

    mirror = _novel_dir("novel_a") / "threads" / "t1.json"
    assert mirror.is_file(), "保存章节后伏笔镜像被清空了 —— 实现绕过了模型"
    assert load_thread("novel_a", "t1") is not None
    assert list_threads("novel_a") == ["t1"]


def test_deleted_thread_mirror_is_removed():
    """删除后镜像不能残留（否则作者在目录里看到一条已经删掉的伏笔）。"""
    save_novel(Novel(title="人类大进步"), "novel_a")
    save_thread("novel_a", PlotThread(id="t1", title="怀表的来历", planted_chapter=1))
    assert delete_thread("novel_a", "t1") is True

    novel = load_novel("novel_a")
    assert novel is not None
    novel.chapters.append(Chapter(chapter_number=1, title="第一章", content="正文"))
    save_novel(novel, "novel_a")

    assert not (_novel_dir("novel_a") / "threads" / "t1.json").exists()


def test_ledger_round_trips_through_novel_json():
    """真源是 novel.json 的 threads：直接读文件也要能看到。"""
    save_novel(Novel(title="人类大进步"), "novel_a")
    save_thread("novel_a", PlotThread(id="t1", title="怀表的来历", planted_chapter=3,
                                      strength=5, note="第 30 章揭晓"))

    raw = json.loads((_novel_dir("novel_a") / "novel.json").read_text(encoding="utf-8"))
    assert "threads" in raw and "t1" in raw["threads"]
    assert raw["threads"]["t1"]["planted_chapter"] == 3


def test_legacy_novel_without_threads_key_still_loads():
    """评审 P2-3：N9 之前写下的 novel.json 里没有 `threads` 键。

    必须能正常加载（不炸），并在下次保存后补出该键 —— 否则老书直接打不开。
    """
    save_novel(Novel(title="老书"), "legacy_a")
    meta = _novel_dir("legacy_a") / "novel.json"
    raw = json.loads(meta.read_text(encoding="utf-8"))
    raw.pop("threads", None)                        # 模拟 N9 之前的文件
    meta.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    novel = load_novel("legacy_a")
    assert novel is not None, "老书加载失败"
    assert novel.threads == {}                      # 缺键 → 空账本，而不是 None

    save_thread("legacy_a", PlotThread(id="t1", title="新伏笔", planted_chapter=1))
    raw2 = json.loads(meta.read_text(encoding="utf-8"))
    assert "threads" in raw2 and "t1" in raw2["threads"]
