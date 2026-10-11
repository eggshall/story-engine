"""注入清单落盘（N6）—— 让"当时注入了什么"可长期回看。

N4b 的评审待办：`context_manifest` 原来只随 SSE `done` 载荷下发一次，刷新页面就没了。
作者事后想核对"这一章到底注入了哪些设定"时无从查起，架构里"注入可见性"就只兑现了一半。

落点：`<小说目录>/manifests/ch_0001.json`（经 `_novel_dir`，支持自定义路径小说）。
写入是**旁路**的：manifest 写失败绝不能影响章节生成（生成成功了就是成功了）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from story_engine.tools import novel_storage

logger = logging.getLogger("story_engine.writer.manifest")

MANIFEST_DIRNAME = "manifests"


def manifest_path(novel_id: str, chapter_number: int) -> Path:
    """注入清单文件路径（命名与 beats 一致：ch_XXXX.json）。"""
    return novel_storage._novel_dir(novel_id) / MANIFEST_DIRNAME / f"ch_{chapter_number:04d}.json"


def save_manifest(novel_id: str, chapter_number: int, manifest: Dict[str, Any]) -> Optional[Path]:
    """把注入清单写盘；失败只告警并返回 None（不影响生成流程）。

    写入走 `novel_storage._atomic_write`（同一套原子写），并且是**模块属性**调用而不是
    `from ... import _atomic_write`：后者会把函数对象绑死在本模块命名空间，测试里 patch
    `novel_storage._atomic_write` 就失效了（写失败路径根本没被测到）。
    """
    try:
        path = manifest_path(novel_id, chapter_number)
        path.parent.mkdir(parents=True, exist_ok=True)
        novel_storage._atomic_write(path, json.dumps(manifest, ensure_ascii=False, indent=2))
        return path
    except Exception as e:  # noqa: BLE001 —— 旁路数据，绝不带崩主流程
        logger.warning("注入清单写盘失败（不影响本章生成）: %s", e)
        return None


def load_manifest(novel_id: str, chapter_number: int) -> Optional[Dict[str, Any]]:
    """读回注入清单；没有就返回 None（作者可能还没用 v2 生成过这一章）。"""
    path = manifest_path(novel_id, chapter_number)
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("注入清单读取失败: %s", e)
        return None
    return data if isinstance(data, dict) else None
