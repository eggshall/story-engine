"""P6 数据管线 — Gutenberg 中文公版书目抓取。

数据源: https://www.gutenberg.org/browse/languages/zh （国内直连可达）
输出: meta/gutenberg_catalog.json  {gutenberg_id: 标题}
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Dict

import httpx

from .config import CATALOG_FILE, ensure_dirs

logger = logging.getLogger("story_engine.catalog")

BROWSE_URL = "https://www.gutenberg.org/browse/languages/zh"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StoryEngine-P6/0.1"
TIMEOUT = 30.0


def fetch_catalog() -> Dict[str, str]:
    """抓取 Gutenberg 中文书目，返回 {ebook_id: title}。"""
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
        resp = client.get(BROWSE_URL)
        resp.raise_for_status()
        html = resp.text

    items = re.findall(r'<a href="/ebooks/(\d+)"[^>]*>(.*?)</a>', html, re.S)
    catalog: Dict[str, str] = {}
    for bid, title in items:
        t = re.sub(r"<[^>]+>", "", title).strip()
        if bid not in catalog:
            catalog[bid] = t
    return catalog


def save_catalog(catalog: Dict[str, str]) -> None:
    """保存书目到 meta/gutenberg_catalog.json。"""
    ensure_dirs()
    tmp = CATALOG_FILE.with_name(CATALOG_FILE.name + ".tmp")
    tmp.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    import os
    os.replace(tmp, CATALOG_FILE)


def load_catalog() -> Dict[str, str]:
    """加载已保存的书目；损坏/不存在则抓取（L15.7）。"""
    if CATALOG_FILE.exists():
        try:
            data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            logger.warning("书目缓存内容非对象，重新抓取")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("书目缓存损坏（%s），重新抓取", e)
    catalog = fetch_catalog()
    save_catalog(catalog)
    return catalog


if __name__ == "__main__":
    t0 = time.time()
    cat = fetch_catalog()
    save_catalog(cat)
    print(f"Gutenberg 中文书目: {len(cat)} 本, 用时 {time.time()-t0:.1f}s")
    print(f"已保存: {CATALOG_FILE}")
