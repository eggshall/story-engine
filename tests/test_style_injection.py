"""P6 文风注入链路回归测试 — camelCase 解析 + 完整画像渲染"""
import sys

sys.path.insert(0, "src")

from story_engine.api.schemas import ChatRequest
from story_engine.style.analyzer import StyleAnalyzer
from story_engine.style.db import StyleProfile


def test_chat_request_accepts_camelcase():
    """前端 camelCase 字段应被解析到 snake_case 字段（P5+ 修复）"""
    req = ChatRequest(
        messages=[{"role": "user", "content": "测试"}],
        mode="write",
        stylePrompt="典雅风格",
        profileId="style_abc",
    )
    assert req.style_prompt == "典雅风格"
    assert req.profile_id == "style_abc"


def test_chat_request_accepts_snake_case():
    """后端内部 snake_case 调用仍兼容"""
    req = ChatRequest(
        messages=[{"role": "user", "content": "测试"}],
        style_prompt="口语化",
        profile_id="style_def",
    )
    assert req.style_prompt == "口语化"
    assert req.profile_id == "style_def"


def test_render_style_block_full():
    """完整画像渲染：风格总结 + 量化特征 + 原文示例 三段"""
    profile = StyleProfile(
        name="测试风格",
        style_prompt="典雅古朴的章回体文风。",
        features={
            "词汇水平": {"value": "典雅", "score": 9},
            "平均句长": {"value": "30-50字", "score": 6},
            "对话比例": {"value": "25%", "score": 5},
            "叙事视角": {"value": "全知视角", "score": 10},
            "整体风格总结": "典雅古朴的章回体文风。",
        },
        sample_text="话说天下大势，分久必合，合久必分。\n" * 20,
    )
    block = StyleAnalyzer.render_style_block(profile, sample_len=30)
    assert "【风格总结】典雅古朴的章回体文风。" in block
    assert "【量化特征】" in block
    assert "词汇水平: 典雅 (9分)" in block
    assert "对话比例: 25% (5分)" in block
    assert "【原文示例】" in block
    assert "话说天下大势" in block


def test_render_style_block_fallback_prompt():
    """无 features/sample 时，至少保留风格总结"""
    profile = StyleProfile(name="空画像", style_prompt="只有一句话。")
    block = StyleAnalyzer.render_style_block(profile)
    assert "【风格总结】只有一句话。" in block
    assert "【量化特征】" not in block
