"""N6 E2E（真实 HTTP）：审稿页要用到的两块后端能力。

1. **注入清单落盘**（N4b 评审待办）：v2 生成后清单写到 `<小说目录>/manifests/ch_XXXX.json`，
   并且 `GET /api/check/manifest` 读回来的内容必须与 SSE done 载荷里那份**完全一致**
   —— 否则"事后能回看"是假的（两处各说各话）。
2. **带指令重写**：`instruction` 非空 → 输出候选稿但**绝不落盘**（覆盖正文是不可逆动作），
   且候选稿能直接喂给校验器（审稿页的"改完再校验"闭环）。

链路：真实 socket(uvicorn) ←httpx→ 鉴权中间件 → 路由 → 装配器 → OpenAIClient → 假上游
"""

from __future__ import annotations

import json

import httpx
import pytest

from story_engine.core.models import Chapter, Novel
from story_engine.tools.novel_storage import _novel_dir, load_novel, save_novel
from tests.e2e.fake_upstream import FakeUpstream, parse_sse_events, real_http_stack, write_config

pytestmark = pytest.mark.e2e

API_KEY = "e2e-n6-key"
BEAT = "本章节拍：舱内失重，主角必须在返航与继续之间做选择。"
OLD_TEXT = "旧正文：他站在舷窗前，一句话也没说。"
FAKE_OUTPUT = "擂台之上"          # 假上游固定产出


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    upstream = FakeUpstream()
    upstream.set_mode("ok")
    cfg = write_config(tmp_path_factory.mktemp("e2e-n6"), upstream.base_url, API_KEY)

    with real_http_stack(cfg) as base:
        yield base, upstream

    upstream.close()


@pytest.fixture
def novels_root(tmp_path, monkeypatch):
    root = tmp_path / "novels"
    root.mkdir()
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", root)
    return root


def _make_novel(root, novel_id: str, *, with_old_chapter: bool = False) -> None:
    d = root / novel_id
    d.mkdir(parents=True, exist_ok=True)
    novel = Novel(title="人类大进步")
    novel.chapters = [
        Chapter(chapter_number=1, title="第一次发射",
                content="第一章正文：发射失败，主角背下全部责任。")
    ]
    if with_old_chapter:
        novel.chapters.append(
            Chapter(chapter_number=2, title="试炼", content=OLD_TEXT, word_count=len(OLD_TEXT))
        )
    save_novel(novel, novel_id)
    (d / "beats").mkdir(exist_ok=True)
    (d / "beats" / "ch_0002.md").write_text(BEAT, encoding="utf-8")


def _post_v2(base: str, payload: dict) -> tuple[httpx.Response, list]:
    resp = httpx.post(
        f"{base}/api/generate/chapter/v2",
        json=payload,
        headers={"X-API-Key": API_KEY},
        timeout=60,
    )
    assert resp.status_code == 200, resp.status_code
    return resp, parse_sse_events(resp.text)


def _done(events: list) -> dict:
    dones = [p for ev, p in events if ev == "done"]
    assert len(dones) == 1, [ev for ev, _p in events]
    return dones[0]


def _get_manifest(base: str, novel_id: str, chapter_number: int) -> dict:
    resp = httpx.get(
        f"{base}/api/check/manifest",
        params={"novel_id": novel_id, "chapter_number": chapter_number},
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    assert resp.status_code == 200, resp.status_code
    return resp.json()


class TestManifestPersisted:
    def test_persisted_manifest_equals_delivered_one(self, stack, novels_root):
        base, upstream = stack
        _make_novel(novels_root, "n6-manifest")
        upstream.clear()

        _resp, events = _post_v2(base, {"novel_id": "n6-manifest", "chapter_number": 2,
                                        "chapter_title": "试炼"})
        done = _done(events)

        path = _novel_dir("n6-manifest") / "manifests" / "ch_0002.json"
        assert path.is_file(), f"注入清单没落盘：{path}"
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk == done["context_manifest"]     # 两处必须同一份（不是各说各话）
        assert on_disk["budget_tokens"] == 40000

        fetched = _get_manifest(base, "n6-manifest", 2)
        assert fetched["success"] is True
        assert fetched["data"] == done["context_manifest"]

    def test_generate_mode_reports_saved(self, stack, novels_root):
        base, upstream = stack
        _make_novel(novels_root, "n6-saved")
        upstream.clear()

        _resp, events = _post_v2(base, {"novel_id": "n6-saved", "chapter_number": 2,
                                        "chapter_title": "试炼"})

        done = _done(events)
        assert done["saved"] is True
        assert done["rewrite"] is False
        saved = load_novel("n6-saved")
        assert saved is not None
        assert saved.chapters[-1].content.strip() == FAKE_OUTPUT

    def test_missing_manifest_is_explicit_not_silent(self, stack, novels_root):
        base, _upstream = stack
        _make_novel(novels_root, "n6-nomanifest")

        body = _get_manifest(base, "n6-nomanifest", 2)     # 第 2 章还没用 v2 生成过

        assert body["success"] is False
        assert "注入清单" in body["message"]

    def test_manifest_endpoint_requires_api_key(self, stack, novels_root):
        base, _upstream = stack

        resp = httpx.get(
            f"{base}/api/check/manifest",
            params={"novel_id": "n6-manifest", "chapter_number": 2},
            timeout=30,
        )

        assert resp.status_code == 401


class TestInstructionRewrite:
    def test_rewrite_returns_candidate_without_saving(self, stack, novels_root):
        """带指令重写：上游收到"现有正文 + 指令"，产出的候选稿**不落盘**。"""
        base, upstream = stack
        _make_novel(novels_root, "n6-rewrite", with_old_chapter=True)
        upstream.clear()

        _resp, events = _post_v2(base, {
            "novel_id": "n6-rewrite",
            "chapter_number": 2,
            "instruction": "把开头的环境描写删掉，直接从对话进入",
        })

        done = _done(events)
        assert done["rewrite"] is True
        assert done["saved"] is False
        assert done["chapter"]["content"].strip() == FAKE_OUTPUT

        # 上游确实收到了"现有正文"与"作者的修改指令"（否则重写就是凭空重写）
        prompt = "\n".join(
            str(m.get("content", ""))
            for m in upstream.stream_requests()[0]["body"]["messages"]
        )
        assert OLD_TEXT in prompt
        assert "把开头的环境描写删掉，直接从对话进入" in prompt
        # 重写也要带装配上下文（节拍）
        assert BEAT in prompt

        # 磁盘上这一章**一个字都没变**
        on_disk = load_novel("n6-rewrite")
        assert on_disk is not None
        chapter2 = next(c for c in on_disk.chapters if c.chapter_number == 2)
        assert chapter2.content == OLD_TEXT
        assert len(on_disk.chapters) == 2              # 没有多出一章

    def test_rewrite_without_existing_chapter_is_error_not_empty_stream(self, stack, novels_root):
        base, upstream = stack
        _make_novel(novels_root, "n6-rewrite-empty")     # 只有第 1 章
        upstream.clear()

        _resp, events = _post_v2(base, {"novel_id": "n6-rewrite-empty", "chapter_number": 5,
                                        "instruction": "加强悬念"})

        names = [ev for ev, _p in events]
        assert "error" in names, names
        assert "done" not in names                        # N2 契约：error 之后不再有事件
        err = [p for ev, p in events if ev == "error"][0]
        assert "还没有正文" in json.dumps(err, ensure_ascii=False)
        assert upstream.stream_requests() == []           # 连上游都不该调

    def test_rewrite_candidate_can_be_checked(self, stack, novels_root):
        """闭环：重写候选稿 → 直接送校验器（审稿页"改完立刻看一眼"）。"""
        base, upstream = stack
        _make_novel(novels_root, "n6-loop", with_old_chapter=True)
        upstream.clear()
        _resp, events = _post_v2(base, {"novel_id": "n6-loop", "chapter_number": 2,
                                        "instruction": "加入一段 AI 味很重的总结"})
        candidate = _done(events)["chapter"]["content"]

        resp = httpx.post(
            f"{base}/api/check/chapter",
            json={"text": candidate},
            headers={"X-API-Key": API_KEY},
            timeout=30,
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["text_length"] == len(candidate)
        assert data["level"] in ("alert", "warn", "ok")
        assert data["findings"], "候选稿也要出报告（哪怕只是钩子提示）"
