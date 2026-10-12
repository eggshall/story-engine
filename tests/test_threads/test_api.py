"""N9 接口契约：伏笔账本 CRUD（按小说绑定）。

用 TestClient 打真实路由（过鉴权中间件与 schema），不 mock 业务层。
路由前缀沿用 N8 的处理方式：`/api/novel/{id}/threads` 单独一个文件。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.core.models import Novel
from story_engine.tools.novel_storage import save_novel

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(make_config, tmp_path, monkeypatch):
    """隔离小说根；`make_config` 写一份不含 security.api_key 的配置 → 本机回环放行。"""
    make_config({"llm": {"default_model": "m", "models": []}})
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
    save_novel(Novel(title="人类大进步"), "novel_a")
    save_novel(Novel(title="另一本"), "novel_b")
    return tmp_path


def _thread(tid="t1", **kw):
    body = {"id": tid, "title": "怀表的来历", "planted_chapter": 1, "strength": 4}
    body.update(kw)
    return body


def _create(novel_id="novel_a", body=None):
    return client.post(f"/api/novel/{novel_id}/threads", json=body or _thread())


class TestCRUD:
    def test_create_then_list(self):
        assert _create().json()["success"] is True

        body = client.get("/api/novel/novel_a/threads").json()

        assert body["success"] is True
        assert body["data"]["ids"] == ["t1"]
        assert body["data"]["threads"][0]["title"] == "怀表的来历"

    def test_duplicate_is_explicit_failure(self):
        _create()
        again = _create(body=_thread(title="偷偷改掉"))
        assert again.json()["success"] is False, "同名不能静默覆盖"

    def test_update(self):
        _create()
        resp = client.put("/api/novel/novel_a/threads/t1", json=_thread(title="新标题"))
        assert resp.json()["success"] is True
        assert client.get("/api/novel/novel_a/threads").json()["data"]["threads"][0]["title"] == "新标题"

    def test_delete(self):
        _create()
        assert client.delete("/api/novel/novel_a/threads/t1").json()["success"] is True
        assert client.get("/api/novel/novel_a/threads").json()["data"]["ids"] == []

    def test_delete_missing_fails(self):
        assert client.delete("/api/novel/novel_a/threads/nope").json()["success"] is False

    def test_unknown_novel_fails(self):
        resp = client.get("/api/novel/no_such/threads")
        assert resp.json()["success"] is False


class TestAdvance:
    def test_advance_to_paid_off(self):
        _create()
        resp = client.post(
            "/api/novel/novel_a/threads/t1/advance",
            json={"status": "paid_off", "chapter_number": 9},
        )
        assert resp.json()["success"] is True
        data = resp.json()["data"]
        assert data["status"] == "paid_off" and data["payoff_chapter"] == 9

    def test_invalid_status_is_rejected_not_500(self):
        _create()
        resp = client.post(
            "/api/novel/novel_a/threads/t1/advance",
            json={"status": "done", "chapter_number": 9},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False


class TestIsolation:
    def test_ledgers_do_not_leak(self):
        _create("novel_a")
        assert client.get("/api/novel/novel_b/threads").json()["data"]["ids"] == []


class TestReviewFixes:
    """评审（N9-REVIEW）点出的问题，逐条钉死回归。"""

    def test_change_id_cannot_hijack_another_thread(self):
        """P1-1：改 id 时不能静默覆盖另一条伏笔（真实数据丢失路径）。"""
        _create(body=_thread("t1", title="第一条"))
        _create(body=_thread("t2", title="第二条"))

        resp = client.put("/api/novel/novel_a/threads/t1", json=_thread("t2", title="劫持"))

        assert resp.json()["success"] is False
        by_id = {
            t["id"]: t
            for t in client.get("/api/novel/novel_a/threads").json()["data"]["threads"]
        }
        assert by_id["t2"]["title"] == "第二条", "t2 被静默改写了"
        assert by_id["t1"]["title"] == "第一条", "t1 不该被删掉"

    def test_change_id_to_free_slot_still_works(self):
        """改 id 到未被占用的 id 仍应成功（别为了修 P1-1 把功能关掉）。"""
        _create(body=_thread("t1", title="第一条"))

        resp = client.put("/api/novel/novel_a/threads/t1", json=_thread("t9", title="第一条"))

        assert resp.json()["success"] is True
        assert client.get("/api/novel/novel_a/threads").json()["data"]["ids"] == ["t9"]

    def test_camel_case_body_is_accepted(self):
        """P2-1：文档承诺 camelCase 兼容，必须真有测试（原来发驼峰会被静默丢成 0）。"""
        resp = client.post(
            "/api/novel/novel_a/threads",
            json={"id": "t9", "title": "驼峰", "plantedChapter": 50},
        )

        assert resp.json()["success"] is True
        threads = client.get("/api/novel/novel_a/threads").json()["data"]["threads"]
        assert threads[0]["planted_chapter"] == 50, "驼峰字段被静默丢弃了"

    def test_unknown_field_is_rejected_not_dropped(self):
        """P2-1：拼错的字段必须 422，不能悄悄丢掉作者的数据。"""
        resp = client.post(
            "/api/novel/novel_a/threads", json={"id": "t9", "planted_chapterX": 3}
        )
        assert resp.status_code == 422

    def test_advance_camel_case_is_accepted(self):
        """P2-1：advance 同样要认驼峰。"""
        _create()
        resp = client.post(
            "/api/novel/novel_a/threads/t1/advance",
            json={"status": "paid_off", "chapterNumber": 9},
        )
        assert resp.json()["data"]["payoff_chapter"] == 9

    def test_request_model_stays_in_sync_with_core(self):
        """P2-1 的防漂移：请求模型是 core 模型的副本，字段一旦分叉必须在测试里炸掉。"""
        from story_engine.api.routes.threads import PlotThreadRequest
        from story_engine.core.models import PlotThread

        assert set(PlotThreadRequest.model_fields) == set(PlotThread.model_fields)
