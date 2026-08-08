"""文件工具 — 读写/格式检测"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Union


def read_text(path: Path) -> Optional[str]:
    """安全读取文本文件（UTF-8）"""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return None


def write_text(path: Path, content: str) -> bool:
    """安全写入文本文件"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def resolve_within(root: Path, user_path: Union[str, Path]) -> Path:
    """将用户提供的路径解析为 root 之下的绝对路径，防目录穿越。

    拒绝：空值、绝对路径、Windows 盘符路径、含 `..` 的越界路径。
    解析（resolve）后再次确认仍在 root 之内，否则抛 ValueError。
    """
    raw = str(user_path)
    if not raw.strip():
        raise ValueError("路径不能为空")
    if _WINDOWS_DRIVE_RE.match(raw):
        raise ValueError(f"非法路径: {raw!r}")
    p = Path(raw)
    if p.is_absolute():
        raise ValueError(f"不允许绝对路径: {raw!r}")
    root_resolved = root.resolve()
    resolved = (root / p).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"路径越界: {raw!r}")
    return resolved


def list_text_files(dir_path: Path, ext: str = ".txt") -> List[Path]:
    """列出目录下所有指定后缀的文件"""
    if not dir_path.exists():
        return []
    return sorted(dir_path.glob(f"*{ext}"))


def detect_encoding(path: Path) -> str:
    """简单检测文件编码"""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        try:
            raw.decode("gbk")
            return "gbk"
        except UnicodeDecodeError:
            return "latin-1"
