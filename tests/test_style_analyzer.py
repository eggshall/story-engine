"""测试：StyleAnalyzer — analyze_style / check_consistency / prompt 生成（E3.5）。

全部离线：mock `_chat` 与 httpx 客户端，不调用本地 Ollama。
async 用例沿用仓库惯例 `asyncio.run()`（见 test_writer/test_sse.py）。
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

from story_engine.style.analyzer import StyleAnalyzer
from story_engine.style.db import StyleProfile


def _profile(**kw) -> StyleProfile:
    defaults = dict(
        name="测试风格",
        style_prompt="古典典雅，句长均匀，对话精炼",
    )
    defaults.update(kw)
    return StyleProfile(**defaults)


class TestExtractJson:
    def test_direct_json(self):
        raw = '{"a": 1, "b": "x"}'
        assert StyleAnalyzer._extract_json(raw) == {"a": 1, "b": "x"}

    def test_braced_in_text(self):
        raw = "模型输出如下：\n```json\n{\"consistency_score\": 8}\n```\n结束"
        assert StyleAnalyzer._extract_json(raw) == {"consistency_score": 8}

    def test_invalid_returns_none(self):
        assert StyleAnalyzer._extract_json("完全不是 JSON") is None
        assert StyleAnalyzer._extract_json("{ broken") is None


class TestFeaturesToPrompt:
    def test_empty(self):
        assert StyleAnalyzer._features_to_prompt({}) == ""

    def test_builds_prompt(self):
        feats = {
            "词汇水平": {"value": "典雅", "score": 8},
            "整体风格总结": "一句话总结",
        }
        out = StyleAnalyzer._features_to_prompt(feats)
        assert "词汇水平: 典雅" in out
        assert "一句话总结" in out  # 整体风格总结 也会进入 prompt

    def test_skips_unknown(self):
        feats = {"词汇水平": {"value": "未知"}, "平均句长": "20字"}
        out = StyleAnalyzer._features_to_prompt(feats)
        assert out == "平均句长: 20字"


class TestRenderStyleBlock:
    def test_full_block(self):
        p = _profile(
            features={
                "词汇水平": {"value": "典雅", "score": 8},
                "对话比例": {"value": "低", "score": 3},
                "整体风格总结": "总结语",
            },
            sample_text="这是样本段落。" * 10,
        )
        block = StyleAnalyzer.render_style_block(p)
        assert "【风格总结】古典典雅" in block
        assert "【量化特征】" in block
        assert "词汇水平: 典雅 (8分)" in block
        assert "整体风格总结" not in block  # 量化特征中排除总结字段
        assert "【原文示例】" in block

    def test_minimal_profile(self):
        p = _profile(style_prompt="", features={}, sample_text="")
        block = StyleAnalyzer.render_style_block(p)
        assert block == ""


class TestChat:
    def test_chat_success_strips_think(self):
        from unittest.mock import Mock

        analyzer = StyleAnalyzer()
        client = AsyncMock()
        resp = Mock()
        resp.raise_for_status = Mock()
        resp.json = Mock(return_value={
            "choices": [{"message": {"content": "<think>推理过程</think>实际内容"}}]
        })
        client.post = AsyncMock(return_value=resp)
        analyzer._client = client

        async def _run():
            return await analyzer._chat(["用户消息"], system="系统提示")

        out = asyncio.run(_run())
        assert out == "实际内容"
        payload = client.post.await_args.kwargs["json"]
        assert payload["messages"][0] == {"role": "system", "content": "系统提示"}
        assert payload["stream"] is False

    def test_chat_error_returns_masked(self):
        analyzer = StyleAnalyzer()
        client = AsyncMock()
        client.post.side_effect = RuntimeError("本地模型连接失败")
        analyzer._client = client

        async def _run():
            return await analyzer._chat(["hi"])

        out = asyncio.run(_run())
        assert out.startswith("【分析失败】")

    def test_get_client_lazy(self):
        analyzer = StyleAnalyzer()
        assert analyzer._client is None
        c1 = analyzer._get_client()
        c2 = analyzer._get_client()
        assert c1 is c2  # 复用一个持久客户端

    def test_close_releases_client(self):
        analyzer = StyleAnalyzer()
        client = AsyncMock()
        analyzer._client = client

        async def _run():
            await analyzer.close()

        asyncio.run(_run())
        client.aclose.assert_awaited_once()
        assert analyzer._client is None
        asyncio.run(_run())  # 幂等


class TestAnalyzeStyle:
    def test_returns_features(self):
        analyzer = StyleAnalyzer()
        feats = {"词汇水平": {"value": "典雅", "score": 8}}
        analyzer._chat = AsyncMock(return_value=json.dumps(feats, ensure_ascii=False))

        async def _run():
            return await analyzer.analyze_style("这是一段文本")

        out = asyncio.run(_run())
        assert out == feats
        assert "这是一段文本" in analyzer._chat.await_args.args[0][0]

    def test_long_text_truncated(self):
        analyzer = StyleAnalyzer()
        analyzer._chat = AsyncMock(return_value="{}")

        async def _run():
            await analyzer.analyze_style("字" * 9000)

        asyncio.run(_run())
        prompt = analyzer._chat.await_args.args[0][0]
        assert "字" * 4000 in prompt
        assert len(prompt) < 5000  # 已截断

    def test_bad_json_fallback(self):
        analyzer = StyleAnalyzer()
        analyzer._chat = AsyncMock(return_value="模型回复了一堆文字")

        async def _run():
            return await analyzer.analyze_style("文本")

        out = asyncio.run(_run())
        assert out["整体风格总结"] == "解析失败"
        assert "raw_analysis" in out


class TestCheckConsistency:
    def test_returns_result(self):
        analyzer = StyleAnalyzer()
        result = {"consistency_score": 9, "suggestions": ["保持"]}
        analyzer._chat = AsyncMock(return_value=json.dumps(result, ensure_ascii=False))

        async def _run():
            return await analyzer.check_consistency("正文文本", _profile())

        out = asyncio.run(_run())
        assert out == result

    def test_missing_style_info(self):
        analyzer = StyleAnalyzer()
        analyzer._chat = AsyncMock()

        async def _run():
            return await analyzer.check_consistency(
                "正文", _profile(style_prompt="", features={})
            )

        out = asyncio.run(_run())
        assert out == {"consistency_score": 5, "error": "缺少风格描述信息"}
        analyzer._chat.assert_not_awaited()

    def test_features_build_prompt(self):
        analyzer = StyleAnalyzer()
        analyzer._chat = AsyncMock(return_value="{}")
        p = _profile(
            style_prompt="",
            features={"词汇水平": {"value": "通俗", "score": 6}},
        )

        async def _run():
            await analyzer.check_consistency("正文", p)

        asyncio.run(_run())
        prompt = analyzer._chat.await_args.args[0][0]
        assert "词汇水平: 通俗" in prompt  # _features_to_prompt 兜底

    def test_bad_response_fallback(self):
        analyzer = StyleAnalyzer()
        analyzer._chat = AsyncMock(return_value="无法解析的输出")

        async def _run():
            return await analyzer.check_consistency("正文", _profile())

        out = asyncio.run(_run())
        assert out["consistency_score"] == 5
        assert "raw" in out


class TestGenerateStylePrompt:
    def test_uses_summary_without_chat(self):
        analyzer = StyleAnalyzer()
        analyzer._chat = AsyncMock()

        async def _run():
            return await analyzer.generate_style_prompt({"整体风格总结": "冷峻克制"})

        out = asyncio.run(_run())
        assert out == "冷峻克制"
        analyzer._chat.assert_not_awaited()

    def test_chat_when_no_summary(self):
        analyzer = StyleAnalyzer()
        analyzer._chat = AsyncMock(return_value="生成的风格描述")

        async def _run():
            return await analyzer.generate_style_prompt({"词汇水平": {"value": "典雅"}})

        out = asyncio.run(_run())
        assert out == "生成的风格描述"
