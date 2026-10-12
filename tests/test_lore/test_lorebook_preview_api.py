"""世界观「关键词触发预览」接口 —— RED 先行。

为什么要有这个接口（而不是前端自己算）：
触发逻辑的真源是 `lore/lorebook.py::find_matching_entries`（纯函数），装配器 `_lore_provider`
就是用它、并配 `LORE_MAX_ENTRIES=50` + `lore:overflow` 自报截断。前端若自己再实现一遍匹配，
就会出现评审刚批评过的那类「两处定义悄悄分叉」—— 预览说会注入、真写时却不注入。
所以预览**复用同一个函数与同一个上限**，并把「超出上限被丢掉多少条」如实报出来。

语义要点（与装配器一致）：
- `enabled=False` 的条目不参与；
- 一个条目命中多个关键词只算一次；
- 按 `priority` 降序、同优先级按 (书名, 条目ID) 升序 —— 结果确定；
- 只看**传入的这本书**的设定集（书间隔离）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.core.models import Novel
from story_engine.tools.novel_storage import save_novel

client = TestClient(app)

PREVIEW = "/api/novel/{}/lorebooks/preview"


@pytest.fixture(autouse=True)
def isolated(make_config, tmp_path, monkeypatch):
    make_config({"llm": {"default_model": "m", "models": []}})
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
    monkeypatch.setattr("story_engine.lore.library.LIBRARY_DIR", tmp_path / "library" / "lore")
    save_novel(Novel(title="甲书"), "novel_a")
    save_novel(Novel(title="乙书"), "novel_b")
    return tmp_path


def _book(novel_id="novel_a", name="天玄大陆", entries=None):
    body = {
        "name": name,
        "description": "",
        "entries": entries
        or {
            "culti": {"keys": ["筑基", "金丹"], "content": "境界：筑基→金丹", "priority": 80},
            "sword": {"keys": ["青锋"], "content": "上古神兵", "priority": 20},
        },
    }
    return client.post(f"/api/novel/{novel_id}/lorebooks", json=body)


def _preview(text, novel_id="novel_a"):
    return client.post(PREVIEW.format(novel_id), json={"text": text})


class TestPreview:
    def test_hits_are_returned_with_which_key_matched(self):
        _book()

        body = _preview("他祭出筑基之力，青锋剑出鞘").json()

        assert body["success"] is True
        ids = [m["entry_id"] for m in body["data"]["matches"]]
        assert ids == ["culti", "sword"]  # 优先级 80 > 20
        assert body["data"]["matches"][0]["keys_hit"] == ["筑基"]
        assert body["data"]["matches"][0]["book"] == "天玄大陆"
        assert body["data"]["count"] == 2

    def test_priority_order_is_descending(self):
        _book(entries={
            "low": {"keys": ["甲"], "content": "x", "priority": 10},
            "high": {"keys": ["乙"], "content": "y", "priority": 90},
        })

        ids = [m["entry_id"] for m in _preview("甲乙").json()["data"]["matches"]]

        assert ids == ["high", "low"]

    def test_disabled_entry_does_not_match(self):
        _book(entries={
            "off": {"keys": ["筑基"], "content": "x", "priority": 80, "enabled": False},
        })

        data = _preview("筑基").json()["data"]

        assert data["count"] == 0
        assert data["matches"] == []

    def test_no_hit_is_empty_not_an_error(self):
        _book()

        body = _preview("这句话里没有任何关键词").json()

        assert body["success"] is True
        assert body["data"]["count"] == 0

    def test_isolation_between_novels(self):
        _book(novel_id="novel_a")
        _book(novel_id="novel_b", name="乙书设定", entries={
            "other": {"keys": ["筑基"], "content": "乙书的筑基", "priority": 50},
        })

        data = _preview("筑基", "novel_a").json()["data"]

        assert [m["book"] for m in data["matches"]] == ["天玄大陆"]

    def test_overflow_is_reported_not_silently_dropped(self):
        """命中数超过 `LORE_MAX_ENTRIES` 时必须**自报**（与装配器 `lore:overflow` 同一口径）。"""
        from story_engine.writer.context_sources import LORE_MAX_ENTRIES

        entries = {
            f"e{i}": {"keys": ["关键词"], "content": "x", "priority": i} for i in range(LORE_MAX_ENTRIES + 3)
        }
        _book(entries=entries)

        data = _preview("关键词").json()["data"]

        assert data["count"] == LORE_MAX_ENTRIES
        assert data["overflow"] == 3

    def test_unknown_novel_is_readable_failure(self):
        body = _preview("筑基", "nope").json()

        assert body["success"] is False
        assert "不存在" in body["message"]
