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
import time
from typing import Any, Dict, List, Optional

from .config import INDEX_FILE, ensure_dirs


def load_index() -> List[Dict[str, Any]]:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return []


def save_index(records: List[Dict[str, Any]]) -> None:
    ensure_dirs()
    INDEX_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def add_record(record: Dict[str, Any]) -> None:
    """追加一条记录（按 id 去重）。"""
    records = load_index()
    records = [r for r in records if r.get("id") != record.get("id")]
    record.setdefault("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
    records.append(record)
    save_index(records)


def find_by_id(rid: str) -> Optional[Dict[str, Any]]:
    for r in load_index():
        if r.get("id") == rid:
            return r
    return None


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
