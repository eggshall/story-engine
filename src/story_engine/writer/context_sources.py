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
        Slot("recap", priority=SUMMARIES, provider="recap", renderer="bullets", max_tokens=3000),
        Slot("chapter_tail", priority=CHAPTER_TAIL, provider="chapter_tail", renderer="plain",
             # 槽位预算的口径是"字符"（estimate_tokens 按字符计），与 provider 的截断字数一致
             max_tokens=CHAPTER_TAIL_CHARS),
        Slot("characters", priority=CHARACTERS, provider="characters", renderer="plain",
             max_tokens=3000),
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
    """

    def _p(_inputs: Mapping[str, Any]) -> List[ContextPiece]:
        prev = [c for c in chapters if getattr(c, "chapter_number", None) == chapter_number - 1]
        if not prev:
            return []
        content = (getattr(prev[0], "content", "") or "").strip()
        if not content:
            return []
        was_truncated = len(content) > CHAPTER_TAIL_CHARS
        tail = content[-CHAPTER_TAIL_CHARS:]
        return [
            ContextPiece(
                text=tail,
                source=f"chapter_tail:ch_{chapter_number - 1:04d}",
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
