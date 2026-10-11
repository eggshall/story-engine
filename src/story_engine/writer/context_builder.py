"""装配器 v0（N4）— 槽位注册表 + 注入清单 + 预算裁剪。

## 为什么是"槽位"而不是一堆 if

装配器是后续所有阶段的接缝：素材/技法/条款/知识库都要往 prompt 里注入东西。
如果把"注入什么"写死在生成函数里，每加一条数据源都要改生成链路（评审 R2 的返工警告）。
所以这里只做三件事：

1. **声明**：每个槽位是 `Slot(slot_id, priority, provider, renderer, max_tokens)`；
   provider 与 renderer 都是**注册表里的名字**，新增数据源只需注册。
2. **装配**：`build(inputs)` 产出「文本 + `ContextManifest`」，一一对应。
3. **裁剪**：先按槽位自己的 `max_tokens` 截断，再按全局预算从低优先级裁，
   `priority=PINNED` 的槽位永不裁。

## 预算与优先级（N4a 评审后定稿）

- `priority`：**0 = 永不裁剪**（`PINNED`：主线 / 本章节拍 / 风格块）；**数值越大越先被裁**。
  同优先级时"后声明者先裁"（结果确定）。常用档位见下面常量。
- 两级预算：槽位级 `Slot.max_tokens`（超出则按片段粒度截断，`truncated=True`）
  + 全局 `budget_tokens`（超出则整槽裁掉并记入 `dropped`）。
- **token 口径统一（评审 P0-1）**：裁剪判定与 `manifest.total_tokens` 都用
  **实际注入的渲染文本**长度；`entries` 里的 per-piece tokens 只作溯源展示。
  之前两者不一致，导致 `over_budget=False` 却实际超预算（复现：bullets 渲染 17 token，记账 9）。
- **pinned 允许超预算但会明示**：pinned 槽位使总量超过全局预算时，仍然注入（架构要求
  "永不砍风格块与节拍"），同时 `over_budget=True` 且写 WARNING 日志 —— 不静默超发。
- `token` 估算：`len(text)`（P0-5，不引 tiktoken）。注意这是**字符数**口径：
  中文近似 1 字≈1 token，纯 ASCII/JSON 会被**高估**（约 4 字符≈1 token）。
  它只用于"谁大谁先被裁"的相对比较，真token以模型 usage 为准（按语言加权是已知债）。

## 可见性（"注入了什么"必须能查）

`ContextManifest` 同时记录三种状态，任何槽位都不会静默消失（评审 P1-1/P1-2/P1-3）：

- `entries`：真正注入的片段（来源 / 字符数 / token / 是否截断）
- `dropped`：被全局预算裁掉的**整槽**（含片段数、来源、token）
- `skipped`：没注成的槽位及原因（`provider_missing` / `empty` / `error:<异常类型>`）

与整体架构的对应：这份 manifest 就是"注入可见性"的数据源，随后挂到 SSE 的 `done`
载荷上（N2 已定好传输契约）。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger("story_engine.writer.context")

# ── 优先级档位（0 = 永不裁；数值越大越先被裁）─────────────
PINNED = 0          # 主线 / 本章节拍 / 风格块 —— 缺了就不对
CHAPTER_TAIL = 10   # 上一章结尾原文
SUMMARIES = 20      # 前情摘要（多片段）
CHARACTERS = 30     # 角色卡 / Lorebook 命中
METHODOLOGY = 60    # 技法条款（后续阶段）
RETRIEVAL = 90      # 检索命中：预算不够时最先被砍

# ── 数据结构 ─────────────────────────────────────────────


@dataclass(frozen=True)
class Slot:
    """一个注入槽位。

    - `slot_id`: 槽位标识（进 manifest，便于作者与代码对齐）
    - `priority`: `PINNED`(0) = 永不裁剪；越大越先被预算裁掉
    - `provider`: provider 注册表里的名字（返回 `list[ContextPiece]`）
    - `renderer`: renderer 注册表里的名字（把片段拼成文本）
    - `max_tokens`: 槽位级预算；超出则按片段粒度截断并标记 `truncated`
    """

    slot_id: str
    priority: int
    provider: str
    renderer: str = "plain"
    max_tokens: Optional[int] = None


@dataclass
class ContextPiece:
    """provider 返回的一段内容（`source` 用于 manifest 溯源，如 `summary:ch_0001`）。"""

    text: str
    source: str


@dataclass
class ManifestEntry:
    """"这一段是从哪来的、有多大"。"""

    slot_id: str
    source: str
    chars: int
    tokens: int
    priority: int
    truncated: bool = False


@dataclass
class DroppedSlot:
    """被全局预算裁掉的整槽（评审 P1-1：多片段槽位要能看出"裁掉了几条、哪些来源"）。"""

    slot_id: str
    pieces: int
    sources: List[str]
    tokens: int


@dataclass
class SkippedSlot:
    """没注成的槽位及原因（`provider_missing` / `empty` / `error:<异常类型>`）。"""

    slot_id: str
    reason: str


@dataclass
class ContextManifest:
    """注入清单：entries 与真正拼进 prompt 的片段一一对应。"""

    entries: List[ManifestEntry] = field(default_factory=list)
    dropped: List[DroppedSlot] = field(default_factory=list)
    skipped: List[SkippedSlot] = field(default_factory=list)
    total_tokens: int = 0
    budget_tokens: Optional[int] = None
    token_estimate: bool = True
    over_budget: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """可 JSON 序列化（要挂到 SSE done 载荷上）。"""
        return {
            "entries": [asdict(e) for e in self.entries],
            "dropped": [asdict(d) for d in self.dropped],
            "skipped": [asdict(s) for s in self.skipped],
            "total_tokens": self.total_tokens,
            "budget_tokens": self.budget_tokens,
            "token_estimate": self.token_estimate,
            "over_budget": self.over_budget,
        }


@dataclass
class AssembledContext:
    text: str
    manifest: ContextManifest


# ── 估算与渲染 ───────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """中文启发式 token 估算（P0-5）：按字符数计。

    仅用于**相对**比较（谁大谁先被裁）与预算守门；中文近似 1 字≈1 token，
    纯 ASCII/JSON 会被高估（约 4 字符≈1 token）—— 按语言加权是已知债（N4b/N7 再处理）。
    """
    return len(text)


def _render_plain(pieces: Sequence[ContextPiece]) -> str:
    return "\n".join(p.text for p in pieces if p.text)


def _render_bullets(pieces: Sequence[ContextPiece]) -> str:
    return "\n".join(f"- {p.text}" for p in pieces if p.text)


RENDERERS: Dict[str, Callable[[Sequence[ContextPiece]], str]] = {
    "plain": _render_plain,
    "bullets": _render_bullets,
}

Provider = Callable[[Mapping[str, Any]], List[ContextPiece]]


# ── 装配器 ───────────────────────────────────────────────

class ContextBuilder:
    """按槽位装配上下文并产出注入清单。"""

    def __init__(
        self,
        slots: Sequence[Slot],
        providers: Mapping[str, Provider] | None = None,
        budget_tokens: Optional[int] = None,
        renderers: Mapping[str, Callable[[Sequence[ContextPiece]], str]] | None = None,
    ) -> None:
        self.slots = list(slots)
        seen: set[str] = set()
        for slot in self.slots:
            if slot.slot_id in seen:
                raise ValueError(f"重复的 slot_id: {slot.slot_id!r}（槽位标识必须唯一）")
            seen.add(slot.slot_id)
        self.providers: Dict[str, Provider] = dict(providers or {})
        self.renderers = {**RENDERERS, **(renderers or {})}
        self.budget_tokens = budget_tokens

    # -- 单槽位求值 --------------------------------------------------
    def _collect(
        self, slot: Slot, inputs: Mapping[str, Any], skipped: List[SkippedSlot]
    ) -> List[ContextPiece]:
        provider = self.providers.get(slot.provider)
        if provider is None:
            skipped.append(SkippedSlot(slot.slot_id, "provider_missing"))
            return []
        try:
            raw = provider(inputs)
        except Exception as e:  # noqa: BLE001 —— 单个 provider 崩了不能带崩整次装配（评审 P1-3）
            logger.warning("槽位 %s 的 provider 抛异常，已跳过：%s", slot.slot_id, e)
            skipped.append(SkippedSlot(slot.slot_id, f"error:{type(e).__name__}"))
            return []

        if raw is None:
            skipped.append(SkippedSlot(slot.slot_id, "empty"))
            return []
        if not isinstance(raw, (list, tuple)):
            # provider 契约是 list[ContextPiece]；返回别的类型要记账而不是崩（评审 P2）
            skipped.append(SkippedSlot(slot.slot_id, f"error:provider_returned_{type(raw).__name__}"))
            return []

        pieces = [p for p in raw if isinstance(p, ContextPiece) and p.text]
        if len(pieces) != len(raw):
            skipped.append(SkippedSlot(slot.slot_id, "error:invalid_pieces"))
        if not pieces:
            skipped.append(SkippedSlot(slot.slot_id, "empty"))
        return pieces

    def _render(self, slot: Slot, pieces: Sequence[ContextPiece]) -> str:
        renderer = self.renderers.get(slot.renderer)
        if renderer is None:
            logger.warning("槽位 %s 的 renderer=%r 未注册，退回 plain", slot.slot_id, slot.renderer)
            renderer = _render_plain
        return renderer(pieces)

    def _apply_slot_budget(
        self, slot: Slot, pieces: List[ContextPiece]
    ) -> tuple[List[ContextPiece], set[int]]:
        """槽位级预算：按片段粒度截断，返回 (片段, 被截断的下标集合)。

        判定用的是**渲染后文本**的 token（与全局预算、manifest 记账同一口径）——
        否则 renderer 加的分隔符/前缀（如 bullets 的 "- "）会让"实际注入量"超出槽位预算
        （这正是评审 P0-1 在同一处暴露过的口径问题）。
        """
        if slot.max_tokens is None:
            return pieces, set()

        kept: List[ContextPiece] = []
        truncated: set[int] = set()
        for i, piece in enumerate(pieces):
            if estimate_tokens(self._render(slot, kept + [piece])) <= slot.max_tokens:
                kept.append(piece)
                continue
            remaining = slot.max_tokens - estimate_tokens(self._render(slot, kept))
            if remaining > 0:
                text = piece.text[:remaining]
                while text and estimate_tokens(
                    self._render(slot, kept + [ContextPiece(text=text, source=piece.source)])
                ) > slot.max_tokens:
                    text = text[:-1]
                if text:
                    kept.append(ContextPiece(text=text, source=piece.source))
                    truncated.add(len(kept) - 1)
            truncated.add(i)  # 即使裁到 0 也要留痕：这一段没完整进去
            break
        return kept, truncated

    def build(self, inputs: Mapping[str, Any] | None = None) -> AssembledContext:
        """装配上下文（纯函数：同输入同输出）。

        `inputs` 会被浅拷贝后传给 provider —— provider 往里面写脏数据不能影响调用方，
        否则"同输入同输出"的承诺就破了（评审 P2）。
        """
        safe_inputs: Dict[str, Any] = dict(inputs or {})

        # 1) 逐槽位取内容（保持声明顺序 → 结果确定）
        skipped: List[SkippedSlot] = []
        staged: List[tuple[Slot, List[ContextPiece], set[int], str, int]] = []
        for slot in self.slots:
            pieces = self._collect(slot, safe_inputs, skipped)
            if not pieces:
                continue
            pieces, truncated_idx = self._apply_slot_budget(slot, pieces)
            if not pieces:
                skipped.append(SkippedSlot(slot.slot_id, "over_slot_budget"))
                continue
            rendered = self._render(slot, pieces)
            staged.append((slot, pieces, truncated_idx, rendered, estimate_tokens(rendered)))

        # 2) 全局预算裁剪：从"最大 priority"往下裁；PINNED 永不裁
        dropped: List[DroppedSlot] = []
        if self.budget_tokens is not None:
            total = sum(t for *_rest, t in staged)
            # 裁剪顺序：priority 降序；同 priority 时**后声明**的先裁（结果确定）
            for idx in sorted(range(len(staged)), key=lambda i: (-staged[i][0].priority, -i)):
                slot, pieces, _trunc, _text, tokens = staged[idx]
                if total <= self.budget_tokens:
                    break
                if slot.priority <= PINNED:
                    continue
                dropped.append(
                    DroppedSlot(
                        slot_id=slot.slot_id,
                        pieces=len(pieces),
                        sources=[p.source for p in pieces],
                        tokens=tokens,
                    )
                )
                total -= tokens

        dropped_set = {d.slot_id for d in dropped}

        # 3) 拼文本 + 生成清单（一一对应；token 口径与实际注入一致）
        blocks: List[str] = []
        entries: List[ManifestEntry] = []
        total_tokens = 0
        for slot, pieces, truncated_idx, rendered, tokens in staged:
            if slot.slot_id in dropped_set or not rendered:
                continue
            blocks.append(rendered)
            total_tokens += tokens
            for i, piece in enumerate(pieces):
                entries.append(
                    ManifestEntry(
                        slot_id=slot.slot_id,
                        source=piece.source,
                        chars=len(piece.text),
                        tokens=estimate_tokens(piece.text),
                        priority=slot.priority,
                        truncated=i in truncated_idx,
                    )
                )

        text = "\n\n".join(b for b in blocks if b)
        over_budget = self.budget_tokens is not None and total_tokens > self.budget_tokens
        if over_budget:
            # pinned 允许超预算（架构要求永不砍风格块与节拍），但绝不能静默（评审 P1-5）
            logger.warning(
                "装配超出全局预算：实际 %s > 预算 %s（PINNED 槽位保留导致，已明示 over_budget）",
                total_tokens,
                self.budget_tokens,
            )

        manifest = ContextManifest(
            entries=entries,
            dropped=dropped,
            skipped=skipped,
            total_tokens=total_tokens,
            budget_tokens=self.budget_tokens,
            over_budget=over_budget,
        )
        return AssembledContext(text=text, manifest=manifest)
