"""导出路由 — MD / JSON 导出与导入"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from story_engine.api.schemas import ApiResponse, ExportRequest, ExportResult, ImportRequest
from story_engine.core.models import Novel
from story_engine.tools.novel_storage import NOVELS_ROOT, load_novel, save_novel

logger = logging.getLogger("story_engine.export")
router = APIRouter(prefix="/api/export", tags=["export"])

IMPORT_ROUTER = APIRouter(prefix="/api/import", tags=["import"])


# ── MD 导出 ──────────────────────────────────────────────


def _to_markdown(data: dict, chapter_numbers: List[int] | None = None) -> str:
    """将小说数据转为 Markdown 格式"""
    lines: List[str] = []
    title = data.get("title", "未命名")
    author = data.get("author", "")
    genre = data.get("genre", "")
    synopsis = data.get("synopsis", "")

    lines.append(f"# {title}")
    lines.append("")
    if author:
        lines.append(f"**作者：** {author}")
    if genre:
        lines.append(f"**类型：** {genre}")
    lines.append("---")
    if synopsis:
        lines.append(f"> {synopsis}")
        lines.append("")
    lines.append("")

    chapters = data.get("chapters", [])
    for ch in chapters:
        ch_num = ch.get("chapter_number", 0)
        if chapter_numbers and ch_num not in chapter_numbers:
            continue
        ch_title = ch.get("title", f"第{ch_num}章")
        content = ch.get("content", "")
        lines.append(f"## 第{ch_num}章 {ch_title}")
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


@router.post("/md")
async def export_md(req: ExportRequest) -> ApiResponse:
    """导出小说为 Markdown 文件"""
    novel_id = req.novel_id
    if not novel_id:
        return ApiResponse(success=False, message="请指定 novel_id")

    novel = load_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"小说 '{novel_id}' 不存在")

    data = novel.model_dump()

    # 确定输出目录
    out_dir = Path(req.output_dir) if req.output_dir else (NOVELS_ROOT / novel_id / "exports")
    out_dir.mkdir(parents=True, exist_ok=True)

    ch_numbers = None if req.export_all else (req.chapter_numbers or None)
    md = _to_markdown(data, ch_numbers)

    # 写入文件
    output_file = out_dir / f"{novel_id}.md"
    output_file.write_text(md, encoding="utf-8")

    # 计算导出的章节数和字数
    chapters = data.get("chapters", [])
    exported = chapters if ch_numbers is None else [c for c in chapters if c.get("chapter_number") in ch_numbers]
    word_count = sum(len(c.get("content", "")) for c in exported)

    return ApiResponse(
        success=True,
        data=ExportResult(
            success=True,
            path=str(output_file),
            format="md",
            chapters_exported=len(exported),
            word_count=word_count,
        ).model_dump(),
    )


# ── JSON 导出 ────────────────────────────────────────────


@router.post("/json")
async def export_json(req: ExportRequest) -> ApiResponse:
    """导出小说为 JSON 项目文件"""
    novel_id = req.novel_id
    if not novel_id:
        return ApiResponse(success=False, message="请指定 novel_id")

    novel = load_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"小说 '{novel_id}' 不存在")

    data = novel.model_dump()

    # 确定输出目录
    out_dir = Path(req.output_dir) if req.output_dir else (NOVELS_ROOT / novel_id / "exports")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 写入 JSON
    output_file = out_dir / f"{novel_id}.json"
    output_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    chapters = data.get("chapters", [])
    word_count = sum(len(c.get("content", "")) for c in chapters)

    return ApiResponse(
        success=True,
        data=ExportResult(
            success=True,
            path=str(output_file),
            format="json",
            chapters_exported=len(chapters),
            word_count=word_count,
        ).model_dump(),
    )


# ── JSON 导入 ────────────────────────────────────────────


@IMPORT_ROUTER.post("/json")
async def import_json(req: ImportRequest) -> ApiResponse:
    """从 JSON 导入项目"""
    try:
        data: Dict[str, Any] = json.loads(req.json_data)
    except json.JSONDecodeError as e:
        return ApiResponse(
            success=False,
            message=f"JSON 格式错误: {str(e)}",
        )

    title = data.get("title", "未命名")
    novel_id = req.restore_path or data.get("id", "") or title

    # 检查是否已存在
    existing = load_novel(novel_id)
    if existing and not req.force:
        return ApiResponse(
            success=False,
            message=f"小说 '{novel_id}' 已存在，使用 force=true 覆盖",
        )

    try:
        novel = Novel(**data)
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"数据格式错误: {str(e)}",
        )

    save_novel(novel, novel_id=novel_id)

    return ApiResponse(
        success=True,
        data={
            "id": novel_id,
            "title": novel.title,
            "chapter_count": len(novel.chapters),
            "word_count": sum(ch.word_count for ch in novel.chapters),
        },
    )
