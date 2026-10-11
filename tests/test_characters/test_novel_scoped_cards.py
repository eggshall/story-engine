"""N8 契约测试：角色卡按小说绑定（项目空间）。

背景（现状 bug）：角色卡原来是**全局**目录 `data/characters/*.json`，
生成时无条件把全部卡并入当前小说 → 所有小说共用一副卡组；
而前端"角色卡"页更是纯内存态（刷新即丢）。N8 的目标：

1. 卡属于**某一本小说**：存 `<小说目录>/characters/` 与 novel.json 的 `characters` 字典；
2. A 书的卡绝不进 B 书（隔离性）；生成只注入本书的卡；
3. **不再读写全局** `data/characters/`；
4. 素材库 `data/library/characters/`：只做「另存为素材 / 从素材导入」的**纯复制**
   （改素材不影响已导入的书）。

关键陷阱（写测试时就钉死）：`novel_storage._write_files` 每次保存都会按模型里的字典
**重建** `characters/` 目录，所以实现必须走 `load_novel → 改模型 → save_novel`；
绕过模型直接写镜像目录，会在下一次保存时被整目录清空（数据丢失）。
"""

from __future__ import annotations

import json

import pytest

from story_engine.characters import library
from story_engine.characters.manager import (
    NovelNotFound,
    delete_card,
    list_cards,
    load_card,
    save_card,
    search_cards,
)
from story_engine.core.models import CharacterCard, Novel
from story_engine.tools.novel_storage import _novel_dir, load_novel, save_novel


@pytest.fixture(autouse=True)
def _tmp_roots(tmp_path, monkeypatch):
    """两个全局根都指到 tmp：小说根 + 素材库根（别碰真实 data/）。"""
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
    monkeypatch.setattr("story_engine.characters.library.LIBRARY_DIR", tmp_path / "library" / "characters")
    return tmp_path


def _make_novel(novel_id: str, title: str = "人类大进步") -> None:
    save_novel(Novel(title=title), novel_id)


def _card(name: str, **kw) -> CharacterCard:
    base = dict(name=name, description="d", personality="p", background="b", appearance="a")
    base.update(kw)
    return CharacterCard(**base)


class TestNovelScopedCRUD:
    def test_save_then_list_and_load(self):
        _make_novel("novel_a")

        assert save_card("novel_a", _card("沈约")) is True

        assert list_cards("novel_a") == ["沈约"]
        card = load_card("novel_a", "沈约")
        assert card is not None and card.name == "沈约"

    def test_card_lands_in_this_novel_dir(self):
        _make_novel("novel_a")
        save_card("novel_a", _card("沈约"))

        mirror = _novel_dir("novel_a") / "characters" / "沈约.json"
        assert mirror.is_file(), "角色卡必须落在本书目录（human-readable 镜像）"
        assert json.loads(mirror.read_text(encoding="utf-8"))["name"] == "沈约"

    def test_card_survives_chapter_save(self):
        """真实陷阱：保存章节会重建 characters/ 目录 —— 卡必须活下来。"""
        _make_novel("novel_a")
        save_card("novel_a", _card("沈约"))

        # 模拟"另存一次小说"（保存章节/正文都会走这条路径）
        novel = load_novel("novel_a")
        assert novel is not None
        save_novel(novel, "novel_a")

        assert list_cards("novel_a") == ["沈约"]
        assert (_novel_dir("novel_a") / "characters" / "沈约.json").is_file()

    def test_save_existing_without_overwrite_is_refused(self):
        _make_novel("novel_a")
        save_card("novel_a", _card("沈约", description="第一版"))

        assert save_card("novel_a", _card("沈约", description="第二版")) is False
        assert load_card("novel_a", "沈约").description == "第一版"

        assert save_card("novel_a", _card("沈约", description="第二版"), overwrite=True) is True
        assert load_card("novel_a", "沈约").description == "第二版"

    def test_update_and_delete(self):
        _make_novel("novel_a")
        save_card("novel_a", _card("沈约"))

        save_card("novel_a", _card("沈约", personality="冷"), overwrite=True)
        assert load_card("novel_a", "沈约").personality == "冷"

        assert delete_card("novel_a", "沈约") is True
        assert list_cards("novel_a") == []
        assert load_card("novel_a", "沈约") is None
        assert not (_novel_dir("novel_a") / "characters" / "沈约.json").exists()

    def test_delete_missing_returns_false(self):
        _make_novel("novel_a")

        assert delete_card("novel_a", "不存在") is False

    def test_search_matches_name_and_body(self):
        _make_novel("novel_a")
        save_card("novel_a", _card("沈约", description="总工程师"))
        save_card("novel_a", _card("林岚", personality="谨慎但嘴硬"))

        assert search_cards("novel_a", "沈") == ["沈约"]
        assert search_cards("novel_a", "嘴硬") == ["林岚"]
        assert search_cards("novel_a", "无此人") == []

    def test_unknown_novel_raises(self):
        with pytest.raises(NovelNotFound):
            list_cards("no-such-novel")
        with pytest.raises(NovelNotFound):
            save_card("no-such-novel", _card("沈约"))


class TestIsolation:
    def test_cards_do_not_leak_between_novels(self):
        _make_novel("novel_a", "人类大进步")
        _make_novel("novel_b", "另一本")
        save_card("novel_a", _card("沈约"))
        save_card("novel_b", _card("张小满"))

        assert list_cards("novel_a") == ["沈约"]
        assert list_cards("novel_b") == ["张小满"]
        assert load_card("novel_b", "沈约") is None

    def test_same_name_in_two_novels_is_independent(self):
        _make_novel("novel_a")
        _make_novel("novel_b")
        save_card("novel_a", _card("沈约", description="A 版"))
        save_card("novel_b", _card("沈约", description="B 版"))

        assert load_card("novel_a", "沈约").description == "A 版"
        assert load_card("novel_b", "沈约").description == "B 版"

    def test_deleting_from_one_novel_keeps_the_other(self):
        _make_novel("novel_a")
        _make_novel("novel_b")
        save_card("novel_a", _card("沈约"))
        save_card("novel_b", _card("沈约"))

        delete_card("novel_a", "沈约")

        assert list_cards("novel_a") == []
        assert list_cards("novel_b") == ["沈约"]

    def test_does_not_touch_global_characters_dir(self, tmp_path):
        """退役全局目录：任何操作都不该在 data/characters/ 下留东西。"""
        global_dir = tmp_path / "global_characters"
        global_dir.mkdir()
        _make_novel("novel_a")

        save_card("novel_a", _card("沈约"))
        list_cards("novel_a")
        delete_card("novel_a", "沈约")

        assert list(global_dir.iterdir()) == []


class TestLibraryCopySemantics:
    def test_export_then_import_is_a_copy(self):
        _make_novel("novel_a")
        _make_novel("novel_b")
        save_card("novel_a", _card("沈约", description="A 版"))

        assert library.export_to_library("novel_a", "沈约") is True
        assert library.list_library() == ["沈约"]

        assert library.import_from_library("novel_b", "沈约") is True
        assert load_card("novel_b", "沈约").description == "A 版"

        # 纯复制：改素材/改原书，都不该影响已经导入的那份
        save_card("novel_a", _card("沈约", description="A 改"), overwrite=True)
        assert load_card("novel_b", "沈约").description == "A 版"
        assert library.load_from_library("沈约").description == "A 版"

    def test_import_with_new_name(self):
        _make_novel("novel_a")
        _make_novel("novel_b")
        save_card("novel_a", _card("沈约"))
        library.export_to_library("novel_a", "沈约")

        assert library.import_from_library("novel_b", "沈约", new_name="老沈") is True
        assert list_cards("novel_b") == ["老沈"]
        assert load_card("novel_b", "老沈").name == "老沈"

    def test_import_refuses_to_clobber_without_overwrite(self):
        _make_novel("novel_a")
        save_card("novel_a", _card("沈约", description="本书自己的"))
        library.export_to_library("novel_a", "沈约")
        save_card("novel_a", _card("沈约", description="本书自己的"), overwrite=True)

        assert library.import_from_library("novel_a", "沈约") is False
        assert load_card("novel_a", "沈约").description == "本书自己的"

    def test_missing_library_item_returns_false(self):
        _make_novel("novel_a")

        assert library.import_from_library("novel_a", "不存在的素材") is False
        assert library.load_from_library("不存在的素材") is None

    def test_export_missing_card_returns_false(self):
        _make_novel("novel_a")

        assert library.export_to_library("novel_a", "不存在") is False
        assert library.list_library() == []
