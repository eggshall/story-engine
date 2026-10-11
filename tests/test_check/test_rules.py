"""N5 契约测试：A 类校验器 5 条（章末钩子/对话占比/段落长度/视角一致性/禁词与 AI 味）。

验收依据（计划书 2.2）：**构造"无钩子/对话失衡/超长段/视角突跳/命中禁词"的样例文本，
逐条命中并给出定位**；另外（评审项）"无基线时返回 ok/skipped 而非误报 alert"。

这组测试的两个坚持：

- 每条规则都有"命中"与"不命中"两侧（只测命中会纵容永远报错的实现）；
- 断言**级别 + 定位**（不是只断言"有 findings"），因为审稿页要靠定位跳转。
"""

from __future__ import annotations

import pytest

from story_engine.check.rules import (
    PARAGRAPH_MAX_CHARS,
    Baseline,
    build_baseline,
    run_rules,
)

HOOK_TAIL = "他握紧扶手。突然，舱体猛地一震。"

# 干净章：有钩子（突然/灯灭了）、段落都短、视角统一（第一人称）、无套话
CLEAN_CHAP_TEXT = "我推开门，我听见风。突然，灯灭了。\n\n我站住，我没敢回头。"


def _finding(report, rule_id, level):
    return [f for f in report.findings if f.rule_id == rule_id and f.level == level]


class TestChapterHook:
    def test_no_hook_is_flagged_with_location(self):
        text = "他走进舱门。\n\n他看了一眼仪表。\n\n一切都很正常，任务按计划推进。"

        report = run_rules(text, rules=("chapter_hook",))

        hits = _finding(report, "chapter_hook", "warn")
        assert len(hits) == 1
        loc = hits[0].location
        assert loc is not None
        assert loc.end == len(text)
        assert loc.excerpt.strip()            # 有摘录，审稿页能展示
        assert "钩子" in hits[0].suggestion

    def test_hook_keyword_passes(self):
        report = run_rules(f"他一动不动。\n\n{HOOK_TAIL}", rules=("chapter_hook",))

        assert _finding(report, "chapter_hook", "ok")
        assert not _finding(report, "chapter_hook", "warn")

    def test_suspense_question_passes(self):
        text = "信号来自哪里？他盯着屏幕。\n\n那究竟是谁发出来的？"

        report = run_rules(text, rules=("chapter_hook",))

        assert _finding(report, "chapter_hook", "ok")


class TestParagraphLength:
    def test_overlong_paragraph_is_located(self):
        long_para = "他" + "继续向前走，" * 60          # 远超 300 字
        text = f"开场很短。\n\n{long_para}\n\n结尾很短。"

        report = run_rules(text, rules=("paragraph_length",))

        hits = _finding(report, "paragraph_length", "warn")
        assert len(hits) == 1
        loc = hits[0].location
        assert loc is not None and loc.paragraph_index == 1
        assert text[loc.start:loc.end] == long_para     # 定位必须精确指向那一段
        assert str(PARAGRAPH_MAX_CHARS) in hits[0].suggestion

    def test_normal_paragraphs_pass(self):
        text = "第一段。\n\n第二段也不长。\n\n第三段。"

        report = run_rules(text, rules=("paragraph_length",))

        assert _finding(report, "paragraph_length", "ok")


class TestPovConsistency:
    def test_quoted_third_person_dialogue_is_not_a_jump(self):
        """P1-1：第一人称正文里的对白说"他"是在说别人，剥掉引号后不该判视角突跳。"""
        text = (
            "我推开门，我看见窗边的光。\n\n"
            "「他昨天就走了，他说他不会再回来。」我说。\n\n"
            "我叹了口气，我轻轻关上门。"
        )

        report = run_rules(text, rules=("pov_consistency",))

        assert _finding(report, "pov_consistency", "ok")
        assert not _finding(report, "pov_consistency", "warn")

    def test_object_pronoun_does_not_switch_pov(self):
        """P1-2：第一人称里写物件（`它`）不算视角切换（只按 他/她 判）。"""
        text = (
            "我拿起它，我看了它一眼。\n\n"
            "我把它放回桌上，我知道它在等。\n\n"
            "它静静地躺在那里，它泛着冷光。"
        )

        report = run_rules(text, rules=("pov_consistency",))

        assert _finding(report, "pov_consistency", "ok")

    def test_jump_suggestion_names_the_actual_person(self):
        """P1-3：建议文案必须说清是第几人称（原来是单元素集合渲染成"第一/第三人称"）。"""
        text = (
            "我推开门，我听见风。\n\n"
            "我数着呼吸，我知道来不及了。\n\n"
            "他站在走廊尽头，他的影子被灯拉得很长。\n\n"
            "我最终迈了出去。"
        )

        report = run_rules(text, rules=("pov_consistency",))

        warn = _finding(report, "pov_consistency", "warn")[0]
        assert "第三人称标记" in warn.suggestion
        assert "第一/第三人称" not in warn.suggestion

    def test_pov_jump_is_flagged(self):
        # 主视角第一人称（3 段），第 3 段突然只有第三人称标记
        text = (
            "我推开门，我听见风从缝隙里钻进来。\n\n"
            "我数着呼吸，我知道再等下去就来不及了。\n\n"
            "他站在走廊尽头，他的影子被灯拉得很长。\n\n"
            "我最终迈了出去。"
        )

        report = run_rules(text, rules=("pov_consistency",))

        hits = _finding(report, "pov_consistency", "warn")
        assert len(hits) == 1
        assert hits[0].details["dominant"] == "first"
        assert hits[0].location is not None
        assert hits[0].location.paragraph_index == 2
        assert "第三人称" in hits[0].suggestion

    def test_consistent_pov_passes(self):
        # 每段都要有足够的人称标记（POV_MIN_MARKERS=2），否则规则会判定"样本不足"
        text = (
            "我推开门，我听见风。\n\n"
            "我数着呼吸，我知道来不及了。\n\n"
            "我迈了出去，我没有回头。"
        )

        report = run_rules(text, rules=("pov_consistency",))

        assert _finding(report, "pov_consistency", "ok")

    def test_too_few_marked_paragraphs_is_skipped_not_ok(self):
        """样本不足时必须是 skipped（"无法判定"），而不是假装 ok。"""
        report = run_rules("他走了。\n\n很短的一段。", rules=("pov_consistency",))

        assert _finding(report, "pov_consistency", "skipped")


class TestAiFlavor:
    def test_normal_chinese_is_not_flagged(self):
        """P0-2：`然而，/但是，/在…的…下` 是正常中文，不能当硬告警（原来会大面积误报）。"""
        text = (
            "但是，他还是答应了。\n\n"
            "在夜色的笼罩下，他慢慢往前走。\n\n"
            "然而他停下了。"
        )

        report = run_rules(text, rules=("ai_flavor",))

        hard_warns = [f for f in _finding(report, "ai_flavor", "warn") if "AI 套话" in f.suggestion]
        assert hard_warns == [], [f.suggestion for f in hard_warns]

    def test_real_tell_is_located(self):
        text = "他沉默了。值得注意的是，仪表盘的读数在缓慢下降。"

        report = run_rules(text, rules=("ai_flavor",))

        hits = _finding(report, "ai_flavor", "warn")
        located = [h for h in hits if h.location and "值得注意的是" in h.location.excerpt]
        assert located, [h.suggestion for h in hits]
        loc = located[0].location
        assert text[loc.start:loc.end] == "值得注意的是"
        assert located[0].details["tell"] == "值得注意的是"

    def test_soft_patterns_aggregate(self):
        text = "然而他停下了。但是风更大了。毕竟他答应了。不由得握紧手。"

        report = run_rules(text, rules=("ai_flavor",))

        warnings = _finding(report, "ai_flavor", "warn")
        assert any("软性套话" in w.suggestion for w in warnings)

    def test_clean_text_passes(self):
        text = "他推开门。风灌进来，纸页翻了一下。他没说话。"

        report = run_rules(text, rules=("ai_flavor",))

        assert _finding(report, "ai_flavor", "ok")


class TestDialogueRatio:
    def test_without_baseline_it_is_skipped_not_alert(self):
        """评审要求：无基线不得误报（宁可"无法判定"）。"""
        text = "他推开门。风灌进来。" * 20

        report = run_rules(text, rules=("dialogue_ratio",), baseline=Baseline())

        hits = _finding(report, "dialogue_ratio", "skipped")
        assert len(hits) == 1
        assert "基线" in hits[0].suggestion

    def test_matching_baseline_passes(self):
        """基线取自被测文本自身 → 必须 ok（不手搓比例，避免测试自己算错）。"""
        from story_engine.style import metrics

        text = "他说：「我们该走了，这里不能再待。」风从缝隙里钻进来，谁也没有动。"
        baseline = Baseline(dialogue_ratio=metrics.dialogue_ratio(text), source="previous_chapters")

        report = run_rules(text, rules=("dialogue_ratio",), baseline=baseline)

        hit = _finding(report, "dialogue_ratio", "ok")[0]
        assert hit.details["delta_pp"] == 0.0

    def test_within_tolerance_band_passes(self):
        """容忍带 ±15 个百分点：比基线高 10 个百分点仍算 ok。"""
        from story_engine.style import metrics

        text = "他说：「我们该走了，这里不能再待。」风从缝隙里钻进来，谁也没有动。"
        baseline = Baseline(
            dialogue_ratio=metrics.dialogue_ratio(text) + 0.10, source="previous_chapters"
        )

        report = run_rules(text, rules=("dialogue_ratio",), baseline=baseline)

        assert _finding(report, "dialogue_ratio", "ok")

    def test_far_off_baseline_warns_with_numbers(self):
        baseline = Baseline(dialogue_ratio=0.40, source="previous_chapters")
        text = "他推开门，风灌进来，纸页翻动，走廊里没有人。"

        report = run_rules(text, rules=("dialogue_ratio",), baseline=baseline)

        hits = _finding(report, "dialogue_ratio", "warn")
        assert len(hits) == 1
        assert hits[0].details["baseline_source"] == "previous_chapters"
        assert hits[0].details["delta_pp"] < 0            # 实际比基线少
        assert "偏少" in hits[0].suggestion


class TestBaseline:
    def test_real_profile_shape_is_used(self):
        """P0-1：真实画像用中文键 + score 字典（style/db.py::DIALOGUE_RATIO），必须认出来。"""
        real_shape = {
            "对话比例": {"value": "对话较多", "score": 0.42, "说明": "人物对白占比偏高"},
            "平均句长": {"value": "中等", "score": 0.5},
        }

        baseline = build_baseline(
            profile_features=real_shape,
            previous_texts=["他说：「走。」" * 10, "他走了很久。"],
        )

        assert baseline.source == "profile"          # 画像优先于前序章节
        assert baseline.dialogue_ratio == pytest.approx(0.42)

    def test_profile_without_numeric_score_falls_back(self):
        """只有定性描述、没有可用数值时，必须降级到前序章节（而不是假装用了画像）。"""
        qualitative = {"对话比例": {"value": "对话较多"}}   # 没有 score

        baseline = build_baseline(
            profile_features=qualitative,
            previous_texts=["他说：「走。」" * 10, "他走了很久。"],
        )

        assert baseline.source == "previous_chapters"

    def test_english_numeric_key_still_supported(self):
        baseline = build_baseline(profile_features={"dialogue_ratio": 0.35})

        assert baseline.source == "profile"
        assert baseline.dialogue_ratio == pytest.approx(0.35)

    def test_previous_chapters_median(self):
        chapters = [
            "「走。」" * 10,                      # 高对话
            "他走了很久，没有说话。",              # 低对话
            "「等等。」" * 8,
        ]

        baseline = build_baseline(previous_texts=chapters)

        assert baseline.source == "previous_chapters"
        assert 0 <= float(baseline.dialogue_ratio) <= 1

    def test_single_previous_chapter_is_not_enough(self):
        baseline = build_baseline(previous_texts=["只有一章「走。」"])

        assert baseline.source == "none"
        assert baseline.has_dialogue is False

    def test_empty_profile_value_ignored(self):
        baseline = build_baseline(profile_features={"对话比例": None})

        assert baseline.source == "none"


class TestReportShape:
    def test_full_report_runs_all_five_rules(self):
        text = "他推开门。\n\n" + "他继续向前走，" * 60 + "\n\n" + "一切都结束了。"

        report = run_rules(text)
        payload = report.to_dict()

        assert set(report.rules_run) == {
            "chapter_hook", "dialogue_ratio", "paragraph_length", "pov_consistency", "ai_flavor"
        }
        assert payload["level"] in ("alert", "warn", "ok")     # skipped 不进整章级别（P1-5）
        assert set(payload["summary"]) == {"alert", "warn", "ok", "skipped"}
        assert payload["text_length"] == len(text)
        assert set(payload["by_rule"]) <= {
            "chapter_hook", "dialogue_ratio", "paragraph_length", "pov_consistency", "ai_flavor"
        }
        # 每条发现都必须能直接喂给审稿页：级别 + 定位 + 建议
        for item in payload["findings"]:
            assert set(item) >= {"rule_id", "rule_name", "level", "suggestion", "location", "details"}

    def test_skipped_is_flagged_as_incomplete_not_as_problem(self):
        """P1-5：干净文本 + 无基线 → 级别 ok，但必须标记 incomplete 与 skipped_rules。"""
        report = run_rules(CLEAN_CHAP_TEXT)

        assert report.level == "ok"
        assert report.incomplete is True
        assert report.skipped_rules == ["dialogue_ratio"]

    def test_incomplete_false_when_baseline_present(self):
        baseline = Baseline(dialogue_ratio=0.0, source="previous_chapters")

        report = run_rules(CLEAN_CHAP_TEXT, baseline=baseline)

        assert report.incomplete is False
        assert report.skipped_rules == []

    def test_worst_level_wins(self):
        # 含超长段（warn）→ 整章至少 warn
        report = run_rules("他" + "走，" * 200)

        assert report.level == "warn"
        assert report.summary()["warn"] >= 1

    def test_by_rule_aggregates_multiple_findings(self):
        text = "他" + "走，" * 200 + "\n\n" + "他" + "看，" * 200

        report = run_rules(text, rules=("paragraph_length",))

        assert report.by_rule()["paragraph_length"]["warn"] == 2

    def test_deterministic(self):
        text = "他推开门。突然，灯灭了。"

        assert run_rules(text).to_dict() == run_rules(text).to_dict()

    def test_unknown_rule_raises(self):
        with pytest.raises(ValueError):
            run_rules("文本", rules=("not_a_rule",))

    def test_empty_text_does_not_crash(self):
        report = run_rules("")

        assert report.text_length == 0
        assert report.findings                    # 仍给出各规则的判定（多为 warn/skipped）
