"""文风 vs 题材匹配推荐测试 — 原型向量 + 余弦相似度 + API"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.style.db import StyleDb, StyleProfile
from story_engine.style.recommend import recommend_profiles


def _make_profile(name: str, genre: str, vocab: int, sent: int,
                  dialog: int = 5, pov: int = 8) -> StyleProfile:
    """构造带数值特征的画像"""
    return StyleProfile(
        name=name,
        author="测试",
        source_work="测试作品",
        genre=genre,
        features={
            "词汇水平": {"value": "x", "score": vocab},
            "平均句长": {"value": "x", "score": sent},
            "对话比例": {"value": "x", "score": dialog},
            "叙事视角": {"value": "x", "score": pov},
        },
        style_prompt=f"{name}的风格描述",
        tags=[],
    )


@pytest.fixture
def db_with_recommend_data(tmp_path: Path) -> StyleDb:
    """模拟题材数据：武侠 2 本（特征相近）、科幻 2 本（特征相近但不同）"""
    import story_engine.style.db as db_module

    if hasattr(db_module._log, "conn") and db_module._log.conn is not None:
        db_module._log.conn.close()
    db_module._log.conn = None
    db_module.STYLE_DB_DIR = tmp_path / "style_profiles"
    db_module.STYLE_DB_PATH = db_module.STYLE_DB_DIR / "style_profiles.db"

    db = StyleDb()
    profiles = [
        # 武侠：典雅 + 长句 + 高对话
        _make_profile("金庸古龙风", "武侠", vocab=9, sent=8, dialog=7),
        _make_profile("梁羽生风", "武侠", vocab=8, sent=8, dialog=6),
        # 科幻：冷静 + 短句 + 低对话
        _make_profile("三体冷峻风", "科幻", vocab=6, sent=5, dialog=3),
        _make_profile("基地史诗风", "科幻", vocab=6, sent=4, dialog=3),
        # 悬疑：短句 + 高对话
        _make_profile("福尔摩斯风", "悬疑", vocab=5, sent=6, dialog=8),
    ]
    for p in profiles:
        p.id = db.save_profile(p)
    return db


# ── 推荐算法单元测试 ────────────────────────────────────


class TestRecommend:
    def test_recommend_same_genre_first(self, db_with_recommend_data):
        """同题材画像优先于跨题材"""
        results = recommend_profiles("武侠", top_k=5)
        assert len(results) == 5
        # 前两个应是武侠题材
        assert results[0]["same_genre"] is True
        assert results[1]["same_genre"] is True
        # 分数应大于 0
        assert results[0]["score"] > 0

    def test_recommend_matches_similar_style(self, db_with_recommend_data):
        """目标题材无画像时，推荐风格最相近的画像"""
        # 悬疑原型：短句 + 高对话。金庸古龙风（长句高对话）应比三体（短句低对话）更接近？
        # 悬疑：sent=6, dialog=8；武侠金庸：sent=8, dialog=7 → 相似度较高
        results = recommend_profiles("悬疑", top_k=3)
        # 福尔摩斯风（悬疑本体）排第一
        assert results[0]["profile"].name == "福尔摩斯风"
        assert results[0]["same_genre"] is True
        # 其余为跨题材推荐
        names = [r["profile"].name for r in results[1:]]
        assert "金庸古龙风" in names  # 风格最接近悬疑（对话多）

    def test_recommend_same_genre_only(self, db_with_recommend_data):
        """严格模式只返回该题材画像"""
        results = recommend_profiles("武侠", top_k=10, include_same_genre_only=True)
        assert len(results) == 2
        assert all(r["same_genre"] for r in results)

    def test_recommend_unknown_genre(self, db_with_recommend_data):
        """未知题材：无原型向量，返回按名称排序的全部画像（同题材无）"""
        results = recommend_profiles("不存在题材", top_k=3)
        assert len(results) == 3
        assert all(not r["same_genre"] for r in results)

    def test_recommend_empty_db(self, tmp_path: Path):
        """空数据库返回空列表"""
        import story_engine.style.db as db_module
        if hasattr(db_module._log, "conn") and db_module._log.conn is not None:
            db_module._log.conn.close()
        db_module._log.conn = None
        db_module.STYLE_DB_DIR = tmp_path / "style_profiles_empty"
        db_module.STYLE_DB_PATH = db_module.STYLE_DB_DIR / "style_profiles.db"
        StyleDb()  # 初始化空库
        results = recommend_profiles("武侠", top_k=5)
        assert results == []


# ── API 测试 ────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestRecommendAPI:
    def test_recommend_endpoint(self, client: TestClient):
        """推荐接口返回结构正确"""
        resp = client.get("/api/style/recommend?genre=武侠&top_k=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["genre"] == "武侠"
        assert "recommendations" in data
        assert data["total"] <= 3
        if data["recommendations"]:
            item = data["recommendations"][0]
            assert "profile" in item
            assert "score" in item
            assert "same_genre" in item
            assert item["profile"]["name"]

    def test_recommend_endpoint_default(self, client: TestClient):
        """无参数调用不报错"""
        resp = client.get("/api/style/recommend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["genre"] == ""
        assert "note" in data

    def test_recommend_endpoint_topk_clamped(self, client: TestClient):
        """top_k 超范围被钳制"""
        resp = client.get("/api/style/recommend?genre=武侠&top_k=999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] <= 70
