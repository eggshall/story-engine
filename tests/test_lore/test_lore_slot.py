"""N8 世界观切片（方案 B）：装配器新增 `lore` 槽位。

**为什么需要这个槽位**（实测证据，不是推测）——装配器原来的槽位真值是：

```
mainline(0) style(0) beat(0) chapter_tail(10) threads(20) recap(20) characters(30)
有没有 lore/世界观 槽位：False
```

也就是说走装配器的 `/api/generate/chapter/v2`（计划里的"真路径"）**压根不注入设定集**；
世界观只活在 `engine._build_world_context()` 那条 legacy 手拼 prompt 的路径上，
与 AGENTS.md §4 强约定「上下文一律经 `context_builder.py` 按槽位装配，不要在生成函数里手拼 prompt」
相矛盾。方案 B = 把它接进装配器，而不是继续加固 legacy 路径。

本文件钉死的契约：
1. `lore` 槽位已注册，且**可被裁**（世界观属"设定"类，不是硬约束）
2. 触发源**只用已写过的那一章正文** —— 不许拿正在写/后面才写的章节内容提前泄漏设定
3. 命中条目的**实际文本**进清单（manifest 必须与真正注入的文本一一对应）
4. 没命中 / 没设定集 / 第一章 → 进 `skipped`（"没注成必须可见"）
5. 书间隔离：别的书的设定集不许漏进来
"""

from __future__ import annotations

import pytest

from story_engine.core.models import Chapter, LoreBook, LorebookEntry, Novel
from story_engine.tools.novel_storage import save_novel
from story_engine.writer.context_builder import PINNED
from story_engine.writer.context_sources import (
    LORE_MAX_ENTRIES,
    build_novel_builder,
    default_slots,
)


@pytest.fixture(autouse=True)
def _isolate_novels(novels_root):
    """强制隔离小说根目录。

    本文件的 provider 会经 `build_novel_builder(novel, novel_id, ...)` 读小说目录下的手写件
    （`mainline.md`/`recap.md`/`beats/`），不隔离就会读到真实 `data/novels/` 里的同名书，
    测试结果随本机数据变化。隔离复用 `tests/conftest.py` 的 `novels_root`（别自己重造）。
    """
    return novels_root


def _books() -> dict:
    return {
        "天玄大陆": LoreBook(
            name="天玄大陆",
            entries={
                "culti": LorebookEntry(
                    keys=["筑基", "金丹"], content="境界：筑基→金丹", priority=80
                ),
                "sect": LorebookEntry(
                    keys=["天玄宗"], content="天玄宗在东域", priority=70
                ),
                "dead": LorebookEntry(
                    keys=["废案"], content="不该出现", priority=99, enabled=False
                ),
            },
        ),
        "现代都市": LoreBook(
            name="现代都市",
            entries={"car": LorebookEntry(keys=["汽车"], content="都市背景", priority=60)},
        ),
    }


def _novel(books: dict | None = None, prev_text: str = "他盘膝坐下，运转筑基功法。") -> Novel:
    novel = Novel(title="A 书", lorebooks=_books() if books is None else books)
    if prev_text:
        novel.chapters = [Chapter(chapter_number=1, title="第一章", content=prev_text)]
    return novel


def _build(novel: Novel, chapter_number: int = 2):
    return build_novel_builder(novel, "novel_a", chapter_number=chapter_number).build({})


def _sources(ctx) -> list[str]:
    """只取 **lore 槽位**的来源。

    注意 manifest.entries 是**所有槽位**的片段（chapter_tail / characters 等也在里面），
    所以这里必须按前缀过滤 —— 否则断言 `_sources(ctx) == []` 会因为上一章结尾片段而失败。
    """
    return [e.source for e in ctx.manifest.entries if e.source.startswith("lore:")]


def _skipped_ids(ctx) -> dict:
    return {s.slot_id: s.reason for s in ctx.manifest.skipped}


class TestSlotRegistration:
    def test_lore_slot_is_registered(self):
        slots = {s.slot_id: s for s in default_slots()}

        assert "lore" in slots, "装配器没有世界观槽位 —— v2 路径不会注入设定集"
        assert slots["lore"].provider == "lore"

    def test_lore_slot_is_trimmable(self):
        """世界观属"设定"类，必须能被全局预算裁掉；被提成 PINNED 会挤掉风格块/节拍。"""
        slot = {s.slot_id: s for s in default_slots()}["lore"]

        assert slot.priority != PINNED
        assert slot.max_tokens and slot.max_tokens > 0

    def test_lore_sits_with_the_other_setting_slots(self):
        """顺序 = 进 prompt 的顺序；设定类（角色卡/世界观）应当相邻。"""
        ids = [s.slot_id for s in default_slots()]

        assert ids.index("lore") > ids.index("characters")


class TestInjection:
    def test_triggered_entry_reaches_the_manifest(self):
        ctx = _build(_novel())

        assert "lore:天玄大陆:culti" in _sources(ctx)

    def test_manifest_matches_what_is_injected(self):
        """manifest 必须与真正拼进 prompt 的文本一一对应。

        注意 `ManifestEntry` 只带溯源字段（source/chars/tokens/priority/truncated），
        真正的注入文本在 `AssembledContext.text` —— 所以两边都要断言，不能只看清单。
        """
        ctx = _build(_novel())

        assert "lore:天玄大陆:culti" in _sources(ctx)
        assert "境界：筑基→金丹" in ctx.text

    def test_disabled_entry_is_never_injected(self):
        ctx = _build(_novel(prev_text="这段提到废案内容。"))

        assert _sources(ctx) == []
        assert "不该出现" not in ctx.text

    def test_injected_block_is_self_describing(self):
        """每条注入自带【书名 + 触发词】标签，模型才知道这段设定属于哪个世界。

        与 legacy `build_lore_context` 的差别：legacy 用一整块头
        `【世界观设定 — 自动注入】`；装配器按**条目**给片段（manifest 才能精确到条目、
        槽位预算才能按条截断），所以标签下移到每一条上。
        """
        ctx = _build(_novel())

        assert "天玄大陆" in ctx.text
        assert "筑基" in ctx.text


class TestTriggerSource:
    def test_first_chapter_has_nothing_to_trigger_on(self):
        """还没写过任何一章 → 没有触发源，槽位空着（不是报错）。"""
        novel = _novel(prev_text="")

        ctx = _build(novel, chapter_number=1)

        assert _skipped_ids(ctx).get("lore") == "empty"

    def test_current_chapter_content_never_used_as_trigger(self):
        """**关键隔离**：正在写的第 2 章即使已有正文，也不能拿它当触发源 ——
        否则等于把本章还没生成的内容/未来信息提前泄漏进 prompt。"""
        novel = _novel(prev_text="今天天气不错。")
        novel.chapters.append(Chapter(chapter_number=2, title="二", content="他运转筑基功法。"))

        ctx = _build(novel, chapter_number=2)

        assert _sources(ctx) == []          # 第 1 章无关键词 → 不该被第 2 章正文触发

    def test_trigger_uses_the_immediately_previous_chapter(self):
        novel = _novel(prev_text="今天天气不错。")
        novel.chapters.append(Chapter(chapter_number=2, title="二", content="他运转筑基功法。"))
        novel.chapters.append(Chapter(chapter_number=3, title="三", content="无关内容。"))

        ctx = _build(novel, chapter_number=3)

        assert "lore:天玄大陆:culti" in _sources(ctx)     # 触发源是第 2 章


class TestSkippedVisibility:
    def test_no_match_is_skipped_empty(self):
        ctx = _build(_novel(prev_text="完全无关的一段话。"))

        assert _skipped_ids(ctx).get("lore") == "empty"
        assert _sources(ctx) == []

    def test_novel_without_lorebooks_is_skipped(self):
        ctx = _build(_novel(books={}))

        assert _skipped_ids(ctx).get("lore") == "empty"


class TestIsolation:
    def test_other_novels_lorebooks_never_leak_in(self):
        """同目录下**另一本**有命中的书，也不许漏进本书的注入清单。

        N8 评审 P2-1 修正了这条用例：原来只构造了一本 `lorebooks={}` 的空书，断言
        `_sources(ctx) == []` —— 那与「空设定集不注入」是同一个断言，把 provider 改回
        读共享目录也照样通过（循环论证）。现在先在 `novels_root` 里真放一本**会被命中**的
        书并证明它确实命得中，再断言本书拿不到它。
        """
        other = Novel(title="B 书", lorebooks=_books())
        other.chapters = [
            Chapter(chapter_number=1, title="一", content="他运转筑基功法，天玄宗。")
        ]
        save_novel(other, "novel_b")
        # 前置证据：这本书的设定集确实是「能被触发」的，否则下面的空断言毫无意义
        assert "lore:天玄大陆:culti" in _sources(_build(other))

        novel = _novel(books={})                 # 本书没有任何设定集
        novel.chapters = [
            Chapter(chapter_number=1, title="一", content="他运转筑基功法，天玄宗。" * 3)
        ]

        ctx = _build(novel)

        assert _sources(ctx) == []
        assert _skipped_ids(ctx).get("lore") == "empty"


class TestSkippedReasonContract:
    def test_skipped_empty_reason_is_shared_by_three_causes(self):
        """`skipped: empty` 同时表达三种成因，**故意不拆新理由**（N8 评审 P2-3 的处置）。

        三种成因：① 本书没有设定集 ② 第一章没有触发源 ③ 有触发源但没命中关键词。
        理由字符串与既有槽位（`chapter_tail` 等）保持同一口径；要区分成因就看
        `entries` 里有没有 lore 片段 + 这本书有没有设定集。这条用例把口径钉住，
        防止有人误以为能靠 `reason` 区分，也防止以后有人为 lore 单独造一个理由
        而与其它槽位不一致。
        """
        no_books = _build(_novel(books={}))            # ①
        no_trigger_source = _build(_novel(), chapter_number=1)   # ②
        no_match = _build(_novel(prev_text="完全无关的一段话。"))  # ③

        for cause, ctx in (("无设定集", no_books), ("无触发源", no_trigger_source), ("未命中", no_match)):
            assert _skipped_ids(ctx).get("lore") == "empty", cause
            assert _sources(ctx) == [], cause


class TestOverflowVisibility:
    def test_more_hits_than_cap_are_reported(self):
        """命中超过单次注入上限时，**被丢的条数必须出现在清单里**（N8 评审 P2-2）。

        原实现吃 `find_matching_entries` 的默认 10 条上限：第 11 条起既不进 `entries`，
        也不进 `skipped`/`dropped` —— 清单与真实注入不一致，违反 §4「没注成必须可见」。
        """
        entries = {
            f"e{i:03d}": LorebookEntry(keys=["筑基"], content=f"设定{i}", priority=50)
            for i in range(LORE_MAX_ENTRIES + 7)
        }
        novel = _novel(books={"海量设定": LoreBook(name="海量设定", entries=entries)})

        ctx = _build(novel)
        sources = _sources(ctx)

        assert len([s for s in sources if s != "lore:overflow"]) == LORE_MAX_ENTRIES
        assert "lore:overflow" in sources
        assert "另有 7 条" in ctx.text
        overflow = next(e for e in ctx.manifest.entries if e.source == "lore:overflow")
        assert overflow.truncated is True, "溢出片段必须自报被截断，否则读者以为这就是全部"
