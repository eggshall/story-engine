"""P6 数据管线 — Gutenberg 全文下载器。

从 Gutenberg 下载指定 ebook 的 UTF-8 纯文本全文，存入 raw/。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import httpx

from .config import RAW_DIR, ensure_dirs

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StoryEngine-P6/0.1"
TIMEOUT = 60.0

# 新版 Gutenberg 文本缓存 URL 格式（UTF-8）
TEXT_URL = "https://www.gutenberg.org/cache/epub/{eid}/pg{eid}.txt"

# 有效正文的最短长度（低于此值视为下载不完整，需重下）
_MIN_CHARS = 1000


def _is_valid_gutenberg_text(text: str) -> bool:
    """校验下载内容质量：够长 + 含可识别正文（START 标记或中文字符）。"""
    if len(text) < _MIN_CHARS:
        return False
    head = text[:500]
    if "START OF THE PROJECT GUTENBERG EBOOK" in head:
        return True
    # 无样板标记时要求含中文字符（本项目聚焦中文公版书）
    return any("\u4e00" <= ch <= "\u9fff" for ch in text[:2000])


def download_ebook(eid: str, raw_dir: Optional[Path] = None) -> Path:
    """下载 ebook 全文到 raw/pg{eid}.txt，返回文件路径。

    已下载文件按内容校验（长度 + 中文/样板标记）判断是否完整，
    不完整时重新下载；写盘用临时文件 + os.replace 原子落盘。

    Raises:
        httpx.HTTPError: 下载失败
    """
    ensure_dirs()
    target = (raw_dir or RAW_DIR) / f"pg{eid}.txt"
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            existing = ""
        if _is_valid_gutenberg_text(existing):
            return target  # 已下载且完整

    headers = {"User-Agent": USER_AGENT}
    url = TEXT_URL.format(eid=eid)
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        text = resp.text  # Gutenberg 缓存文件为 UTF-8

    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)
    return target
