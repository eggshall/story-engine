"""文风漂移检测 — 生成后自动告警（纯 Python, 无需 LLM）

为什么需要独立检测器: ConStory-Bench（ACL 2026, arXiv 2603.05890）把
「叙事与文风」列为独立的失效类别（视角混淆 / 语气不一致 / 文风偏移）, 并发现
文风类错误与时间线、角色、世界观、事实类错误的相关性接近零 —— **事实一致性
检查通过, 不代表文风没漂**。因此文风需要独立工具链。

本模块做三件事:
1. 从已写完的章节建立文风基线（可复现的正则/统计指标, 见 ``metrics.py``）
2. 对新章节做多指标偏差检测, 分级 ok / warn / alert
3. 叠加 AI 套话命中（复用 ``polish`` 的 AI_PATTERNS / SOFT_PATTERNS）与自定义禁用词

不依赖 LLM: 单章一次检测在毫秒级, 可以每章都跑; LLM 只用于人工触发的深度复核。
"""

from __future__ import annotations

import re
import statistics
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypeAlias, Union

from story_engine.polish import AI_PATTERNS, SOFT_PATTERNS
from story_engine.style.metrics import COMPARABLE_KEYS, measure

# 容差条目: ("rel", 阈值) 或 ("rel", 阈值, 地板值) 或 ("abs", 阈值)
ToleranceSpec: TypeAlias = Union[Tuple[str, float], Tuple[str, float, float]]

# 容差: 指标 -> (类型, 阈值[, 地板值])。类型 rel = 相对偏差（除以 max(基线, 地板)）;
# abs = 绝对差。超过阈值即 warn, 超过 1.5 倍即 alert。
#
# 地板值（floor）的必要性 —— 真实语料实测（《全民魔女1994》1711 章）发现:
# 像"感叹句比例"基线为 0.02 这类接近 0 的指标, 纯相对偏差会把 +0.11 的绝对差
# 放大成 1176% 偏差, 导致作者自己的正常章节被误报 alert。地板值让"近零指标"
# 退回绝对比较。有界比率（0-1 的 ratio 类）直接改用 abs。
DEFAULT_TOLERANCES: Dict[str, ToleranceSpec] = {
    "avg_sentence_length": ("rel", 0.30, 8.0),
    "sentence_length_std": ("rel", 0.45, 5.0),
    "short_sentence_ratio": ("abs", 0.18),
    "long_sentence_ratio": ("abs", 0.18),
    "dialogue_ratio": ("abs", 0.18),
    "avg_paragraph_length": ("rel", 0.40, 10.0),
    "single_sentence_paragraph_ratio": ("abs", 0.22),
    "exclamation_ratio": ("abs", 0.12),
    "question_ratio": ("abs", 0.12),
    "ellipsis_per_1k": ("abs", 6.0),
    "punctuation_diversity": ("rel", 0.30, 4.0),
    "function_word_ratio": ("rel", 0.20, 0.08),
    "pov_first_ratio": ("abs", 0.35),
}

# ── 分级聚合规则 ─────────────────────────────────────────
# 逐指标判级在真实语料上噪声过大:《全民魔女1994》1711 章实测, 逐指标判级会让
# 作者自己的章节 58% 被判 alert（对话/省略号/感叹号这类"当下场景"指标天然摆动）。
# 因此整体级别由聚合规则决定, 单指标只是证据:
#   任一指标 ≥ ALERT_STRONG_RATIO 倍容差  → alert
#   或 ≥ ALERT_MILD_COUNT 个指标 ≥ 1 倍容差 → alert
#   有任一指标 ≥ 1 倍容差 / 命中 AI 套话 / 命中禁用词 → warn（禁用词直接 alert）
ALERT_STRONG_RATIO = 2.0
ALERT_MILD_COUNT = 4

# 指标 -> 中文名（报告用）
METRIC_LABELS: Dict[str, str] = {
    "avg_sentence_length": "平均句长",
    "sentence_length_std": "句长波动",
    "short_sentence_ratio": "短句占比",
    "long_sentence_ratio": "长句占比",
    "dialogue_ratio": "对话占比",
    "avg_paragraph_length": "平均段长",
    "single_sentence_paragraph_ratio": "单句段落占比",
    "exclamation_ratio": "感叹句比例",
    "question_ratio": "疑问句比例",
    "ellipsis_per_1k": "省略号密度",
    "punctuation_diversity": "标点种类数",
    "function_word_ratio": "虚词比例",
    "pov_first_ratio": "第一人称占比",
}

# 偏差方向 -> 建议措辞
_DIRECTION_HINT: Dict[str, str] = {
    "avg_sentence_length": "句长偏离基线：短句化需补足描写节奏, 长句化需警惕翻译腔式从句堆叠",
    "sentence_length_std": "句长波动偏离基线：句长过于均一会显得机械, 过于跳跃会显得割裂",
    "short_sentence_ratio": "短句比例偏离：动作/紧张场景可多短句, 抒情段落需回落",
    "long_sentence_ratio": "长句比例偏离：连续长句是 AI 味的典型特征",
    "dialogue_ratio": "对话占比偏离：场景类型（对话/独白/行动）与基线不同, 或对话被叙述吞掉",
    "avg_paragraph_length": "段落长度偏离：网文手机阅读习惯偏短段",
    "single_sentence_paragraph_ratio": "单句成段比例偏离：影响阅读节奏与强调感",
    "exclamation_ratio": "感叹句比例偏离：过多感叹会削弱情绪张力",
    "question_ratio": "疑问句比例偏离：影响悬念密度",
    "ellipsis_per_1k": "省略号密度偏离：常与语气拖沓相关",
    "punctuation_diversity": "标点种类偏离：标点单一化是文风退化的早期信号",
    "function_word_ratio": "虚词比例偏离：口语化/书面化程度与基线不一致",
    "pov_first_ratio": "人称占比偏离：疑似视角漂移（第一人称 ↔ 第三人称混用）",
}


def build_baseline(samples: Iterable[str]) -> Dict[str, float]:
    """从若干已写章节建立基线 —— 每个指标取中位数（抗单章异常值）。"""
    measurements = [measure(s) for s in samples if s and s.strip()]
    if not measurements:
        return {key: 0.0 for key in COMPARABLE_KEYS}

    baseline: Dict[str, float] = {}
    for key in COMPARABLE_KEYS:
        values = [m.get(key, 0.0) for m in measurements]
        baseline[key] = round(statistics.median(values), 4)
    return baseline


def _tolerance(entry: ToleranceSpec) -> tuple[str, float, float]:
    """把容差条目归一化为 (kind, threshold, floor)；2 元组兼容（floor=0）。"""
    if len(entry) >= 3:
        kind, threshold, floor = entry[0], entry[1], entry[2]
        return str(kind), float(threshold), float(floor)
    return str(entry[0]), float(entry[1]), 0.0


def _deviation(value: float, base: float, kind: str, floor: float = 0.0) -> float:
    """返回偏差: rel 型 = |差|/max(|基线|, 地板); abs 型 = |差|。"""
    if kind == "abs":
        return abs(value - base)
    denom = max(abs(base), floor)
    if denom == 0:
        return 0.0 if value == 0 else 1.0
    return abs(value - base) / denom


def detect_drift(
    text: str,
    baseline: Dict[str, float],
    tolerances: Optional[Dict[str, ToleranceSpec]] = None,
    forbidden_words: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """检测一段文本相对基线的文风漂移。

    返回结构::

        {
          "score": 0-100,          # 文风相似度（100 = 完全贴合基线）
          "level": "ok|warn|alert",
          "metrics": {key: {value, baseline, deviation, threshold, severity}},
          "alerts": ["..."],       # 人可读告警
          "ai_tells": {count, hits},
          "forbidden_hits": [...],
          "suggestions": [...],
          "character_count": int,
        }
    """
    tol: Dict[str, ToleranceSpec] = dict(DEFAULT_TOLERANCES)
    if tolerances:
        tol.update(tolerances)

    current = measure(text or "")
    details: Dict[str, Dict[str, Any]] = {}
    alerts: List[str] = []
    suggestions: List[str] = []
    deviations: List[float] = []

    for key in COMPARABLE_KEYS:
        kind, threshold, floor = _tolerance(tol.get(key, ("rel", 0.5)))
        if threshold <= 0:
            continue
        value = current.get(key, 0.0)
        base = baseline.get(key, 0.0)
        dev = _deviation(value, base, kind, floor)
        ratio = dev / threshold
        severity = "ok" if ratio <= 1 else ("warn" if ratio <= 1.5 else "alert")
        deviations.append(min(ratio, 1.5))

        details[key] = {
            "value": round(value, 4),
            "baseline": round(base, 4),
            "deviation": round(dev, 4),
            "threshold": threshold,
            "kind": kind,
            "ratio": round(ratio, 3),
            "severity": severity,
        }

        if severity != "ok":
            label = METRIC_LABELS.get(key, key)
            direction = "高于" if value > base else "低于"
            alerts.append(
                f"{label}{direction}基线 {ratio * 100:.0f}% 容差"
                f"（当前 {value:.2f} / 基线 {base:.2f}）"
            )
            hint = _DIRECTION_HINT.get(key)
            if hint and hint not in suggestions:
                suggestions.append(hint)

    # ── AI 套话命中（不依赖 LLM, 与 polish 的精修词表同源）──
    # AI_PATTERNS 与 SOFT_PATTERNS 会重叠命中同一处文本（如 "然而，" 同时被
    # `然而[，,]` 与 `然而` 命中）。按起始位置去重: 同一处套话只算一次。
    hits: List[Dict[str, Any]] = []
    seen_positions: set[int] = set()
    for pattern in dict.fromkeys([p for p, _ in AI_PATTERNS] + list(SOFT_PATTERNS)):
        for match in re.finditer(pattern, text or ""):
            if match.start() in seen_positions:
                continue
            seen_positions.add(match.start())
            hits.append({"pattern": pattern, "match": match.group(), "position": match.start()})
    hits.sort(key=lambda h: h["position"])
    text_len = len(text or "")
    ai_density = len(hits) / (text_len / 1000) if text_len else 0.0
    if hits:
        suggestions.append(
            f"命中 {len(hits)} 处 AI 套话（{ai_density:.2f}/千字）, 建议过一遍精修 DeAIFilter"
        )

    # ── 自定义禁用词 ──
    forbidden_hits = []
    for word in forbidden_words or []:
        if not word:
            continue
        count = (text or "").count(word)
        if count:
            forbidden_hits.append({"word": word, "count": count})
    if forbidden_hits:
        words = "、".join(f"{h['word']}×{h['count']}" for h in forbidden_hits)
        alerts.append(f"命中禁用词: {words}")
        suggestions.append("禁用词需替换后再交付（硬约束, 见 SCHEMA 的文风层）")

    # ── 评分: 100 - 平均偏差占比（上限 60 分扣减, 保留可读性）──
    mean_ratio = statistics.fmean(deviations) if deviations else 0.0
    score = max(0, min(100, round(100 - mean_ratio * 100)))

    # ── 整体分级: 聚合规则（见文件头 ALERT_* 常量说明）──
    ratio_map = {key: d["ratio"] for key, d in details.items()}
    mild = [key for key, r in ratio_map.items() if r >= 1.0]
    strong = [key for key, r in ratio_map.items() if r >= ALERT_STRONG_RATIO]

    if forbidden_hits or strong or len(mild) >= ALERT_MILD_COUNT:
        level = "alert"
    elif mild or hits:
        level = "warn"
    else:
        level = "ok"

    return {
        "score": score,
        "level": level,
        "level_reason": _level_reason(level, strong, mild, forbidden_hits, hits),
        "metrics": details,
        "alerts": alerts,
        "ai_tells": {
            "count": len(hits),
            "per_1k": round(ai_density, 3),
            "hits": hits[:30],
        },
        "forbidden_hits": forbidden_hits,
        "suggestions": suggestions,
        "character_count": text_len,
    }


def _level_reason(
    level: str,
    strong: List[str],
    mild: List[str],
    forbidden_hits: List[Dict[str, Any]],
    hits: List[Dict[str, Any]],
) -> str:
    """把整体级别翻译成一句可读依据 —— 便于前端展示与人工复核。"""
    if forbidden_hits:
        return "命中禁用词（硬约束）"
    if level == "alert":
        if strong:
            labels = "、".join(METRIC_LABELS.get(k, k) for k in strong[:3])
            return f"指标严重偏离: {labels}"
        return f"{len(mild)} 项指标同时偏离基线（疑似整体文风漂移）"
    if level == "warn":
        if mild:
            labels = "、".join(METRIC_LABELS.get(k, k) for k in mild[:3])
            return f"轻度偏离: {labels}" + (f"；另有 {len(hits)} 处 AI 套话" if hits else "")
        return f"命中 {len(hits)} 处 AI 套话"
    return "与基线一致"
