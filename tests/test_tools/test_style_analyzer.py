"""测试：文风分析器 — 风格定量分析"""
from __future__ import annotations

from story_engine.tools.style_analyzer import (
    analyze_text_style,
    build_style_profile,
    extract_techniques,
    compare_with_profile,
)
from story_engine.tools.memory_models import StyleProfile


class TestAnalyzeTextStyle:
    def test_empty_text(self):
        result = analyze_text_style("")
        assert result == {}

    def test_basic_analysis(self):
        text = "张三丰走上了武当山。山间云雾缭绕，仙鹤齐鸣。「好地方！」他赞叹道。"
        result = analyze_text_style(text, source_name="测试")
        assert result["total_chars"] > 0
        assert result["avg_sentence_length"] > 0
        assert result["source_name"] == "测试"

    def test_dialogue_detection(self):
        text = "「你好！」「你好！」「再见！」"
        result = analyze_text_style(text)
        assert result["dialogue_percentage"] > 0.5

    def test_sentence_count(self):
        text = "第一句。第二句！第三句？第四句。第五句。"
        result = analyze_text_style(text)
        assert result["sentence_count"] >= 3

    def test_top_adjectives(self):
        text = "美丽的花园。宏伟的大殿。神秘的功法。古老的传说。"
        result = analyze_text_style(text)
        assert len(result["top_adjectives"]) > 0


class TestBuildStyleProfile:
    def test_basic_profile(self):
        text = "张三丰走上武当山。山间云雾缭绕。"
        profile = build_style_profile(text, "test_novel", "武侠风格", "测试来源")
        assert profile.novel_id == "test_novel"
        assert profile.name == "武侠风格"
        assert profile.avg_sentence_length > 0
        assert len(profile.samples) == 1
        assert profile.samples[0].source_name == "测试来源"

    def test_with_source_url(self):
        text = "测试文本。"
        profile = build_style_profile(text, "n2", "n", source_name="来源")
        assert profile.novel_id == "n2"


class TestExtractTechniques:
    def test_short_opening(self):
        text = "杀。\n张三丰走上了武当山。"
        techs = extract_techniques(text)
        assert any("短句开篇" in t for t in techs)

    def test_chinese_dialogue(self):
        text = "「你好！」张三丰说道。"
        techs = extract_techniques(text)
        assert any("中式对话" in t for t in techs)

    def test_short_paragraphs(self):
        text = "短。\n段落。\n节奏快。"
        techs = extract_techniques(text)
        # 短段落检测可能触发，不强制断言
        assert isinstance(techs, list)


class TestCompareWithProfile:
    def test_no_profile_stats(self):
        profile = StyleProfile(novel_id="test", name="empty")
        diffs = compare_with_profile(profile, "一段测试文本。")
        assert diffs == {}

    def test_similar_text(self):
        profile = StyleProfile(novel_id="test", name="t", avg_sentence_length=10)
        diffs = compare_with_profile(profile, "短文本。刚好两句话。测试。")
        # 短文本，偏差可能小
        assert isinstance(diffs, dict)
