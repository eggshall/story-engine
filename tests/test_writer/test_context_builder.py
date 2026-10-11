"""N4（切片一）契约测试：槽位注册表 + ContextManifest + 预算裁剪。

为什么先有这组测试（评审 R2）：装配器是后续所有阶段（素材/技法/条款/知识库）都要挂进去的
接缝，接口形状定错了会强制返工。所以先把**纯函数部分**钉死，再接真实数据源。

契约（N4 起生效）：

  S1 槽位由 `Slot(slot_id, priority, provider, renderer, max_tokens)` 声明；provider/renderer 是
     **注册表里的名字**，不是直接传函数 —— 后续阶段新增数据源只需注册，不改装配器。
  S2 装配结果 = 文本 + `ContextManifest`（"注入了什么"）；manifest 与实际拼进 prompt 的片段一一对应。
  S3 两级预算：槽位级 `max_tokens` 截断 → 全局 `budget_tokens` 裁整槽；`priority=PINNED(0)` 永不裁。
  S4 **不静默消失**（评审 P1-1/P1-2）：注入的进 `entries`、被裁的进 `dropped`（含片段数与来源）、
     没注成的进 `skipped`（带原因）。
  S5 token 用中文启发式（字符数）估算；**口径统一**（评审 P0-1）：裁剪判定与 `total_tokens`
     都按"实际注入的渲染文本"算，不能一个按渲染后、一个按片段之和。
  S6 同一输入两次装配结果完全一致；provider 抛异常不能让整次装配崩。
"""

from __future__ import annotations

from story_engine.writer.context_builder import (
    PINNED,
    RETRIEVAL,
    AssembledContext,
    ContextBuilder,
    ContextManifest,
    ContextPiece,
    DroppedSlot,
    ManifestEntry,
    SkippedSlot,
    Slot,
    estimate_tokens,
)


def _static(text: str, source: str = "static"):
    """一个最简单的 provider：返回固定文本片段。"""

    def _provider(_inputs) -> list[ContextPiece]:
        return [ContextPiece(text=text, source=source)]

    return _provider


def _builder(*slots: Slot, budget: int | None = None, providers: dict | None = None) -> ContextBuilder:
    return ContextBuilder(
        slots=list(slots),
        providers=providers or {},
        budget_tokens=budget,
    )


class TestAssemblyAndManifest:
    def test_all_slots_land_in_text_and_manifest(self):
        builder = _builder(
            Slot("mainline", priority=PINNED, provider="mainline", renderer="plain"),
            Slot("style", priority=PINNED, provider="style", renderer="plain"),
            Slot("beat", priority=PINNED, provider="beat", renderer="plain"),
            Slot("retrieval", priority=RETRIEVAL, provider="retrieval", renderer="plain"),
            providers={
                "mainline": _static("主线：人类走出地球。"),
                "style": _static("文风：冷峻克制。"),
                "beat": _static("本章节拍：第一次接触。"),
                "retrieval": _static("检索：旧地球档案片段。"),
            },
        )

        result = builder.build({})

        assert isinstance(result, AssembledContext)
        for chunk in ("主线：人类走出地球。", "文风：冷峻克制。", "本章节拍：第一次接触。", "检索：旧地球档案片段。"):
            assert chunk in result.text

        entries = {e.slot_id: e for e in result.manifest.entries}
        assert set(entries) == {"mainline", "style", "beat", "retrieval"}
        assert isinstance(entries["mainline"], ManifestEntry)
        assert entries["mainline"].source == "static"
        assert entries["mainline"].chars == len("主线：人类走出地球。")
        assert entries["mainline"].truncated is False
        assert result.manifest.skipped == []

    def test_manifest_totals_match_injected_text(self):
        """S5：`total_tokens` 必须等于**实际注入文本**的 token（口径统一，评审 P0-1）。"""
        builder = _builder(
            Slot("a", priority=PINNED, provider="a", renderer="plain"),
            Slot("b", priority=10, provider="b", renderer="bullets"),
            providers={"a": _static("甲" * 30), "b": _static("乙" * 70)},
        )

        result = builder.build({})

        assert result.manifest.total_tokens == sum(estimate_tokens(x) for x in result.text.split("\n\n"))
        assert result.manifest.token_estimate is True

    def test_multi_piece_provider_yields_one_entry_per_piece(self):
        """摘要这类槽位天然是多片段：每片一条记录，来源可追到具体章号。"""

        def summaries(_inputs) -> list[ContextPiece]:
            return [
                ContextPiece(text="第1章摘要：主角醒来。", source="summary:ch_0001"),
                ContextPiece(text="第2章摘要：发现信号。", source="summary:ch_0002"),
            ]

        builder = _builder(
            Slot("summaries", priority=20, provider="summaries", renderer="bullets"),
            providers={"summaries": summaries},
        )

        result = builder.build({})

        sources = [e.source for e in result.manifest.entries]
        assert sources == ["summary:ch_0001", "summary:ch_0002"]
        assert "第1章摘要：主角醒来。" in result.text

    def test_empty_input_yields_empty_manifest(self):
        def nothing(_inputs) -> list[ContextPiece]:
            return []

        builder = _builder(
            Slot("empty", priority=10, provider="empty", renderer="plain"),
            providers={"empty": nothing},
        )

        result = builder.build({})

        assert result.text.strip() == ""
        assert result.manifest.entries == []
        assert result.manifest.dropped == []
        # S4：不是"什么都不发生"，而是明说"这个槽位是空的"
        assert [s.reason for s in result.manifest.skipped] == ["empty"]


class TestVisibilityOfSkippedAndErrors:
    """S4（评审 P1-2/P1-3）：没注成的槽位必须能看出"为什么没注成"。"""

    def test_missing_provider_is_recorded(self):
        builder = _builder(Slot("missing", priority=10, provider="not-registered", renderer="plain"))

        result = builder.build({})

        assert result.manifest.entries == []
        assert [(s.slot_id, s.reason) for s in result.manifest.skipped] == [
            ("missing", "provider_missing")
        ]

    def test_provider_exception_does_not_break_assembly(self):
        def boom(_inputs):
            raise RuntimeError("DB 挂了")

        builder = _builder(
            Slot("bad", priority=10, provider="bad", renderer="plain"),
            Slot("good", priority=PINNED, provider="good", renderer="plain"),
            providers={"bad": boom, "good": _static("保住了")},
        )

        result = builder.build({})

        assert "保住了" in result.text                      # 其他槽位不受影响
        assert [s.reason for s in result.manifest.skipped] == ["error:RuntimeError"]

    def test_provider_returning_wrong_type_is_recorded(self):
        builder = _builder(
            Slot("weird", priority=10, provider="weird", renderer="plain"),
            providers={"weird": lambda _i: "我不是列表"},  # type: ignore[arg-type,return-value]
        )

        result = builder.build({})

        assert result.manifest.entries == []
        assert [s.reason for s in result.manifest.skipped] == ["error:provider_returned_str"]

    def test_inputs_are_copied_before_providers_see_them(self):
        """provider 往 inputs 里写脏数据，不能影响调用方（否则"同输入同输出"承诺就破了）。"""

        def mutating(inputs):
            inputs["hacked"] = True
            return [ContextPiece(text="x", source="s")]

        caller_inputs = {"novel_id": "n1"}
        builder = _builder(
            Slot("mut", priority=10, provider="mut", renderer="plain"),
            providers={"mut": mutating},
        )

        builder.build(caller_inputs)

        assert caller_inputs == {"novel_id": "n1"}


class TestBudgetTrim:
    def test_trims_lowest_priority_first(self):
        builder = _builder(
            Slot("keep", priority=PINNED, provider="keep", renderer="plain"),
            Slot("mid", priority=30, provider="mid", renderer="plain"),
            Slot("low", priority=RETRIEVAL, provider="low", renderer="plain"),
            budget=25,
            providers={
                "keep": _static("保" * 10),   # 10 字 ≈ 10 token
                "mid": _static("中" * 10),
                "low": _static("裁" * 10),
            },
        )

        result = builder.build({})

        assert "裁" not in result.text          # 最低优先级先被裁
        assert "中" in result.text              # 25 的预算：10+10 装得下
        assert "保" in result.text
        assert [d.slot_id for d in result.manifest.dropped] == ["low"]
        assert result.manifest.total_tokens == 20
        assert result.manifest.over_budget is False

    def test_dropped_keeps_sources_and_piece_count(self):
        """评审 P1-1：多片段槽位被裁时，要能看出裁掉了几条、哪些来源。"""

        def summaries(_inputs) -> list[ContextPiece]:
            return [
                ContextPiece(text="甲" * 10, source="summary:ch_0001"),
                ContextPiece(text="乙" * 10, source="summary:ch_0002"),
            ]

        builder = _builder(
            Slot("keep", priority=PINNED, provider="keep", renderer="plain"),
            Slot("summaries", priority=20, provider="summaries", renderer="bullets"),
            budget=12,
            providers={"keep": _static("保" * 10), "summaries": summaries},
        )

        result = builder.build({})

        dropped = result.manifest.dropped
        assert len(dropped) == 1
        assert isinstance(dropped[0], DroppedSlot)
        assert dropped[0].slot_id == "summaries"
        assert dropped[0].pieces == 2
        assert dropped[0].sources == ["summary:ch_0001", "summary:ch_0002"]
        assert dropped[0].tokens > 0

    def test_pinned_slots_are_never_trimmed_and_over_budget_is_explicit(self):
        builder = _builder(
            Slot("style", priority=PINNED, provider="style", renderer="plain"),
            Slot("beat", priority=PINNED, provider="beat", renderer="plain"),
            Slot("retrieval", priority=RETRIEVAL, provider="retrieval", renderer="plain"),
            budget=5,
            providers={
                "style": _static("文" * 50),
                "beat": _static("节" * 50),
                "retrieval": _static("检" * 50),
            },
        )

        result = builder.build({})

        assert "文" in result.text and "节" in result.text   # PINNED：永不裁
        assert "检" not in result.text
        assert [d.slot_id for d in result.manifest.dropped] == ["retrieval"]
        # 超额是明示的：pinned 允许超发，但必须标记 + 记账与实际注入一致
        assert result.manifest.over_budget is True
        assert result.manifest.total_tokens == 100

    def test_same_priority_tie_break_drops_later_declared_first(self):
        """评审 P1-6：同优先级时的确定顺序（后声明先裁）此前没有被测过。"""
        builder = _builder(
            Slot("first", priority=50, provider="first", renderer="plain"),
            Slot("second", priority=50, provider="second", renderer="plain"),
            budget=12,
            providers={"first": _static("1" * 12), "second": _static("2" * 12)},
        )

        result = builder.build({})

        assert [d.slot_id for d in result.manifest.dropped] == ["second"]
        assert "1" * 12 in result.text

    def test_renderer_prefix_counts_toward_budget(self):
        """P0-1 回归：bullets 的 "- " 前缀与换行也占 token，记账不能漏（曾出现 over_budget 假阴性）。"""

        def three(_inputs) -> list[ContextPiece]:
            return [
                ContextPiece(text="aaa", source="p1"),
                ContextPiece(text="bbb", source="p2"),
                ContextPiece(text="ccc", source="p3"),
            ]

        builder = _builder(
            Slot("notes", priority=PINNED, provider="notes", renderer="bullets"),
            budget=10,
            providers={"notes": three},
        )

        result = builder.build({})

        injected = len(result.text)          # "- aaa\n- bbb\n- ccc" = 17
        assert injected == 17
        assert result.manifest.total_tokens == injected   # 修复前记账是 9
        assert result.manifest.over_budget is True        # 修复前是 False

    def test_dropped_order_is_deterministic_by_priority(self):
        builder = _builder(
            Slot("a", priority=10, provider="a", renderer="plain"),
            Slot("b", priority=RETRIEVAL, provider="b", renderer="plain"),
            Slot("c", priority=50, provider="c", renderer="plain"),
            budget=12,
            providers={"a": _static("A" * 12), "b": _static("B" * 12), "c": _static("C" * 12)},
        )

        result = builder.build({})

        assert [d.slot_id for d in result.manifest.dropped] == ["b", "c"]

    def test_budget_none_means_no_trim(self):
        builder = _builder(
            Slot("x", priority=99, provider="x", renderer="plain"),
            providers={"x": _static("X" * 5000)},
        )

        result = builder.build({})

        assert result.manifest.dropped == []
        assert "X" * 5000 in result.text


class TestPerSlotBudget:
    """评审 P1-4：架构要求"每个槽位有独立预算与填充策略"，留出槽位级 max_tokens。"""

    def test_slot_max_tokens_truncates_at_piece_granularity(self):
        def five(_inputs) -> list[ContextPiece]:
            return [ContextPiece(text=f"片段{i}" * 2, source=f"s{i}") for i in range(5)]

        builder = _builder(
            Slot("summaries", priority=20, provider="summaries", renderer="plain",
                 max_tokens=12),
            providers={"summaries": five},
        )

        result = builder.build({})

        assert estimate_tokens(result.text) <= 12
        assert len(result.manifest.entries) < 5
        assert any(e.truncated for e in result.manifest.entries)   # truncated 不再恒为 False

    def test_slot_budget_none_keeps_everything(self):
        builder = _builder(
            Slot("all", priority=20, provider="all", renderer="plain"),
            providers={"all": _static("全" * 100)},
        )

        result = builder.build({})

        assert len(result.text) == 100
        assert all(not e.truncated for e in result.manifest.entries)


class TestDeterminismAndGuards:
    def test_same_input_same_output(self):
        builder = _builder(
            Slot("a", priority=PINNED, provider="a", renderer="plain"),
            Slot("b", priority=10, provider="b", renderer="bullets"),
            providers={"a": _static("甲"), "b": _static("乙")},
        )

        first = builder.build({"novel_id": "n1"})
        second = builder.build({"novel_id": "n1"})

        assert first.text == second.text
        assert first.manifest.to_dict() == second.manifest.to_dict()

    def test_manifest_is_json_serialisable(self):
        import json

        builder = _builder(
            Slot("a", priority=PINNED, provider="a", renderer="plain"),
            providers={"a": _static("甲")},
        )

        result = builder.build({})

        payload = json.dumps(result.manifest.to_dict(), ensure_ascii=False)
        assert "a" in payload and "tokens" in payload

    def test_duplicate_slot_id_rejected(self):
        import pytest

        with pytest.raises(ValueError):
            _builder(
                Slot("same", priority=PINNED, provider="a", renderer="plain"),
                Slot("same", priority=10, provider="b", renderer="plain"),
            )

    def test_manifest_dataclass_defaults(self):
        """空 manifest 的形状（N4b 要挂到 SSE done 载荷，字段必须稳定）。"""
        m = ContextManifest()

        assert m.entries == [] and m.dropped == [] and m.skipped == []
        assert m.total_tokens == 0 and m.over_budget is False
        assert isinstance(SkippedSlot("s", "empty").reason, str)
        assert estimate_tokens("中文字符") == 4
