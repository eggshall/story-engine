"""资料检索路由 — 联网搜索 + 保存结果"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query

from story_engine.api.schemas import ApiResponse, ResearchRequest, ResearchResult
from story_engine.core.config import data_dir
from story_engine.tools.web_search import search_web

router = APIRouter(prefix="/api/research", tags=["research"])

RESEARCH_DIR = data_dir() / "research"


@router.post("/")
async def research(req: ResearchRequest) -> ApiResponse:
    """检索资料并保存 — 调用真实搜索引擎获取结果"""
    query = req.query.strip()
    if not query:
        return ApiResponse(success=False, message="检索内容不能为空")

    # 调用真实搜索引擎
    search_response = await search_web(
        query,
        max_results=8,
        extract_content=True,
        max_extract=1,
    )

    # 格式化 sources 列表
    sources = []
    for r in search_response.results:
        sources.append({
            "title": r.title,
            "snippet": r.snippet,
            "url": r.url,
            "source": r.source,
        })

    # 构建 summary
    summary = search_response.summary if search_response.summary else f"关于「{query}」的搜索结果"
    if search_response.extracted_pages:
        summary += "\n\n" + "\n".join(search_response.extracted_pages)

    # 保存检索记录到磁盘
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 生成安全的文件名
    safe_query = "".join(c if c.isalnum() or c in "._- " else "_" for c in query)
    record = {
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "sources": sources,
        "summary": summary,
        "engine_used": search_response.engine_used,
        "category": req.lore_category if req.save_to_lore else "research",
    }
    record_file = RESEARCH_DIR / f"{ts}_{safe_query[:20]}.json"
    with open(record_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    return ApiResponse(
        success=True,
        message=f"检索完成，找到 {len(sources)} 条结果",
        data=ResearchResult(
            query=query,
            summary=summary,
            sources=sources,
            saved_to=str(record_file),
        ).model_dump(),
    )


@router.get("/")
async def list_research(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse:
    """列出历史研究记录"""
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    # 按修改时间排序，最新的在前
    files = sorted(
        RESEARCH_DIR.glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    records = []
    for f in files[offset:offset + limit]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                record = json.load(fh)
            record["saved_to"] = str(f)
            records.append(record)
        except (json.JSONDecodeError, OSError):
            continue

    return ApiResponse(
        success=True,
        message=f"共 {len(files)} 条记录",
        data=records,
    )
