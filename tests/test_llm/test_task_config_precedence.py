"""N3 契约测试：config 里的 `task` / `thinking` 真的生效（优先级明确、不留死角）。

优先级（N3 起生效，写在 api_client 的 docstring 里）：

    请求级 `LLMRequest.task`（显式设置）
      > 模型配置 `task`（config: llm.models[].task）
      > 默认 "generate"

    `thinking`：模型配置显式给出时优先于按 task 推导的默认值。

为什么要这组测试：N3 之前 config 里根本没有这两个字段（写了会被静默剥离），
于是"config 驱动调用契约"是空话；不测优先级就只剩"字段能存下来"。
"""

from __future__ import annotations

import pytest

from story_engine.llm.api_client import OpenAIClient
from story_engine.llm.base import TASK_GENERATE, LLMRequest


def _client(**extra) -> OpenAIClient:
    cfg = {
        "name": "m",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-test",
    }
    cfg.update(extra)
    return OpenAIClient(cfg)


def _payload(client: OpenAIClient, **req_kwargs) -> dict:
    return client._build_payload(LLMRequest(messages=[{"role": "user", "content": "hi"}], **req_kwargs))


class TestTaskPrecedence:
    def test_config_task_used_when_request_unset(self):
        """config: task=plan + 请求未指定 → 走规划语义（开思考、不发 temperature）"""
        payload = _payload(_client(task="plan"))

        assert payload["thinking"] == {"type": "enabled"}
        assert "temperature" not in payload

    def test_explicit_request_task_wins_over_config(self):
        """请求级显式 task 覆盖 config 默认（正文生成必须能强制关思考）"""
        payload = _payload(_client(task="plan"), task=TASK_GENERATE)

        assert payload["thinking"] == {"type": "disabled"}
        assert "temperature" in payload

    def test_no_config_task_keeps_default_generate(self):
        """没有 config task 时行为与 N1 完全一致（回归）"""
        payload = _payload(_client())

        assert payload["thinking"] == {"type": "disabled"}
        assert "temperature" in payload

    def test_unset_task_is_allowed_and_means_default(self):
        """"未设置"是合法状态（空串），不能被当成拼错的 task 而抛错"""
        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], task="")
        assert req.task == ""
        payload = _client()._build_payload(req)
        assert payload["thinking"] == {"type": "disabled"}

    def test_typo_task_still_raises(self):
        """回归（N1 评审 P1-2）：拼错的 task 仍必须立刻炸"""
        with pytest.raises(ValueError):
            LLMRequest(messages=[], task="genrate")


class TestThinkingOverride:
    def test_config_thinking_overrides_task_derivation(self):
        """config 显式 thinking 优先：让"规划模型"也能被迫关思考（或反之）"""
        payload = _payload(_client(task="plan", thinking={"type": "disabled"}))

        assert payload["thinking"] == {"type": "disabled"}
        # 关思考后 temperature 才有效 → 必须发出去（不能因为 task=plan 就不发）
        assert "temperature" in payload

    def test_config_thinking_enabled_for_generate(self):
        payload = _payload(_client(thinking={"type": "enabled"}), task=TASK_GENERATE)

        assert payload["thinking"] == {"type": "enabled"}
        assert "temperature" not in payload

    def test_non_thinking_provider_never_gets_field(self):
        """非 deepseek 的 OpenAI 兼容服务不发 thinking（乱发可能 400，N1 评审 P2-1 回归）"""
        payload = _payload(_client(provider="openai", thinking={"type": "disabled"}))

        assert "thinking" not in payload

    def test_reasoning_effort_never_sent(self):
        payload = _payload(_client(task="plan", thinking={"type": "enabled"}))

        assert "reasoning_effort" not in payload


class TestPerModelTimeout:
    """N3：模型级 read_timeout 之前被 config 白名单静默剥离（本地模型 300s → 120s）。"""

    def test_per_model_read_timeout_reaches_client(self):
        client = _client(read_timeout=300, connect_timeout=5)

        assert client.read_timeout == 300
        assert client.connect_timeout == 5

    def test_missing_timeouts_fall_back_to_defaults(self):
        client = _client()

        assert client.read_timeout == 60  # api_client 的缺省
        assert client.connect_timeout == 10
