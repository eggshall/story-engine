"""测试：精修系统"""
from story_engine.polish import (
    DeAIFilter, detect_narrative_style, analyze_rhythm,
    check_style_consistency, check_continuity,
)
from story_engine.core.models import Chapter


class TestDeAIFilter:
    def test_clean_basic(self):
        filter_ = DeAIFilter()
        text = "然而，他并没有放弃。值得注意的是，他成功了。"
        cleaned = filter_.clean(text)
        # AI_PATTERNS 移除逗号，部分词整词删除
        assert "，" not in cleaned  # 逗号被移除
        assert "然而" in cleaned    # "然而"仅移除逗号
        # "值得注意的是" 整词被删除（替换为空）

    def test_clean_no_change(self):
        filter_ = DeAIFilter()
        text = "他大步流星走进房间，目光如炬。"
        cleaned = filter_.clean(text)
        assert cleaned == text  # 无 AI 套话应保持不变

    def test_scan_soft(self):
        filter_ = DeAIFilter()
        findings = filter_.scan_soft("然而，事情并没有那么简单。")
        assert len(findings) >= 1

    def test_report(self):
        filter_ = DeAIFilter()
        report = filter_.report("然而，他来了。值得一提的是，他很强。")
        assert report["soft_hits_count"] >= 2
        assert report["removed_chars"] > 0


class TestStyleAnalysis:
    def test_dialogue_ratio(self):
        text = "他说：「你好。」她说：「再见。」"
        analysis = detect_narrative_style(text)
        assert analysis["character_count"] > 0
        assert "dialogue_ratio" in analysis
        assert "avg_sentence_length" in analysis

    def test_empty_text(self):
        analysis = detect_narrative_style("")
        assert analysis["sentence_count"] == 0


class TestRhythm:
    def test_analyze_rhythm(self):
        text = "突然，一道身影闪过！没想到他突破了！原来真相是这样的！难道这就是天意？"
        analysis = analyze_rhythm(text)
        assert analysis["hook_count"] > 0
        assert analysis["rating"] != ""

    def test_empty_text(self):
        analysis = analyze_rhythm("")
        assert analysis["hook_count"] == 0


class TestContinuity:
    def test_check_continuity(self):
        text = "林晓月站在山巅。寒风吹过她的长发。"
        result = check_continuity(text, ["林晓月"])
        assert result["consistent"]
        assert len(result["issues"]) == 0

    def test_missing_character(self):
        text = "故事开始了。"
        result = check_continuity(text, ["林晓月"])
        assert not result["consistent"]

    def test_no_known_names(self):
        result = check_continuity("一些文字", [])
        assert result["consistent"]


class TestStyleConsistency:
    def test_single_chapter(self):
        result = check_style_consistency([
            Chapter(chapter_number=1, content="第一章内容。" * 20)
        ])
        assert result["consistent"]

    def test_multiple_chapters(self):
        result = check_style_consistency([
            Chapter(chapter_number=1, content="他说：你好。" * 10),
            Chapter(chapter_number=2, content="她说：再见。" * 10),
        ])
        assert "chapter_styles" in result
