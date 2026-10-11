"""测试：角色卡管理器（N8 起按小说绑定 → 全部走 novel_id）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from story_engine.characters.manager import (
    create_example_card,
    delete_card,
    list_cards,
    load_card,
    save_card,
    search_cards,
)
from story_engine.core.models import CharacterCard, Novel
from story_engine.tools.novel_storage import save_novel

NOVEL_ID = "novel_manager_test"


class TestCharacterManager:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """用临时小说根目录测试（别碰真实 data/novels）。"""
        self.root = tmp_path / "novels"
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", self.root)
        save_novel(Novel(title="测试书"), NOVEL_ID)
        yield

    def test_novel_dir_is_created(self):
        assert (Path(self.root) / NOVEL_ID).is_dir()

    def test_save_and_list(self):
        card = CharacterCard(name="test_char")
        assert save_card(NOVEL_ID, card)
        assert "test_char" in list_cards(NOVEL_ID)

    def test_load(self):
        assert save_card(NOVEL_ID, CharacterCard(name="test_load", description="描述"))

        loaded = load_card(NOVEL_ID, "test_load")

        assert loaded is not None
        assert loaded.name == "test_load"
        assert loaded.description == "描述"

    def test_delete(self):
        assert save_card(NOVEL_ID, CharacterCard(name="to_delete"))

        assert delete_card(NOVEL_ID, "to_delete")
        assert "to_delete" not in list_cards(NOVEL_ID)

    def test_search(self):
        for name in ["alpha", "beta", "gamma"]:
            save_card(NOVEL_ID, CharacterCard(name=name))

        results = search_cards(NOVEL_ID, "alpha")

        assert "alpha" in results
        assert "beta" not in results

    def test_create_example(self):
        card = create_example_card()
        assert card.name == "林晓月"
        assert len(card.relationships) >= 1
