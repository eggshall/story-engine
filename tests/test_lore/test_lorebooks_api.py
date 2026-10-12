"""N8 契约测试：世界观设定集接口（按小说绑定 + 素材库纯复制语义）。

用 TestClient 打真实路由（含鉴权中间件、schema 过一遍），不 mock 业务层。
真实 socket + 真上游那一层在 `tests/e2e/test_n8_lorebooks_real_http.py`。
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
    """隔离小说根**与世界观素材库根**；建两本书用于隔离性断言。

    `make_config` 是仓库既有 fixture：写一份不含 `security.api_key` 的配置 → 鉴权放行
    （与 `test_characters_api.py` 同一套做法，别自己 monkeypatch 配置对象）。
    素材库根必须一起隔离，否则用例会写进真实 `data/library/lore/`。
    """
    make_config({"llm": {"default_model": "m", "models": []}})
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
    monkeypatch.setattr("story_engine.lore.library.LIBRARY_DIR", tmp_path / "library" / "lore")
    save_novel(Novel(title="人类大进步"), "novel_a")
    save_novel(Novel(title="另一本"), "novel_b")
    return tmp_path


def _book(name="天玄大陆", content="境界：筑基→金丹", **kw):
    body = {
        "name": name,
        "description": "东域修仙体系",
        "entries": {"culti": {"keys": ["筑基", "金丹"], "content": content, "priority": 80}},
    }
    body.update(kw)
    return body


def _create(novel_id="novel_a", body=None):
    return client.post(f"/api/novel/{novel_id}/lorebooks", json=body or _book())


def _names(novel_id="novel_a"):
    return client.get(f"/api/novel/{novel_id}/lorebooks").json()["data"]["names"]


def _books_by_name(novel_id="novel_a"):
    return {
        b["name"]: b
        for b in client.get(f"/api/novel/{novel_id}/lorebooks").json()["data"]["books"]
    }


class TestCRUD:
    def test_create_then_list(self):
        assert _create().json()["success"] is True

        body = client.get("/api/novel/novel_a/lorebooks").json()

        assert body["success"] is True
        assert body["data"]["names"] == ["天玄大陆"]
        assert body["data"]["books"][0]["entries"]["culti"]["content"] == "境界：筑基→金丹"

    def test_duplicate_name_is_explicit_failure(self):
        _create()

        again = _create(body=_book(content="偷偷改掉"))

        assert again.json()["success"] is False
        assert "已存在" in again.json()["message"]
        # 原设定没被改
        assert _books_by_name()["天玄大陆"]["entries"]["culti"]["content"] == "境界：筑基→金丹"

    def test_update_existing(self):
        _create()

        resp = client.put("/api/novel/novel_a/lorebooks/天玄大陆", json=_book(content="改过的正文"))

        assert resp.json()["success"] is True
        assert _books_by_name()["天玄大陆"]["entries"]["culti"]["content"] == "改过的正文"

    def test_update_missing_is_failure(self):
        resp = client.put("/api/novel/novel_a/lorebooks/不存在", json=_book(name="不存在"))

        assert resp.json()["success"] is False
        assert "不存在" in resp.json()["message"]

    def test_delete_then_delete_again_is_failure(self):
        _create()

        assert client.delete("/api/novel/novel_a/lorebooks/天玄大陆").json()["success"] is True
        assert _names() == []
        again = client.delete("/api/novel/novel_a/lorebooks/天玄大陆")
        assert again.json()["success"] is False
        assert "不存在" in again.json()["message"]


class TestRenameNeverEatsAnotherBook:
    """改名 = 删旧建新；目标名已被占用时**必须失败**。

    这是 N9 评审 P1-1 在伏笔上实测出的数据丢失路径（PUT 改 id 静默覆盖另一条记录），
    同类守卫在设定集上必须有 —— 否则作者改个名字就吃掉另一条设定，且返回 success=true。
    """

    def test_rename_to_free_name_works(self):
        _create()

        resp = client.put("/api/novel/novel_a/lorebooks/天玄大陆", json=_book(name="东域设定"))

        assert resp.json()["success"] is True
        assert _names() == ["东域设定"]

    def test_rename_onto_existing_name_fails_and_keeps_both(self):
        _create()
        _create(body=_book(name="现代都市", content="都市背景"))

        resp = client.put(
            "/api/novel/novel_a/lorebooks/天玄大陆",
            json=_book(name="现代都市", content="被吃掉的正文"),
        )

        assert resp.json()["success"] is False
        assert "已存在" in resp.json()["message"]
        # 两条都还在，且内容都没被改
        assert _names() == ["天玄大陆", "现代都市"]
        assert _books_by_name()["现代都市"]["entries"]["culti"]["content"] == "都市背景"


class TestBookScoping:
    def test_books_do_not_see_each_other(self):
        _create("novel_a")

        assert _names("novel_b") == []

    def test_unknown_novel_is_explicit_failure(self):
        resp = _create("definitely-missing")

        assert resp.json()["success"] is False
        assert "不存在" in resp.json()["message"]
        assert client.get("/api/novel/definitely-missing/lorebooks").json()["success"] is False


class TestRequestBoundary:
    def test_typo_field_is_rejected_not_silently_dropped(self):
        """拼错的字段必须 422，而不是被静默丢弃（N9 边界原则：`extra="forbid"`）。"""
        resp = _create(body={"name": "天玄大陆", "descriptoin": "拼错了"})

        assert resp.status_code == 422


class TestLibrary:
    def test_export_then_import_is_a_pure_copy(self):
        _create("novel_a")

        assert client.post("/api/novel/novel_a/lorebooks/天玄大陆/to-library").json()["success"] is True
        assert client.get("/api/library/lorebooks").json()["data"]["names"] == ["天玄大陆"]

        resp = client.post(
            "/api/novel/novel_b/lorebooks/import", json={"source": "library", "name": "天玄大陆"}
        )
        assert resp.json()["success"] is True

        # 改**源书**里那一条，已导入的那本不受影响（纯复制，不是共享引用）
        client.put("/api/novel/novel_a/lorebooks/天玄大陆", json=_book(content="源书改了"))

        imported = _books_by_name("novel_b")["天玄大陆"]
        assert imported["entries"]["culti"]["content"] == "境界：筑基→金丹"

    def test_import_from_another_book(self):
        _create("novel_a")

        resp = client.post(
            "/api/novel/novel_b/lorebooks/import", json={"source": "novel_a", "name": "天玄大陆"}
        )

        assert resp.json()["success"] is True
        assert _names("novel_b") == ["天玄大陆"]

    def test_import_duplicate_needs_overwrite(self):
        _create("novel_a")
        client.post("/api/novel/novel_a/lorebooks/天玄大陆/to-library")
        client.post(
            "/api/novel/novel_b/lorebooks/import", json={"source": "library", "name": "天玄大陆"}
        )

        again = client.post(
            "/api/novel/novel_b/lorebooks/import", json={"source": "library", "name": "天玄大陆"}
        )

        assert again.json()["success"] is False
        assert "已有同名设定集" in again.json()["message"]


class TestLibraryIdentityConflicts:
    """素材库的文件名不是身份（N8 评审 P1-1）：不同名字撞同一文件名时不许静默覆盖。

    `_slug` 是有损的（`"A B"` / `"A_B"` / `"a/b"` 都 → `A_B`），原来无条件 `write_text`
    会让先导出的素材**无声消失**，两次都返回 success=true。
    """

    def test_slug_collision_does_not_silently_overwrite(self):
        _create("novel_a", _book(name="A B", content="第一份"))
        _create("novel_a", _book(name="A_B", content="第二份"))

        first = client.post("/api/novel/novel_a/lorebooks/A B/to-library")
        second = client.post("/api/novel/novel_a/lorebooks/A_B/to-library")

        assert first.json()["success"] is True
        assert second.json()["success"] is False
        assert "文件名" in second.json()["message"]
        # 先导出的那份还在，内容没被吃
        lib = client.get("/api/library/lorebooks").json()["data"]
        assert lib["names"] == ["A B"]
        assert lib["books"][0]["entries"]["culti"]["content"] == "第一份"

    def test_same_identity_export_is_idempotent(self):
        """同名同身份重复另存不该报错（作者点两次不算冲突）。"""
        _create("novel_a")

        assert client.post("/api/novel/novel_a/lorebooks/天玄大陆/to-library").json()["success"] is True
        again = client.post("/api/novel/novel_a/lorebooks/天玄大陆/to-library")

        assert again.json()["success"] is True

    def test_explicit_overwrite_flag_takes_the_name(self):
        _create("novel_a", _book(name="A B", content="第一份"))
        _create("novel_a", _book(name="A_B", content="第二份"))
        client.post("/api/novel/novel_a/lorebooks/A B/to-library")

        forced = client.post("/api/novel/novel_a/lorebooks/A_B/to-library?overwrite=true")

        assert forced.json()["success"] is True
        assert client.get("/api/library/lorebooks").json()["data"]["names"] == ["A_B"]

    def test_names_and_books_agree(self):
        """`names` 必须用**内嵌名**，不能回 slug 后的 stem，否则两者不自洽。"""
        _create("novel_a", _book(name="含 空格"))
        client.post("/api/novel/novel_a/lorebooks/含 空格/to-library")

        lib = client.get("/api/library/lorebooks").json()["data"]

        assert lib["names"] == ["含 空格"]
        assert [b["name"] for b in lib["books"]] == ["含 空格"]

    def test_export_missing_source_is_honest(self):
        resp = client.post("/api/novel/novel_a/lorebooks/没有这个/to-library")

        assert resp.json()["success"] is False
        assert "不存在" in resp.json()["message"]


class TestImportFailureMessages:
    def test_missing_material_says_so(self):
        """源素材不存在 → 提示指向「素材库里没有」，不能指向「本书已存在」（N8 评审 P1-2）。

        原来两种情况都返回 False，界面会对着一份根本不存在的素材反复让人勾「覆盖」。
        """
        resp = client.post(
            "/api/novel/novel_a/lorebooks/import", json={"source": "library", "name": "ghost"}
        )

        assert resp.json()["success"] is False
        assert "素材库里没有" in resp.json()["message"]
        assert "覆盖" not in resp.json()["message"]

    def test_invalid_source_is_not_a_server_error(self):
        """`source` 非法（路径穿越样式）→ 可读失败，不是 HTTP 500（N8 评审 P1-3）。"""
        resp = client.post(
            "/api/novel/novel_a/lorebooks/import",
            json={"source": "../../etc/passwd", "name": "x"},
        )

        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "非法" in resp.json()["message"]

    def test_camel_case_new_name_is_honored(self):
        """前端按项目约定发驼峰 `newName`，不能静默忽略（N8 评审 P2-3）。"""
        _create("novel_a")
        client.post("/api/novel/novel_a/lorebooks/天玄大陆/to-library")

        resp = client.post(
            "/api/novel/novel_b/lorebooks/import",
            json={"source": "library", "name": "天玄大陆", "newName": "东域设定"},
        )

        assert resp.json()["success"] is True
        assert _names("novel_b") == ["东域设定"]


class TestRequestBoundaryExtras:
    def test_nested_entry_typo_is_rejected(self):
        """条目里拼错字段也必须 422（只给顶层 forbid 时它会被静默丢弃，评审 P2-2）。"""
        resp = _create(body={
            "name": "天玄大陆",
            "entries": {"e": {"keys": ["k"], "content": "x", "categorie": "地理"}},
        })

        assert resp.status_code == 422

    def test_empty_name_is_rejected(self):
        """空名的镜像会落成 `untitled.json`，与任何 slug 为 untitled 的名字碰撞（评审 P2-4）。"""
        resp = _create(body={"name": "", "entries": {}})

        assert resp.status_code == 422
