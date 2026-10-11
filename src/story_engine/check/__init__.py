"""校验器包（N5）— A 类确定性规则（章末钩子/对话占比/段长/视角/禁词）。"""

from story_engine.check.rules import (
    Baseline,
    CheckReport,
    Finding,
    Location,
    build_baseline,
    run_rules,
)

__all__ = ["Baseline", "CheckReport", "Finding", "Location", "build_baseline", "run_rules"]
