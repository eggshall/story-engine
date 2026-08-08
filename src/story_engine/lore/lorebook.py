"""Lorebook 管理器 — CRUD + 关键词触发检索"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from story_engine.core.config import data_dir
from story_engine.core.models import LoreBook, LorebookEntry

LOREB_DIR = data_dir() / "lore"


def _ensure_dir() -> None:
    LOREB_DIR.mkdir(parents=True, exist_ok=True)


def _lore_path(name: str) -> Path:
    return LOREB_DIR / f"{name}.json"


def list_lorebooks() -> List[str]:
    """列出所有设定集"""
    _ensure_dir()
    return sorted(p.stem for p in LOREB_DIR.glob("*.json"))


def load_lorebook(name: str) -> Optional[LoreBook]:
    path = _lore_path(name)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return LoreBook(**data)


def save_lorebook(book: LoreBook, overwrite: bool = False) -> bool:
    _ensure_dir()
    path = _lore_path(book.name)
    if path.exists() and not overwrite:
        return False
    with open(path, "w", encoding="utf-8") as f:
        json.dump(book.model_dump(exclude_none=True), f, ensure_ascii=False, indent=2)
    return True


def delete_lorebook(name: str) -> bool:
    path = _lore_path(name)
    if not path.exists():
        return False
    path.unlink()
    return True


# ── 关键词触发引擎 ──────────────────────────────────────

def find_matching_entries(text: str, max_results: int = 10) -> List[tuple[str, LorebookEntry]]:
    """扫描文本中出现的 Lorebook 关键词，返回匹配条目（按优先级排序）"""
    matches: List[tuple[str, LorebookEntry, int]] = []  # (book_name, entry, priority)

    for book_name in list_lorebooks():
        book = load_lorebook(book_name)
        if not book:
            continue
        for entry_id, entry in book.entries.items():
            if not entry.enabled:
                continue
            # 检查任意关键词是否出现在文本中
            for key in entry.keys:
                if key in text:
                    matches.append((book_name, entry, entry.priority))
                    break  # 一个条目只匹配一次

    # 按优先级降序排列
    matches.sort(key=lambda x: x[2], reverse=True)
    return [(name, entry) for name, entry, _ in matches[:max_results]]


def build_lore_context(text: str, max_results: int = 10) -> str:
    """从文本中触发 Lorebook 条目，拼成上下文字符串注入提示词"""
    matched = find_matching_entries(text, max_results)
    if not matched:
        return ""

    blocks = ["【世界观设定 — 自动注入】"]
    for book_name, entry in matched:
        blocks.append(f"● [{book_name}] {'|'.join(entry.keys)}")
        blocks.append(f"  {entry.content}")
        blocks.append("")

    return "\n".join(blocks)


# ── 示例设定集 ──────────────────────────────────────────

def create_example_lorebook() -> LoreBook:
    """创建示例世界观设定集"""
    return LoreBook(
        name="天玄大陆",
        description="修仙世界 · 天玄大陆的基础设定",
        entries={
            "culti-levels": LorebookEntry(
                keys=["筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫"],
                content="修仙境界从低到高：筑基→金丹→元婴→化神→炼虚→合体→大乘→渡劫。"
                        "每阶分前、中、后期。渡劫成功飞升仙界，失败则兵解或陨落。",
                priority=80,
                category="修炼体系",
            ),
            "tianxuan-zong": LorebookEntry(
                keys=["天玄宗", "天玄"],
                content="天玄宗：东域三大宗门之一，以剑修和冰系功法闻名。宗主是渡劫期大能。"
                        "宗门位于冰封山脉，常年积雪，但灵力极为充沛。",
                priority=70,
                category="势力",
            ),
            "bingfeng-lingti": LorebookEntry(
                keys=["冰凤灵体", "冰凤"],
                content="冰凤灵体：上古冰凤血脉觉醒的体质。修炼冰系功法速度是常人的十倍，"
                        "但体内寒气会在月圆之夜反噬，需要至阳之物调和。",
                priority=90,
                category="特殊体质",
            ),
            "snow-fox": LorebookEntry(
                keys=["雪狐", "灵兽"],
                content="雪狐：天玄宗周边的灵兽，通体雪白，拥有微弱的冰系灵力。"
                        "智商极高，可通人言。百年以上的雪狐可以化形。",
                priority=50,
                category="灵兽",
            ),
        },
    )
