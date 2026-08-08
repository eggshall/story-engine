"""测试：写作引擎 — 大纲/写作/草稿三种模式 + 上下文构建 + 保存"""

import asyncio
import json

import pytest

from story_engine.core.models import Chapter, ChapterOutline, CharacterCard, Novel
from story_engine.llm.base import LLMRequest, LLMResponse
from story_engine.writer.engine import WritingEngine


class FakeRouter:
    """记录请求的假 router，返回可配置响应。"""

    def __init__(self, response=None):
        self.captured: list[LLMRequest] = []
        self.response = response or LLMResponse(content="ok")

    async def chat(self, request: LLMRequest, model_name=None):
        self.captured.append(request)
        return self.response


def _novel(with_chapters: bool = True) -> Novel:
    novel = Novel(
        title="测试之书",
        author="作者",
        genre="玄幻",
        synopsis="一段梗概",
        characters={
            "主角": CharacterCard(name="主角", description="勇敢的少年", personality="沉稳"),
        },
    )
    if with_chapters:
        novel.chapters = [
            Chapter(chapter_number=1, title="第一章", content="这是第一段内容，用于前情提要。" * 3),
        ]
    return novel


def _engine(router=None) -> WritingEngine:
    return WritingEngine(router or FakeRouter())


class TestLoadNovel:
    def test_load_and_require_novel(self):
        engine = _engine()
        with pytest.raises(RuntimeError):
            asyncio.run(engine.generate_outline(1))
        engine.load_novel(_novel())
        assert engine.current_novel is not None


class TestContextBuild:
    def test_character_context_includes_card(self):
        engine = _engine()
        engine.load_novel(_novel())
        ctx = engine._build_character_context(engine.current_novel.characters)
        assert "【角色设定】" in ctx
        assert "主角" in ctx

    def test_character_context_empty(self):
        engine = _engine()
        assert engine._build_character_context({}) == ""

    def test_previous_summary_empty(self):
        engine = _engine()
        assert "尚未有前情" in engine._build_previous_summary([])

    def test_previous_summary_window(self):
        engine = _engine()
        chapters = [
            Chapter(chapter_number=i, title=f"第{i}章", content="x" * 300)
            for i in range(1, 8)
        ]
        summary = engine._build_previous_summary(chapters, max_chapters=5)
        assert "第3章" in summary
        assert "第7章" in summary
        assert "第1章" not in summary  # 只保留最后 5 章

    def test_world_context_empty_without_chapters(self):
        engine = _engine()
        engine.load_novel(_novel(with_chapters=False))
        assert engine._build_world_context() == ""

    def test_world_context_empty_without_novel(self):
        engine = _engine()
        assert engine._build_world_context() == ""


class TestGenerateOutline:
    def test_success_parses_json(self):
        router = FakeRouter(response=LLMResponse(
            content='```json\n{"title": "新章", "summary": "概要", '
                    '"beats": ["打斗", {"name": "转折"}], '
                    '"key_scenes": ["场景A"], "word_estimate": 1500}\n```',
            model="m",
        ))
        engine = _engine(router)
        engine.load_novel(_novel())
        outline = asyncio.run(engine.generate_outline(2, title="指定名"))
        assert outline is not None
        assert outline.title == "新章"
        assert outline.summary == "概要"
        assert outline.beats == ["打斗", "转折"]  # 混合格式提取
        assert outline.key_scenes == ["场景A"]
        assert outline.word_estimate == 1500
        assert router.captured[0].temperature == 0.7

    def test_success_parses_raw_json(self):
        router = FakeRouter(response=LLMResponse(content='{"summary": "直接", "beats": []}', model="m"))
        engine = _engine(router)
        engine.load_novel(_novel())
        outline = asyncio.run(engine.generate_outline(1))
        assert outline.summary == "直接"

    def test_fallback_on_bad_json(self):
        router = FakeRouter(response=LLMResponse(content="不是 JSON", model="m"))
        engine = _engine(router)
        engine.load_novel(_novel())
        outline = asyncio.run(engine.generate_outline(1))
        assert outline.summary.startswith("不是 JSON")  # 兜底取前 200 字
        assert outline.beats == []
        assert outline.key_scenes == []

    def test_failure_returns_none(self):
        router = FakeRouter(response=LLMResponse(success=False, error="模型挂了"))
        engine = _engine(router)
        engine.load_novel(_novel())
        assert asyncio.run(engine.generate_outline(1)) is None


class TestWriteChapter:
    def test_success_creates_chapter(self):
        router = FakeRouter(response=LLMResponse(content=" 正文内容 ", model="deepseek"))
        engine = _engine(router)
        engine.load_novel(_novel())
        outline = ChapterOutline(chapter_number=3, title="第三章", summary="s", word_estimate=1000)
        chapter = asyncio.run(engine.write_chapter(outline))
        assert chapter is not None
        assert chapter.content == "正文内容"  # strip 后
        assert chapter.chapter_number == 3
        assert chapter.model_used == "deepseek"
        assert chapter.outline is outline
        assert router.captured[0].max_tokens == 2000  # word_estimate * 2

    def test_failure_returns_none(self):
        router = FakeRouter(response=LLMResponse(success=False, error="err"))
        engine = _engine(router)
        engine.load_novel(_novel())
        outline = ChapterOutline(chapter_number=1, title="t", summary="s")
        assert asyncio.run(engine.write_chapter(outline)) is None

    def test_requires_novel(self):
        engine = _engine()
        outline = ChapterOutline(chapter_number=1, title="t", summary="s")
        with pytest.raises(RuntimeError):
            asyncio.run(engine.write_chapter(outline))


class TestDraftChapter:
    def test_generates_multiple_versions(self):
        router = FakeRouter(response=LLMResponse(content="草稿", model="m"))
        engine = _engine(router)
        engine.load_novel(_novel())
        outline = ChapterOutline(chapter_number=2, title="第二章", summary="s")
        drafts = asyncio.run(engine.draft_chapter(outline, draft_count=3))
        assert len(drafts) == 3
        assert all(d.content == "草稿" for d in drafts)
        assert drafts[0].title == "第二章 (草稿1)"
        assert drafts[2].title == "第二章 (草稿3)"
        assert len(router.captured) == 3
        # 温度随版本递增：0.9 / 1.0 / 1.1
        temps = [r.temperature for r in router.captured]
        assert temps == pytest.approx([0.9, 1.0, 1.1])

    def test_failure_uses_placeholder(self):
        router = FakeRouter(response=LLMResponse(success=False, error="err"))
        engine = _engine(router)
        engine.load_novel(_novel())
        outline = ChapterOutline(chapter_number=1, title="t", summary="s")
        drafts = asyncio.run(engine.draft_chapter(outline, draft_count=2))
        assert all(d.content == "(生成失败)" for d in drafts)

    def test_requires_novel(self):
        engine = _engine()
        outline = ChapterOutline(chapter_number=1, title="t", summary="s")
        with pytest.raises(RuntimeError):
            asyncio.run(engine.draft_chapter(outline))


class TestSaveNovel:
    def test_save_to_default_dir(self, monkeypatch, tmp_path):
        from story_engine.writer import engine as engine_mod

        data_dir = tmp_path / "data"
        monkeypatch.setattr(engine_mod, "data_dir", lambda: data_dir)
        engine = _engine()
        engine.load_novel(_novel())
        path = engine.save_novel()
        assert path == data_dir / "novels" / "测试之书.json"
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["title"] == "测试之书"

    def test_save_to_custom_path(self, tmp_path):
        engine = _engine()
        engine.load_novel(_novel())
        target = tmp_path / "custom" / "novel.json"
        path = engine.save_novel(target)
        assert path == target
        assert target.exists()

    def test_save_requires_novel(self):
        engine = _engine()
        with pytest.raises(RuntimeError):
            engine.save_novel()
