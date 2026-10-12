"""装配器的真实数据源（N4b）—— 手写件 + 已有记忆 + 风格块接成 provider。

MVP-2 的边界（计划书 §2 的 2.1 与 §3）：

- **主线 / 前情 / 章节拍在 MVP-2 是手写的** → 目录里的 `mainline.md` / `recap.md` / `beats/ch_XXXX.md`
- 摘要槽位先读手写 `recap.md`；**N7 换成 SQLite 结构化摘要时只替换 provider，装配器不动**
  （这是 N4a 把 provider/renderer 做成"注册表名字"的意义）
- 上一章结尾原文、角色卡、风格块直接复用既有数据
- 不做：素材卡片 / 技法库 / 条款库 / 向量检索（阶段 Ⅲ–Ⅵ 才做）

所有 provider 的契约与 N4a 一致：`(inputs) -> list[ContextPiece]`；读不到内容就返回空列表，
由装配器记进 `manifest.skipped`（"没注成"必须是可见的）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from story_engine.core.models import Novel
from story_engine.lore.lorebook import find_matching_entries
from story_engine.threads.manager import open_threads_of
from story_engine.tools.novel_storage import _novel_dir
from story_engine.writer.context_builder import (
    CHAPTER_TAIL,
    CHARACTERS,
    PINNED,
    SUMMARIES,
    ContextBuilder,
    ContextPiece,
    Slot,
)

# 单次写作的上下文预算（与 P7-LONG-MEMORY 的"总 ≤39.6K token"对齐，留余量给生成）
DEFAULT_BUDGET_TOKENS = 40_000

# 上一章结尾取多少字（计划书 2.1：上一章结尾 2000 字）
CHAPTER_TAIL_CHARS = 2000

# 伏笔账本槽位预算（N9）：账本是"记忆"类，可被全局预算裁，所以给一个明确上限
THREADS_MAX_TOKENS = 1200

# 世界观槽位预算（N8）：设定集命中可能很多条，给一个上限并按条截断
LORE_MAX_TOKENS = 2000

#: 单次注入的设定**条目数**上限。命中超过上限时必须**可见**（§4「没注成必须可见」）：
#: 早先这里吃 `find_matching_entries` 的默认 10 条，第 11 条起既不进 `entries`，
#: 也不进 `skipped`/`dropped`，清单与真实注入不一致（N8 评审 P2-2）。现在超出部分
#: 以 `lore:overflow` 片段自报条数。
LORE_MAX_ENTRIES = 50


def _read_text(path: Path) -> str:
    """读手写件。**只有"文件不存在"才算"作者还没写"**（返回空串）。

    评审 P1-4：原来把 `OSError` 一律吞掉，于是权限/IO 故障会伪装成"该槽位没内容"（`skipped: empty`），
    与"没注成必须可见且原因准确"矛盾。现在其余 `OSError` 抛出 → 由装配器记成 `error:<类型>`。
    """
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    return ""


def default_slots() -> List[Slot]:
    """标准槽位表（顺序 = 进 prompt 的顺序；PINNED 永不裁）。"""
    return [
        Slot("mainline", priority=PINNED, provider="mainline", renderer="plain", max_tokens=1500),
        Slot("style", priority=PINNED, provider="style", renderer="plain", max_tokens=1500),
        Slot("beat", priority=PINNED, provider="beat", renderer="plain", max_tokens=2000),
        # 伏笔账本（N9）：回答的是「本章该推进什么」，与节拍同级紧邻。
        # 优先级取 SUMMARIES（可被裁）而非 PINNED —— 账本属"记忆"类，不是硬约束。
        Slot("threads", priority=SUMMARIES, provider="threads", renderer="bullets",
             max_tokens=THREADS_MAX_TOKENS),
        Slot("recap", priority=SUMMARIES, provider="recap", renderer="bullets", max_tokens=3000),
        Slot("chapter_tail", priority=CHAPTER_TAIL, provider="chapter_tail", renderer="plain",
             # 槽位预算的口径是"字符"（estimate_tokens 按字符计），与 provider 的截断字数一致
             max_tokens=CHAPTER_TAIL_CHARS),
        Slot("characters", priority=CHARACTERS, provider="characters", renderer="plain",
             max_tokens=3000),
        # 世界观设定集（N8 方案 B）：与角色卡同属"设定"档，排在它后面（设定类相邻）。
        # 为什么必须进装配器：装配器原先**没有世界观槽位**，走装配器的 v2 路径压根不注入
        # 设定集 —— 世界观只活在 engine 的 legacy 手拼 prompt 路径上，与「上下文一律经槽位
        # 装配」的约定相矛盾。优先级取 CHARACTERS（可被裁）而非 PINNED：世界观命中属"资料"，
        # 不是每次生成都必须的硬约束。
        Slot("lore", priority=CHARACTERS, provider="lore", renderer="plain",
             max_tokens=LORE_MAX_TOKENS),
    ]


# ── providers ────────────────────────────────────────────

def _mainline_provider(novel_id: str, override: str = "") -> Callable[[Mapping[str, Any]], List[ContextPiece]]:
    def _p(_inputs: Mapping[str, Any]) -> List[ContextPiece]:
        # 空白覆盖串不算"传了"（否则既不回退文件、又注入一段空白）—— 评审 P2-6
        text = (override or "").strip() or _read_text(_novel_dir(novel_id) / "mainline.md")
        return [ContextPiece(text=text, source="mainline")] if text else []

    return _p


def _recap_provider(novel_id: str, override: str = "") -> Callable[[Mapping[str, Any]], List[ContextPiece]]:
    """手写前情：一行一条 → 每行一个片段。

    注意 `source="recap:N"` 里的 **N 是行号，不是章号**（评审 P2-1）；
    N7 换成结构化摘要后 source 会变成 `summary:ch_XXXX`（逐章一条），届时只替换本 provider。
    """

    def _p(_inputs: Mapping[str, Any]) -> List[ContextPiece]:
        text = (override or "").strip() or _read_text(_novel_dir(novel_id) / "recap.md")
        if not text:
            return []
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return [ContextPiece(text=ln, source=f"recap:{i + 1}") for i, ln in enumerate(lines)]

    return _p


def _beat_provider(
    novel_id: str, chapter_number: int, override: str = ""
) -> Callable[[Mapping[str, Any]], List[ContextPiece]]:
    """本章节拍（手写）：`beats/ch_0007.md`。"""

    def _p(_inputs: Mapping[str, Any]) -> List[ContextPiece]:
        text = (override or "").strip()
        if not text:
            text = _read_text(_novel_dir(novel_id) / "beats" / f"ch_{chapter_number:04d}.md")
        return [ContextPiece(text=text, source=f"beat:ch_{chapter_number:04d}")] if text else []

    return _p


def _chapter_tail_provider(
    chapters: Sequence[Any], chapter_number: int
) -> Callable[[Mapping[str, Any]], List[ContextPiece]]:
    """上一章结尾原文（最后 CHAPTER_TAIL_CHARS 字）—— 长文连贯的关键短上下文。

    截断要**自报**（`ContextPiece.truncated`）：否则作者在注入清单里看到 `chars=2000`
    会以为上一章只有 2000 字（评审 P1-3）。

    "上一章"口径与世界观共用 `previous_chapter()`（N8 评审 P2-6）：原来这里写死
    `chapter_number - 1`，于是章节跳号（缺第 4 章时写第 5 章）会出现「世界观拿到了第 3 章
    的正文、上一章结尾却是空的」这种自相矛盾的清单。取到的**真实章号**写进 `source`，
    作者一眼能看出这段结尾来自哪一章。
    """

    def _p(_inputs: Mapping[str, Any]) -> List[ContextPiece]:
        prev = previous_chapter(chapters, chapter_number)
        if prev is None:
            return []
        content = (getattr(prev, "content", "") or "").strip()
        if not content:
            return []
        used = getattr(prev, "chapter_number", chapter_number - 1)
        was_truncated = len(content) > CHAPTER_TAIL_CHARS
        tail = content[-CHAPTER_TAIL_CHARS:]
        return [
            ContextPiece(
                text=tail,
                source=f"chapter_tail:ch_{used:04d}",
                truncated=was_truncated,
            )
        ]

    return _p


def _characters_provider(
    characters: Mapping[str, Any],
) -> Callable[[Mapping[str, Any]], List[ContextPiece]]:
    """角色卡：复用 `CharacterCard.to_prompt_block()`（与既有写作路径渲染一致）。"""

    def _p(_inputs: Mapping[str, Any]) -> List[ContextPiece]:
        pieces: List[ContextPiece] = []
        for name, card in (characters or {}).items():
            block = ""
            render = getattr(card, "to_prompt_block", None)
            if callable(render):
                block = str(render() or "").strip()
            if not block:
                block = f"{name}：{getattr(card, 'description', '') or ''}".strip()
            if block:
                pieces.append(ContextPiece(text=block, source=f"character:{name}"))
        return pieces

    return _p


def _style_provider(style_block: str) -> Callable[[Mapping[str, Any]], List[ContextPiece]]:
    def _p(_inputs: Mapping[str, Any]) -> List[ContextPiece]:
        return [ContextPiece(text=style_block, source="style")] if style_block else []

    return _p


def previous_chapter(chapters: Sequence[Any], chapter_number: int) -> Any | None:
    """取**紧邻的前一章**对象（编号 < 本章 里最大的那一章）；没有就 `None`。

    装配器里所有"上一章"口径都必须走这里 —— 同一份上下文里两套口径会让作者无法解释
    注入清单（N8 评审 P2-6）。
    """
    previous = [c for c in chapters if getattr(c, "chapter_number", 0) < chapter_number]
    if not previous:
        return None
    return max(previous, key=lambda c: c.chapter_number)


def previous_chapter_text(chapters: Sequence[Any], chapter_number: int) -> str:
    """取**紧邻的前一章**正文。

    刻意不用 `chapters[-1]`：补写中间某章、或本章已有正文（重写场景）时，`[-1]` 会取到
    错的文本，甚至把**正在写/未来**章节的内容当触发源 —— 那等于提前把设定泄漏进 prompt。
    只取「编号 < 本章」里最大的那一章；没有就返回空串（第一章没有触发源，槽位空着）。
    """
    prev = previous_chapter(chapters, chapter_number)
    if prev is None:
        return ""
    return getattr(prev, "content", "") or ""


def _lore_provider(
    novel: Novel, chapter_number: int
) -> Callable[[Mapping[str, Any]], List[ContextPiece]]:
    """世界观（Lorebook）——按关键词从**本书**的设定集里触发（N8 方案 B）。

    这是本节点的核心落点：装配器原先没有世界观槽位，v2 路径不注入设定集。

    只读 `novel.lorebooks`（本书真源）→ 书间隔离由数据来源保证（`build_novel_builder`
    拿到的是**这一本** `Novel`，provider 不再去读任何共享目录），不需要额外过滤。
    端到端证据：`tests/e2e/test_n8_lore_real_http.py::test_other_book_lore_never_leaks`
    —— 两本书用**同一个触发词**、各自内容不同，断言彼此不进对方的 prompt。

    命中条目的文本自带 `[书名] 触发词` 标签，模型才知道这段设定属于哪个世界。

    `max_results=None` + 自己截断到 `LORE_MAX_ENTRIES`：静默丢第 N+1 条会让清单与真实注入
    不一致（N8 评审 P2-2），所以超出部分额外发一条 `lore:overflow` 片段自报条数。

    返回 `[]` → 进 `manifest.skipped: empty`。这个 `empty` **同时覆盖三种成因**：本书没有
    设定集 / 第一章没有触发源 / 有触发源但没命中关键词。与既有槽位口径一致（`_chapter_tail_provider`
    等同样只用 `empty`，不单独造理由字符串），三种成因的区别请看 `entries` 是否为空 + 本书有没有
    设定集（N8 评审 P2-3 的处置：口径写清楚，由 `test_skipped_empty_reason_is_shared_by_three_causes` 钉住）。
    """

    def _p(_inputs: Mapping[str, Any]) -> List[ContextPiece]:
        books = getattr(novel, "lorebooks", None) or {}
        if not books:
            return []
        text = previous_chapter_text(getattr(novel, "chapters", []) or [], chapter_number)
        if not text:
            return []
        matches = find_matching_entries(books, text, max_results=None)
        pieces: List[ContextPiece] = []
        for book_name, entry_id, entry in matches[:LORE_MAX_ENTRIES]:
            head = f"[{book_name}] {'|'.join(entry.keys)}"
            pieces.append(
                ContextPiece(text=f"{head}\n{entry.content}", source=f"lore:{book_name}:{entry_id}")
            )
        dropped = len(matches) - LORE_MAX_ENTRIES
        if dropped > 0:
            pieces.append(
                ContextPiece(
                    text=(
                        f"（另有 {dropped} 条设定在本章触发，超出单次注入上限 "
                        f"{LORE_MAX_ENTRIES} 条，本次未注入）"
                    ),
                    source="lore:overflow",
                    truncated=True,
                )
            )
        return pieces

    return _p


def _threads_provider(
    novel: Novel, chapter_number: int
) -> Callable[[Mapping[str, Any]], List[ContextPiece]]:
    """本章该带上的伏笔（N9）—— **规则过滤**，不是检索（§9.1.1 的非目标）。

    筛选与排序**直接复用 `threads.manager.open_threads_of`**，不在这里重抄一遍口径
    （评审 P2-5：provider 与 manager 各写一套过滤，只共享状态常量，迟早漂移）。
    读不到账本 → 返回 `[]` → 装配器记进 `manifest.skipped: empty`（"没注成"必须可见）。
    """

    def _p(_inputs: Mapping[str, Any]) -> List[ContextPiece]:
        pieces: List[ContextPiece] = []
        for t in open_threads_of(novel, chapter_number):
            gap = chapter_number - (t.planted_chapter or 0)
            line = f"{t.title or t.id}（{t.status}｜埋于第 {t.planted_chapter} 章，已 {gap} 章未回收"
            if getattr(t, "note", ""):
                line += f"｜计划：{t.note}"
            line += "）"
            pieces.append(ContextPiece(text=line, source=f"thread:{t.id}"))
        return pieces

    return _p


# ── 组装 ─────────────────────────────────────────────────

def build_providers(
    novel: Novel,
    novel_id: str,
    *,
    chapter_number: int,
    style_block: str = "",
    mainline_text: str = "",
    beat_text: str = "",
    recap_text: str = "",
) -> Dict[str, Callable[[Mapping[str, Any]], List[ContextPiece]]]:
    """标准槽位对应的 provider 表（可单独替换其中任意一项）。"""
    return {
        "mainline": _mainline_provider(novel_id, mainline_text),
        "style": _style_provider(style_block),
        "beat": _beat_provider(novel_id, chapter_number, beat_text),
        "recap": _recap_provider(novel_id, recap_text),
        "chapter_tail": _chapter_tail_provider(getattr(novel, "chapters", []) or [], chapter_number),
        "characters": _characters_provider(getattr(novel, "characters", {}) or {}),
        "lore": _lore_provider(novel, chapter_number),
        "threads": _threads_provider(novel, chapter_number),
    }


def build_novel_builder(
    novel: Novel,
    novel_id: str,
    *,
    chapter_number: int,
    style_block: str = "",
    mainline_text: str = "",
    beat_text: str = "",
    recap_text: str = "",
    budget_tokens: Optional[int] = DEFAULT_BUDGET_TOKENS,
    slots: Optional[Sequence[Slot]] = None,
    extra_providers: Optional[Mapping[str, Callable[[Mapping[str, Any]], List[ContextPiece]]]] = None,
) -> ContextBuilder:
    """按标准槽位表组装一台装配器（真实数据源已接好）。

    `extra_providers` 用于后续阶段（素材/技法/条款/检索）挂新数据源 —— 不改本函数签名。
    """
    providers = build_providers(
        novel,
        novel_id,
        chapter_number=chapter_number,
        style_block=style_block,
        mainline_text=mainline_text,
        beat_text=beat_text,
        recap_text=recap_text,
    )
    if extra_providers:
        providers.update(extra_providers)
    return ContextBuilder(
        slots=list(slots or default_slots()),
        providers=providers,
        budget_tokens=budget_tokens,
    )
