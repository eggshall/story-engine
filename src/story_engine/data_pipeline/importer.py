"""P6 数据管线 — 本地导入通道。

用户把自有文本（网络小说、电子书导出等）丢进 D:/文章数据/imports/：
    - 子目录  → 目录名即书名，目录下所有分卷合并为一本书
    - 散落文件 → 单文件成书（txt 自动识别 UTF-8/GBK；epub 解包提取）
清洗后存入 corpus/imports/<书名>.txt，源文件归档到 imports/done/。
"""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cleaner import clean_text, to_paragraphs
from .config import CORPUS_DIR, IMPORTS_DIR, ensure_dirs
from .index import add_record

_SUFFIXES = (".txt", ".epub", ".md")


def _clean_title(name: str) -> str:
    """清理书名: 去括号注释(章节范围)、去尾部符号。"""
    name = re.sub(r"[(（\[【].*?[)）\]】]", "", name).strip()
    name = re.sub(r"[._\-—\s]+$", "", name)
    return name or "未命名"


def _detect_and_decode(data: bytes) -> str:
    """尝试 UTF-8 -> GBK 解码。"""
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_epub_text(path: Path) -> str:
    """从 epub 提取正文纯文本（整本合并）。"""
    parts: List[str] = []
    with zipfile.ZipFile(path) as zf:
        html_files = sorted(
            n for n in zf.namelist()
            if n.lower().endswith((".xhtml", ".html", ".htm"))
            and not n.lower().startswith(("mimetype", "meta-inf"))
        )
        for name in html_files:
            parts.append(_html_to_text(_detect_and_decode(zf.read(name))))
    return "\n\n".join(parts)


def _html_to_text(text: str) -> str:
    """HTML → 纯文本。"""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def _parse_ncx_top_level(zf) -> List[Dict[str, str]]:
    """解析 toc.ncx 顶级 navPoint: [{label, src}]。"""
    import xml.etree.ElementTree as ET

    ncx = zf.read("toc.ncx").decode("utf-8", errors="replace")
    root = ET.fromstring(ncx)
    ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
    books = []
    for np in root.findall("./ncx:navMap/ncx:navPoint", ns):
        label = np.find("ncx:navLabel/ncx:text", ns)
        content = np.find("ncx:content", ns)
        if label is not None and content is not None:
            books.append({
                "label": (label.text or "").strip(),
                "src": content.get("src", ""),
            })
    return books


def extract_epub_books(path: Path) -> List[Dict[str, Any]]:
    """拆分合集 epub → [{title, text}]。非合集(无 ncx 或单书)返回整本。"""
    with zipfile.ZipFile(path) as zf:
        try:
            navpoints = _parse_ncx_top_level(zf)
        except Exception:  # noqa: BLE001 - ncx 解析失败按整本处理
            navpoints = []

        part_files = sorted(
            n for n in zf.namelist() if re.match(r"text/part\d+", n)
        )
        if len(navpoints) < 2 or not part_files:
            # 非合集: 整本导入
            return [{"title": _clean_title(path.stem), "text": _extract_epub_text(path)}]

        books = []
        for i, book in enumerate(navpoints):
            start = book["src"]
            end = navpoints[i + 1]["src"] if i + 1 < len(navpoints) else None
            files = [f for f in part_files if f >= start and (end is None or f < end)]
            text = "\n\n".join(_html_to_text(_detect_and_decode(zf.read(f))) for f in files)
            books.append({"title": _clean_title(book["label"]), "text": text})
        return books


def _read_file_text(path: Path) -> str:
    if path.suffix.lower() == ".epub":
        return _extract_epub_text(path)
    return _detect_and_decode(path.read_bytes())


def _save_corpus(title: str, raw_texts: List[str], genre: str, author: str) -> Dict[str, Any]:
    """合并清洗并入库，返回记录。"""
    cleaned = clean_text("\n\n".join(raw_texts))
    paras = to_paragraphs(cleaned)
    if not paras:
        raise ValueError(f"清洗后为空: {title}")

    out_dir = CORPUS_DIR / "imports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{title}.txt"
    out_path.write_text("\n\n".join(paras), encoding="utf-8")

    record = {
        "id": f"import:{title}",
        "title": title,
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


def import_dir(dir_path: Path, genre: str = "other", author: str = "") -> List[Dict[str, Any]]:
    """目录=一本书/一个合集: epub 合集拆分多本, 多 txt 分卷合并一本。"""
    files = sorted(f for f in dir_path.iterdir() if f.suffix.lower() in _SUFFIXES)
    if not files:
        return []

    recs: List[Dict[str, Any]] = []
    epubs = [f for f in files if f.suffix.lower() == ".epub"]
    if epubs:
        for ep in epubs:
            for book in extract_epub_books(ep):
                if not book["text"].strip():
                    continue
                try:
                    recs.append(_save_corpus(book["title"], [book["text"]], genre, author))
                except ValueError as exc:
                    print(f"    跳过空书 {book['title']}: {exc}")
    else:
        title = _clean_title(dir_path.name)
        raw_texts = [_read_file_text(f) for f in files]
        recs.append(_save_corpus(title, raw_texts, genre, author))

    _archive(dir_path)
    return recs


def import_file(path: Path, genre: str = "other", author: str = "") -> Optional[Dict[str, Any]]:
    """单文件导入。"""
    title = _clean_title(path.stem)
    rec = _save_corpus(title, [_read_file_text(path)], genre, author)
    _archive(path)
    return rec


def _archive(item: Path) -> None:
    """导入成功后归档源文件到 imports/done/。"""
    done = IMPORTS_DIR / "done"
    done.mkdir(parents=True, exist_ok=True)
    target = done / item.name
    if target.exists():
        shutil.rmtree(target) if item.is_dir() else target.unlink()
    shutil.move(str(item), str(target))


def scan_imports(genre: str = "other", author: str = "") -> List[Dict[str, Any]]:
    """扫描 imports/，导入所有未处理文件/目录。"""
    ensure_dirs()
    imported = []
    for item in sorted(IMPORTS_DIR.iterdir()):
        if item.name.startswith(".") or item.name == "done":
            continue
        try:
            if item.is_dir():
                recs = import_dir(item, genre=genre, author=author)
            elif item.suffix.lower() in _SUFFIXES:
                recs = [import_file(item, genre=genre, author=author)]
            else:
                recs = []
            for rec in recs:
                if rec:
                    imported.append(rec)
                    print(f"  ✅ 导入: {rec['title']} ({rec['chars']}字)")
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ 导入失败 {item.name}: {exc.__class__.__name__}: {exc}")
    return imported
