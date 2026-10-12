"""Lorebook 管理器 — **按小说绑定**（N8）的 CRUD + 关键词触发引擎。

## 存储约定（与角色卡同源，见 `docs/design/P7-MVP-PLAN.md` §「N8 决策」）

- 真源 = `<小说目录>/novel.json` 的 `lorebooks` 字典
- 镜像 = `<小说目录>/lore/<设定集名>.json`（human-readable，由 `_write_files` 重建）
- **必须经 `load_novel → 改模型 → save_novel` 写入**：绕过模型直接写镜像目录，
  下一次保存章节会被整目录清空（作者眼里是「设定集莫名其妙没了」）

## 为什么要改（N8）

改之前是世界观的全局目录 `data/lore/`（`LOREB_DIR`），于是**所有书共用一副设定集**：
A 书的修仙设定会注入到 B 书的都市故事里。N8 已把角色卡改成按书绑定，世界观当时没跟着做，
留下「角色卡按书、世界观全局」两套语义并存 —— 本文件消灭这个不一致。

## 触发引擎为什么是纯函数

`find_matching_entries` / `build_lore_context` 接收「设定集字典」而不是自己去读磁盘：
- `WritingEngine` 与装配器都已经持有 `novel`（内含 `lorebooks`），再读一次磁盘既浪费、
  又可能与手上这本不一致（读到的是刚被别的进程改过的版本）；
- 纯函数让「命中哪些条目」可以脱离文件系统直接断言。
"""

from __future__ import annotations

import logging
from typing import List, Mapping, Optional, Tuple

from story_engine.core.errors import NovelNotFound  # 共享异常，不反向依赖 characters（评审 P2-5）
from story_engine.core.models import LoreBook, LorebookEntry, Novel
from story_engine.tools.novel_storage import load_novel, save_novel

logger = logging.getLogger("story_engine.lore")

# 单次注入最多带多少条设定（与 legacy 行为一致）
DEFAULT_MAX_RESULTS = 10


def _require_novel(novel_id: str) -> Novel:
    """取小说；不存在就**显式报错**，不要静默返回空 —— 否则界面显示"没有设定"是骗人的。"""
    novel = load_novel(novel_id)
    if novel is None:
        raise NovelNotFound(f"小说不存在: {novel_id}")
    return novel


# ── CRUD（按小说绑定）────────────────────────────────────

def list_lorebooks(novel_id: str) -> List[str]:
    """列出**这本书**的设定集名（按名排序，结果确定）。"""
    return sorted(_require_novel(novel_id).lorebooks.keys())


def load_lorebook(novel_id: str, name: str) -> Optional[LoreBook]:
    """读一本书的某个设定集；不存在返回 None（存在但没有 = 空是两回事）。"""
    return _require_novel(novel_id).lorebooks.get(name)


def save_lorebook(novel_id: str, book: LoreBook, overwrite: bool = False) -> bool:
    """保存设定集。

    同名默认**不覆盖**（返回 False 且什么都不改）——「不静默覆盖作者内容」是与角色卡
    一致的原则：要覆盖必须显式 `overwrite=True`。
    """
    novel = _require_novel(novel_id)
    if book.name in novel.lorebooks and not overwrite:
        return False
    novel.lorebooks[book.name] = book
    save_novel(novel, novel_id)
    return True


def delete_lorebook(novel_id: str, name: str) -> bool:
    """删除；不存在返回 False（不抛）。"""
    novel = _require_novel(novel_id)
    if name not in novel.lorebooks:
        return False
    del novel.lorebooks[name]
    save_novel(novel, novel_id)
    return True


# ── 关键词触发引擎（纯函数，不碰磁盘）────────────────────

def find_matching_entries(
    books: Mapping[str, LoreBook], text: str, max_results: int | None = DEFAULT_MAX_RESULTS
) -> List[Tuple[str, str, LorebookEntry]]:
    """扫描 `text` 里出现的关键词，返回 `(书名, 条目 ID, 条目)`，按优先级降序。

    - 只在**传入的这批设定集**里找（书间隔离由调用方保证：只传本书的 `lorebooks`）
    - `enabled=False` 的条目不参与
    - 一个条目命中多个关键词也只算一次
    - `max_results=None` 表示**不截断**，由调用方自己负责上限并**自报**被丢的条数。
      装配器就是这么用的：静默丢掉第 N+1 条会让注入清单与真实注入不一致（N8 评审 P2-2）。
      默认值 10 保留给 `build_lore_context` 这条 legacy 一整块路径。
    """
    matches: List[Tuple[str, str, LorebookEntry, int]] = []
    for book_name, book in (books or {}).items():
        for entry_id, entry in getattr(book, "entries", {}).items():
            if not entry.enabled:
                continue
            if any(key in text for key in entry.keys):
                matches.append((book_name, entry_id, entry, entry.priority))

    # 优先级降序；同优先级按 (书名, 条目 ID) 升序 —— 结果必须确定，否则同输入不同输出
    matches.sort(key=lambda m: (-m[3], m[0], m[1]))
    if max_results is None:
        return [(book, entry_id, entry) for book, entry_id, entry, _p in matches]
    return [(book, entry_id, entry) for book, entry_id, entry, _p in matches[:max_results]]


def build_lore_context(
    books: Mapping[str, LoreBook], text: str, max_results: int = DEFAULT_MAX_RESULTS
) -> str:
    """把命中的设定拼成一段上下文（legacy 形态：一整块，带表头）。

    legacy `engine._build_world_context()` 走这条路；走装配器的新路径按条目注入
    （见 `writer/context_sources.py::_lore_provider`），那份能精确到条目的 manifest。
    """
    matched = find_matching_entries(books, text, max_results)
    if not matched:
        return ""

    blocks = ["【世界观设定 — 自动注入】"]
    for book_name, _entry_id, entry in matched:
        blocks.append(f"● [{book_name}] {'|'.join(entry.keys)}")
        blocks.append(f"  {entry.content}")
        blocks.append("")

    return "\n".join(blocks)


# ── 示例设定集 ──────────────────────────────────────────

def create_example_lorebook() -> LoreBook:
    """创建示例世界观设定集（仅作为示例数据，不自动入库）。"""
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
