"""注入清单落盘测试（N6）—— 旁路数据，写失败不能带崩生成。"""

from __future__ import annotations

import json

import pytest

from story_engine.tools.novel_storage import _novel_dir
from story_engine.writer.manifest_store import load_manifest, manifest_path, save_manifest

MANIFEST = {
    "budget_tokens": 40000,
    "total_tokens": 1234,
    "entries": [{"slot_id": "beat", "tokens": 120, "sources": ["beats/ch_0001.md"]}],
    "dropped": [],
    "skipped": [],
}


@pytest.fixture(autouse=True)
def _tmp_novels_root(tmp_path, monkeypatch):
    """把小说根目录指向 tmp（别碰真实 data/novels）。"""
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
    return tmp_path


class TestRoundtrip:
    def test_save_then_load(self):
        path = save_manifest("novel_a", 3, MANIFEST)

        assert path == manifest_path("novel_a", 3)
        assert path is not None and path.is_file()
        assert load_manifest("novel_a", 3) == MANIFEST

    def test_file_lands_in_novel_dir_with_zero_padded_name(self):
        save_manifest("novel_a", 7, MANIFEST)

        expected = _novel_dir("novel_a") / "manifests" / "ch_0007.json"
        assert expected.is_file()
        # 中文不被转义（作者要看"节拍/前情"这些名字）
        assert "beat" in expected.read_text(encoding="utf-8")

    def test_missing_manifest_is_none_not_error(self):
        assert load_manifest("novel_never_generated", 1) is None

    def test_corrupt_manifest_is_none_and_does_not_raise(self):
        path = manifest_path("novel_a", 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ 不是 json", encoding="utf-8")

        assert load_manifest("novel_a", 1) is None

    def test_non_dict_manifest_is_none(self):
        path = manifest_path("novel_a", 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[1, 2, 3]", encoding="utf-8")

        assert load_manifest("novel_a", 1) is None

    def test_manifest_is_valid_utf8_json_for_author_reading(self):
        save_manifest("novel_a", 1, {"entries": [{"sources": ["主线.md"]}]})

        raw = manifest_path("novel_a", 1).read_text(encoding="utf-8")
        assert "主线.md" in raw                      # ensure_ascii=False
        assert json.loads(raw)["entries"][0]["sources"] == ["主线.md"]


class TestWriteFailureNeverBreaksGeneration:
    def test_atomic_write_failure_returns_none(self, monkeypatch):
        def boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr("story_engine.tools.novel_storage._atomic_write", boom)

        assert save_manifest("novel_a", 1, MANIFEST) is None
        assert load_manifest("novel_a", 1) is None

    def test_unwritable_dir_returns_none(self, monkeypatch):
        def boom(*_a, **_k):
            raise PermissionError("read-only")

        monkeypatch.setattr("story_engine.writer.manifest_store.Path.mkdir", boom)

        assert save_manifest("novel_a", 1, MANIFEST) is None


class TestCustomPathNovel:
    def test_manifest_follows_indexed_custom_path(self, monkeypatch, tmp_path):
        """自定义路径的小说，清单必须落到它自己的目录（经索引解析），别落到默认根。"""
        custom = tmp_path / "d盘里的书" / "人类大进步"
        custom.mkdir(parents=True)
        monkeypatch.setattr(
            "story_engine.tools.novel_storage._index_get",
            lambda novel_id: str(custom) if novel_id == "novel_custom" else None,
        )

        save_manifest("novel_custom", 2, MANIFEST)

        assert (custom / "manifests" / "ch_0002.json").is_file()
        assert load_manifest("novel_custom", 2) == MANIFEST
