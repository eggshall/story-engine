"""文风 vs 题材匹配推荐 — 题材原型向量 + 余弦相似度

用户选择目标题材（如"武侠"、"悬疑"），推荐文风与该题材最匹配的画像。
原理：
  1. 对已有题材，用该题材下所有画像的量化特征 score 计算"题材原型向量"（均值）
  2. 用户选题材 → 对全部画像计算与题材原型的余弦相似度，返回 Top-N
  3. 跨题材推荐：即使画像标注的题材不同，只要文风特征接近目标题材也会入选
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from story_engine.style.db import StyleDb, StyleProfile

# 参与相似度计算的特征键（排除纯描述性/文本特征）
_SCORE_KEYS: Tuple[str, ...] = (
    "词汇水平",
    "平均句长",
    "句长变化",
    "虚词使用",
    "对话比例",
    "叙事视角",
    "排比对仗",
    "疑问句比例",
    "比喻使用",
    "拟人使用",
    "引用用典",
    "平均段落长度",
    "描写特点",
)


def _feature_vector(profile: StyleProfile) -> List[float]:
    """提取画像的数值特征向量（score 归一化到 0-1）"""
    features = profile.features or {}
    vec: List[float] = []
    for key in _SCORE_KEYS:
        item = features.get(key)
        if isinstance(item, dict):
            score = item.get("score")
            if isinstance(score, (int, float)):
                vec.append(min(max(score / 10.0, 0.0), 1.0))
                continue
        vec.append(0.5)  # 缺失特征取中性值
    return vec


def _cosine_sim(a: List[float], b: List[float]) -> float:
    """余弦相似度（向量等长，均已归一化）"""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _genre_prototype(db: StyleDb, genre: str) -> List[float]:
    """计算某题材下所有画像特征均值 → 题材原型向量"""
    profiles = db.list_profiles(genre=genre)
    if not profiles:
        return []
    vecs = [_feature_vector(p) for p in profiles]
    n = len(vecs[0])
    proto = [sum(v[i] for v in vecs) / len(vecs) for i in range(n)]
    return proto


def recommend_profiles(
    genre: str,
    top_k: int = 5,
    include_same_genre_only: bool = False,
) -> List[Dict[str, Any]]:
    """按题材推荐文风画像。

    Args:
        genre: 目标题材（如"武侠"/"悬疑"/"严肃文学"），空则返回全部画像
        top_k: 返回数量
        include_same_genre_only: 只推荐标注为该题材的画像（严格过滤）

    Returns:
        [{profile, score, same_genre}...] 按相似度降序
    """
    db = StyleDb()

    if include_same_genre_only:
        # 严格模式：直接返回该题材下全部画像（按名称排序，分数=1.0）
        profiles = db.list_profiles(genre=genre)
        results = [
            {"profile": p, "score": 1.0, "same_genre": True}
            for p in profiles
        ]
        return results[:top_k]

    # 智能模式：题材原型 + 余弦相似度（含跨题材推荐）
    prototype = _genre_prototype(db, genre)
    all_profiles = db.list_profiles()

    scored: List[Dict[str, Any]] = []
    for p in all_profiles:
        if prototype:
            score = _cosine_sim(_feature_vector(p), prototype)
        else:
            # 目标题材无画像（如"武侠"库内没有）→ 用标签/描述匹配兜底，
            # 当前 tags 为空，退化为均匀排序
            score = 0.0
        scored.append(
            {
                "profile": p,
                "score": round(score, 4),
                "same_genre": p.genre == genre,
            }
        )

    # 同题材优先，其次按相似度降序
    scored.sort(key=lambda x: (-int(x["same_genre"]), -x["score"]))
    return scored[:top_k]


def get_genre_prototypes() -> Dict[str, List[float]]:
    """返回所有题材的原型向量（用于调试/展示）"""
    db = StyleDb()
    result = {}
    for genre in db.get_genres():
        proto = _genre_prototype(db, genre)
        if proto:
            result[genre] = [round(x, 4) for x in proto]
    return result
