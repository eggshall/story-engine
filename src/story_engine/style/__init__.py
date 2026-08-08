"""文风数据库 — Style Profile System

用本地模型(Qwen3.5-9B)分析小说文本，提取可量化的文风特征，
存入 SQLite 数据库，供前端选择文风并注入生成。
"""

from story_engine.style.analyzer import StyleAnalyzer
from story_engine.style.db import StyleDb, StyleProfile, get_db
from story_engine.style.schemas import (
    StyleConsistencyRequest,
    StyleConsistencyResult,
    StyleFeatureRequest,
    StyleFeatureSet,
    StyleListResponse,
    StyleProfileResponse,
)

__all__ = [
    "get_db",
    "StyleDb",
    "StyleProfile",
    "StyleAnalyzer",
    "StyleFeatureSet",
    "StyleFeatureRequest",
    "StyleConsistencyRequest",
    "StyleConsistencyResult",
    "StyleProfileResponse",
    "StyleListResponse",
]
