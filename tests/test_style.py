"""文风系统测试 — Style DB + API"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.style.db import FeatureKeys, StyleDb, StyleProfile

# ── Fixtures ────────────────────────────────────────────

@pytest.fixture
def db_with_data(tmp_path: Path) -> StyleDb:
    """带测试数据的文风数据库"""
    import story_engine.style.db as db_module

    # 清空线程本地连接缓存，确保使用临时路径
    if hasattr(db_module._log, "conn") and db_module._log.conn is not None:
        db_module._log.conn.close()
    db_module._log.conn = None

    db_module.STYLE_DB_DIR = tmp_path / "style_profiles"
    db_module.STYLE_DB_PATH = db_module.STYLE_DB_DIR / "style_profiles.db"

    db = StyleDb()

    # 插入测试数据
    profiles = [
        StyleProfile(
            name="金庸武侠风",
            author="金庸",
            source_work="射雕英雄传",
            genre="武侠",
            features={
                "词汇水平": {"value": "典雅", "score": 8},
                "平均句长": {"value": "20-30字", "score": 6},
                "对话比例": {"value": "40%", "score": 5},
                "叙事视角": {"value": "第三人称全知", "score": 7},
            },
            style_prompt="典雅的古风武侠文笔，对话精炼，描写大气",
            sample_text="那少年微微一笑，道：'在下姓郭，单名一个靖字。'",
            tags=["武侠", "古典", "金庸"],
        ),
        StyleProfile(
            name="鲁迅犀利风",
            author="鲁迅",
            source_work="狂人日记",
            genre="文学",
            features={
                "词汇水平": {"value": "犀利", "score": 9},
                "平均句长": {"value": "10-20字", "score": 7},
                "对话比例": {"value": "20%", "score": 8},
            },
            style_prompt="凝练犀利的白话文笔，讽刺意味浓厚，句式短促有力",
            sample_text="我翻开历史一查，这历史没有年代，歪歪斜斜的每页上都写着'仁义道德'几个字。",
            tags=["文学", "现代", "鲁迅"],
        ),
        StyleProfile(
            name="科幻冷峻风",
            author="刘慈欣",
            source_work="三体",
            genre="科幻",
            features={},
            style_prompt="精确冷静的科幻叙事，宏大场景与细节并存，科学术语穿插自然",
            sample_text="",
            tags=["科幻"],
        ),
    ]
    for p in profiles:
        p.id = db.save_profile(p)

    return db


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── 数据库测试 ──────────────────────────────────────────


class TestStyleDb:
    def test_init_creates_tables(self, tmp_path: Path):
        """初始化时自动创建表"""
        import story_engine.style.db as db_module
        # 清空连接缓存
        if hasattr(db_module._log, "conn") and db_module._log.conn is not None:
            db_module._log.conn.close()
        db_module._log.conn = None
        db_module.STYLE_DB_DIR = tmp_path / "style_profiles"
        db_module.STYLE_DB_PATH = db_module.STYLE_DB_DIR / "style_profiles.db"

        # 手动创建连接（会创建目录和表）
        conn = db_module._get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = [r[0] for r in tables]
        assert "style_profiles" in names
        assert "style_analysis_log" in names

    def test_save_and_get_profile(self, db_with_data: StyleDb):
        """保存和读取文风画像"""
        # 我们的 save_profile 用 md5 生成 id，所以不能用 name 直接查
        # 改用列表查
        all_profiles = db_with_data.list_profiles()
        assert len(all_profiles) >= 3

        # 查找金庸
        jinyong = [p for p in all_profiles if "金庸" in p.name]
        assert len(jinyong) == 1
        assert jinyong[0].author == "金庸"
        assert jinyong[0].genre == "武侠"
        assert jinyong[0].features["词汇水平"]["value"] == "典雅"

    def test_list_profiles_by_genre(self, db_with_data: StyleDb):
        """按题材筛选"""
        wuxia = db_with_data.list_profiles(genre="武侠")
        assert len(wuxia) == 1
        assert wuxia[0].name == "金庸武侠风"

        all_genres = db_with_data.get_genres()
        assert "武侠" in all_genres
        assert "文学" in all_genres
        assert "科幻" in all_genres

    def test_search_profiles(self, db_with_data: StyleDb):
        """搜索文风画像"""
        results = db_with_data.search_profiles("鲁迅")
        assert len(results) == 1
        assert "鲁迅" in results[0].name

        results = db_with_data.search_profiles("科幻")
        assert len(results) == 1

        results = db_with_data.search_profiles("不存在的")
        assert len(results) == 0

    def test_delete_profile(self, db_with_data: StyleDb):
        """删除文风画像"""
        all_profiles = db_with_data.list_profiles()
        target = [p for p in all_profiles if "鲁迅" in p.name][0]
        profile_id = target.id

        ok = db_with_data.delete_profile(profile_id)
        assert ok is True

        # 验证已删除
        assert db_with_data.get_profile(profile_id) is None

        # 删除不存在的返回 False
        assert db_with_data.delete_profile("nonexistent_id") is False

    def test_update_profile(self, db_with_data: StyleDb):
        """更新文风画像"""
        all_profiles = db_with_data.list_profiles()
        target = [p for p in all_profiles if "金庸" in p.name][0]
        target.style_prompt = "更新后的风格描述"
        db_with_data.save_profile(target)

        updated = db_with_data.get_profile(target.id)
        assert updated is not None
        assert updated.style_prompt == "更新后的风格描述"

    def test_feature_keys(self):
        """特征键列表"""
        keys = FeatureKeys.all_keys()
        assert len(keys) >= 18
        assert "词汇水平" in keys
        assert "叙事视角" in keys
        assert "比喻使用" in keys
        assert "平均段落长度" in keys

    def test_profile_brief(self):
        """简介格式"""
        p = StyleProfile(name="测试风", author="作者A", source_work="作品B")
        assert "测试风" in p.brief
        assert "作者A" in p.brief
        assert "作品B" in p.brief

        p2 = StyleProfile(name="简版")
        assert p2.brief == "简版"


# ── 分析器测试（mock 本地模型） ──────────────────────────


class TestStyleAnalyzer:
    def test_analyze_style_with_mock(self):
        """mock 本地模型的分析结果"""
        import asyncio

        from story_engine.style.analyzer import StyleAnalyzer

        async def _test():
            analyzer = StyleAnalyzer()
            mock_features = {
                "词汇水平": {"value": "通俗", "score": 6, "detail": "接近口语"},
                "平均句长": {"value": "15-25字", "score": 7},
                "对话比例": {"value": "50%", "score": 6},
                "叙事视角": {"value": "第三人称有限", "score": 8},
                "整体风格总结": "轻快通俗的网络小说笔法",
            }

            original_chat = analyzer._chat
            analyzer._chat = AsyncMock(return_value=json.dumps(mock_features))

            text = "这是一个测试文本。" * 50
            result = await analyzer.analyze_style(text)
            assert result["词汇水平"]["value"] == "通俗"
            assert result["整体风格总结"] == "轻快通俗的网络小说笔法"

            analyzer._chat = original_chat
            await analyzer.close()

        asyncio.run(_test())

    def test_features_to_prompt(self):
        """特征转 prompt 文本"""
        from story_engine.style.analyzer import StyleAnalyzer
        analyzer = StyleAnalyzer()

        features = {
            "词汇水平": {"value": "典雅", "score": 8},
            "平均句长": {"value": "20-30字", "score": 6},
        }
        prompt = analyzer._features_to_prompt(features)
        assert "典雅" in prompt
        assert "20-30字" in prompt

    def test_extract_json(self):
        """JSON 提取"""
        from story_engine.style.analyzer import StyleAnalyzer
        analyzer = StyleAnalyzer()

        raw = '{"key": {"value": "test"}}'
        assert analyzer._extract_json(raw) == {"key": {"value": "test"}}

        # 带 Markdown 包裹
        raw2 = '```json\n{"key": "val"}\n```'
        assert analyzer._extract_json(raw2) == {"key": "val"}

        # 无效 JSON
        assert analyzer._extract_json("not json") is None

        # 空字符串
        assert analyzer._extract_json("") is None


# ── API 测试 ────────────────────────────────────────────


class TestStyleAPI:
    def test_list_profiles_empty(self, client: TestClient):
        """列表（空数据库）"""
        resp = client.get("/api/style/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data

    def test_get_genres(self, client: TestClient):
        """题材列表"""
        resp = client.get("/api/style/genres")
        assert resp.status_code == 200

    def test_search(self, client: TestClient):
        """搜索"""
        resp = client.get("/api/style/search?q=test")
        assert resp.status_code == 200

    def test_save_and_delete(self, client: TestClient):
        """CRUD: 创建 + 删除"""
        # 创建
        save_resp = client.post("/api/style/profiles", json={
            "name": "测试风格",
            "author": "测试",
            "genre": "测试",
            "style_prompt": "测试用风格描述",
            "tags": ["测试"],
        })
        assert save_resp.status_code == 200
        profile_id = save_resp.json()["id"]
        assert profile_id

        # 获取
        get_resp = client.get(f"/api/style/profiles/{profile_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "测试风格"

        # 删除
        del_resp = client.delete(f"/api/style/profiles/{profile_id}")
        assert del_resp.status_code == 200

        # 删除后 404
        get_resp2 = client.get(f"/api/style/profiles/{profile_id}")
        assert get_resp2.status_code == 404

    def test_analyze_endpoint(self, client: TestClient):
        """文风分析接口（mock 模型调用）"""
        with patch("story_engine.style.analyzer.StyleAnalyzer.analyze_style",
                   return_value={"词汇水平": {"value": "通俗"}, "整体风格总结": "测试风格"}):
            resp = client.post("/api/style/analyze", json={
                "text": "这是一段测试文本。" * 30,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "features" in data
            assert data["features"]["词汇水平"]["value"] == "通俗"
            assert data["style_prompt"] == "测试风格"

    def test_analyze_and_save(self, client: TestClient):
        """分析并自动保存"""
        mock_result = {"词汇水平": {"value": "典雅的"}, "整体风格总结": "古典风格"}
        with patch("story_engine.style.analyzer.StyleAnalyzer.analyze_style",
                   return_value=mock_result):
            resp = client.post("/api/style/analyze", json={
                "text": "这是一个需要分析的文本。" * 30,
                "name": "自动保存测试",
                "author": "测试作者",
                "genre": "测试分类",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["profile_id"]  # 有自动保存的 ID

            # 确认已保存
            get_resp = client.get(f"/api/style/profiles/{data['profile_id']}")
            assert get_resp.status_code == 200
            assert get_resp.json()["name"] == "自动保存测试"

    def test_check_consistency_no_profile(self, client: TestClient):
        """一致性检查 — 无 profile_id 也无 style_prompt"""
        resp = client.post("/api/style/check", json={
            "text": "这是一段测试文本。" * 30,
        })
        assert resp.status_code == 400  # 参数不足

    def test_check_consistency_with_prompt(self, client: TestClient):
        """一致性检查 — 直接传 style_prompt"""
        with patch("story_engine.style.analyzer.StyleAnalyzer.check_consistency",
                   return_value={"consistency_score": 7, "consistent_aspects": ["词汇"],
                                 "inconsistent_aspects": ["句长"], "suggestions": [],
                                 "conclusion": "基本一致"}):
            resp = client.post("/api/style/check", json={
                "text": "这是一段测试文本。" * 30,
                "style_prompt": "典雅的古风文笔",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["consistency_score"] == 7
            assert "词汇" in data["consistent_aspects"]

    def test_check_consistency_not_found(self, client: TestClient):
        """一致性检查 — profile 不存在"""
        resp = client.post("/api/style/check", json={
            "text": "这是一段测试文本。" * 30,
            "profile_id": "nonexistent_id",
        })
        assert resp.status_code == 404
