"""文风量化指标 + 漂移检测测试

覆盖: 指标计算的确定性、空文本容错、基线中位数、漂移分级、AI 套话去重、
禁用词硬告警、容差可覆盖。
"""

from __future__ import annotations

from typing import Dict

from story_engine.style.drift import DEFAULT_TOLERANCES, build_baseline, detect_drift
from story_engine.style.metrics import (
    COMPARABLE_KEYS,
    dialogue_ratio,
    function_word_ratio,
    measure,
    pov_ratios,
    split_paragraphs,
    split_sentences,
)

# 基准文风: 中长句、有对话、多标点（古典叙述腔）
BASELINE_TEXT = (
    "暮色沉下来的时候，檐角的铜铃被风推得响了一声。\n"
    "「你还是来了。」老者没有回头，声音像砂纸擦过木头。\n"
    "他没有答话，只把斗笠摘下，露出半张被刀疤切开的侧脸。\n"
    "雨丝斜斜地扫进廊下，把青石板浸成深色，远处更鼓敲了三下。\n"
)

# 漂移文本: 碎句 + 对话灌水 + AI 套话 + 无正常标点节奏
DRIFTED_TEXT = (
    "他愣住了。真的。太突然了。\n"
    "「你说什么？」他问。「我不知道。」她说。「别问了。」他答。\n"
    "然而，事情并没有那么简单。值得注意的是，一切都变了。毋庸置疑。\n"
)


# ── metrics ──────────────────────────────────────────────


def test_measure_on_empty_text_is_all_zero():
    m = measure("")
    assert m["char_count"] == 0
    assert m["sentence_count"] == 0
    assert m["dialogue_ratio"] == 0.0
    assert m["pov_first_ratio"] == 0.0
    assert set(COMPARABLE_KEYS) <= set(m)


def test_split_sentences_and_paragraphs():
    text = "第一句。第二句！第三句？\n\n第四句。"
    assert split_sentences(text) == ["第一句", "第二句", "第三句", "第四句"]
    assert split_paragraphs(text) == ["第一句。第二句！第三句？", "第四句。"]


def test_dialogue_ratio_supports_cjk_corner_quotes():
    # 引号本身也计入（与 polish.count_dialogue_ratio 口径一致）: 「你来了。」6 字 / 全篇 10 字
    text = "「你来了。」他点头。"
    assert dialogue_ratio(text) == 0.6
    assert dialogue_ratio("") == 0.0


def test_function_word_ratio_distinguishes_register():
    classical = "臣闻之，兵者凶器也，圣人不得已而用之。"
    vernacular = "他说你来了那我们也就可以走了吧。"
    assert function_word_ratio(classical) < function_word_ratio(vernacular)


def test_pov_ratios():
    assert pov_ratios("我看着我")["pov_first_ratio"] == 1.0
    assert pov_ratios("她和他")["pov_third_ratio"] == 1.0
    assert pov_ratios("天在下雨") == {"pov_first_ratio": 0.0, "pov_third_ratio": 0.0}


def test_measure_counts_short_and_long_sentences():
    m = measure("短。这是一个非常长的句子" + "很长" * 30 + "。")
    assert m["short_sentence_ratio"] > 0
    assert m["long_sentence_ratio"] > 0
    assert m["sentence_length_std"] > 0


# ── baseline ─────────────────────────────────────────────


def test_build_baseline_uses_median_and_tolerates_empty_input():
    assert build_baseline([])["dialogue_ratio"] == 0.0

    base = build_baseline([BASELINE_TEXT, BASELINE_TEXT, "完全不同的短句。"])
    # 中位数应贴近重复出现两次的 BASELINE_TEXT，而非被第三个样本带偏
    assert base["dialogue_ratio"] == measure(BASELINE_TEXT)["dialogue_ratio"]
    assert set(COMPARABLE_KEYS) <= set(base)


# ── drift ────────────────────────────────────────────────


def test_same_style_scores_full_and_level_ok():
    baseline = build_baseline([BASELINE_TEXT])
    report = detect_drift(BASELINE_TEXT, baseline)
    assert report["level"] == "ok"
    assert report["score"] == 100
    assert report["alerts"] == []


def test_drifted_text_triggers_alerts_and_suggestions():
    baseline = build_baseline([BASELINE_TEXT])
    report = detect_drift(DRIFTED_TEXT, baseline)

    assert report["level"] in {"warn", "alert"}
    assert report["score"] < 100
    assert report["alerts"], "应有至少一条指标告警"
    assert report["suggestions"], "应给出整改建议"
    assert report["ai_tells"]["count"] > 0
    # 对话占比会显著上升（几乎整段是对话）
    assert report["metrics"]["dialogue_ratio"]["value"] > report["metrics"]["dialogue_ratio"]["baseline"]


def test_ai_tell_hits_are_deduplicated_by_position():
    baseline = build_baseline([BASELINE_TEXT])
    report = detect_drift("然而，他走了。", baseline)
    # "然而，" 同时命中 AI_PATTERNS 与 SOFT_PATTERNS，只应计一次
    assert report["ai_tells"]["count"] == 1
    assert report["ai_tells"]["hits"][0]["match"] == "然而，"


def test_forbidden_words_force_alert_level():
    baseline = build_baseline([BASELINE_TEXT])
    report = detect_drift(BASELINE_TEXT, baseline, forbidden_words=["铜铃", "不存在的词"])
    assert report["level"] == "alert"
    assert report["forbidden_hits"] == [{"word": "铜铃", "count": 1}]
    assert any("禁用词" in a for a in report["alerts"])


def test_tolerances_can_be_relaxed_or_tightened():
    baseline = build_baseline([BASELINE_TEXT])
    loose = {key: ("rel", 100.0) for key in COMPARABLE_KEYS}
    assert detect_drift(DRIFTED_TEXT, baseline, tolerances=loose)["level"] in {"ok", "warn"}

    tight = {key: ("rel", 0.001) for key in COMPARABLE_KEYS}
    tight["dialogue_ratio"] = ("abs", 0.001)
    assert detect_drift(DRIFTED_TEXT, baseline, tolerances=tight)["level"] == "alert"


def test_default_tolerances_cover_every_comparable_metric():
    for key in COMPARABLE_KEYS:
        if key == "pov_third_ratio":  # 与 pov_first_ratio 互补，不重复检测
            continue
        assert key in DEFAULT_TOLERANCES


def test_report_has_metric_details_with_severity():
    baseline = build_baseline([BASELINE_TEXT])
    report = detect_drift(DRIFTED_TEXT, baseline)
    detail = report["metrics"]["avg_sentence_length"]
    assert {"value", "baseline", "deviation", "threshold", "severity", "ratio"} <= set(detail)
    assert detail["severity"] in {"ok", "warn", "alert"}
    assert report["level_reason"]


def test_level_uses_aggregation_not_single_metric():
    """单指标轻度偏离只应 warn; 至少 4 项同时偏离才升 alert（防误报）。"""
    from story_engine.style.drift import ALERT_MILD_COUNT, ToleranceSpec

    baseline = build_baseline([BASELINE_TEXT])
    # 只让"对话占比"偏离：把一个轻微超阈值的容差批量套在其他指标上并不现实,
    # 这里直接验证聚合门槛常量与聚合行为的一致性。
    assert ALERT_MILD_COUNT >= 3

    only_dialogue: Dict[str, ToleranceSpec] = {key: ("rel", 999.0) for key in COMPARABLE_KEYS}
    # 0.12 的绝对容差让"对话占比"偏差落在 1-2 倍容差之间（mild）, 不构成 strong
    only_dialogue["dialogue_ratio"] = ("abs", 0.12)
    report = detect_drift(DRIFTED_TEXT, baseline, tolerances=only_dialogue)
    assert report["level"] == "warn"
    assert len(report["alerts"]) == 1
