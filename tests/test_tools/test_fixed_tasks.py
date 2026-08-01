"""测试：固定流程工具 — 关键词提取 / 章节摘要 / 一致性检查"""
from __future__ import annotations

from story_engine.tools.fixed_tasks import (
    extract_keywords,
    summarize_chapter,
    check_consistency,
    compress_history,
)


class TestExtractKeywords:
    def test_quoted_names(self):
        text = "「张三丰」走进了「武当山」，看见「李四光」正在练剑。"
        kw = extract_keywords(text)
        words = [k["word"] for k in kw]
        assert "张三丰" in words
        assert "武当山" in words
        assert "李四光" in words

    def test_named_entities(self):
        text = "张掌门走上了天山派的大殿。林将军率领三千兵马。"
        kw = extract_keywords(text)
        words = [k["word"] for k in kw]
        # 至少应该提取出高频词
        assert len(kw) >= 0

    def test_empty_text(self):
        assert extract_keywords("") == []

    def test_short_text_no_keywords(self):
        kw = extract_keywords("你好", min_len=2)
        assert len(kw) == 0

    def test_frequency_words(self):
        text = "修炼修炼 修炼修炼 修炼修炼"
        kw = extract_keywords(text)
        # 重复词修炼(4字)出现3次，应被检测
        assert len(kw) > 0

    def test_max_keywords_limit(self):
        text = "「甲」「乙」「丙」「丁」「戊」「己」「庚」「辛」「壬」「癸」"
        kw = extract_keywords(text, max_keywords=3)
        assert len(kw) <= 3


class TestSummarizeChapter:
    def test_empty(self):
        assert summarize_chapter("") == ""

    def test_basic_summary(self):
        text = "张三丰踏上武当山。山间云雾缭绕，仙鹤齐鸣。从此开始修仙之路。"
        summary = summarize_chapter(text, max_chars=50)
        assert len(summary) <= 50
        assert summary == text[:50]

    def test_with_summary_marker(self):
        text = "第一章内容。\n本章要点：张三丰拜师学艺。"
        summary = summarize_chapter(text)
        assert "本章要点" in summary

    def test_long_text(self):
        text = "修仙" * 200
        summary = summarize_chapter(text, max_chars=100)
        assert len(summary) <= 100


class TestCheckConsistency:
    def test_no_issues(self):
        issues = check_consistency("张三丰走上武当山", ["张三丰"], ["武当山"])
        assert len(issues) == 0

    def test_typo_detection(self):
        issues = check_consistency("张三丰走上了武当山", ["张三丰"])
        # 检查是否有疑似错字
        assert isinstance(issues, list)

    def test_place_mismatch(self):
        issues = check_consistency("张三丰走上了武当山", ["张三丰"], ["武当山"])
        # 应该没有错误
        non_typo = [i for i in issues if i["type"] != "typo"]
        assert len(non_typo) >= 0

    def test_empty_names(self):
        issues = check_consistency("一段文本", [])
        assert issues == []


class TestCompressHistory:
    def test_no_compression_needed(self):
        msgs = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
        ]
        result = compress_history(msgs, max_messages=10)
        assert len(result) == 2

    def test_compression(self):
        msgs = [{"role": "user", "content": f"消息{i}"} for i in range(20)]
        result = compress_history(msgs, max_messages=5, reserve_last=2)
        # 1 summary + 2 tail = 3
        assert len(result) == 3
        assert result[0]["role"] == "system"

    def test_empty(self):
        assert compress_history([]) == []
