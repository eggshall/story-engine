"""素材库（N8）—— 角色卡/设定集的「另存为素材 / 从素材导入」来源。

**语义边界（用户定的方案 A：纯每本独立）**：素材库只是**复制来源**，不是共享引用。
导入 = 复制一份进当前小说，之后改素材不影响已经导入的书，反之亦然。

位置：`data/library/characters/<名字>.json`（世界观的素材在 `data/library/lore/`）。
这个目录不是任何小说的运行时依赖 —— 删掉它，所有书照常工作。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from story_engine.core.config import data_dir
from story_engine.core.models import CharacterCard

logger = logging.getLogger("story_engine.characters.library")

LIBRARY_DIR = data_dir() / "library" / "characters"


def _ensure_dir() -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)


def _item_path(name: str) -> Path:
    from story_engine.tools.novel_storage import _safe_json_path

    return _safe_json_path(LIBRARY_DIR, name)


def list_library() -> List[str]:
    """列出素材库里的角色卡名（目录不存在时返回空，不报错）。"""
    if not LIBRARY_DIR.exists():
        return []
    return sorted(p.stem for p in LIBRARY_DIR.glob("*.json"))


def load_from_library(name: str) -> Optional[CharacterCard]:
    path = _item_path(name)
    if not path.is_file():
        return None
    try:
        return CharacterCard(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        logger.warning("素材读取失败 %s: %s", name, e)
        return None


def export_to_library(novel_id: str, name: str, new_name: str = "") -> bool:
    """把某本书里的一张卡**复制**成素材（卡不存在 → False）。"""
    from story_engine.characters.manager import load_card

    card = load_card(novel_id, name)
    if card is None:
        return False
    if new_name:
        card = card.model_copy(update={"name": new_name})
    _ensure_dir()
    try:
        _item_path(card.name).write_text(
            json.dumps(card.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        logger.warning("素材写盘失败 %s: %s", card.name, e)
        return False
    return True


def import_from_library(
    novel_id: str,
    name: str,
    new_name: str = "",
    overwrite: bool = False,
) -> bool:
    """从素材库**复制**进某本书（素材不存在 / 同名已存在且不覆盖 → False）。"""
    from story_engine.characters.manager import save_card

    card = load_from_library(name)
    if card is None:
        return False
    if new_name:
        card = card.model_copy(update={"name": new_name})
    return save_card(novel_id, card, overwrite=overwrite)
