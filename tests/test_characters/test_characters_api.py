"""N8 契约测试：角色卡接口（按小说绑定 + 素材库复制语义）。

用 TestClient 打真实路由（含鉴权中间件、schema 过一遍），不 mock 业务层。
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
    """隔离小说根与素材库根；建两本书用于隔离性断言。

    `make_config` 是仓库既有 fixture：写一份不含 `security.api_key` 的配置 → 鉴权放行
    （与 test_check_api.py 同一套做法，别自己 monkeypatch 配置对象）。
    """
    make_config({"llm": {"default_model": "m", "models": []}})
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
    monkeypatch.setattr(
        "story_engine.characters.library.LIBRARY_DIR", tmp_path / "library" / "characters"
    )
    save_novel(Novel(title="人类大进步"), "novel_a")
    save_novel(Novel(title="另一本"), "novel_b")
    return tmp_path


def _card(name="沈约", **kw):
    body = {"name": name, "description": "总工程师", "personality": "冷静"}
    body.update(kw)
    return body


def _create(novel_id="novel_a", body=None):
    return client.post(f"/api/novel/{novel_id}/characters", json=body or _card())


class TestCRUD:
    def test_create_then_list_then_get(self):
        assert _create().json()["success"] is True

        body = client.get("/api/novel/novel_a/characters").json()

        assert body["success"] is True
        assert body["data"]["names"] == ["沈约"]
        assert body["data"]["cards"][0]["personality"] == "冷静"

    def test_duplicate_name_is_explicit_failure(self):
        _create()

        again = _create(body=_card(description="偷偷改掉"))

        assert again.json()["success"] is False
        assert "已存在" in again.json()["message"]
        # 原卡没被改
        cards = client.get("/api/novel/novel_a/characters").json()["data"]["cards"]
        assert cards[0]["description"] == "总工程师"

    def test_update_existing(self):
        _create()

        resp = client.put("/api/novel/novel_a/characters/沈约",
                          json=_card(personality="冷得发硬"))

        assert resp.json()["success"] is True
        cards = client.get("/api/novel/novel_a/characters").json()["data"]["cards"]
        assert cards[0]["personality"] == "冷得发硬"

    def test_update_can_rename_without_leaving_stale_card(self):
        _create()

        resp = client.put("/api/novel/novel_a/characters/沈约", json=_card(name="老沈"))

        assert resp.json()["success"] is True
        names = client.get("/api/novel/novel_a/characters").json()["data"]["names"]
        assert names == ["老沈"]                      # 旧名字不留残影

    def test_update_missing_is_failure(self):
        resp = client.put("/api/novel/novel_a/characters/查无此人", json=_card())

        assert resp.json()["success"] is False
        assert "不存在" in resp.json()["message"]

    def test_delete(self):
        _create()

        assert client.delete("/api/novel/novel_a/characters/沈约").json()["success"] is True
        assert client.get("/api/novel/novel_a/characters").json()["data"]["names"] == []
        assert client.delete("/api/novel/novel_a/characters/沈约").json()["success"] is False

    def test_search(self):
        _create(body=_card("沈约", description="总工程师"))
        _create(body=_card("林岚", personality="嘴硬"))

        assert client.get("/api/novel/novel_a/characters", params={"q": "嘴硬"}).json()["data"]["names"] == ["林岚"]

    def test_unknown_novel_is_message_not_500(self):
        resp = client.get("/api/novel/no-such/characters")

        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "不存在" in resp.json()["message"]


class TestIsolation:
    def test_two_novels_have_their_own_cards(self):
        _create("novel_a", _card("沈约"))
        _create("novel_b", _card("张小满"))

        a = client.get("/api/novel/novel_a/characters").json()["data"]["names"]
        b = client.get("/api/novel/novel_b/characters").json()["data"]["names"]

        assert a == ["沈约"]
        assert b == ["张小满"]

    def test_same_name_in_both_novels_is_independent(self):
        _create("novel_a", _card("沈约", description="A 版"))
        _create("novel_b", _card("沈约", description="B 版"))

        client.delete("/api/novel/novel_a/characters/沈约")

        b = client.get("/api/novel/novel_b/characters").json()["data"]["cards"]
        assert b[0]["description"] == "B 版"


class TestLibrary:
    def test_to_library_then_list(self):
        _create()

        resp = client.post("/api/novel/novel_a/characters/沈约/to-library")

        assert resp.json()["success"] is True
        assert client.get("/api/library/characters").json()["data"]["names"] == ["沈约"]

    def test_export_missing_card_is_failure(self):
        assert client.post("/api/novel/novel_a/characters/无/to-library").json()["success"] is False

    def test_import_from_library_into_another_novel(self):
        _create()
        client.post("/api/novel/novel_a/characters/沈约/to-library")

        resp = client.post("/api/novel/novel_b/characters/import",
                           json={"source": "library", "name": "沈约"})

        assert resp.json()["success"] is True
        assert client.get("/api/novel/novel_b/characters").json()["data"]["names"] == ["沈约"]

    def test_import_is_a_copy_not_a_shared_reference(self):
        _create("novel_a", _card(description="A 版"))
        client.post("/api/novel/novel_a/characters/沈约/to-library")
        client.post("/api/novel/novel_b/characters/import", json={"source": "library", "name": "沈约"})

        # 改 A 书的卡 → B 书那份不该跟着变
        client.put("/api/novel/novel_a/characters/沈约", json=_card(description="A 改了"))

        b_cards = client.get("/api/novel/novel_b/characters").json()["data"]["cards"]
        assert b_cards[0]["description"] == "A 版"

    def test_import_from_another_novel(self):
        _create("novel_a", _card("沈约"))

        resp = client.post("/api/novel/novel_b/characters/import",
                           json={"source": "novel_a", "name": "沈约", "new_name": "老沈"})

        assert resp.json()["success"] is True
        assert client.get("/api/novel/novel_b/characters").json()["data"]["names"] == ["老沈"]

    def test_import_clash_is_explicit(self):
        _create("novel_a", _card("沈约"))
        _create("novel_b", _card("沈约", description="本书自己的"))
        client.post("/api/novel/novel_a/characters/沈约/to-library")

        resp = client.post("/api/novel/novel_b/characters/import",
                           json={"source": "library", "name": "沈约"})

        assert resp.json()["success"] is False
        assert "同名" in resp.json()["message"]
        # 勾选覆盖才改得动
        ok = client.post("/api/novel/novel_b/characters/import",
                         json={"source": "library", "name": "沈约", "overwrite": True})
        assert ok.json()["success"] is True

    def test_import_missing_source_is_failure(self):
        resp = client.post("/api/novel/novel_a/characters/import",
                           json={"source": "library", "name": "不存在的素材"})

        assert resp.json()["success"] is False

    def test_import_from_missing_novel_is_failure(self):
        resp = client.post("/api/novel/novel_a/characters/import",
                           json={"source": "no-such-novel", "name": "沈约"})

        assert resp.json()["success"] is False
        assert "不存在" in resp.json()["message"]

    def test_slug_collision_does_not_silently_overwrite(self):
        """素材库的文件名不是身份：不同名字撞同一文件名必须显式失败（N8 评审 P1-1）。

        `_slug` 有损（`"A B"` / `"A_B"` 都 → `A_B`），原来两次另存都返回 success=true，
        先导出的那份无声消失。这里用**同一个源卡 + 两个会撞车的 new_name** 构造，
        以免混入另一个既有缺陷（见下）。

        ⚠️ 已知的**既有**缺陷（不在本切片范围，已在 `N8-REVIEW.md` 记录）：`characters/`
        镜像的文件名也走 `_slug`，而 `load_novel` 会**回读**该目录。所以同一本书里同时建
        `"A B"` 与 `"A_B"` 两张卡时，两个镜像写同一个文件，回读后后者把前者顶掉 ——
        真源 `novel.json` 里两张都在，但界面上先建的那张**看不见**（`lore/` 没这个问题，
        因为它不回读）。
        """
        _create("novel_a", _card("沈约", description="第一份"))

        first = client.post("/api/novel/novel_a/characters/沈约/to-library",
                            params={"new_name": "A B"})
        second = client.post("/api/novel/novel_a/characters/沈约/to-library",
                             params={"new_name": "A_B"})

        assert first.json()["success"] is True
        assert second.json()["success"] is False
        assert "文件名" in second.json()["message"]
        # 先导出的那份还在，内容没被吃；names 用内嵌名而不是 slug 后的 stem
        lib = client.get("/api/library/characters").json()["data"]
        assert lib["names"] == ["A B"]
        assert lib["cards"][0]["description"] == "第一份"

    def test_import_missing_material_says_so(self):
        """「素材库里没有」与「本书已有同名」要分开说（N8 评审 P1-2）。"""
        resp = client.post("/api/novel/novel_a/characters/import",
                           json={"source": "library", "name": "ghost"})

        assert resp.json()["success"] is False
        assert "素材库里没有" in resp.json()["message"]

    def test_invalid_source_is_not_a_server_error(self):
        """`source` 非法 → 可读失败，不是 HTTP 500（N8 评审 P1-3）。"""
        resp = client.post("/api/novel/novel_a/characters/import",
                           json={"source": "../../etc/passwd", "name": "沈约"})

        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "非法" in resp.json()["message"]
