"""测试：资料检索 API — 离线 mock 版（E2.3：联网用例改 mock，保证 CI 幂等）

原实现直接调用真实搜索引擎（非幂等、受网络波动影响），
现统一 mock `research.search_web`，聚焦路由自身的组装/落盘/列表逻辑。
"""

import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.tools.web_search import SearchResponse, SearchResult


@pytest.fixture(autouse=True)
def setup_test_env(test_config, reset_router):
    """确保测试环境有最小配置（统一 conftest fixture）"""
    yield


client = TestClient(app)


def _fake_search_response(query: str, n: int = 2) -> SearchResponse:
    """构造假搜索结果（不触发任何网络请求）"""
    return SearchResponse(
        query=query,
        results=[
            SearchResult(
                title=f"结果{i + 1}",
                snippet=f"关于 {query} 的第 {i + 1} 条摘要",
                url=f"https://example.com/{query}-{i + 1}",
                source="mock",
            )
            for i in range(n)
        ],
        summary=f"关于「{query}」的汇总摘要",
        engine_used="mock",
        extracted_pages=["【结果1】(https://example.com/1)\n正文内容片段\n"],
    )


@pytest.fixture
def mock_search(monkeypatch):
    """把 research 路由的 search_web 替换为可控 mock"""
    import story_engine.api.routes.research as research_mod

    m = AsyncMock()
    monkeypatch.setattr(research_mod, "search_web", m)
    return m


@pytest.fixture
def tmp_research_dir(monkeypatch, tmp_path):
    """隔离的 research 记录目录"""
    import story_engine.api.routes.research as research_mod

    monkeypatch.setattr(research_mod, "RESEARCH_DIR", tmp_path)
    return tmp_path


class TestResearchPost:
    """测试 POST /api/research/ — 基于 mock 搜索结果"""

    def test_empty_query(self):
        """空查询应返回 success=False"""
        resp = client.post("/api/research/", json={"query": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert not data["success"]

    def test_research_returns_results(self, mock_search, tmp_research_dir):
        """POST /api/research/ 应返回格式化后的搜索结果"""
        mock_search.return_value = _fake_search_response("Python programming language")

        resp = client.post("/api/research/", json={"query": "Python programming language"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"], f"Expected success, got: {data}"

        # mock 搜索参数被正确透传
        mock_search.assert_awaited_once()
        kwargs = mock_search.await_args.kwargs
        assert kwargs["max_results"] == 8
        assert kwargs["extract_content"] is True

        result = data["data"]
        assert result["query"] == "Python programming language"

        # sources 非空且字段完整
        assert isinstance(result["sources"], list)
        assert len(result["sources"]) > 0
        for src in result["sources"]:
            assert "title" in src
            assert "snippet" in src
            assert "url" in src
            assert isinstance(src["title"], str)
            assert isinstance(src["snippet"], str)
            assert isinstance(src["url"], str)

        # summary 不是占位符
        assert result["summary"] != "待填充资料"
        assert result["summary"] != ""

        # saved_to 是非空文件路径
        assert result["saved_to"] != ""
        assert isinstance(result["saved_to"], str)

    def test_research_creates_record_file(self, mock_search, tmp_research_dir):
        """验证 research 记录文件被创建在磁盘上"""
        mock_search.return_value = _fake_search_response("artificial intelligence")

        resp = client.post("/api/research/", json={"query": "artificial intelligence"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]

        json_files = list(tmp_research_dir.glob("*.json"))
        assert len(json_files) > 0, f"No research record files found in {tmp_research_dir}"

        with open(json_files[0], "r", encoding="utf-8") as f:
            record = json.load(f)
        assert record["query"] == "artificial intelligence"
        assert "sources" in record or "timestamp" in record

    def test_research_saves_to_lore(self, mock_search, tmp_research_dir):
        """带 save_to_lore=True 的查询应记录 category"""
        mock_search.return_value = _fake_search_response("machine learning basics")

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

        json_files = list(tmp_research_dir.glob("*.json"))
        with open(json_files[0], "r", encoding="utf-8") as f:
            record = json.load(f)
        assert record["category"] == "ai_knowledge"

    def test_research_handles_no_results(self, mock_search, tmp_research_dir):
        """搜索无结果时仍返回 success 与空 sources（不抛错）"""
        mock_search.return_value = _fake_search_response("不存在的内容", n=0)

        resp = client.post("/api/research/", json={"query": "不存在的主题"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        assert data["data"]["sources"] == []


class TestResearchGet:
    """测试 GET /api/research/ — 列出历史研究记录"""

    def test_list_research_records_empty(self, tmp_research_dir):
        """空目录返回空列表"""
        resp = client.get("/api/research/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        assert isinstance(data["data"], list)
        assert data["data"] == []

    def test_list_research_records_with_data(self, mock_search, tmp_research_dir):
        """有记录时应返回列表"""
        mock_search.return_value = _fake_search_response("quantum computing")

        client.post("/api/research/", json={"query": "quantum computing"})

        resp = client.get("/api/research/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

        record = data["data"][0]
        assert "query" in record
        assert "timestamp" in record or "saved_to" in record

    def test_list_research_skips_corrupt_files(self, tmp_research_dir):
        """损坏的 JSON 文件应被跳过而不是 500"""
        (tmp_research_dir / "bad.json").write_text("{ not json", encoding="utf-8")
        (tmp_research_dir / "ok.json").write_text(
            json.dumps({"query": "好记录", "timestamp": "2026-01-01"}), encoding="utf-8"
        )

        resp = client.get("/api/research/")
        assert resp.status_code == 200
        data = resp.json()
        records = data["data"]
        assert len(records) == 1
        assert records[0]["query"] == "好记录"

    def test_list_research_limit_offset(self, mock_search, tmp_research_dir):
        """limit/offset 分页生效"""
        for q in ("主题一", "主题二", "主题三"):
            mock_search.return_value = _fake_search_response(q)
            client.post("/api/research/", json={"query": q})

        resp = client.get("/api/research/?limit=2&offset=1")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

        resp2 = client.get("/api/research/?limit=999")
        assert resp2.status_code == 422  # limit 上限 200
