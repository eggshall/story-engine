"""N3 契约测试：`llm.models` 的配置 schema 必须"放行真实使用的字段、不静默剥离"。

背景（计划书 §9.1 N3 + P0-2）：`core/config.py::_LLMModelConfig` 是白名单，`Config._load`
会把每个模型条目过一遍 `model_validate(...).model_dump()`。只要字段不在白名单里，
**就被静默丢掉**——实测被丢掉的正是线上真在用的字段：

- `weight`（config.yaml 里每个模型都写了）
- `read_timeout`（本地 qwen 写的是 300，被丢后一律用 `llm.read_timeout=120`
  → 本地长文生成会在 120s 被掐断，且没有任何提示）
- `connect_timeout` / `timeout`（旧兼容字段）
- N3 要求的 `task` / `thinking`（模型级默认任务与思考开关，config 驱动的入口）

契约（N3 起生效）：

  C1 已知字段一个都不能丢（含 timeouts/weight/task/thinking）。
  C2 未知字段**保留 + 告警**，而不是静默消失（配置写错键名时必须能看见）。
  C3 非法条目（缺 name 等）仍照旧被过滤并告警（不要把校验放宽成"什么都收"）。
  C4 `task` 值必须在 `VALID_TASKS` 内：写错时降级为"未设置"并告警，
     而不是把整条模型配置连坐掉、也不是静默当成 generate。
"""

from __future__ import annotations

import logging

import yaml

from story_engine.core.config import Config, _validate_models

KNOWN_EXTRA_FIELDS = {
    "weight": 10,
    "read_timeout": 300,
    "connect_timeout": 5,
    "timeout": 90,
}


class TestKnownFieldsSurvive:
    def test_timeouts_weight_survive(self):
        """C1：这些字段以前会被静默剥离（本地模型 read_timeout=300 被改成 120）。"""
        entry = {
            "name": "qwen-local",
            "provider": "local",
            "model_id": "qwen3.5:9b-q6-fixed",
            "enabled": True,
            **KNOWN_EXTRA_FIELDS,
        }

        out = _validate_models([entry])[0]

        for key, value in KNOWN_EXTRA_FIELDS.items():
            assert out.get(key) == value, f"{key} 被剥离或改写了: {out}"

    def test_task_and_thinking_survive(self):
        """C1：N3 新增的 config 驱动入口。"""
        entry = {
            "name": "planner",
            "provider": "deepseek",
            "model_id": "deepseek-chat",
            "task": "plan",
            "thinking": {"type": "enabled"},
        }

        out = _validate_models([entry])[0]

        assert out["task"] == "plan"
        assert out["thinking"] == {"type": "enabled"}

    def test_real_config_file_keeps_local_read_timeout(self, tmp_path):
        """C1 端到端（配置层）：真实形状的 config.yaml 载入后，本地模型仍带自己的 300s。"""
        path = tmp_path / "config.yaml"
        path.write_text(
            yaml.dump(
                {
                    "llm": {
                        "default_model": "qwen3.5-9b-q6",
                        "connect_timeout": 10,
                        "read_timeout": 120,
                        "models": [
                            {
                                "name": "qwen3.5-9b-q6",
                                "provider": "local",
                                "model_id": "qwen3.5:9b-q6-fixed",
                                "base_url": "http://localhost:11434",
                                "read_timeout": 300,
                                "weight": 5,
                            },
                            {
                                "name": "deepseek-v4-pro",
                                "provider": "deepseek",
                                "model_id": "deepseek-chat",
                                "weight": 10,
                            },
                        ],
                    }
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        models = Config(path).get("llm.models")
        by_name = {m["name"]: m for m in models}

        assert by_name["qwen3.5-9b-q6"]["read_timeout"] == 300
        assert by_name["qwen3.5-9b-q6"]["weight"] == 5
        assert by_name["deepseek-v4-pro"]["weight"] == 10
        # 没写 read_timeout 的模型不应被凭空塞一个值（注入由 _build_router_locked 负责）
        assert "read_timeout" not in by_name["deepseek-v4-pro"]


class TestUnknownAndInvalid:
    def test_unknown_key_is_kept_and_warned(self, caplog):
        """C2：写错键名不能静默丢掉。"""
        entry = {"name": "m1", "provider": "deepseek", "modle_id": "typo-key", "future_opt": True}

        with caplog.at_level(logging.WARNING, logger="story_engine.config"):
            out = _validate_models([entry])[0]

        assert out.get("future_opt") is True
        assert out.get("modle_id") == "typo-key"  # 保留原样，交给使用者发现
        warned = " ".join(r.getMessage() for r in caplog.records)
        assert "future_opt" in warned or "modle_id" in warned, warned

    def test_invalid_entry_still_filtered(self, caplog):
        """C3：校验不能放宽成"什么都收"。"""
        with caplog.at_level(logging.WARNING, logger="story_engine.config"):
            out = _validate_models([{"provider": "deepseek"}, "not-a-dict", None])

        assert out == []
        assert caplog.records, "非法条目必须有告警，不能静默过滤"

    def test_invalid_task_degrades_to_unset_with_warning(self, caplog):
        """C4：task 写错 → 降级为"未设置" + 告警（不连坐整条配置、也不静默当 generate）。"""
        entry = {"name": "m2", "provider": "deepseek", "task": "genrate"}

        with caplog.at_level(logging.WARNING, logger="story_engine.config"):
            out = _validate_models([entry])[0]

        assert out.get("task") in (None, ""), out
        assert "genrate" in " ".join(r.getMessage() for r in caplog.records)

    def test_valid_task_kept(self):
        for task in ("generate", "extract", "plan"):
            out = _validate_models([{"name": "m3", "provider": "deepseek", "task": task}])[0]
            assert out["task"] == task


class TestBadTypesDoNotDropEntry:
    """评审 P1-2 / P2-1：非法**类型**不能连坐整条模型配置，非法 thinking 不能原样发给上游。

    N3 之前：`task: 5` / `thinking: "disabled"` 会在 Pydantic 类型校验阶段失败 →
    整条模型被过滤（与 config.py 里"不连坐整条配置"的注释直接矛盾）；
    而 `thinking: {"type": "xxx"}` 反而一路通过、被原样发到上游（可能 400）。
    """

    def test_non_string_task_degrades_and_keeps_entry(self, caplog):
        for bad in (5, True, ["plan"], {"a": 1}):
            with caplog.at_level(logging.WARNING, logger="story_engine.config"):
                out = _validate_models([{"name": "m", "provider": "deepseek", "task": bad}])

            assert len(out) == 1, f"task={bad!r} 不应导致整条模型被过滤"
            assert out[0].get("task") is None
        assert "task" in " ".join(r.getMessage() for r in caplog.records)

    def test_non_dict_thinking_degrades_and_keeps_entry(self, caplog):
        for bad in ("disabled", 5, ["disabled"]):
            with caplog.at_level(logging.WARNING, logger="story_engine.config"):
                out = _validate_models([{"name": "m", "provider": "deepseek", "thinking": bad}])

            assert len(out) == 1, f"thinking={bad!r} 不应导致整条模型被过滤"
            assert out[0].get("thinking") is None

    def test_illegal_thinking_type_is_dropped(self, caplog):
        """值域校验：type 只能是 enabled/disabled，否则丢弃（宁可等默认推导，也不发未知字段）。"""
        with caplog.at_level(logging.WARNING, logger="story_engine.config"):
            out = _validate_models(
                [{"name": "m", "provider": "deepseek", "thinking": {"type": "xxx"}}]
            )

        assert len(out) == 1
        assert out[0].get("thinking") is None
        assert "thinking" in " ".join(r.getMessage() for r in caplog.records)

    def test_valid_thinking_kept(self):
        for value in ("disabled", "enabled"):
            out = _validate_models(
                [{"name": "m", "provider": "deepseek", "thinking": {"type": value}}]
            )[0]
            assert out["thinking"] == {"type": value}

    def test_task_on_non_supporting_provider_warns(self, caplog):
        """P2-2：本地/Anthropic 客户端不消费 task/thinking → 写了必须告警（避免静默空操作）。"""
        with caplog.at_level(logging.WARNING, logger="story_engine.config"):
            _validate_models(
                [{"name": "local-1", "provider": "local", "task": "plan",
                  "thinking": {"type": "disabled"}}]
            )

        warned = " ".join(r.getMessage() for r in caplog.records)
        assert "local" in warned and ("不支持" in warned or "不生效" in warned), warned
