"""测试：API 删除全流程"""
import asyncio, tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.tools.novel_storage import NOVELS_ROOT
from story_engine.api.routes.novel import router as novel_router
from story_engine.api.routes.export import router as export_router

client = TestClient(app)


async def _run_test():
    # 通过 API 测试完整流程
    # 1. 创建
    resp = client.post("/api/novel/", json={"title": "删除测试", "author": "测试"})
    d = resp.json()
    print(f"1. 创建: {d['success']}, id={d['data'].get('id', '?')}")
    nid = d["data"]["id"]

    # 2. 列表确认存在
    resp = client.get("/api/novel/")
    ids = [n["id"] for n in resp.json()["data"]]
    print(f"2. 列表中有吗: {nid in ids}")

    # 3. 删除
    resp = client.delete(f"/api/novel/{nid}")
    print(f"3. 删除返回: {resp.status_code} {resp.json()}")

    # 4. 列表确认删除
    resp = client.get("/api/novel/")
    ids2 = [n["id"] for n in resp.json()["data"]]
    print(f"4. 删除后列表中: {nid in ids2}")

    # 5. 尝试获取已删除的小说 → 应该失败
    resp = client.get(f"/api/novel/{nid}")
    print(f"5. 获取已删除: {resp.json().get('success','?')} (应为False)")

    print("\n✅ 测试完成")


asyncio.run(_run_test())
