"""世界观素材库（N8）—— 设定集的「另存为素材 / 从素材导入」来源。

**语义边界（用户定的方案 A：纯每本独立）**：素材库只是**复制来源**，不是共享引用。
导入 = 复制一份进当前小说，之后改素材不影响已经导入的书，反之亦然。

位置：`data/library/lore/<slug>.json`（角色卡的素材在 `data/library/characters/`）。
这个目录**不是任何小说的运行时依赖** —— 删掉它，所有书照常工作。

## 文件名不是身份（N8 评审 P1-1 的处置）

库文件用 `_slug(名字).json` 落盘，而 `_slug` 是**有损**的：`"A B"`、`"A_B"`、`"a/b"` 都变成
`A_B`。于是「两个不同名字 → 同一个文件」是可能的；若无条件 `write_text`，就会把一个已存在的
素材**静默覆盖**（实测：两次都返回成功，先导出的那个无声消失）。

本模块的规则：

- **身份以文件里内嵌的 `name` 为准**，文件名只负责寻址；
- `load_from_library(name)` 会**校验内嵌名与请求名一致**，不一致视为「没有这个素材」——
  否则 `"A B"` 会读到身份为 `"A_B"` 的那份，调用方拿到的东西与要求的不是同一个；
- 导出前比对目标文件：**同名同身份 = 幂等刷新**（允许，重复另存不该报错），
  **不同身份撞同一文件名 = 显式失败**（除非显式 `overwrite=True`）；
- `list_library()` 返回**内嵌名**而不是 `stem`，否则 `names` 与 `books[].name` 会不自洽。

返回码用 `Literal` 而不是 `bool`：路由要给出**诚实**的失败原因（「源不存在」与「目标已存在」
是两回事，混成一个 False 会让界面提示撒谎 —— N8 评审 P1-2）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Literal, Optional

from story_engine.core.config import data_dir
from story_engine.core.models import LoreBook

logger = logging.getLogger("story_engine.lore.library")

LIBRARY_DIR = data_dir() / "library" / "lore"

#: 导出结果：成功 / 源设定集不存在 / 文件名被**别的身份**占用 / 写盘失败
ExportResult = Literal["ok", "source_missing", "name_taken", "write_failed"]

#: 导入结果：成功 / 素材库里没有这个素材 / 本书已有同名设定集（且未勾选覆盖）
ImportResult = Literal["ok", "source_missing", "target_exists"]


def _ensure_dir() -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)


def _item_path(name: str) -> Path:
    from story_engine.tools.novel_storage import _safe_json_path

    return _safe_json_path(LIBRARY_DIR, name)


def _load_path(path: Path) -> Optional[LoreBook]:
    if not path.is_file():
        return None
    try:
        return LoreBook(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        logger.warning("世界观素材读取失败 %s: %s", path.name, e)
        return None


def list_library() -> List[str]:
    """列出素材库里的设定集名（**用文件内嵌的 name**，目录不存在时返回空）。"""
    if not LIBRARY_DIR.exists():
        return []
    names: List[str] = []
    for path in sorted(LIBRARY_DIR.glob("*.json")):
        book = _load_path(path)
        names.append(book.name if book is not None else path.stem)
    return sorted(names)


def load_from_library(name: str) -> Optional[LoreBook]:
    """按名字取素材；**内嵌名与请求名不一致时视为不存在**（文件名不是身份）。"""
    book = _load_path(_item_path(name))
    if book is None or book.name != name:
        return None
    return book


def export_to_library(
    novel_id: str, name: str, new_name: str = "", overwrite: bool = False
) -> ExportResult:
    """把某本书里的一个设定集**复制**成素材。

    目标文件已被**别的身份**占用时返回 `"name_taken"` —— 不同名字映射到同一文件名
    （`_slug` 有损）时不允许静默覆盖；同名同身份则视为幂等刷新，允许。
    """
    from story_engine.lore.lorebook import load_lorebook

    book = load_lorebook(novel_id, name)
    if book is None:
        return "source_missing"
    if new_name:
        book = book.model_copy(update={"name": new_name})

    target = _item_path(book.name)
    if target.is_file() and not overwrite:
        existing = _load_path(target)
        if existing is None or existing.name != book.name:
            return "name_taken"

    _ensure_dir()
    try:
        target.write_text(
            json.dumps(book.model_dump(exclude_none=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("世界观素材写盘失败 %s: %s", book.name, e)
        return "write_failed"
    return "ok"


def import_from_library(
    novel_id: str,
    name: str,
    new_name: str = "",
    overwrite: bool = False,
) -> ImportResult:
    """从素材库**复制**进某本书（源缺失与目标冲突是**两个不同**的失败原因）。"""
    from story_engine.lore.lorebook import save_lorebook

    book = load_from_library(name)
    if book is None:
        return "source_missing"
    if new_name:
        book = book.model_copy(update={"name": new_name})
    if save_lorebook(novel_id, book, overwrite=overwrite):
        return "ok"
    return "target_exists"
