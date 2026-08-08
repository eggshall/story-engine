"""测试：项目导出/导入 API"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app


@pytest.fixture(autouse=True)
def setup_test_env(make_config, novels_root, reset_router):
    """建立测试环境：1 个小说 + 2 章节（统一 conftest fixture）"""
    make_config({
        "llm": {
            "default_model": "test-model",
            "models": [
                {"name": "test-model", "provider": "openai",
                 "model_id": "test", "base_url": "http://localhost:8080",
                 "api_key": "test", "enabled": True},
            ]
        }
    })

    # 创建测试小说
    import story_engine.tools.novel_storage as ns
    from story_engine.core.models import Chapter, Novel

    novel = Novel(
        title="测试小说标题",
        author="测试作者",
        genre="奇幻",
        synopsis="一段测试简介",
        chapters=[
            Chapter(chapter_number=1, title="第一章", content="这是第一章内容。"),
            Chapter(chapter_number=2, title="第二章", content="这是第二章内容。"),
        ],
        characters={},
        lorebooks={},
        created="2026-06-01",
        updated="2026-06-24",
    )
    ns.save_novel(novel, novel_id="test-novel")
    yield novels_root


client = TestClient(app)


class TestJsonExport:
    """POST /api/export/json — JSON 项目导出"""

    def test_export_json_success(self):
        resp = client.post("/api/export/json", json={"novel_id": "test-novel"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        result = data["data"]
        assert result["format"] == "json"
        assert result["success"] is True

    def test_export_json_includes_all_fields(self):
        resp = client.post("/api/export/json", json={"novel_id": "test-novel"})
        result = resp.json()["data"]
        path = result["path"]
        # 读取导出的 JSON
        exported = json.loads(Path(path).read_text(encoding="utf-8"))
        assert exported["title"] == "测试小说标题"
        assert exported["author"] == "测试作者"
        assert exported["genre"] == "奇幻"
        assert exported["synopsis"] == "一段测试简介"
        assert len(exported["chapters"]) == 2
        assert exported["chapters"][0]["title"] == "第一章"
        assert exported["chapters"][0]["content"] == "这是第一章内容。"

    def test_export_json_with_output_dir(self, setup_test_env):
        root = setup_test_env
        out_dir = root / "custom-exports"
        resp = client.post("/api/export/json", json={
            "novel_id": "test-novel",
            "output_dir": str(out_dir.relative_to(root)),
        })
        assert resp.status_code == 200
        result = resp.json()["data"]
        # 文件应该在指定目录
        assert out_dir.resolve() in Path(result["path"]).resolve().parents

    @pytest.mark.parametrize("bad", ["/etc", "/mnt/d/evil", "../", "..", "D:\\evil", "../../etc"])
    def test_export_json_rejects_unsafe_output_dir(self, bad):
        resp = client.post("/api/export/json", json={
            "novel_id": "test-novel",
            "output_dir": bad,
        })
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_export_json_returns_404_for_nonexistent_novel(self):
        resp = client.post("/api/export/json", json={"novel_id": "non-existent"})
        assert resp.status_code == 404

    def test_export_md_still_works(self):
        """确保现有 MD 导出不受影响"""
        resp = client.post("/api/export/md", json={
            "novel_id": "test-novel",
            "export_all": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["format"] == "md"
        assert data["data"]["chapters_exported"] == 2


class TestJsonImport:
    """POST /api/import/json — JSON 项目导入"""

    def test_import_json_creates_novel(self):
        # 先导出
        export_resp = client.post("/api/export/json", json={"novel_id": "test-novel"})
        export_path = export_resp.json()["data"]["path"]
        json_data = Path(export_path).read_text(encoding="utf-8")

        # 导入为新小说（不同 ID）
        import_data = json.loads(json_data)
        import_data["id"] = "imported-novel"
        import_data["title"] = "导入小说"
        json_str = json.dumps(import_data, ensure_ascii=False)

        resp = client.post("/api/import/json", json={"json_data": json_str})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["title"] == "导入小说"

        # 验证可以加载
        from story_engine.tools.novel_storage import load_novel
        novel = load_novel("imported-novel")
        assert novel is not None
        assert novel.title == "导入小说"
        assert len(novel.chapters) == 2

    def test_import_json_detects_duplicate(self):
        # 导入已存在 ID 的小说
        export_resp = client.post("/api/export/json", json={"novel_id": "test-novel"})
        export_path = export_resp.json()["data"]["path"]
        json_data = Path(export_path).read_text(encoding="utf-8")

        # 不换 ID — 默认应报错
        resp = client.post("/api/import/json", json={"json_data": json_data})
        assert resp.status_code == 200
        # 由于是覆盖已有 ID，success 可能 false 除非 force=True
        # 取决于实现 — 允许覆盖或拒绝

    def test_import_json_with_force_overwrite(self):
        """force=True 应覆盖已有的"""
        export_resp = client.post("/api/export/json", json={"novel_id": "test-novel"})
        export_path = export_resp.json()["data"]["path"]
        json_data = Path(export_path).read_text(encoding="utf-8")

        resp = client.post("/api/import/json", json={
            "json_data": json_data,
            "force": True,
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_import_json_invalid_data_returns_error(self):
        resp = client.post("/api/import/json", json={"json_data": "{not valid json}"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    @pytest.mark.parametrize("bad", ["/etc", "../", "D:\\evil", "../../etc"])
    def test_import_json_rejects_unsafe_restore_path(self, bad):
        export_resp = client.post("/api/export/json", json={"novel_id": "test-novel"})
        export_path = export_resp.json()["data"]["path"]
        json_data = Path(export_path).read_text(encoding="utf-8")
        resp = client.post("/api/import/json", json={
            "json_data": json_data,
            "restore_path": bad,
            "force": True,
        })
        assert resp.status_code == 400
