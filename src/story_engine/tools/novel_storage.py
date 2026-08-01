"""小说存储引擎 — 每部小说独立目录，支持自定义路径

目录结构:
  data/novels/{novel_id}/        ← 默认保存（novel_id = title 清理后）
  {自定义路径}/{小说名}/         ← 自定义保存
  data/novels/.index.json        ← 索引文件 {novel_id: 真实路径}
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from story_engine.core.config import data_dir
from story_engine.core.models import Novel
from story_engine.tools.memory_models import SoulMemory, StyleProfile, UserProfile

logger = logging.getLogger("story_engine.storage")


# ── 路径常量 ──────────────────────────────────

NOVELS_ROOT = data_dir() / "novels"


def _index_path() -> Path:
    return NOVELS_ROOT / ".index.json"


def _slug(text: str) -> str:
    """将标题转为安全的目录名"""
    s = text.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    s = re.sub(r'[<>:"|?*]', "", s)
    return s or "untitled"


def _hash_id(path: str) -> str:
    """为自定义路径生成短 ID"""
    return "novel_" + hashlib.md5(path.encode()).hexdigest()[:8]


def convert_windows_path(path: str) -> str:
    """Windows C:\\path → /mnt/c/path"""
    m = re.match(r'^([A-Za-z]):[\\/](.*)', path)
    if m:
        return f'/mnt/{m.group(1).lower()}/{m.group(2).replace(chr(92), "/")}'
    return path


# ── 索引管理 ──────────────────────────────────


def _read_index() -> Dict[str, str]:
    ip = _index_path()
    if not ip.exists():
        return {}
    try:
        return json.loads(ip.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("索引损坏: %s", e)
        return {}


def _write_index(idx: Dict[str, str]) -> None:
    ip = _index_path()
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")


def _index_has(novel_id: str) -> bool:
    return novel_id in _read_index()


def _index_get(novel_id: str) -> Optional[str]:
    return _read_index().get(novel_id)


def _index_register(novel_id: str, real_path: str) -> None:
    idx = _read_index()
    idx[novel_id] = real_path
    _write_index(idx)
    logger.info("索引: %s → %s", novel_id, real_path)


def _index_unregister(novel_id: str) -> None:
    idx = _read_index()
    if novel_id in idx:
        del idx[novel_id]
        _write_index(idx)
        logger.info("索引移除: %s", novel_id)


# ── 路径解析 ──────────────────────────────────


def _novel_dir(novel_id: str) -> Path:
    """返回小说的实际存储目录"""
    # 先查索引
    real = _index_get(novel_id)
    if real:
        return Path(real)
    # 否则在默认目录
    return NOVELS_ROOT / novel_id


# ── 小说 CRUD ─────────────────────────────────


def list_novels() -> List[Dict[str, Any]]:
    """列出所有小说"""
    novels: List[Dict[str, Any]] = []
    seen: set[str] = set()

    # 1. 扫描默认目录
    if NOVELS_ROOT.exists():
        for d in sorted(NOVELS_ROOT.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                meta = d / "novel.json"
                if meta.exists():
                    _add_novel(novels, seen, d.name, meta)

    # 2. 扫描索引中的自定义路径
    for nid, path in _read_index().items():
        meta = Path(path) / "novel.json"
        if meta.exists() and nid not in seen:
            _add_novel(novels, seen, nid, meta)
        elif not meta.exists():
            # 索引指向的路径已不存在，清理
            logger.info("清理无效索引: %s → %s", nid, path)

    return sorted(novels, key=lambda x: x.get("updated", ""), reverse=True)


def _add_novel(novels: list, seen: set, nid: str, meta_file: Path) -> None:
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        seen.add(nid)
        novels.append({
            "id": nid,
            "title": data.get("title", nid),
            "author": data.get("author", ""),
            "genre": data.get("genre", ""),
            "word_count": data.get("word_count", 0),
            "chapter_count": len(data.get("chapters", [])),
            "created": data.get("created", ""),
            "updated": data.get("updated", ""),
            "save_path": str(meta_file.parent),
        })
    except Exception:
        pass


def load_novel(novel_id: str) -> Optional[Novel]:
    """加载小说"""
    nd = _novel_dir(novel_id)
    meta = nd / "novel.json"
    if not meta.exists():
        logger.warning("小说不存在: %s (%s)", novel_id, nd)
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        # 从章节目录加载
        ch_dir = nd / "chapters"
        if ch_dir.exists():
            chs = []
            for f in sorted(ch_dir.glob("ch_*.json")):
                try:
                    chs.append(json.loads(f.read_text(encoding="utf-8")))
                except Exception:
                    continue
            if chs:
                data["chapters"] = chs
        # 从角色目录加载
        ch_dir2 = nd / "characters"
        if ch_dir2.exists():
            chars = {}
            for f in ch_dir2.glob("*.json"):
                try:
                    c = json.loads(f.read_text(encoding="utf-8"))
                    chars[c.get("name", f.stem)] = c
                except Exception:
                    continue
            if chars:
                data["characters"] = chars
        return Novel(**data)
    except Exception as e:
        logger.error("加载失败 %s: %s", novel_id, e)
        return None


def save_novel(novel: Novel, novel_id: str = "") -> str:
    """保存小说，返回 novel_id

    规则:
      - novel_id 为空或相对名称 → 保存到 data/novels/{slug}/
      - novel_id 为绝对路径(/mnt/...) → 保存到 {novel_id}/{小说名}/，注册索引
      - novel_id 已注册索引 → 从索引取真实目录（自定义路径小说）
    """
    novel.updated = datetime.now().isoformat()

    # 先查索引：如果 novel_id 已注册（自定义路径），从索引取真实目录
    indexed_path = _index_get(novel_id) if novel_id else None
    if indexed_path:
        real_dir = Path(indexed_path)
        real_dir.mkdir(parents=True, exist_ok=True)
        nid = novel_id
    else:
        custom_path = convert_windows_path(novel_id) if novel_id and novel_id.startswith("/") else ""
        title_slug = _slug(novel.title)

        if custom_path:
            # 保存到自定义路径: {路径}/{小说名}/
            real_dir = Path(custom_path) / title_slug
            real_dir.mkdir(parents=True, exist_ok=True)
            # ID = hash of real path
            nid = _hash_id(str(real_dir))
            _index_register(nid, str(real_dir))
        else:
            nid = novel_id or title_slug
            real_dir = NOVELS_ROOT / nid
            real_dir.mkdir(parents=True, exist_ok=True)

    # 创建子目录
    for sub in ("chapters", "lore", "characters", "research", "uploads",
                "style_profiles", "exports"):
        (real_dir / sub).mkdir(exist_ok=True)

    # 写数据文件
    data = novel.model_dump(exclude_none=True)
    _write_files(real_dir, data)

    return nid


def _write_files(base: Path, data: dict) -> None:
    """写入所有数据文件"""
    # 章节
    ch_dir = base / "chapters"
    for f in ch_dir.glob("*.json"):
        f.unlink()
    for ch in data.get("chapters", []):
        (ch_dir / f"ch_{ch['chapter_number']:04d}.json").write_text(
            json.dumps(ch, ensure_ascii=False, indent=2), encoding="utf-8")

    # 角色
    ch_dir2 = base / "characters"
    for f in ch_dir2.glob("*.json"):
        f.unlink()
    for cname, cdata in data.get("characters", {}).items():
        (ch_dir2 / f"{cname}.json").write_text(
            json.dumps(cdata, ensure_ascii=False, indent=2), encoding="utf-8")

    # lore
    for lbname, lbdata in data.get("lorebooks", {}).items():
        (base / "lore" / f"{lbname}.json").write_text(
            json.dumps(lbdata, ensure_ascii=False, indent=2), encoding="utf-8")

    # 主文件
    (base / "novel.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_novel(novel_id: str) -> bool:
    """删除小说（目录 + 索引）"""
    nd = _novel_dir(novel_id)
    had_dir = nd.exists()
    had_index = _index_has(novel_id)

    if not had_dir and not had_index:
        logger.warning("小说不存在: %s", novel_id)
        return False

    if had_dir:
        shutil.rmtree(nd)
        logger.info("已删除目录: %s", nd)

    _index_unregister(novel_id)

    # 如果默认目录下也有，也删
    default_dir = NOVELS_ROOT / novel_id
    if default_dir.exists() and default_dir != nd:
        shutil.rmtree(default_dir)
        logger.info("已删除默认目录: %s", default_dir)

    return True


# ── 灵魂记忆 ──────────────────────────────────


def load_soul_memory(novel_id: str) -> SoulMemory:
    f = _novel_dir(novel_id) / "soul_memory.json"
    if f.exists():
        try:
            return SoulMemory(**json.loads(f.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning("记忆加载失败 %s: %s", novel_id, e)
    return SoulMemory(novel_id=novel_id, novel_title="")


def save_soul_memory(mem: SoulMemory) -> None:
    mem.updated = datetime.now().isoformat()
    d = _novel_dir(mem.novel_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "soul_memory.json").write_text(
        json.dumps(mem.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


# ── 文风 ──────────────────────────────────────


def list_style_profiles(novel_id: str) -> List[Dict[str, Any]]:
    d = _novel_dir(novel_id) / "style_profiles"
    if not d.exists():
        return []
    result = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            result.append({
                "name": data.get("name", f.stem),
                "style_summary": data.get("style_summary", "")[:100],
                "created": data.get("created", ""),
            })
        except Exception:
            continue
    return result


def save_style_profile(profile: StyleProfile) -> None:
    nd = _novel_dir(profile.novel_id)
    nd.mkdir(parents=True, exist_ok=True)
    sd = nd / "style_profiles"
    sd.mkdir(exist_ok=True)
    (sd / f"{profile.name}.json").write_text(
        json.dumps(profile.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


# ── 用户画像 ──────────────────────────────────

USER_PROFILE_PATH = data_dir() / "user_profile.json"


def load_user_profile() -> UserProfile:
    if USER_PROFILE_PATH.exists():
        try:
            return UserProfile(**json.loads(USER_PROFILE_PATH.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning("用户画像加载失败: %s", e)
    return UserProfile()


def save_user_profile(profile: UserProfile) -> None:
    profile.updated = datetime.now().isoformat()
    USER_PROFILE_PATH.write_text(
        json.dumps(profile.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


# ── 世界地图 ──────────────────────────────────


def save_map_data(novel_id: str, image_path: str, markers: List[Dict]) -> None:
    """保存小说地图数据（图片路径 + 标记列表）"""
    nd = _novel_dir(novel_id)
    nd.mkdir(parents=True, exist_ok=True)
    map_file = nd / "world_map.json"
    data = {"image_path": image_path, "markers": markers}
    map_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_map_data(novel_id: str) -> Dict:
    """加载小说地图数据"""
    nd = _novel_dir(novel_id)
    map_file = nd / "world_map.json"
    if not map_file.exists():
        return {"image_path": "", "markers": []}
    try:
        return json.loads(map_file.read_text(encoding="utf-8"))
    except Exception:
        return {"image_path": "", "markers": []}
