"""素材库（N8）—— 角色卡/设定集的「另存为素材 / 从素材导入」来源。

**语义边界（用户定的方案 A：纯每本独立）**：素材库只是**复制来源**，不是共享引用。
导入 = 复制一份进当前小说，之后改素材不影响已经导入的书，反之亦然。

位置：`data/library/characters/<slug>.json`（世界观的素材在 `data/library/lore/`）。
这个目录不是任何小说的运行时依赖 —— 删掉它，所有书照常工作。

## 文件名不是身份（与 `lore/library.py` 同源，N8 评审 P1-1）

库文件用 `_slug(名字).json` 落盘，而 `_slug` 是**有损**的：`"A B"`、`"A_B"`、`"a/b"` 都会变成
`A_B`。于是「不同名字 → 同一个文件」是可能的；无条件 `write_text` 会把已存在的素材**静默覆盖**。

规则（两套素材库保持一致）：

- **身份以文件内嵌的 `name` 为准**，文件名只负责寻址；
- `load_from_library` 校验内嵌名与请求名一致，不一致视为「没有这个素材」；
- 导出：**同名同身份 = 幂等刷新**（允许），**不同身份撞同一文件名 = 显式失败**
  （除非显式 `overwrite=True`）；
- `list_library()` 返回内嵌名而不是 `stem`。

返回码用 `Literal` 而不是 `bool`：「源不存在」与「目标已存在」是两个不同的失败原因，
路由要靠它给出诚实提示（N8 评审 P1-2）。

## 与小说内镜像目录的策略差异（有意）

小说目录下的镜像（`characters/`/`lore/`/`threads/`）对撞名名字**自动加短 hash** 区分
（`novel_storage._mirror_file_names`），因为它们由 `_write_files` 整目录重建、不需要与人协商。
**素材库故意保持裸 slug + 显式失败**：库文件是**真源**、是作者可复用的资产，静默改名比报错更糟
（「我另存的名字怎么变了」），所以撞名一律返回 `name_taken` 让调用方自己决定。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Literal, Optional

from story_engine.core.config import data_dir
from story_engine.core.models import CharacterCard

logger = logging.getLogger("story_engine.characters.library")

LIBRARY_DIR = data_dir() / "library" / "characters"

#: 导出结果：成功 / 源卡不存在 / 文件名被**别的身份**占用 / 写盘失败
ExportResult = Literal["ok", "source_missing", "name_taken", "write_failed"]

#: 导入结果：成功 / 素材库里没有这张卡 / 本书已有同名卡（且未勾选覆盖）
ImportResult = Literal["ok", "source_missing", "target_exists"]


def _ensure_dir() -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)


def _item_path(name: str) -> Path:
    from story_engine.tools.novel_storage import _safe_json_path

    return _safe_json_path(LIBRARY_DIR, name)


def _load_path(path: Path) -> Optional[CharacterCard]:
    if not path.is_file():
        return None
    try:
        return CharacterCard(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        logger.warning("素材读取失败 %s: %s", path.name, e)
        return None


def list_library() -> List[str]:
    """列出素材库里的角色卡名（**用文件内嵌的 name**，目录不存在时返回空）。"""
    if not LIBRARY_DIR.exists():
        return []
    names: List[str] = []
    for path in sorted(LIBRARY_DIR.glob("*.json")):
        card = _load_path(path)
        names.append(card.name if card is not None else path.stem)
    return sorted(names)


def load_from_library(name: str) -> Optional[CharacterCard]:
    """按名字取素材；**内嵌名与请求名不一致时视为不存在**（文件名不是身份）。"""
    card = _load_path(_item_path(name))
    if card is None or card.name != name:
        return None
    return card


def export_to_library(
    novel_id: str, name: str, new_name: str = "", overwrite: bool = False
) -> ExportResult:
    """把某本书里的一张卡**复制**成素材。

    目标文件已被**别的身份**占用时返回 `"name_taken"` —— 不同名字映射到同一文件名
    （`_slug` 有损）时不允许静默覆盖；同名同身份则视为幂等刷新，允许。
    """
    from story_engine.characters.manager import load_card

    card = load_card(novel_id, name)
    if card is None:
        return "source_missing"
    if new_name:
        card = card.model_copy(update={"name": new_name})

    target = _item_path(card.name)
    if target.is_file() and not overwrite:
        existing = _load_path(target)
        if existing is None or existing.name != card.name:
            return "name_taken"

    _ensure_dir()
    try:
        target.write_text(
            json.dumps(card.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        logger.warning("素材写盘失败 %s: %s", card.name, e)
        return "write_failed"
    return "ok"


def import_from_library(
    novel_id: str,
    name: str,
    new_name: str = "",
    overwrite: bool = False,
) -> ImportResult:
    """从素材库**复制**进某本书（源缺失与目标冲突是**两个不同**的失败原因）。"""
    from story_engine.characters.manager import save_card

    card = load_from_library(name)
    if card is None:
        return "source_missing"
    if new_name:
        card = card.model_copy(update={"name": new_name})
    if save_card(novel_id, card, overwrite=overwrite):
        return "ok"
    return "target_exists"
