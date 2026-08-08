"""测试：世界地图 API"""

import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.core.models import Novel


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """建立测试环境：1 个小说 + 地图数据"""
    tmp_cfg = Path(tempfile.mktemp(suffix=".yaml"))
    config_data = {"llm": {"default_model": "test", "models": []}}
    with open(tmp_cfg, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    monkeypatch.setattr("story_engine.core.config._config_instance", None)
    monkeypatch.setattr("story_engine.core.config.DEFAULT_CONFIG_PATH", tmp_cfg)

    import story_engine.tools.novel_storage as ns
    monkeypatch.setattr(ns, "NOVELS_ROOT", Path(tempfile.mktemp()))
    ns.NOVELS_ROOT.mkdir(parents=True, exist_ok=True)

    novel = Novel(title="测试地图小说", chapters=[])
    ns.save_novel(novel, novel_id="map-novel")
    yield


client = TestClient(app)


class TestWorldMap:
    """地图标记 CRUD"""

    def test_get_empty_map(self):
        resp = client.get("/api/novel/map-novel/map")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["markers"] == []

    def test_save_markers(self):
        markers = [
            {"id": "m1", "name": "王城", "x": 45.2, "y": 30.1,
             "lore_entry_id": "entry_1", "description": "大陆中心王城"},
            {"id": "m2", "name": "迷雾森林", "x": 80.0, "y": 60.0,
             "lore_entry_id": "entry_2", "description": "北方神秘森林"},
        ]
        resp = client.post("/api/novel/map-novel/map", json={
            "image_path": "/uploaded/map.png",
            "markers": markers,
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # 验证读取
        resp2 = client.get("/api/novel/map-novel/map")
        data = resp2.json()["data"]
        assert data["image_path"] == "/uploaded/map.png"
        assert len(data["markers"]) == 2
        assert data["markers"][0]["name"] == "王城"
        assert data["markers"][0]["x"] == 45.2

    def test_update_map(self):
        """重复保存应覆盖"""
        markers = [{"id": "m1", "name": "旧标记", "x": 10, "y": 20}]
        client.post("/api/novel/map-novel/map", json={
            "image_path": "/old.png", "markers": markers,
        })

        new_markers = [{"id": "m2", "name": "新标记", "x": 50, "y": 50}]
        client.post("/api/novel/map-novel/map", json={
            "image_path": "/new.png", "markers": new_markers,
        })

        resp = client.get("/api/novel/map-novel/map")
        data = resp.json()["data"]
        assert data["image_path"] == "/new.png"
        assert len(data["markers"]) == 1
        assert data["markers"][0]["name"] == "新标记"

    def test_returns_404_for_nonexistent_novel(self):
        resp = client.get("/api/novel/non-existent/map")
        assert resp.status_code == 404
        resp2 = client.post("/api/novel/non-existent/map", json={"markers": []})
        assert resp2.status_code == 404

    def test_image_upload_endpoint_exists(self):
        """验证图片上传端点存在"""
        resp = client.post("/api/novel/map-novel/map/image")
        # 应该返回 422 (缺少文件) 而不是 404
        assert resp.status_code in (200, 422)
