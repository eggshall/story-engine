"""N5 契约测试：`POST /api/check/chapter` 的返回结构与基线策略。

计划书 2.3 的验收：「契约测试：接口返回结构与 schema 一致；校验报告含 level/location/suggestion」。
用 TestClient（进程内）跑契约层；跨进程的真实 HTTP 验证见 `tests/e2e/test_n5_check_real_http.py`。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app
from story_engine.core.models import Chapter, Novel
from story_engine.tools.novel_storage import save_novel

client = TestClient(app)

TEXT_WITH_ISSUES = (
    "他推开门。\n\n"
    + "他继续向前走，" * 60          # 超长段
    + "\n\n值得注意的是，仪表盘读数在缓慢下降。"   # AI 套话
    + "\n\n一切都结束了。"           # 无钩子
)

CLEAN_TEXT = "我推开门，我听见风。突然，灯灭了。\n\n我站住，我没敢回头。"


@pytest.fixture
def no_key(make_config):
    make_config({"llm": {"default_model": "m", "models": []}})


@pytest.fixture
def novels_root(tmp_path, monkeypatch):
    root = tmp_path / "novels"
    root.mkdir()
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", root)
    return root


class TestContractShape:
    def test_report_matches_schema(self, no_key):
        resp = client.post("/api/check/chapter", json={"text": TEXT_WITH_ISSUES})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]

        assert data["level"] in ("alert", "warn", "ok")     # skipped 不是整章级别（P1-5）
        assert set(data["summary"]) == {"alert", "warn", "ok", "skipped"}
        assert data["incomplete"] is True                    # 无基线 → 对话占比没判定
        assert "dialogue_ratio" in data["skipped_rules"]
        assert set(data["by_rule"]) <= {
            "chapter_hook", "dialogue_ratio", "paragraph_length", "pov_consistency", "ai_flavor"
        }
        assert data["text_length"] == len(TEXT_WITH_ISSUES)
        assert set(data["rules_run"]) == {
            "chapter_hook", "dialogue_ratio", "paragraph_length", "pov_consistency", "ai_flavor"
        }
        # 每条发现都要能直接喂审稿页：级别 + 定位 + 建议
        assert data["findings"], "有问题的文本不应给出空报告"
        for f in data["findings"]:
            assert set(f) >= {"rule_id", "rule_name", "level", "suggestion", "location", "details"}
            assert f["level"] in ("alert", "warn", "ok", "skipped")

    def test_issues_are_actually_caught(self, no_key):
        resp = client.post("/api/check/chapter", json={"text": TEXT_WITH_ISSUES})

        data = resp.json()["data"]
        by_rule = {f["rule_id"]: f for f in data["findings"]}

        assert by_rule["chapter_hook"]["level"] == "warn"
        assert by_rule["paragraph_length"]["level"] == "warn"
        assert by_rule["paragraph_length"]["location"]["paragraph_index"] == 1
        assert any(
            f["rule_id"] == "ai_flavor" and "值得注意的是" in (f["location"] or {}).get("excerpt", "")
            for f in data["findings"]
        )
        assert data["level"] == "warn"

    def test_clean_text_passes(self, no_key):
        resp = client.post("/api/check/chapter", json={"text": CLEAN_TEXT})

        data = resp.json()["data"]
        # P1-5：干净文本的级别必须是 ok（无基线只让 incomplete=True，不该把整章标成 skipped）
        assert data["level"] == "ok"
        assert data["summary"]["warn"] == 0
        assert data["incomplete"] is True

    def test_offsets_are_relative_to_raw_request_text(self, no_key):
        """P1-4：带前导空白的文本，location 必须相对**原文**（否则前端按 start:end 跳转会错位）。"""
        padded = "\n\n   " + "他推开门。\n\n" + "他" + "继续走，" * 90 + "\n\n一切都结束了。   \n"

        resp = client.post("/api/check/chapter", json={"text": padded})

        data = resp.json()["data"]
        assert data["text_length"] == len(padded)
        para = next(f for f in data["findings"] if f["rule_id"] == "paragraph_length")
        loc = para["location"]
        assert padded[loc["start"]:loc["end"]].startswith("他继续走，")
        hook = next(f for f in data["findings"] if f["rule_id"] == "chapter_hook")
        assert hook["location"]["end"] == len(padded)


class TestBaseline:
    def test_without_baseline_dialogue_ratio_is_skipped(self, no_key):
        resp = client.post("/api/check/chapter", json={"text": CLEAN_TEXT})

        data = resp.json()["data"]
        finding = next(f for f in data["findings"] if f["rule_id"] == "dialogue_ratio")
        assert finding["level"] == "skipped"
        assert data["baseline_source"] == "none"

    def test_previous_chapters_supply_baseline(self, no_key, novels_root):
        novel = Novel(title="基线测试")
        novel.chapters = [
            Chapter(chapter_number=1, title="一", content="他说：「走。」" * 20),
            Chapter(chapter_number=2, title="二", content="他说：「等等。」" * 18),
            Chapter(chapter_number=3, title="三", content=CLEAN_TEXT),
        ]
        save_novel(novel, "baseline-novel")

        resp = client.post(
            "/api/check/chapter", json={"novel_id": "baseline-novel", "chapter_number": 3}
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["baseline_source"] == "previous_chapters"
        finding = next(f for f in data["findings"] if f["rule_id"] == "dialogue_ratio")
        assert finding["level"] in ("ok", "warn")     # 有基线 → 给出判定，而不是 skipped
        assert finding["details"]["expected"] > 0

    def test_baseline_chapters_limit_is_respected(self, no_key, novels_root):
        novel = Novel(title="上限测试")
        novel.chapters = [
            Chapter(chapter_number=i, title=f"{i}", content="他说：「走。」" * 10) for i in range(1, 6)
        ]
        novel.chapters.append(Chapter(chapter_number=6, title="六", content=CLEAN_TEXT))
        save_novel(novel, "limit-novel")

        resp = client.post(
            "/api/check/chapter",
            json={"novel_id": "limit-novel", "chapter_number": 6, "baseline_chapters": 1},
        )

        # 只取 1 章做基线 → 不足 min_previous(2) → 回到无基线
        data = resp.json()["data"]
        assert data["baseline_source"] == "none"


class TestProfileBaselineWiring:
    """P0-1 的路由侧证据：真实画像形状（中文键 + score）能一路带到 baseline_source=profile。"""

    def test_real_profile_shape_reaches_route(self, no_key, monkeypatch):
        real_shape = {"对话比例": {"value": "对话较多", "score": 0.30}}
        monkeypatch.setattr(
            "story_engine.api.routes.check._profile_features", lambda _pid: real_shape
        )

        resp = client.post(
            "/api/check/chapter", json={"text": CLEAN_TEXT, "profile_id": "any-profile"}
        )

        data = resp.json()["data"]
        assert data["baseline_source"] == "profile"
        finding = next(f for f in data["findings"] if f["rule_id"] == "dialogue_ratio")
        assert finding["level"] in ("ok", "warn")     # 有画像基线 → 给出判定而非 skipped
        assert finding["details"]["baseline_source"] == "profile"


class TestCustomPathNovel:
    """计划书 P0-7：自定义路径的小说也要能读到章节（经索引解析真实目录）。"""

    def test_chapter_is_read_from_indexed_custom_path(self, no_key, monkeypatch, tmp_path):
        custom = tmp_path / "somewhere-else" / "我的小说"
        custom.mkdir(parents=True)
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
        monkeypatch.setattr(
            "story_engine.tools.novel_storage._index_get",
            lambda novel_id: str(custom) if novel_id == "novel_custom1" else None,
        )
        novel = Novel(title="自定义路径")
        novel.chapters = [Chapter(chapter_number=1, title="一", content=TEXT_WITH_ISSUES)]
        save_novel(novel, "novel_custom1")            # 经索引写到自定义目录

        resp = client.post(
            "/api/check/chapter", json={"novel_id": "novel_custom1", "chapter_number": 1}
        )

        data = resp.json()["data"]
        assert data["text_length"] == len(TEXT_WITH_ISSUES)
        assert (custom / "novel.json").exists()


class TestRequestValidation:
    def test_neither_text_nor_chapter_is_rejected(self, no_key):
        resp = client.post("/api/check/chapter", json={})

        body = resp.json()
        assert body["success"] is False
        assert "text" in body["message"]

    def test_unknown_chapter_reports_message(self, no_key, novels_root):
        novel = Novel(title="空书")
        save_novel(novel, "empty-novel")

        resp = client.post(
            "/api/check/chapter", json={"novel_id": "empty-novel", "chapter_number": 1}
        )

        body = resp.json()
        assert body["success"] is False
        assert "不存在" in body["message"] or "为空" in body["message"]

    def test_blank_text_is_treated_as_missing(self, no_key):
        resp = client.post("/api/check/chapter", json={"text": "   \n  "})

        assert resp.json()["success"] is False
