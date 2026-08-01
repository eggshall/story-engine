"""测试：核心数据模型"""
import pytest
from story_engine.core.models import (
    CharacterCard, Relationship, LoreEntry, CharacterLoreBook,
    LoreBook, LorebookEntry, ChapterOutline, Chapter, Novel,
    LLMConfig, ModelConfig,
)


class TestCharacterCard:
    def test_minimal_card(self):
        card = CharacterCard(name="测试角色")
        assert card.name == "测试角色"
        assert card.version == "2.0"
        assert card.tags == []

    def test_full_card(self):
        card = CharacterCard(
            name="林晓月",
            description="天才少女",
            personality="外冷内热",
            tags=["修仙", "女主"],
            relationships=[Relationship(target="云逸风", relation="师兄")],
        )
        assert len(card.relationships) == 1
        assert card.relationships[0].target == "云逸风"

    def test_to_prompt_block(self):
        card = CharacterCard(name="测试", description="描述", personality="性格")
        block = card.to_prompt_block()
        assert "【角色名】测试" in block
        assert "【描述】描述" in block
        assert "【性格】性格" in block

    def test_to_json_dict(self):
        card = CharacterCard(name="测试")
        d = card.to_json_dict()
        assert d["name"] == "测试"
        assert d["version"] == "2.0"


class TestNovel:
    def test_empty_novel(self):
        n = Novel(title="测试小说")
        assert n.chapter_count() == 0
        assert n.word_count() == 0

    def test_with_chapters(self):
        n = Novel(title="测试")
        n.chapters.append(Chapter(chapter_number=1, content="你好世界", word_count=4))
        assert n.chapter_count() == 1
        assert n.word_count() == 4

    def test_serialization(self):
        n = Novel(title="测试", author="作者", genre="玄幻")
        n.chapters.append(Chapter(chapter_number=1, content="内容"))
        d = n.model_dump(exclude_none=True)
        assert d["title"] == "测试"
        assert len(d["chapters"]) == 1


class TestLoreModels:
    def test_lorebook_entry(self):
        entry = LorebookEntry(keys=["魔法", "法力"], content="魔法设定")
        assert "魔法" in entry.keys
        assert entry.priority == 10

    def test_lorebook(self):
        book = LoreBook(name="世界观")
        book.entries["magic"] = LorebookEntry(keys=["魔法"], content="魔法设定")
        assert len(book.entries) == 1

    def test_chapter_outline(self):
        outline = ChapterOutline(chapter_number=1, summary="概要")
        assert outline.chapter_number == 1
        assert outline.word_estimate == 2000
