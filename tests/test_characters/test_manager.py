"""测试：角色卡管理器"""
import tempfile
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
from story_engine.core.models import CharacterCard


class TestCharacterManager:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        """使用临时目录测试"""
        self.tmp_dir = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.characters.manager.CHARACTERS_DIR", self.tmp_dir)
        yield

    def test_save_and_list(self):
        card = CharacterCard(name="test_char")
        assert save_card(card)
        cards = list_cards()
        assert "test_char" in cards

    def test_load(self):
        card = CharacterCard(name="test_load", description="描述")
        save_card(card)
        loaded = load_card("test_load")
        assert loaded is not None
        assert loaded.name == "test_load"
        assert loaded.description == "描述"

    def test_delete(self):
        card = CharacterCard(name="to_delete")
        save_card(card)
        assert delete_card("to_delete")
        assert "to_delete" not in list_cards()

    def test_search(self):
        for name in ["alpha", "beta", "gamma"]:
            save_card(CharacterCard(name=name))
        results = search_cards("alpha")
        assert "alpha" in results
        assert "beta" not in results

    def test_create_example(self):
        card = create_example_card()
        assert card.name == "林晓月"
        assert len(card.relationships) >= 1
