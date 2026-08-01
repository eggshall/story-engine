"""文风数据库 — SQLite 存储层

表结构:
  - style_profiles: 文风画像主表（每部作品/作者一条）
  - style_features: 量化特征表（JSON 存储特征向量）
  - style_samples: 代表性段落（原文摘录）
  - style_descriptions: 自然语言风格描述（注入 prompt 用）
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from story_engine.core.config import data_dir

_log = threading.local()

STYLE_DB_DIR = data_dir() / "style_profiles"
STYLE_DB_PATH = STYLE_DB_DIR / "style_profiles.db"


# ── 数据类 ─────────────────────────────────────────────

@dataclass
class StyleProfile:
    """文风画像"""
    name: str  # 显示名称，如 "金庸风格"、"鲁迅风格"
    id: str = ""  # 唯一 ID (auto-generate)
    author: str = ""  # 原作者
    source_work: str = ""  # 来源作品
    genre: str = ""  # 题材分类: 武侠/言情/科幻/悬疑/历史/...

    # 量化特征 (JSON)
    features: Dict = field(default_factory=dict)

    # 自然语言风格描述 — 注入 prompt 用
    style_prompt: str = ""

    # 代表性段落（文本片段）
    sample_text: str = ""

    # 元信息
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @property
    def brief(self) -> str:
        """简短摘要"""
        parts = [self.name]
        if self.author:
            parts.append(f"作者: {self.author}")
        if self.source_work:
            parts.append(f"作品: {self.source_work}")
        return " | ".join(parts)


@dataclass
class FeatureKeys:
    """文风特征键名 — 和本地模型分析 prompt 对齐"""
    # 词汇特征
    VOCAB_LEVEL = "词汇水平"        # 通俗/典雅/古朴/华丽
    WORD_LENGTH_AVG = "平均词长"     # 每句平均词数
    FUNCTION_WORDS = "虚词使用"      # 虚词频率 (的/了/着/过/啊/呢/吗...)

    # 句式特征
    SENTENCE_LEN_AVG = "平均句长"    # 字符数
    SENTENCE_LEN_VAR = "句长变化"    # 标准差
    PARALLELISM = "排比/对仗"        # 排比句频率
    QUESTION_RATIO = "疑问句比例"    # 问句占比
    EXCLAM_RATIO = "感叹句比例"     # 感叹句占比

    # 修辞特征
    METAPHOR = "比喻使用"            # 比喻频率
    PERSONIFY = "拟人使用"           # 拟人频率
    QUOTATION = "引用/用典"         # 引用频率
    REPETITION = "重复/强调"         # 重复修辞频率

    # 叙事特征
    POV = "叙事视角"                # 第一人称/第三人称/全知视角
    DIALOGUE_RATIO = "对话比例"      # 对话文字占全文比例
    NARRATION_RATIO = "叙述比例"     # 叙述文字占比
    DESCRIPTION_RATIO = "描写比例"    # 环境/外貌/心理描写占比

    # 段落特征
    PARAGRAPH_LEN_AVG = "平均段落长度"  # 字符数
    PARAGRAPH_LEN_VAR = "段落长度变化"
    TRANSITION = "过渡方式"          # 章节过渡特点

    @classmethod
    def all_keys(cls) -> List[str]:
        return [
            cls.VOCAB_LEVEL, cls.WORD_LENGTH_AVG, cls.FUNCTION_WORDS,
            cls.SENTENCE_LEN_AVG, cls.SENTENCE_LEN_VAR,
            cls.PARALLELISM, cls.QUESTION_RATIO, cls.EXCLAM_RATIO,
            cls.METAPHOR, cls.PERSONIFY, cls.QUOTATION, cls.REPETITION,
            cls.POV, cls.DIALOGUE_RATIO, cls.NARRATION_RATIO,
            cls.DESCRIPTION_RATIO,
            cls.PARAGRAPH_LEN_AVG, cls.PARAGRAPH_LEN_VAR, cls.TRANSITION,
        ]


# ── 数据库操作 ─────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    if not hasattr(_log, "conn") or _log.conn is None:
        STYLE_DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(STYLE_DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _init_tables(conn)
        _log.conn = conn
    return _log.conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS style_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            author TEXT DEFAULT '',
            source_work TEXT DEFAULT '',
            genre TEXT DEFAULT '',
            features TEXT DEFAULT '{}',
            style_prompt TEXT DEFAULT '',
            sample_text TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS style_analysis_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_text_hash TEXT,
            source_text_preview TEXT,
            profile_id TEXT,
            features TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_profile_genre
            ON style_profiles(genre);
        CREATE INDEX IF NOT EXISTS idx_profile_author
            ON style_profiles(author);
    """)


def get_db() -> StyleDb:
    return StyleDb()


class StyleDb:
    """文风数据库操作"""

    def list_profiles(self, genre: str = "") -> List[StyleProfile]:
        """列出所有文风画像"""
        conn = _get_conn()
        if genre:
            rows = conn.execute(
                "SELECT * FROM style_profiles WHERE genre = ? ORDER BY name",
                (genre,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM style_profiles ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def get_profile(self, profile_id: str) -> Optional[StyleProfile]:
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM style_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        return self._row_to_profile(row) if row else None

    def save_profile(self, profile: StyleProfile) -> str:
        """保存文风画像（插入或更新）"""
        conn = _get_conn()
        if not profile.id:
            import hashlib, time
            raw = f"{profile.name}_{time.time()}"
            profile.id = hashlib.md5(raw.encode()).hexdigest()[:12]

        conn.execute("""
            INSERT INTO style_profiles
                (id, name, author, source_work, genre, features,
                 style_prompt, sample_text, tags, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, author=excluded.author,
                source_work=excluded.source_work, genre=excluded.genre,
                features=excluded.features, style_prompt=excluded.style_prompt,
                sample_text=excluded.sample_text, tags=excluded.tags,
                updated_at=datetime('now')
        """, (
            profile.id, profile.name, profile.author,
            profile.source_work, profile.genre,
            json.dumps(profile.features, ensure_ascii=False),
            profile.style_prompt, profile.sample_text,
            json.dumps(profile.tags, ensure_ascii=False),
        ))
        conn.commit()
        return profile.id

    def delete_profile(self, profile_id: str) -> bool:
        conn = _get_conn()
        cur = conn.execute(
            "DELETE FROM style_profiles WHERE id = ?", (profile_id,)
        )
        conn.commit()
        return cur.rowcount > 0

    def search_profiles(self, query: str) -> List[StyleProfile]:
        """搜索文风画像（按名称/作者/作品）"""
        conn = _get_conn()
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM style_profiles WHERE name LIKE ? OR author LIKE ? OR source_work LIKE ?",
            (like, like, like),
        ).fetchall()
        return [self._row_to_profile(r) for r in rows]

    def get_genres(self) -> List[str]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT DISTINCT genre FROM style_profiles WHERE genre != '' ORDER BY genre"
        ).fetchall()
        return [r["genre"] for r in rows]

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> StyleProfile:
        return StyleProfile(
            id=row["id"],
            name=row["name"],
            author=row["author"],
            source_work=row["source_work"],
            genre=row["genre"],
            features=json.loads(row["features"] or "{}"),
            style_prompt=row["style_prompt"] or "",
            sample_text=row["sample_text"] or "",
            tags=json.loads(row["tags"] or "[]"),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )
