"""文风量化指标 — 纯 Python 实现（无第三方依赖）

把一段文本转换成可比较的数值向量, 用于:

1. 生成后漂移检测 (``style/drift.py``) — 与目标基线对比
2. 章节间一致性巡检 (跨章巡检同一批指标)
3. 为 LLM 生成的 14 维画像 (``style/db.py``) 提供**确定性**补充:
   LLM 打分是主观的、每次调用可能不同; 本模块的正则/统计指标可复现。

设计约束: 不引入 jieba / numpy 等新依赖 —— 全部基于 ``re`` 与 ``statistics``。
中文不需要分词也能算句长、对话占比、标点丰富度、虚词比例、人称分布。
"""

from __future__ import annotations

import re
import statistics
from typing import Dict, List

# ── 切分规则 ──────────────────────────────────────────────

_SENTENCE_SPLIT = re.compile(r"[。！？!?…]+")
_PARAGRAPH_SPLIT = re.compile(r"\n+")

# 对话引号（中英文常见形式, 含弯引号）
_QUOTE_SPAN = re.compile(r"「[^」]*」|『[^』]*』|“[^”]*”|‘[^’]*’|\"[^\"]*\"|'[^']*'")

# 标点集合（用于丰富度统计）
_PUNCT_CHARS = set("。，、；：？！…—～·．「」『』（）()《》〈〉【】[]“”‘’\"':;,.!?")

# 中文功能词/虚词（高频、低信息量, 比例反映语体：口语 vs 书面/文言）
_FUNCTION_WORDS = set(
    "的了是在和与也都就而及或但却之于以被把给向从对着过地得吗呢吧啊呀哦嗯嘛"
    "们很更最又还只才即如若因故则与其乃矣乎哉"
)

# 第一人称 / 第三人称代词（视角漂移检测）
_FIRST_PERSON = ("我", "咱")
_THIRD_PERSON = ("他", "她", "它", "祂")

# 指标键（稳定命名, 供前端/报告引用）
METRIC_KEYS: List[str] = [
    "char_count",
    "sentence_count",
    "avg_sentence_length",
    "sentence_length_std",
    "short_sentence_ratio",
    "long_sentence_ratio",
    "dialogue_ratio",
    "paragraph_count",
    "avg_paragraph_length",
    "single_sentence_paragraph_ratio",
    "exclamation_ratio",
    "question_ratio",
    "ellipsis_per_1k",
    "punctuation_diversity",
    "function_word_ratio",
    "pov_first_ratio",
    "pov_third_ratio",
]

# 可参与"漂移比较"的指标（绝对量随长度变化, 不参与比较）
COMPARABLE_KEYS: List[str] = [
    "avg_sentence_length",
    "sentence_length_std",
    "short_sentence_ratio",
    "long_sentence_ratio",
    "dialogue_ratio",
    "avg_paragraph_length",
    "single_sentence_paragraph_ratio",
    "exclamation_ratio",
    "question_ratio",
    "ellipsis_per_1k",
    "punctuation_diversity",
    "function_word_ratio",
    "pov_first_ratio",
    "pov_third_ratio",
]

SHORT_SENTENCE_MAX = 10
LONG_SENTENCE_MIN = 50


def split_sentences(text: str) -> List[str]:
    """按中文句末标点切句, 去掉空白与落单标点。"""
    parts = _SENTENCE_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def split_paragraphs(text: str) -> List[str]:
    """按换行切段, 过滤空行。"""
    return [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]


def dialogue_ratio(text: str) -> float:
    """对话占比 = 引号内字符数 / 总字符数。

    与 ``polish.count_dialogue_ratio`` 的区别: 额外支持中文弯引号 “”（大模型与
    Word 粘贴文本里最常见的形式）。对空文本返回 0.0。
    """
    total = len(text)
    if total == 0:
        return 0.0
    quoted = sum(len(m) for m in _QUOTE_SPAN.findall(text))
    return round(quoted / total, 4)


def _ratio(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def function_word_ratio(text: str) -> float:
    """虚词（功能词）比例 —— 反映语体：口语/现代白话偏高, 古典/文言偏低。"""
    if not text:
        return 0.0
    hits = sum(1 for ch in text if ch in _FUNCTION_WORDS)
    return round(hits / len(text), 4)


def strip_quoted_spans(text: str) -> str:
    """剥掉引号内的对白（`「」『』“”‘’""''`）。

    用途：视角一致性判定。对白里出现"他/她"是在说**别人**，不构成叙述视角；
    不剥离会把"第一人称正文 + 一句引用第三人称的对白"误报成视角突跳（N5 评审 P1-1）。
    """
    return _QUOTE_SPAN.sub("", text)


def pov_counts(text: str, include_objects: bool = True) -> Dict[str, int]:
    """人称**计数**（第一/第三人称标记词出现次数）—— `pov_ratios` 与视角一致性校验共用。

    `include_objects=False` 时不计入 `它/祂`：第一人称场景里描述物件（"我拿起它"）
    不代表视角切换（N5 评审 P1-2）。
    """
    third_words = _THIRD_PERSON if include_objects else tuple(w for w in _THIRD_PERSON if w not in ("它", "祂"))
    return {
        "pov_first_count": sum(text.count(w) for w in _FIRST_PERSON),
        "pov_third_count": sum(text.count(w) for w in third_words),
    }


def pov_ratios(text: str) -> Dict[str, float]:
    """人称分布 —— 视角漂移（第一人称 ↔ 第三人称）的量化依据。"""
    counts = pov_counts(text)
    first = counts["pov_first_count"]
    third = counts["pov_third_count"]
    total = first + third
    if total == 0:
        return {"pov_first_ratio": 0.0, "pov_third_ratio": 0.0}
    return {
        "pov_first_ratio": round(first / total, 4),
        "pov_third_ratio": round(third / total, 4),
    }


def punctuation_diversity(text: str) -> int:
    """出现的不同标点种类数（种类丰富度, 而非频次）。"""
    return len({ch for ch in text if ch in _PUNCT_CHARS})


def measure(text: str) -> Dict[str, float]:
    """计算全部指标, 返回 ``{metric_key: value}``。

    空文本返回全 0 的指标集（不抛异常）—— 调用方无需特判。
    """
    text = text or ""
    sentences = split_sentences(text)
    paragraphs = split_paragraphs(text)
    sent_lens = [len(s) for s in sentences]
    para_lens = [len(p) for p in paragraphs]

    sent_count = len(sentences)
    char_count = len(text)

    metrics: Dict[str, float] = {
        "char_count": float(char_count),
        "sentence_count": float(sent_count),
        "avg_sentence_length": round(statistics.fmean(sent_lens), 2) if sent_lens else 0.0,
        "sentence_length_std": round(statistics.pstdev(sent_lens), 2) if len(sent_lens) > 1 else 0.0,
        "short_sentence_ratio": _ratio(sum(1 for n in sent_lens if n <= SHORT_SENTENCE_MAX), sent_count),
        "long_sentence_ratio": _ratio(sum(1 for n in sent_lens if n >= LONG_SENTENCE_MIN), sent_count),
        "dialogue_ratio": dialogue_ratio(text),
        "paragraph_count": float(len(paragraphs)),
        "avg_paragraph_length": round(statistics.fmean(para_lens), 2) if para_lens else 0.0,
        "single_sentence_paragraph_ratio": _ratio(
            sum(1 for p in paragraphs if len(split_sentences(p)) <= 1), len(paragraphs)
        ),
        "exclamation_ratio": _ratio(len(re.findall(r"[！!]", text)), sent_count),
        "question_ratio": _ratio(len(re.findall(r"[？?]", text)), sent_count),
        "ellipsis_per_1k": round(
            (text.count("…") + len(re.findall(r"\.\.\.+", text))) / (char_count / 1000), 2
        )
        if char_count
        else 0.0,
        "punctuation_diversity": float(punctuation_diversity(text)),
        "function_word_ratio": function_word_ratio(text),
    }
    metrics.update(pov_ratios(text))
    return metrics
