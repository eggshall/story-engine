"""测试：灵魂记忆数据模型"""
from __future__ import annotations

from story_engine.tools.memory_models import (
    SoulMemory,
    CharacterMemory,
    PlotMemory,
    WritingStyleMemory,
    UserProfile,
    StyleProfile,
    WritingSample,
)


class TestCharacterMemory:
    def test_default(self):
        cm = CharacterMemory(name="主角")
        assert cm.name == "主角"
        assert cm.voice == ""
        assert cm.key_traits == []

    def test_with_voice(self):
        cm = CharacterMemory(name="配角", voice="憨厚老实", personality_notes="忠诚")
        assert cm.voice == "憨厚老实"
        assert cm.personality_notes == "忠诚"


class TestSoulMemory:
    def test_default(self):
        mem = SoulMemory(novel_id="id1", novel_title="测试")
        assert mem.novel_id == "id1"
        assert mem.novel_title == "测试"
        assert len(mem.characters) == 0

    def test_update_character_voice(self):
        mem = SoulMemory(novel_id="id", novel_title="T")
        mem.update_character_voice("林晓月", "温柔聪慧")
        assert "林晓月" in mem.characters
        assert mem.characters["林晓月"].voice == "温柔聪慧"

    def test_update_plot(self):
        mem = SoulMemory(novel_id="id", novel_title="T")
        mem.update_plot(chapter_summary="主角进入秘境", threads=["秘境"])
        assert mem.plot.last_chapter_summary == "主角进入秘境"
        assert "秘境" in mem.plot.active_threads

    def test_update_character_twice(self):
        mem = SoulMemory(novel_id="id", novel_title="T")
        mem.update_character_voice("张三", "严肃")
        mem.update_character_voice("张三", "幽默")
        assert mem.characters["张三"].voice == "幽默"

    def test_user_notes(self):
        mem = SoulMemory(novel_id="id", novel_title="T")
        mem.user_notes = "多写内心戏"
        mem.custom_system_prompt = "偏好古风"
        mem.writing_mode_pref = "细腻"
        assert mem.user_notes == "多写内心戏"
        assert mem.custom_system_prompt == "偏好古风"
        assert mem.writing_mode_pref == "细腻"

    def test_style_fields(self):
        mem = SoulMemory(novel_id="id", novel_title="T")
        mem.style.tone = "轻松"
        mem.style.pov = "第三人称"
        mem.style.pacing = "快"
        assert mem.style.tone == "轻松"
        assert mem.style.pov == "第三人称"

    def test_updated_timestamp(self):
        import datetime
        mem = SoulMemory(novel_id="id", novel_title="T")
        before = mem.updated
        mem.update_plot(chapter_summary="更新")
        assert mem.updated >= before


class TestUserProfile:
    def test_default(self):
        up = UserProfile()
        assert up.preferred_name == ""
        assert up.default_writing_mode == "balance"

    def test_custom_values(self):
        up = UserProfile(
            preferred_name="作家",
            default_writing_mode="细腻",
            common_genres=["玄幻", "仙侠"],
            pet_phrases=["不过"],
        )
        assert up.preferred_name == "作家"
        assert "玄幻" in up.common_genres


class TestStyleProfile:
    def test_default(self):
        sp = StyleProfile(novel_id="n1", name="分析")
        assert sp.novel_id == "n1"
        assert sp.name == "分析"
        assert sp.samples == []

    def test_with_samples(self):
        sp = StyleProfile(
            novel_id="n1", name="分析",
            avg_sentence_length=12.5,
            dialogue_percentage=0.3,
            writing_techniques=["短句开篇", "排比"],
        )
        sp.samples.append(WritingSample(source_name="金庸", text_snippet="飞雪连天"))
        assert sp.avg_sentence_length == 12.5
        assert sp.dialogue_percentage == 0.3
        assert len(sp.writing_techniques) == 2
        assert len(sp.samples) == 1
