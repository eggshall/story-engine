"""P6 数据管线 — 语料主索引管理 (meta/index.json)。

每条记录字段:
    id           唯一 ID (gutenberg:24264 / import:作品名)
    title        标题
    author       作者（可为空）
    translator   译者（中译本时）
    source       来源类别 (gutenberg/ctext/import)
    gutenberg_id Gutenberg 编号（来源为 gutenberg 时）
    genre        题材标签 (serious/humor_satire/tragic/popular/other)
    file         语料文件相对路径 (corpus/...)
    chars        字数
    paragraphs   段落数
    created_at   入库时间
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List

from .config import INDEX_FILE, ensure_dirs

logger = logging.getLogger("story_engine.index")

# 单写者锁：串行化读改写，避免并发丢更新（L15.1）
_write_lock = threading.Lock()


def load_index() -> List[Dict[str, Any]]:
    if not INDEX_FILE.exists():
        return []
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        logger.warning("索引内容非列表，返回空")
        return []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("索引损坏，防御式返回空: %s", e)
        return []


def save_index(records: List[Dict[str, Any]]) -> None:
    ensure_dirs()
    # 临时文件 + os.replace 原子落盘，避免写一半留下损坏索引
    tmp = INDEX_FILE.with_name(INDEX_FILE.name + ".tmp")
    tmp.write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    os.replace(tmp, INDEX_FILE)


def add_record(record: Dict[str, Any]) -> None:
    """追加一条记录（按 id 去重）。单写者锁串行化读改写。"""
    with _write_lock:
        records = load_index()
        records = [r for r in records if r.get("id") != record.get("id")]
        record.setdefault("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        records.append(record)
        save_index(records)


def stats() -> Dict[str, Any]:
    """索引统计：总数/各题材/各来源数量。"""
    records = load_index()
    by_genre: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    total_chars = 0
    for r in records:
        g = r.get("genre", "other")
        s = r.get("source", "?")
        by_genre[g] = by_genre.get(g, 0) + 1
        by_source[s] = by_source.get(s, 0) + 1
        total_chars += r.get("chars", 0)
    return {
        "total": len(records),
        "total_chars": total_chars,
        "by_genre": by_genre,
        "by_source": by_source,
    }
