"""测试：资料检索 API — 真实联网搜索"""

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.core.config import get_config


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """确保测试环境有最小配置"""
    import yaml
    tmp_cfg = Path(tempfile.mktemp(suffix=".yaml"))
    config_data = {
        "llm": {
            "default_model": "test-model",
            "models": [
                {"name": "test-model", "provider": "openai",
                 "model_id": "test", "base_url": "http://localhost:8080",
                 "api_key": "test", "enabled": True},
            ]
        }
    }
    with open(tmp_cfg, "w") as f:
        yaml.dump(config_data, f)

    monkeypatch.setattr("story_engine.core.config._config_instance", None)
    monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", tmp_cfg)
    monkeypatch.setattr("story_engine.api.routes.generate._router", None)
    yield


client = TestClient(app)


class TestResearchPost:
    """测试 POST /api/research/ — 真实联网搜索"""

    def test_empty_query(self):
        """空查询应返回 success=False"""
        resp = client.post("/api/research/", json={"query": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert not data["success"]

    def test_research_returns_real_results(self, monkeypatch):
        """POST /api/research/ 应返回真实搜索结果"""
        import story_engine.api.routes.research as research_mod
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr(research_mod, "RESEARCH_DIR", tmp)

        resp = client.post("/api/research/", json={"query": "Python programming language"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"], f"Expected success, got: {data}"

        result = data["data"]
        # 验证 query 匹配
        assert result["query"] == "Python programming language"

        # 验证 sources 是非空列表（真实搜索结果）
        assert isinstance(result["sources"], list), "sources should be a list"
        assert len(result["sources"]) > 0, f"Expected non-empty sources, got: {result['sources']}"

        # 验证每个 source 有必要的字段
        for src in result["sources"]:
            assert "title" in src, f"source missing title: {src}"
            assert "snippet" in src, f"source missing snippet: {src}"
            assert "url" in src, f"source missing url: {src}"
            assert isinstance(src["title"], str)
            assert isinstance(src["snippet"], str)
            assert isinstance(src["url"], str)

        # 验证 summary 不是硬编码的占位符
        assert result["summary"] != "待填充资料", "Summary should not be the hardcoded placeholder"
        assert result["summary"] != "", "Summary should not be empty"

        # 验证 saved_to 是非空文件路径
        assert result["saved_to"] != "", "saved_to should not be empty"
        assert isinstance(result["saved_to"], str)

    def test_research_creates_record_file(self, monkeypatch):
        """验证 research 记录文件被创建在磁盘上"""
        import story_engine.api.routes.research as research_mod
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr(research_mod, "RESEARCH_DIR", tmp)

        resp = client.post("/api/research/", json={"query": "artificial intelligence"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]

        # 验证 JSON 文件被创建
        json_files = list(tmp.glob("*.json"))
        assert len(json_files) > 0, f"No research record files found in {tmp}"

        # 验证文件内容有效
        with open(json_files[0], "r", encoding="utf-8") as f:
            record = json.load(f)
        assert record["query"] == "artificial intelligence"
        assert "sources" in record or "timestamp" in record

    def test_research_saves_to_lore(self, monkeypatch):
        """带 save_to_lore=True 的查询应正常工作"""
        import story_engine.api.routes.research as research_mod
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr(research_mod, "RESEARCH_DIR", tmp)

        resp = client.post("/api/research/", json={
            "query": "machine learning basics",
            "save_to_lore": True,
            "lore_category": "ai_knowledge",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        result = data["data"]
        assert result["query"] == "machine learning basics"
        assert len(result["sources"]) > 0


class TestResearchGet:
    """测试 GET /api/research/ — 列出历史研究记录"""

    def test_list_research_records_empty(self, monkeypatch):
        """空目录返回空列表"""
        import story_engine.api.routes.research as research_mod
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr(research_mod, "RESEARCH_DIR", tmp)

        resp = client.get("/api/research/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        assert isinstance(data["data"], list)
        assert data["data"] == []

    def test_list_research_records_with_data(self, monkeypatch):
        """有记录时应返回列表"""
        import story_engine.api.routes.research as research_mod
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr(research_mod, "RESEARCH_DIR", tmp)

        # 先创建几条记录
        client.post("/api/research/", json={"query": "quantum computing"})

        # 获取列表
        resp = client.get("/api/research/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

        # 验证记录包含必要字段
        record = data["data"][0]
        assert "query" in record
        assert "timestamp" in record or "saved_to" in record
