"""文风 API 路由 — Style CRUD + 分析 + 一致性检查"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from story_engine.style import StyleAnalyzer, StyleDb, StyleProfile
from story_engine.style.schemas import (
    StyleAnalyzeResponse,
    StyleConsistencyRequest,
    StyleConsistencyResult,
    StyleFeatureRequest,
    StyleGenerateRequest,
    StyleListResponse,
    StyleProfileResponse,
    StyleRecommendResponse,
    StyleRecommendItem,
    StyleSaveRequest,
)

logger = logging.getLogger("story_engine.api")

router = APIRouter(prefix="/api/style", tags=["style"])


def _get_db() -> StyleDb:
    return StyleDb()


def _get_analyzer() -> StyleAnalyzer:
    return StyleAnalyzer()


# ── 文风画像 CRUD ─────────────────────────────────────


@router.get("/profiles", response_model=StyleListResponse)
async def list_profiles(genre: str = ""):
    """列出所有文风画像"""
    db = _get_db()
    profiles = db.list_profiles(genre=genre)
    return StyleListResponse(
        profiles=[StyleProfileResponse(**p.__dict__) for p in profiles],
        total=len(profiles),
    )


@router.get("/profiles/{profile_id}", response_model=StyleProfileResponse)
async def get_profile(profile_id: str):
    """获取文风画像详情"""
    db = _get_db()
    profile = db.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="文风画像不存在")
    return StyleProfileResponse(**profile.__dict__)


@router.post("/profiles", response_model=StyleProfileResponse)
async def save_profile(req: StyleSaveRequest):
    """创建/更新文风画像"""
    db = _get_db()
    profile = StyleProfile(
        name=req.name,
        author=req.author,
        source_work=req.source_work,
        genre=req.genre,
        features=req.features,
        style_prompt=req.style_prompt,
        sample_text=req.sample_text,
        tags=req.tags,
    )
    profile.id = db.save_profile(profile)
    saved = db.get_profile(profile.id)
    return StyleProfileResponse(**saved.__dict__)


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    """删除文风画像"""
    db = _get_db()
    ok = db.delete_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文风画像不存在")
    return {"status": "deleted", "id": profile_id}


@router.get("/genres")
async def list_genres():
    """列出所有题材分类"""
    db = _get_db()
    return {"genres": db.get_genres()}


@router.get("/search")
async def search_profiles(q: str = ""):
    """搜索文风画像"""
    if not q:
        db = _get_db()
        profiles = db.list_profiles()
    else:
        db = _get_db()
        profiles = db.search_profiles(q)
    return StyleListResponse(
        profiles=[StyleProfileResponse(**p.__dict__) for p in profiles],
        total=len(profiles),
    )


# ── 文风分析 ──────────────────────────────────────────


@router.post("/analyze", response_model=StyleAnalyzeResponse)
async def analyze_style(req: StyleFeatureRequest):
    """分析文本的文风特征"""
    analyzer = _get_analyzer()
    try:
        features = await analyzer.analyze_style(req.text)
    finally:
        await analyzer.close()

    # 生成风格描述
    style_prompt = features.get("整体风格总结", "")
    if not style_prompt:
        style_prompt = await analyzer.generate_style_prompt(features)

    profile_id = ""
    if req.name:
        # 自动保存为文风画像
        db = _get_db()
        profile = StyleProfile(
            name=req.name,
            author=req.author,
            source_work=req.source_work,
            genre=req.genre,
            features=features,
            style_prompt=style_prompt,
            sample_text=req.text[:500],
        )
        profile.id = db.save_profile(profile)
        profile_id = profile.id

    return StyleAnalyzeResponse(
        features=features,
        style_prompt=style_prompt,
        profile_id=profile_id,
    )


@router.post("/check", response_model=StyleConsistencyResult)
async def check_consistency(req: StyleConsistencyRequest):
    """检查文本与文风的一致性"""
    db = _get_db()
    profile = None
    style_prompt = req.style_prompt

    if req.profile_id:
        profile = db.get_profile(req.profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="文风画像不存在")
        style_prompt = profile.style_prompt or ""

    if not style_prompt and profile:
        style_prompt = analyzer._features_to_prompt(profile.features)  # noqa

    if not style_prompt:
        raise HTTPException(status_code=400, detail="需要提供 profile_id 或 style_prompt")

    analyzer = _get_analyzer()
    try:
        result = await analyzer.check_consistency(req.text, profile or StyleProfile(
            name="临时", style_prompt=style_prompt
        ))
    finally:
        await analyzer.close()

    return StyleConsistencyResult(
        consistency_score=result.get("consistency_score", 5),
        consistent_aspects=result.get("consistent_aspects", []),
        inconsistent_aspects=result.get("inconsistent_aspects", []),
        suggestions=result.get("suggestions", []),
        conclusion=result.get("conclusion", ""),
    )


# ── 带文风的生成 ──────────────────────────────────────


@router.post("/generate")
async def generate_with_style(req: StyleGenerateRequest):
    """带文风的小说内容生成（SSE 流式）"""
    from sse_starlette.sse import EventSourceResponse

    from story_engine.api.schemas import ChatRequest
    from story_engine.api.routes.generate import _get_router
    from story_engine.api.sse import event_stream

    # 加载文风画像
    db = _get_db()
    style_block = ""
    if req.profile_id:
        profile = db.get_profile(req.profile_id)
        if profile:
            style_block = StyleAnalyzer.render_style_block(profile)
        else:
            raise HTTPException(status_code=404, detail="文风画像不存在")
    elif req.style_prompt:
        style_block = req.style_prompt

    # 构建带文风的 system prompt
    extra_style = ""
    if style_block:
        extra_style = f"\n\n请严格遵循以下文风风格进行创作：\n{style_block}"

    # 加载小说信息
    outline_hint = ""
    if req.outline:
        outline_hint = f"\n大纲参考：\n{req.outline}"

    user_prompt = f"""请创作小说第 {req.chapter_number} 章{'「' + req.chapter_title + '」' if req.chapter_title else ''}。{outline_hint}{extra_style}

请用中文创作，保持文风一致。"""

    chat_req = ChatRequest(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt="你是一位专业小说作家。" + extra_style,
        model=req.model,
        temperature=0.8,
        stream=True,
        mode="write",
    )

    router_inst = _get_router()

    from story_engine.llm.base import LLMRequest

    async def _stream_style() -> AsyncGenerator[str, None]:
        request = LLMRequest(
            messages=chat_req.messages,
            system_prompt=chat_req.system_prompt,
            temperature=chat_req.temperature,
            max_tokens=chat_req.max_tokens,
        )
        async for token in router_inst.chat_stream(request, model_name=req.model or None):
            yield token

    return EventSourceResponse(event_stream(_stream_style()))


# ── 文风 vs 题材匹配推荐 ───────────────────────────────


@router.get("/recommend", response_model=StyleRecommendResponse)
async def recommend_by_genre(
    genre: str = "",
    top_k: int = 5,
    same_genre_only: bool = False,
):
    """按题材推荐文风画像 — 题材原型向量 + 余弦相似度（支持跨题材推荐）"""
    from story_engine.style.recommend import recommend_profiles

    results = recommend_profiles(
        genre=genre,
        top_k=max(1, min(top_k, 70)),
        include_same_genre_only=same_genre_only,
    )
    note = ""
    if not genre:
        note = "未指定题材，返回全部画像前几名"
    elif not results:
        note = f"题材「{genre}」暂无画像，可先导入语料生成画像"
    elif same_genre_only and not any(r["same_genre"] for r in results):
        note = f"题材「{genre}」暂无画像，已按风格相近返回跨题材推荐"

    return StyleRecommendResponse(
        genre=genre,
        recommendations=[
            StyleRecommendItem(
                profile=StyleProfileResponse(**r["profile"].__dict__),
                score=r["score"],
                same_genre=r["same_genre"],
            )
            for r in results
        ],
        total=len(results),
        note=note,
    )
