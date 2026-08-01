"""固定流程工具集 — 关键词提取 / 章节摘要 / 一致性检查"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


# ── 关键词提取 ────────────────────────────────

# 常见中文角色/地名的模式
_NAME_PATTERN = re.compile(
    r"(?:[^。，；、\s]{2,4}(?:先生|小姐|娘娘|公子|王爷|将军|大人|长老|掌门|宗主|师兄|师妹|师父|徒弟| Emperor|King|Lord|Queen|Princess))"
    r"|(?:[^。，；、\s]{2,4}(?:国|城|山|谷|峰|岛|湖|河|州|府|殿|宫|塔|寺|观|村|镇))"
    r"|(?:「([^」]*)」)"
    r"|(?:『([^』]*)』)"
)


def extract_keywords(text: str, min_len: int = 2, max_keywords: int = 20) -> List[Dict[str, Any]]:
    """从文本中提取可能的关键词（角色名/地名/势力名等）

    返回:
        [{"word": str, "type": str, "count": int}, ...]
    """
    # 1. 引号内的内容（通常是专有名词）
    quoted = re.findall(r'[「『]([^」』]{2,10})[」』]', text)

    # 2. 匹配命名实体模式
    named = [m.group(0) for m in _NAME_PATTERN.finditer(text)]

    # 3. 统计词频（2~6 字词）
    words = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
    word_freq: Dict[str, int] = {}
    for w in words:
        word_freq[w] = word_freq.get(w, 0) + 1

    # 合并结果
    seen: set[str] = set()
    result: List[Dict[str, Any]] = []

    for w in quoted:
        if w not in seen and len(w) >= min_len:
            seen.add(w)
            result.append({"word": w, "type": "引用名", "count": word_freq.get(w, 1)})

    for w in named:
        if w not in seen and len(w) >= min_len:
            seen.add(w)
            result.append({"word": w, "type": "命名实体", "count": word_freq.get(w, 1)})

    for w, cnt in sorted(word_freq.items(), key=lambda x: -x[1]):
        if w not in seen and len(w) >= min_len and cnt >= 3:
            seen.add(w)
            result.append({"word": w, "type": "高频词", "count": cnt})
            if len(result) >= max_keywords:
                break

    return result[:max_keywords]


# ── 章节摘要 ──────────────────────────────────

def summarize_chapter(content: str, max_chars: int = 200) -> str:
    """对章节内容做简单摘要（基于首段 + 关键句提取）"""
    if not content:
        return ""

    # 取前 200 字作为基础
    content = content.strip()
    preview = content[:max_chars]

    # 尝试找 "本章要点" "总结" 等标记
    summary_markers = ["本章要点", "本章小结", "总结", "Summary", "要点"]
    for marker in summary_markers:
        idx = content.find(marker)
        if idx >= 0:
            snippet = content[idx:idx + max_chars]
            return snippet[:max_chars]

    return preview


# ── 一致性检查 ────────────────────────────────

def check_consistency(
    new_text: str,
    known_names: List[str],
    known_places: List[str] = None,
) -> List[Dict[str, Any]]:
    """检查新文本中已知角色/地名是否保持一致

    返回:
        [{"type": "character"|"place"|"typo", "name": str, "issue": str}, ...]
    """
    issues: List[Dict[str, Any]] = []
    known_places = known_places or []

    # 检查角色名是否被错误改写
    for name in known_names:
        # 拆分角色名各部分
        parts = list(name)
        for i in range(1, len(parts)):
            alt = name[:i] + "了" + name[i:]
            if alt in new_text:
                issues.append({
                    "type": "typo",
                    "name": name,
                    "issue": f"可能存在错字「{alt}」，应为「{name}」",
                })
                break

    # 检查地名是否被错误改写
    for place in known_places:
        if place in new_text:
            continue
        # 模糊匹配
        for word in re.findall(r'[\u4e00-\u9fff]{2,6}', new_text):
            if len(word) >= 2 and len(place) >= 2:
                same_chars = sum(1 for a, b in zip(word, place) if a == b)
                if same_chars >= len(place) - 1 and word != place:
                    issues.append({
                        "type": "place",
                        "name": place,
                        "issue": f"地名疑似不一致: 文中写「{word}」，设定为「{place}」",
                    })

    return issues


# ── 上下文压缩 ────────────────────────────────

def compress_history(
    messages: List[Dict[str, str]],
    max_messages: int = 10,
    reserve_last: int = 4,
) -> List[Dict[str, str]]:
    """压缩对话历史：保留最近 N 条完整对话，前面的压缩为摘要"""
    if len(messages) <= max_messages:
        return messages

    # 保留最近 reserve_last 条完整消息
    tail = messages[-reserve_last:]
    head = messages[:-reserve_last]

    # 前面的合并成一条摘要
    summary_text = "以下为之前的对话摘要：\n"
    for m in head:
        role = "用户" if m.get("role") == "user" else "AI"
        content = m.get("content", "")[:100]
        summary_text += f"· {role}: {content}\n"

    summary_msg = {"role": "system", "content": summary_text}
    return [summary_msg] + tail
