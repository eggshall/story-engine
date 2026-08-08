"""P6 数据管线 — Gutenberg 全文下载器。

从 Gutenberg 下载指定 ebook 的 UTF-8 纯文本全文，存入 raw/。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import httpx

from .config import RAW_DIR, ensure_dirs

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StoryEngine-P6/0.1"
TIMEOUT = 60.0

# 新版 Gutenberg 文本缓存 URL 格式（UTF-8）
TEXT_URL = "https://www.gutenberg.org/cache/epub/{eid}/pg{eid}.txt"


def download_ebook(eid: str, raw_dir: Optional[Path] = None) -> Path:
    """下载 ebook 全文到 raw/pg{eid}.txt，返回文件路径。

    Raises:
        httpx.HTTPError: 下载失败
    """
    ensure_dirs()
    target = (raw_dir or RAW_DIR) / f"pg{eid}.txt"
    if target.exists() and target.stat().st_size > 1000:
        return target  # 已下载过

    headers = {"User-Agent": USER_AGENT}
    url = TEXT_URL.format(eid=eid)
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        text = resp.text  # Gutenberg 缓存文件为 UTF-8

    target.write_text(text, encoding="utf-8")
    return target


def download_many(eids, raw_dir: Optional[Path] = None) -> dict:
    """批量下载，返回 {eid: 成功与否}。单个失败不中断。"""
    results: dict[str, Any] = {}
    for eid in eids:
        try:
            p = download_ebook(str(eid), raw_dir)
            results[str(eid)] = p.stat().st_size
        except Exception as exc:  # noqa: BLE001 - 批量下载容忍单点失败
            results[str(eid)] = f"FAIL: {exc.__class__.__name__}"
    return results
