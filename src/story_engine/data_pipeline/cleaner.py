"""P6 数据管线 — 文本清洗器。

职责:
- 去除 Gutenberg 头尾样板文字（新版 "The Project Gutenberg eBook of..." /
  老式版权声明 + 元数据块两种格式）
- 去除多余空行/空白，规范化换行
- 切分为段落列表（供后续文风分析）
- 中文占比兜底校验：确保正文起点无英文样板残留

保留原文用字（繁/简不转换，后续可接入 OpenCC）。
"""
from __future__ import annotations

import re
from typing import List

try:  # 繁转简 (OpenCC t2s); 未安装时跳过转换
    from opencc import OpenCC

    _CONVERTER = OpenCC("t2s")
except ImportError:  # pragma: no cover
    _CONVERTER = None

# Gutenberg 正文起点标记（新版）
_START_MARKERS = [
    "*** START OF THE PROJECT GUTENBERG EBOOK",
    "*** START OF THIS PROJECT GUTENBERG EBOOK",
]
# 尾部结束标记
_END_MARKERS = [
    "*** END OF THE PROJECT GUTENBERG EBOOK",
    "*** END OF THIS PROJECT GUTENBERG EBOOK",
    "End of Project Gutenberg",
    "End of the Project Gutenberg's",
    "End of the Project Gutenberg",
]
# 老式元数据行: Title: / Author: / Release date: / Language: / Credits: ...
_METADATA_LINE = re.compile(r"^[A-Za-z][A-Za-z ]*:")
# Credits 重复行 (无冒号, 如 "Produced by Hoi Man Man")
_PRODUCED_LINE = re.compile(r"^Produced by ")
# 开头版权样板（老式）
_LEGACY_LICENSE = "This eBook is for the use of anyone anywhere"


def _chinese_ratio(s: str) -> float:
    """中文字符占比。"""
    if not s:
        return 0.0
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    return cjk / len(s)


def _find_start_marker(text: str) -> int:
    """返回正文起点索引；找不到返回 -1。

    START 标记后可能没有换行（样板行即正文起点），此时从首个可见字符截取，
    避免把整段正文当作样板丢弃（L15.6）。
    """
    for marker in _START_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            nl = text.find("\n", idx)
            if nl != -1:
                # 跳过样板行后连续的空行
                rest = text[nl + 1:]
                stripped = rest.lstrip("\n")
                return nl + 1 + (len(rest) - len(stripped))
            # 无换行：从标记后的首个非空白可见字符开始
            rest = text[idx + len(marker):]
            for pos, ch in enumerate(rest):
                if ch not in "\r\n \t\u3000":
                    return idx + len(marker) + pos
            return len(text)
    return -1


def _skip_metadata_block(text: str) -> str:
    """老式格式: 从 Title: 行起，跳过元数据行与空行，返回正文。"""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line == "" or _METADATA_LINE.match(line) or _PRODUCED_LINE.match(line):
            i += 1
        else:
            break
    return "\n".join(lines[i:])


def strip_gutenberg_header_footer(text: str) -> str:
    """去掉 Gutenberg 样板头尾，保留正文。"""
    # 1) 尾部截断
    for marker in _END_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
            break

    # 2) 头部: 优先新版 START 标记
    start = _find_start_marker(text)
    if start != -1:
        text = text[start:]
        # START 标记后可能重复 Title:/Author:/Produced by 元数据块
        text = _skip_metadata_block(text)
    else:
        # 老式格式: 版权声明后跟 Title:/Author: 元数据块
        idx = text.find("Title:")
        if idx != -1:
            text = _skip_metadata_block(text[idx:])
        elif _LEGACY_LICENSE in text:
            # 极端情况: 只有版权声明, 找其后的空行结束处
            idx = text.find(_LEGACY_LICENSE)
            seg = text[idx:]
            nl = seg.find("\n\n")
            text = seg[nl + 2 :] if nl != -1 else seg
    return text


def _locate_body_start(text: str) -> str:
    """兜底: 若开头英文残留过多, 前移到第一个中文密集段落。"""
    paras = [p for p in text.split("\n") if p.strip()]
    if not paras:
        return text
    # 开头 2000 字符内检查
    head = text[:2000]
    if _chinese_ratio(head) >= 0.3:
        return text
    for i, p in enumerate(paras):
        if len(p) >= 20 and _chinese_ratio(p) >= 0.5:
            return "\n".join(paras[i:])
    return text


def normalize_whitespace(text: str) -> str:
    """规范化空白：统一换行、去除多余空行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u3000]+(?=\n)", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\n[ \t\u3000]+\n", "\n\n", text)
    return text.strip()


def to_paragraphs(text: str, min_len: int = 10) -> List[str]:
    """按空行切分为段落列表，过滤过短片段。

    空行缺失时（文本全部为单换行分隔）按单换行兜底切分，避免整段吞并
    （L15.6）。兜底触发条件：按空行切分后段落过少或出现超长段。
    """
    import warnings

    paras = [p.strip() for p in text.split("\n\n")]
    paras = [p for p in paras if p]
    # 兜底判断：段落数太少或存在超长段（> 全文字数一半），说明空行结构丢失
    total = sum(len(p) for p in paras)
    if paras and (len(paras) <= 1 or max(len(p) for p in paras) > max(min_len, total // 2)):
        line_paras = [p.strip() for p in text.split("\n")]
        line_paras = [p for p in line_paras if p]
        if len(line_paras) > len(paras):
            warnings.warn("段落空行缺失，已按单换行兜底切分", stacklevel=2)
            paras = line_paras
    return [p for p in paras if len(p) >= min_len]


def to_simplified(text: str) -> str:
    """繁体 → 简体（OpenCC t2s）。"""
    if _CONVERTER is None:
        return text
    return _CONVERTER.convert(text)


def clean_text(raw: str) -> str:
    """完整清洗流程：样板剥离 → 中文起点校验 → 空白规范化 → 繁转简。"""
    text = strip_gutenberg_header_footer(raw)
    text = _locate_body_start(text)
    text = normalize_whitespace(text)
    text = to_simplified(text)
    return text
