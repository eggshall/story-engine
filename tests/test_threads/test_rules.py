"""N9 校验契约：两条 A 类规则（确定性、不调模型、无账本不猜）。

依据 §9.1.1 与 N5 建立的两条铁律：
① 无基线/无账本 → 返回 `skipped` 并说明原因，**不拿拍脑袋的阈值误报**；
② `level` 只表达可执行结论（alert/warn/ok），跳过用 `skipped_rules` / `incomplete` 表达。
"""

from __future__ import annotations

import pytest

from story_engine.check.rules import (
    THREAD_DANGLE_THRESHOLD,
    THREAD_RULES,
    ThreadContext,
    check_dangling_threads,
    check_unknown_payoff,
    run_rules,
)
from story_engine.core.models import PlotThread


def _t(tid: str, **kw) -> PlotThread:
    base = dict(id=tid, title=f"线索{tid}", status="planted", planted_chapter=1)
    base.update(kw)
    return PlotThread(**base)


def _ledger(*threads: PlotThread) -> dict:
    return {t.id: t for t in threads}


class TestDanglingThreads:
    def test_no_ledger_is_skipped(self):
        findings = check_dangling_threads(None, chapter_number=50)
        assert len(findings) == 1 and findings[0].level == "skipped"
        assert "账本" in findings[0].suggestion or "账本" in findings[0].rule_name + findings[0].suggestion

    def test_empty_ledger_is_skipped(self):
        findings = check_dangling_threads({}, chapter_number=50)
        assert [f.level for f in findings] == ["skipped"]

    def test_within_threshold_is_ok(self):
        findings = check_dangling_threads(
            _ledger(_t("t1", planted_chapter=1)), chapter_number=THREAD_DANGLE_THRESHOLD + 1
        )
        assert [f.level for f in findings] == ["ok"]

    def test_beyond_threshold_warns(self):
        findings = check_dangling_threads(
            _ledger(_t("t1", planted_chapter=1)), chapter_number=THREAD_DANGLE_THRESHOLD + 5
        )
        assert [f.level for f in findings] == ["warn"]
        assert findings[0].rule_id == "dangling_threads"

    def test_far_beyond_threshold_alerts(self):
        findings = check_dangling_threads(
            _ledger(_t("t1", planted_chapter=1)),
            chapter_number=THREAD_DANGLE_THRESHOLD * 2 + 5,
        )
        assert [f.level for f in findings] == ["alert"]

    def test_resolved_threads_ignored(self):
        findings = check_dangling_threads(
            _ledger(
                _t("done", status="paid_off", payoff_chapter=10),
                _t("dropped", status="abandoned"),
            ),
            chapter_number=999,
        )
        assert [f.level for f in findings] == ["ok"], "已回收/已放弃不算悬空"

    def test_not_yet_planted_ignored(self):
        findings = check_dangling_threads(
            _ledger(_t("future", planted_chapter=500)), chapter_number=10
        )
        assert [f.level for f in findings] == ["ok"]

    def test_suggestion_carries_thread_title(self):
        findings = check_dangling_threads(
            _ledger(_t("t1", title="怀表的来历", planted_chapter=1)),
            chapter_number=THREAD_DANGLE_THRESHOLD + 5,
        )
        assert "怀表的来历" in findings[0].suggestion


class TestUnknownPayoff:
    def test_no_ledger_is_skipped(self):
        assert [f.level for f in check_unknown_payoff(None, known_chapters=[1, 2])] == ["skipped"]

    def test_no_known_chapters_is_skipped(self):
        findings = check_unknown_payoff(_ledger(_t("t1", payoff_chapter=9)), known_chapters=[])
        assert [f.level for f in findings] == ["skipped"]

    def test_planned_future_payoff_is_not_an_error(self):
        """评审 P2-2：作者按「计划」填的未来回收章不是错误 —— 只有声称已回收但章不存在才算。

        误报过一次：`payoff_chapter=30` + `known_chapters=[1,2,3]` 曾直接 alert。
        """
        findings = check_unknown_payoff(
            _ledger(_t("t1", status="planted", payoff_chapter=30)), known_chapters=[1, 2, 3]
        )
        assert [f.level for f in findings] == ["ok"]

    def test_payoff_pointing_nowhere_alerts(self):
        findings = check_unknown_payoff(
            _ledger(_t("t1", status="paid_off", payoff_chapter=99)), known_chapters=[1, 2, 3]
        )
        assert [f.level for f in findings] == ["alert"]
        assert findings[0].rule_id == "unknown_payoff"

    def test_valid_payoff_is_ok(self):
        findings = check_unknown_payoff(
            _ledger(_t("t1", status="paid_off", payoff_chapter=2)), known_chapters=[1, 2, 3]
        )
        assert [f.level for f in findings] == ["ok"]

    def test_unpaid_thread_without_payoff_is_ok(self):
        findings = check_unknown_payoff(_ledger(_t("t1")), known_chapters=[1, 2, 3])
        assert [f.level for f in findings] == ["ok"], "没填回收章不算错误"


class TestRunRulesIntegration:
    def test_thread_rules_are_a_separate_opt_in_group(self):
        """铁律：伏笔规则不混进默认规则组（否则所有旧书的报告形状都会变）。

        断言的是**行为**——默认组跑出来的报告里不含伏笔规则——而不是
        `THREAD_RULES == (...)` 这种"把实现里的常量再抄一遍"的写法（评审 P2-9：
        改实现测试就跟着改，等于没测）。
        """
        from story_engine.check.rules import DEFAULT_RULES

        report = run_rules("正文" * 300)

        assert set(report.rules_run) == set(DEFAULT_RULES)
        assert not (set(report.by_rule()) & set(THREAD_RULES))
        # 不变式：两组规则不许重叠（重叠会让"只跑默认组"也带出账本规则）
        assert not (set(THREAD_RULES) & set(DEFAULT_RULES))

    def test_run_rules_with_thread_context(self):
        ctx = ThreadContext(
            threads=_ledger(_t("t1", planted_chapter=1)),
            chapter_number=THREAD_DANGLE_THRESHOLD + 5,
            known_chapters=[1, 2, 3],
        )
        report = run_rules("正文" * 300, rules=THREAD_RULES, thread_context=ctx)

        assert set(report.rules_run) == set(THREAD_RULES)
        assert "dangling_threads" in report.by_rule()
        assert report.level in ("warn", "alert")

    def test_run_rules_without_context_reports_skipped_not_alert(self):
        report = run_rules("正文" * 300, rules=THREAD_RULES)

        assert report.level == "ok", "无账本不能报 alert"
        assert set(report.skipped_rules) == set(THREAD_RULES)
        assert report.incomplete is True

    def test_unknown_thread_rule_raises(self):
        with pytest.raises(ValueError):
            run_rules("正文", rules=("not_a_rule",))
