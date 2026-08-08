"""精修系统 — 去AI味 / 风格一致性 / 节奏分析 / 连贯性检查"""

from __future__ import annotations

import re
from typing import Dict, List

from story_engine.core.models import Chapter

# ==========================================================
# 去AI味 — 去除 AI 写作的常见套话
# ==========================================================

# AI 高频套话模式（正则）
AI_PATTERNS = [
    (r"然而[，,]", "然而"),
    (r"但是[，,]", "但是"),
    (r"毕竟[，,]", "毕竟"),
    (r"值得注意的是[，,]", ""),
    (r"值得一提的是[，,]", ""),
    (r"毋庸置疑[，,]", ""),
    (r"不可否认[，,]", ""),
    (r"从某种角度来说[，,]", ""),
    (r"在一定程度上[，,]", ""),
    (r"某种程度", ""),
    (r"可以说[，,]", ""),
    (r"毫无疑问[，,]", ""),
    (r"不禁让人", "让人"),
    (r"不由得", "不由"),
    (r"仿佛[仿佛]", "仿佛"),
    (r"似乎[似乎]", "似乎"),
    (r"让我们[来]?", ""),
    (r"在[\w]+的[\w]+下", ""),  # "在...的...下" 结构
]

# 软性提示词（不强制删除，但标记出来）
SOFT_PATTERNS = [
    r"然而",
    r"但是",
    r"毕竟",
    r"值得一提的是",
    r"值得注意的是",
    r"毫无疑问",
    r"毋庸置疑",
    r"不可否认",
    r"从某种程度上",
    r"在一定程度上",
    r"可以说",
    r"不禁",
    r"不由得",
]

# 连续短句检测（短句长度阈值）
SHORT_SENTENCE_THRESHOLD = 5  # 字数


class DeAIFilter:
    """去AI味处理器"""

    def __init__(self, aggressive: bool = False) -> None:
        self.aggressive = aggressive

    def clean(self, text: str) -> str:
        """应用 AI 套话过滤"""
        result = text
        for pattern, replacement in AI_PATTERNS:
            result = re.sub(pattern, replacement, result)
        return result

    def scan_soft(self, text: str) -> List[Dict]:
        """扫描软性AI痕迹，返回标记列表"""
        findings = []
        for pattern in SOFT_PATTERNS:
            for match in re.finditer(pattern, text):
                findings.append({
                    "pattern": pattern,
                    "match": match.group(),
                    "position": match.start(),
                    "context": text[max(0, match.start() - 20):match.end() + 20],
                })
        return findings

    def report(self, text: str) -> Dict:
        """生成去AI味分析报告"""
        soft_hits = self.scan_soft(text)
        original_len = len(text)
        cleaned = self.clean(text)
        cleaned_len = len(cleaned)

        return {
            "original_length": original_len,
            "cleaned_length": cleaned_len,
            "removed_chars": original_len - cleaned_len,
            "soft_hits_count": len(soft_hits),
            "soft_hits": soft_hits[:20],  # 最多显示20条
        }


# ==========================================================
# 风格一致性
# ==========================================================

def count_dialogue_ratio(text: str) -> float:
    """计算对话占比（对话字数 / 总字数）"""
    dialogues = re.findall(r"「[^」]*」|『[^』]*』|'[^']*'|\"[^\"]*\"", text)
    dialogue_chars = sum(len(d) for d in dialogues)
    total_chars = len(text)
    return dialogue_chars / total_chars if total_chars > 0 else 0.0


def detect_narrative_style(text: str) -> Dict:
    """检测叙事风格特征"""
    sentences = re.split(r"[。！？\n]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return {"avg_sentence_length": 0, "dialogue_ratio": 0,
                "paragraph_count": 0, "sentence_count": 0, "character_count": len(text)}

    avg_len = sum(len(s) for s in sentences) / len(sentences)
    dialogue_ratio = count_dialogue_ratio(text)

    paragraphs = [p for p in text.split("\n\n") if p.strip()]

    return {
        "avg_sentence_length": round(avg_len, 1),
        "dialogue_ratio": round(dialogue_ratio, 3),
        "paragraph_count": len(paragraphs),
        "sentence_count": len(sentences),
        "character_count": len(text),
    }


def check_style_consistency(chapters: List[Chapter]) -> Dict:
    """检查多章节间的风格一致性"""
    if len(chapters) < 2:
        return {"consistent": True, "message": "章节数不足2章，无法对比"}

    styles = []
    for ch in chapters:
        styles.append({
            "chapter": ch.chapter_number,
            "title": ch.title,
            **detect_narrative_style(ch.content),
        })

    # 计算标准差
    ratios = [s["dialogue_ratio"] for s in styles]
    avg = sum(ratios) / len(ratios)
    variance = sum((r - avg) ** 2 for r in ratios) / len(ratios)
    std_dev = variance ** 0.5

    warning = std_dev > 0.15  # 对话占比偏差超过15%视为警告

    return {
        "consistent": not warning,
        "std_dev_dialogue_ratio": round(std_dev, 4),
        "avg_dialogue_ratio": round(avg, 4),
        "message": "风格基本一致" if not warning else "警告：各章节对话占比差异较大，可能风格不统一",
        "chapter_styles": styles,
    }


# ==========================================================
# 节奏分析
# ==========================================================

# 网文爽点/钩子关键词
HOOK_KEYWORDS = [
    "突然", "没想到", "竟然", "原来", "真相是", "就在此时",
    "转机", "意外", "震惊", "不可思议", "恐怖的是",
    "一抹寒光", "一道身影", "一声巨响",
    "突破", "晋级", "觉醒", "获得", "得到",
    "冷笑", "嘴角上扬", "眼神一变",
]

SUSPENSE_PATTERNS = [
    r"究竟[^。？]*[？]",
    r"难道[^。？]*[？]",
    r"到底[^。？]*[？]",
    r"谁[^。？]*[？]",
    r"什么[^。？]*[？]",
]


def analyze_rhythm(text: str) -> Dict:
    """分析章节节奏：爽点密度、钩子强度等"""
    if not text:
        return {"hook_count": 0, "hook_density": 0, "suspense_count": 0,
                "paragraph_count": 0, "avg_paragraph_length": 0,
                "long_paragraphs": 0, "rating": "无内容"}

    hook_count = sum(1 for kw in HOOK_KEYWORDS if kw in text)

    suspense_count = 0
    for pattern in SUSPENSE_PATTERNS:
        suspense_count += len(re.findall(pattern, text))

    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    para_lens = [len(p) for p in paragraphs]
    avg_para_len = sum(para_lens) / len(para_lens) if para_lens else 0

    return {
        "hook_count": hook_count,
        "hook_density": round(hook_count / (len(text) / 1000), 2),  # 每千字
        "suspense_count": suspense_count,
        "paragraph_count": len(paragraphs),
        "avg_paragraph_length": round(avg_para_len, 0),
        "long_paragraphs": sum(1 for plen in para_lens if plen > 300),  # 超过300字的段落
        "rating": _rate_rhythm(hook_count, len(text)),
    }


def _rate_rhythm(hooks: int, text_length: int) -> str:
    """给出节奏评级"""
    chars_per_hook = text_length / max(hooks, 1)
    if chars_per_hook < 300:
        return "紧凑 — 爽点密集"
    elif chars_per_hook < 800:
        return "适中 — 节奏良好"
    elif chars_per_hook < 1500:
        return "偏慢 — 建议增加爽点"
    else:
        return "沉闷 — 缺乏钩子，建议大幅调整"


# ==========================================================
# 连贯性检查
# ==========================================================

def check_continuity(text: str, known_names: List[str]) -> Dict:
    """检查名称一致性"""
    if not known_names:
        return {"consistent": True, "issues": []}

    issues = []
    # 简单启发式：对每个已知名称检查前一次出现后是否在后续文中消失太久
    for name in known_names:
        # 检查是否有相似但不一致的拼写（仅限中文名）
        if re.match(r"^[\u4e00-\u9fff]{2,4}$", name):
            # 找出文中所有出现的位置
            positions = [m.start() for m in re.finditer(re.escape(name), text)]
            if not positions:
                issues.append({"name": name, "issue": "该角色在本章中未出现"})
            elif len(positions) == 1 and len(text) > 2000:
                issues.append({"name": name, "issue": "该角色仅在开头出现一次"})

    return {
        "consistent": len(issues) == 0,
        "issues": issues,
    }
