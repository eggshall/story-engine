"""N5 E2E（真实 HTTP）：`POST /api/check/chapter` 跨层验证。

校验器本身是纯函数（单测已覆盖），但**接口**是跨层的：真实 socket + 鉴权中间件 +
从小说目录读章节（文件落盘）+ schema 序列化。按 §9.3 必须有真 HTTP E2E。

本文件不需要假上游：校验接口不调用模型（这正是"A 类=确定性"的价值——校验不花一次 token）。
"""

from __future__ import annotations

import httpx
import pytest

from story_engine.core.models import Chapter, Novel
from story_engine.tools.novel_storage import save_novel
from tests.e2e.fake_upstream import real_http_stack, write_config

pytestmark = pytest.mark.e2e

API_KEY = "e2e-n5-key"

DIRTY_TEXT = (
    "他推开门。\n\n"
    + "他继续向前走，" * 60
    + "\n\n值得注意的是，仪表盘读数在缓慢下降。"
    + "\n\n一切都结束了。"
)
CLEAN_TEXT = "我推开门，我听见风。突然，灯灭了。\n\n我站住，我没敢回头。"


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    # 校验接口不碰模型，base_url 给个不会用到的地址即可（不需要假上游）
    cfg = write_config(tmp_path_factory.mktemp("e2e-n5"), "http://127.0.0.1:9/v1", API_KEY)
    with real_http_stack(cfg) as base:
        yield base


@pytest.fixture
def novels_root(tmp_path, monkeypatch):
    root = tmp_path / "novels"
    root.mkdir()
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", root)
    monkeypatch.setattr("story_engine.characters.manager.CHARACTERS_DIR", tmp_path / "characters")
    return root


def test_requires_api_key(base_url):
    """新端点不能被鉴权绕开。"""
    resp = httpx.post(f"{base_url}/api/check/chapter", json={"text": CLEAN_TEXT}, timeout=30)

    assert resp.status_code == 401


def test_text_mode_returns_full_report(base_url):
    resp = httpx.post(
        f"{base_url}/api/check/chapter",
        json={"text": DIRTY_TEXT},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )

    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    body = resp.json()
    assert body["success"] is True
    data = body["data"]

    assert data["level"] == "warn"
    assert data["summary"]["warn"] >= 2
    assert data["incomplete"] is True
    assert "dialogue_ratio" in data["skipped_rules"]
    assert set(data["by_rule"]) <= {
        "chapter_hook", "dialogue_ratio", "paragraph_length", "pov_consistency", "ai_flavor"
    }
    by_rule = {f["rule_id"]: f for f in data["findings"] if f["level"] != "ok"}
    assert by_rule["paragraph_length"]["location"]["paragraph_index"] == 1
    assert by_rule["chapter_hook"]["location"]["end"] == len(DIRTY_TEXT)
    # 无基线 → 对话占比必须 skipped（不误报）
    assert next(f for f in data["findings"] if f["rule_id"] == "dialogue_ratio")["level"] == "skipped"
    assert data["baseline_source"] == "none"


def test_chapter_mode_reads_from_disk_and_builds_baseline(base_url, novels_root):
    novel = Novel(title="E2E 校验")
    novel.chapters = [
        Chapter(chapter_number=1, title="一", content="他说：「走。」" * 20),
        Chapter(chapter_number=2, title="二", content="他说：「等等。」" * 18),
        Chapter(chapter_number=3, title="三", content=DIRTY_TEXT),
    ]
    save_novel(novel, "e2e-check-novel")

    resp = httpx.post(
        f"{base_url}/api/check/chapter",
        json={"novel_id": "e2e-check-novel", "chapter_number": 3},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["text_length"] == len(DIRTY_TEXT)          # 真的从磁盘读到了第 3 章
    assert data["baseline_source"] == "previous_chapters"  # 前两章提供了基线
    assert next(f for f in data["findings"] if f["rule_id"] == "dialogue_ratio")["level"] != "skipped"


def test_unknown_novel_is_an_explicit_error(base_url, novels_root):
    resp = httpx.post(
        f"{base_url}/api/check/chapter",
        json={"novel_id": "nope-novel", "chapter_number": 1},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )

    body = resp.json()
    assert body["success"] is False
    assert "nope-novel" in body["message"]


def test_report_is_deterministic_over_real_http(base_url):
    """同一个文本两次请求必须逐字节一致（确定性是"敢当闸门用"的前提）。

    评审 P1-7：必须先断言两次都**成功且非空**，否则"两次都失败"也会通过相等断言。
    """
    first_resp = httpx.post(
        f"{base_url}/api/check/chapter",
        json={"text": DIRTY_TEXT},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    second_resp = httpx.post(
        f"{base_url}/api/check/chapter",
        json={"text": DIRTY_TEXT},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )

    assert first_resp.json()["success"] is True
    assert second_resp.json()["success"] is True
    first = first_resp.json()["data"]
    second = second_resp.json()["data"]
    assert first["findings"], "两次都返回空报告时相等断言没有意义"
    assert first == second
