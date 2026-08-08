"""测试：API 删除全流程（fixture 隔离，不污染真实数据目录）"""

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_env(test_config, novels_root):
    """建立隔离的测试配置与小说存储目录（统一 conftest fixture）"""
    yield novels_root


class TestDeleteFlow:
    """小说创建 → 列表 → 删除 → 确认的全流程"""

    def test_create_list_delete_flow(self, setup_test_env):
        # 1. 创建
        resp = client.post("/api/novel/", json={"title": "删除测试", "author": "测试"})
        assert resp.status_code == 200
        d = resp.json()
        assert d["success"] is True
        nid = d["data"]["id"]

        # 2. 列表确认存在
        resp = client.get("/api/novel/")
        ids = [n["id"] for n in resp.json()["data"]]
        assert nid in ids

        # 3. 删除
        resp = client.delete(f"/api/novel/{nid}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # 4. 列表确认已删除
        resp = client.get("/api/novel/")
        ids2 = [n["id"] for n in resp.json()["data"]]
        assert nid not in ids2

        # 5. 获取已删除的小说 → 应失败
        resp = client.get(f"/api/novel/{nid}")
        assert resp.json().get("success") is False
