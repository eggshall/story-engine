"""N4b 契约测试：真实数据源接入（手写件 + 上一章结尾 + 角色卡 + 风格块）。

MVP-2 的边界（计划书 §2.1/§3）：主线/前情/节拍是**手写**的，摘要槽位先读手写 `recap.md`
（N7 换 SQLite 时只替换 provider）；不做素材卡片/技法库/条款库/检索。

契约：

  P1 手写件路径固定：`mainline.md` / `recap.md` / `beats/ch_XXXX.md`（相对小说目录，经 `_novel_dir`）。
  P2 请求里显式传入的文本（beat/mainline/recap）优先于文件 —— 前端可以直接喂节拍。
  P3 读不到就返回空 → 由装配器记进 `manifest.skipped`（不能静默）。
  P4 上一章结尾取最后 2000 字，`source` 指向具体章号。
  P5 角色卡沿用既有渲染（`CharacterCard.to_prompt_block()`），每卡一条，来源带角色名。
  P6 标准槽位表：主线/风格/节拍 为 PINNED（永不裁），前情 SUMMARIES，结尾 CHAPTER_TAIL，角色 CHARACTERS。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from story_engine.core.models import Chapter, Novel
from story_engine.writer import context_sources as cs
from story_engine.writer.context_builder import (
    CHAPTER_TAIL,
    CHARACTERS,
    PINNED,
    SUMMARIES,
    ContextBuilder,
    Slot,
)


@pytest.fixture
def novels_root(tmp_path, monkeypatch) -> Path:
    """把小说根目录指到临时目录（provider 通过 `_novel_dir` 读盘）。"""
    root = tmp_path / "novels"
    root.mkdir()
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", root)
    return root


def _slice(provider, inputs=None):
    """调用 provider 并返回它给装配器的片段（过滤空片段的行为属于装配器，这里看原始返回）。"""
    return provider(inputs or {})


class TestHandwrittenFiles:
    def test_reads_mainline_recap_and_beat(self, novels_root: Path):
        d = novels_root / "my-novel"
        (d / "beats").mkdir(parents=True)
        (d / "mainline.md").write_text("主线：人类第一次走出太阳系。", encoding="utf-8")
        (d / "recap.md").write_text("第一章：发射失败。\n第二章：发现异常信号。", encoding="utf-8")
        (d / "beats" / "ch_0007.md").write_text("本章节拍：舱内失重，主角做出选择。", encoding="utf-8")

        providers = cs.build_providers(Novel(title="人类大进步"), "my-novel", chapter_number=7)

        mainline = _slice(providers["mainline"])
        assert [p.source for p in mainline] == ["mainline"]
        assert "走出太阳系" in mainline[0].text

        recap = _slice(providers["recap"])
        assert [p.source for p in recap] == ["recap:1", "recap:2"]
        assert "发射失败" in recap[0].text

        beat = _slice(providers["beat"])
        assert beat[0].source == "beat:ch_0007"
        assert "失重" in beat[0].text

    def test_explicit_text_overrides_file(self, novels_root: Path):
        """P2：请求里传的节拍优先（前端“节拍”输入框直接生效，不必先落盘）。"""
        providers = cs.build_providers(
            Novel(title="t"), "no-files-here", chapter_number=3, beat_text="临时节拍：直接喂进来的"
        )

        beat = _slice(providers["beat"])

        assert beat[0].text == "临时节拍：直接喂进来的"

    def test_missing_files_yield_empty_lists(self, novels_root: Path):
        """P3：读不到返回空，装配器会把它记成 skipped（这里只验证 provider 契约）。"""
        providers = cs.build_providers(Novel(title="t"), "empty-novel", chapter_number=1)

        assert _slice(providers["mainline"]) == []
        assert _slice(providers["recap"]) == []
        assert _slice(providers["beat"]) == []
        assert _slice(providers["style"]) == []


class TestChapterTail:
    def test_takes_last_2000_chars_of_previous_chapter(self):
        long_tail = "尾" * 2500
        novel = Novel(title="t")
        novel.chapters = [
            Chapter(chapter_number=1, title="一", content="开头" + long_tail),
            Chapter(chapter_number=2, title="二", content="当前章"),
        ]

        providers = cs.build_providers(novel, "n1", chapter_number=2)
        pieces = _slice(providers["chapter_tail"])

        assert len(pieces) == 1
        assert pieces[0].source == "chapter_tail:ch_0001"
        assert len(pieces[0].text) == cs.CHAPTER_TAIL_CHARS == 2000
        assert "开头" not in pieces[0].text        # 只取结尾
        assert pieces[0].text.endswith("尾")

    def test_no_previous_chapter_yields_empty(self):
        novel = Novel(title="t")
        novel.chapters = [Chapter(chapter_number=5, title="五", content="不是上一章")]

        providers = cs.build_providers(novel, "n1", chapter_number=1)

        assert _slice(providers["chapter_tail"]) == []

    def test_chapter_gap_uses_the_last_written_chapter(self, novels_root: Path):
        """章节跳号（缺第 4 章）时，「上一章」= 已写过里编号最大的那章。

        与世界观**共用同一个口径**（N8 评审 P2-6）：原实现写死 `chapter_number - 1`，
        于是写第 5 章而第 4 章缺号时会给出「世界观拿到了第 3 章正文、上一章结尾却是空的」
        这种自相矛盾的清单。`source` 必须写**真实**章号，作者才知道这段来自哪一章。
        """
        from story_engine.core.models import LoreBook, LorebookEntry

        novel = Novel(title="t")
        novel.lorebooks = {
            "天玄大陆": LoreBook(
                name="天玄大陆",
                entries={"culti": LorebookEntry(keys=["筑基"], content="境界：筑基→金丹")},
            )
        }
        novel.chapters = [
            Chapter(chapter_number=3, title="三", content="他运转筑基功法。"),
            Chapter(chapter_number=5, title="五", content="当前章正文"),
        ]

        providers = cs.build_providers(novel, "gap-novel", chapter_number=5)

        tail = _slice(providers["chapter_tail"])
        assert len(tail) == 1
        assert tail[0].source == "chapter_tail:ch_0003"
        assert "筑基功法" in tail[0].text
        # 两套口径必须指向同一章：世界观也由第 3 章触发（若退回"精确上一章"就会是空的）
        assert [p.source for p in _slice(providers["lore"])] == ["lore:天玄大陆:culti"]


class TestCharactersAndStyle:
    def test_characters_use_existing_renderer(self):
        class Card:
            def to_prompt_block(self) -> str:
                return "【林昭】冷静；口头禅：数据不会说谎。"

        novel = Novel(title="t")
        novel.characters = {"林昭": Card()}  # type: ignore[dict-item]

        providers = cs.build_providers(novel, "n1", chapter_number=1)
        pieces = _slice(providers["characters"])

        assert [p.source for p in pieces] == ["character:林昭"]
        assert "数据不会说谎" in pieces[0].text

    def test_style_block_only_when_given(self):
        with_style = cs.build_providers(Novel(title="t"), "n1", chapter_number=1,
                                       style_block="文风：冷峻克制。")
        without = cs.build_providers(Novel(title="t"), "n1", chapter_number=1)

        assert _slice(with_style["style"])[0].source == "style"
        assert _slice(without["style"]) == []


class TestProviderTruncationVisibility:
    """评审 P1-3：provider 内部截断必须能在注入清单里看出来。"""

    def test_long_previous_chapter_tail_is_marked_truncated(self, novels_root):
        novel = Novel(title="t")
        novel.chapters = [Chapter(chapter_number=1, title="一", content="字" * (cs.CHAPTER_TAIL_CHARS + 500))]
        builder = cs.build_novel_builder(novel, "tail-novel", chapter_number=2)

        result = builder.build({})

        entry = next(e for e in result.manifest.entries if e.slot_id == "chapter_tail")
        assert entry.chars == cs.CHAPTER_TAIL_CHARS
        assert entry.truncated is True          # 修复前恒为 False，作者会以为上一章只有 2000 字

    def test_short_previous_chapter_not_marked(self, novels_root):
        novel = Novel(title="t")
        novel.chapters = [Chapter(chapter_number=1, title="一", content="短结尾")]
        builder = cs.build_novel_builder(novel, "tail-novel-2", chapter_number=2)

        result = builder.build({})

        entry = next(e for e in result.manifest.entries if e.slot_id == "chapter_tail")
        assert entry.truncated is False


class TestReadFailuresAreVisible:
    """评审 P1-4：只有"文件不存在"才算没写；读失败要报 `error:<类型>`，不能伪装成 empty。"""

    def test_permission_error_surfaces_as_error(self, novels_root):
        import os

        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("root 会无视文件权限，无法构造读失败")

        d = novels_root / "locked"
        d.mkdir()
        f = d / "mainline.md"
        f.write_text("手写主线", encoding="utf-8")
        os.chmod(f, 0o000)
        try:
            providers = cs.build_providers(Novel(title="t"), "locked", chapter_number=1)
            builder = ContextBuilder(
                slots=[Slot("mainline", priority=PINNED, provider="mainline")],
                providers=providers,
                budget_tokens=None,
            )

            result = builder.build({})

            assert result.manifest.entries == []
            assert [s.reason for s in result.manifest.skipped] == ["error:PermissionError"]
        finally:
            os.chmod(f, 0o600)

    def test_missing_file_is_still_empty_not_error(self, novels_root):
        providers = cs.build_providers(Novel(title="t"), "nothing-here", chapter_number=1)
        builder = ContextBuilder(
            slots=[Slot("mainline", priority=PINNED, provider="mainline")],
            providers=providers,
            budget_tokens=None,
        )

        result = builder.build({})

        assert [s.reason for s in result.manifest.skipped] == ["empty"]


class TestBlankOverrides:
    """评审 P2-6：纯空白的覆盖串不算"传了"，应回退到文件。"""

    def test_blank_mainline_override_falls_back_to_file(self, novels_root):
        d = novels_root / "blank-test"
        d.mkdir()
        (d / "mainline.md").write_text("文件里的主线", encoding="utf-8")

        providers = cs.build_providers(Novel(title="t"), "blank-test", chapter_number=1,
                                      mainline_text="   \n  ")

        pieces = _slice(providers["mainline"])
        assert pieces[0].text == "文件里的主线"

    def test_blank_beat_override_falls_back_to_file(self, novels_root):
        d = novels_root / "blank-beat"
        (d / "beats").mkdir(parents=True)
        (d / "beats" / "ch_0003.md").write_text("文件里的节拍", encoding="utf-8")

        providers = cs.build_providers(Novel(title="t"), "blank-beat", chapter_number=3,
                                      beat_text="  ")

        assert _slice(providers["beat"])[0].text == "文件里的节拍"


class TestDefaultSlotsAndBuilder:
    def test_slot_table_priorities(self):
        slots = {s.slot_id: s for s in cs.default_slots()}

        assert slots["mainline"].priority == PINNED
        assert slots["style"].priority == PINNED
        assert slots["beat"].priority == PINNED          # 永不裁：架构要求"绝不砍风格块与节拍"
        assert slots["recap"].priority == SUMMARIES
        assert slots["chapter_tail"].priority == CHAPTER_TAIL
        assert slots["characters"].priority == CHARACTERS
        # 顺序 = 进 prompt 的顺序（主线→文风→节拍→伏笔→前情→结尾→角色）
        # ⚠️ 这里冻结了完整槽位表：**新增槽位时必须同步改这一行**（是有意的契约变更，
        #    不是意外——N9 加 threads 槽位时更新过一次）。只加槽位不加断言会让 prompt
        #    顺序漂移而无人发现，所以保留快照 + 旁加不变式（见下）。
        assert [s.slot_id for s in cs.default_slots()] == [
            "mainline", "style", "beat", "threads", "recap", "chapter_tail", "characters", "lore"
        ]
        # 不变式：伏笔是"记忆"类，不许被提成 PINNED（提了就会挤掉风格块/节拍）
        assert slots["threads"].priority > PINNED
        # 不变式：世界观是"资料"类，同样不许 PINNED（N8 方案 B 新增槽位）
        assert slots["lore"].priority > PINNED

    def test_builder_assembles_from_files_with_manifest(self, novels_root: Path):
        d = novels_root / "n2"
        (d / "beats").mkdir(parents=True)
        (d / "mainline.md").write_text("主线：走出太阳系。", encoding="utf-8")
        (d / "beats" / "ch_0002.md").write_text("节拍：第二次发射。", encoding="utf-8")

        novel = Novel(title="t")
        novel.chapters = [Chapter(chapter_number=1, title="一", content="上一章的结尾内容")]
        builder = cs.build_novel_builder(novel, "n2", chapter_number=2)
        result = builder.build({"novel_id": "n2"})

        sources = [e.source for e in result.manifest.entries]
        assert "mainline" in sources
        assert "beat:ch_0002" in sources
        assert "chapter_tail:ch_0001" in sources
        # 没有风格块/角色/前情 → 必须出现在 skipped 里（可见，不是静默消失）
        skipped_slots = {s.slot_id for s in result.manifest.skipped}
        assert {"style", "recap", "characters"} <= skipped_slots
        assert result.manifest.total_tokens == sum(
            len(b) for b in result.text.split("\n\n")
        )

    def test_extra_providers_can_be_plugged_without_touching_builder(self, novels_root: Path):
        """后续阶段（素材/技法/条款/检索）挂新数据源的方式：加槽位 + 加 provider。"""
        from story_engine.writer.context_builder import RETRIEVAL, Slot

        def retrieval(_inputs):
            from story_engine.writer.context_builder import ContextPiece

            return [ContextPiece(text="检索：旧地球档案。", source="retrieval:42")]

        builder = cs.build_novel_builder(
            Novel(title="t"),
            "n3",
            chapter_number=1,
            slots=[*cs.default_slots(), Slot("retrieval", priority=RETRIEVAL, provider="retrieval")],
            extra_providers={"retrieval": retrieval},
        )

        result = builder.build({})

        assert "检索：旧地球档案。" in result.text
        assert any(e.source == "retrieval:42" for e in result.manifest.entries)
