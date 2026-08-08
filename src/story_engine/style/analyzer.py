"""文风分析器 — 使用本地 Qwen3.5-9B 模型分析小说文风

核心能力:
  1. analyze_style(text) — 对给定文本提取文风特征
  2. check_consistency(text, profile) — 检查文本与文风画像的一致性
  3. generate_style_prompt(features) — 生成注入 prompt 用的风格描述
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from story_engine.style.db import StyleProfile

logger = logging.getLogger("story_engine.style")

# Ollama 本地模型
LOCAL_MODEL = "qwen3.5:9b-q6-fixed"
OLLAMA_BASE = "http://localhost:11434"


class StyleAnalyzer:
    """文风分析器 — 调用本地模型提取/分析文风特征"""

    def __init__(self, model: str = LOCAL_MODEL, base_url: str = OLLAMA_BASE):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    # ── 客户端 ────────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=f"{self.base_url}/v1",
                timeout=httpx.Timeout(connect=15, read=120, write=30, pool=10),
            )
        return self._client

    async def _chat(self, messages: list, system: str = "",
                    temperature: float = 0.3, max_tokens: int = 1024) -> str:
        """调用本地模型"""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": m} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if system:
            payload["messages"].insert(
                0, {"role": "system", "content": system}
            )
        try:
            client = self._get_client()
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            # 去除 <think> 块（Qwen 推理过程）
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return content
        except Exception as e:
            logger.error("本地模型调用失败: %s", e)
            return f"【分析失败】{e}"

    # ── 文风分析 ──────────────────────────────────────

    ANALYZE_PROMPT = """你是一位专业的文学风格分析专家。请分析以下小说片段（用 ===TEXT=== 包裹）的文风特征。

请从以下几个维度进行分析，每个维度用「特征名: 值」格式输出，保持客观可量化：

1. **词汇水平**: 通俗/典雅/古朴/华丽/口语化/书面化 — 并给出 1-10 评分
2. **平均句长**: 估计每句平均字符数（范围值即可）
3. **句长变化**: 统一/中等/丰富 — 句长是否多变
4. **虚词使用**: 多/中等/少 — 的/了/着/过 等虚词频率
5. **对话比例**: 估计对话文字占比百分比
6. **叙事视角**: 第一人称/第三人称/全知视角/有限视角
7. **排比对仗**: 多/中等/少 — 排比/对仗句频率
8. **疑问句比例**: 多/中等/少
9. **比喻使用**: 多/中等/少 — 明喻/暗喻频率
10. **拟人使用**: 多/中等/少
11. **引用用典**: 多/中等/少 — 是否常用典
12. **描写特点**: 简练/细腻/华丽/写意 — 环境/外貌/心理描写的风格
13. **平均段落长度**: 短/中/长
14. **整体风格一句话总结**: 20 字以内概括

===TEXT===
{text}
===TEXT===

按以下 JSON 格式输出（只输出 JSON）：
{{
  "词汇水平": {{"value": "通俗", "score": 7, "detail": "..."}},
  "平均句长": {{"value": "20-30字", "score": 5, "detail": "..."}},
  ...
  "整体风格总结": "一句话描述"
}}"""

    async def analyze_style(self, text: str) -> Dict[str, Any]:
        """分析一段文本的文风特征"""
        if len(text) > 4000:
            text = text[:4000]  # 截取前 4000 字符
        prompt = self.ANALYZE_PROMPT.format(text=text)
        raw = await self._chat([prompt], temperature=0.3, max_tokens=2048)

        # 尝试提取 JSON
        features = self._extract_json(raw)
        if features and isinstance(features, dict):
            return features

        logger.warning("JSON 解析失败，返回原始文本: %s", raw[:200])
        return {"raw_analysis": raw, "整体风格总结": "解析失败"}

    # ── 一致性检查 ────────────────────────────────────

    CONSISTENCY_PROMPT = """你是一位文风审校专家。有一段目标文风的描述（用 ===STYLE=== 包裹），
以及一段新的小说文本（用 ===TEXT=== 包裹）。请判断新文本在风格上与目标文风的一致性。

===STYLE===
{style_prompt}

===TEXT===
{text}

请评估：
1. 一致性评分（1-10，10=完全一致）
2. 一致的地方
3. 不一致的地方（如果有）
4. 具体建议：如何让文本更贴近目标文风

按以下 JSON 格式输出（只输出 JSON）：
{{
  "consistency_score": 8,
  "consistent_aspects": ["词汇选择一致", "句长节奏匹配"],
  "inconsistent_aspects": ["对话比例偏高"],
  "suggestions": ["减少对话，增加叙述描写"],
  "conclusion": "总体风格相近，微调对话比例即可"
}}"""

    async def check_consistency(self, text: str,
                                profile: StyleProfile) -> Dict[str, Any]:
        """检查文本与文风画像的一致性"""
        style_prompt = profile.style_prompt or self._features_to_prompt(profile.features)
        if not style_prompt:
            return {"consistency_score": 5, "error": "缺少风格描述信息"}

        if len(text) > 4000:
            text = text[:4000]

        prompt = self.CONSISTENCY_PROMPT.format(
            style_prompt=style_prompt, text=text
        )
        raw = await self._chat([prompt], temperature=0.3, max_tokens=1024)

        result = self._extract_json(raw)
        if result and isinstance(result, dict):
            return result
        return {"consistency_score": 5, "raw": raw[:200]}

    # ── 风格描述生成 ──────────────────────────────────

    DESCRIBE_PROMPT = """你是一位文风分析师。请根据以下文风量化特征，写一段 50-100 字的中文风格描述。
这段描述将作为 AI 写作 prompt 的一部分，让输出保持该风格。

特征:
{features_json}

要求：
- 自然易懂，只描述最突出的 3-5 个特征
- 直接描述「这段文字的特点是...」的风格
- 不要用 JSON 格式，用自然语言
- 100 字以内"""

    async def generate_style_prompt(self, features: Dict[str, Any]) -> str:
        """根据量化特征生成自然语言风格描述"""
        if features.get("整体风格总结"):
            return features["整体风格总结"]

        prompt = self.DESCRIBE_PROMPT.format(
            features_json=json.dumps(features, ensure_ascii=False, indent=2)
        )
        return await self._chat([prompt], temperature=0.4, max_tokens=300)

    # ── 辅助 ──────────────────────────────────────────

    @staticmethod
    def _features_to_prompt(features: Dict[str, Any]) -> str:
        """将特征字典转为简短的自然语言描述"""
        if not features:
            return ""
        parts = []
        for key in ["词汇水平", "平均句长", "对话比例", "叙事视角",
                     "描写特点", "整体风格总结"]:
            val = features.get(key, {})
            if isinstance(val, dict):
                v = val.get("value", "")
            elif isinstance(val, str):
                v = val
            else:
                v = str(val)
            if v and v != "未知":
                parts.append(f"{key}: {v}")
        return "；".join(parts) if parts else ""

    @staticmethod
    def render_style_block(profile: "StyleProfile",
                           sample_len: int = 800) -> str:
        """将文风画像渲染为完整风格指令块（生成注入用）。

        三段式：
          1. 风格总结 — 一句话概括
          2. 量化特征 — 14 维可执行约束（词汇/句长/视角/对话比例…）
          3. 原文示例 — few-shot 锚点（样本段落前 sample_len 字）
        """
        lines = []
        # 1. 风格总结
        sp = profile.style_prompt or ""
        if sp:
            lines.append(f"【风格总结】{sp}")

        # 2. 量化特征（带 score 的优先展示）
        feats = profile.features or {}
        feat_parts = []
        for key, val in feats.items():
            if key == "整体风格总结":
                continue
            if isinstance(val, dict):
                v = val.get("value", "")
                score = val.get("score")
                if v:
                    s = f"{v} ({score}分)" if score else v
                    feat_parts.append(f"{key}: {s}")
            elif isinstance(val, str) and val:
                feat_parts.append(f"{key}: {val}")
        if feat_parts:
            lines.append("【量化特征】" + "；".join(feat_parts))

        # 3. 原文示例（few-shot 锚点）
        sample = (profile.sample_text or "").strip()
        if sample:
            lines.append(f"【原文示例】以下是目标文风的原文片段，请模仿其语气、节奏与用词：\n{sample[:sample_len]}")

        return "\n".join(lines)

    @staticmethod
    def _extract_json(raw: str) -> Optional[Dict]:
        """从模型输出中提取 JSON"""
        # 尝试直接解析
        raw = raw.strip()
        # 找 {} 块
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
