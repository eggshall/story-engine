"""文件工具 — 读写/格式检测"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional


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
