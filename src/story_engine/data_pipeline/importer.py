"""P6 数据管线 — 本地导入通道。

用户把自有文本（网络小说、电子书导出等）丢进 D:/文章数据/imports/，
本模块自动识别并清洗入库：
    - .txt     自动检测编码 (UTF-8 / GBK)
    - .epub    zip 解包提取正文 (HTML 剥离)
清洗后存入 corpus/imports/<作品名>.txt 并登记索引。
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cleaner import clean_text, to_paragraphs
from .config import CORPUS_DIR, IMPORTS_DIR, ensure_dirs
from .index import add_record

_BOM_UTF8 = b"\xef\xbb\xbf"


def _detect_and_decode(data: bytes) -> str:
    """尝试 UTF-8 -> GBK 解码。"""
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_epub_text(path: Path) -> str:
    """从 epub 提取正文纯文本（按文档顺序拼接 html 文本）。"""
    parts: List[str] = []
    with zipfile.ZipFile(path) as zf:
        # 取扩展名为 .xhtml/.html/.htm 的文件，按路径排序保证章节顺序
        html_files = sorted(
            n for n in zf.namelist()
            if n.lower().endswith((".xhtml", ".html", ".htm"))
            and not n.lower().startswith(("mimetype", "meta-inf"))
        )
        for name in html_files:
            data = zf.read(name)
            text = _detect_and_decode(data)
            # 剥离标签，保留段落
            text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", "\n", text)
            text = re.sub(r"&nbsp;?", " ", text)
            text = re.sub(r"&amp;", "&", text)
            text = re.sub(r"&lt;", "<", text)
            text = re.sub(r"&gt;", ">", text)
            text = re.sub(r"\n{2,}", "\n\n", text)
            parts.append(text.strip())
    return "\n\n".join(parts)


def import_file(path: Path, genre: str = "other", author: str = "") -> Dict[str, Any]:
    """导入单个文件，返回索引记录。"""
    ensure_dirs()
    suffix = path.suffix.lower()
    if suffix == ".epub":
        raw_text = _extract_epub_text(path)
    else:
        raw_text = _detect_and_decode(path.read_bytes())

    cleaned = clean_text(raw_text)
    paras = to_paragraphs(cleaned)
    if not paras:
        raise ValueError(f"清洗后为空: {path.name}")

    out_dir = CORPUS_DIR / "imports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{path.stem}.txt"
    out_path.write_text("\n\n".join(paras), encoding="utf-8")

    record = {
        "id": f"import:{path.stem}",
        "title": path.stem,
        "author": author or "",
        "translator": "",
        "source": "import",
        "gutenberg_id": "",
        "genre": genre,
        "file": str(out_path.relative_to(CORPUS_DIR.parent)),
        "chars": sum(len(p) for p in paras),
        "paragraphs": len(paras),
    }
    add_record(record)
    return record


def scan_imports(genre: str = "other") -> List[Dict[str, Any]]:
    """扫描 imports/ 目录，导入所有未入库文件。"""
    ensure_dirs()
    imported = []
    for f in sorted(IMPORTS_DIR.iterdir()):
        if f.is_dir() or f.name.startswith("."):
            continue
        if f.suffix.lower() not in (".txt", ".epub", ".md"):
            continue
        try:
            rec = import_file(f, genre=genre)
            imported.append(rec)
            f.rename(IMPORTS_DIR / "done" / f.name) if False else None
        except Exception as exc:  # noqa: BLE001
            print(f"  导入失败 {f.name}: {exc}")
    return imported
