"""小说管理路由 — 独立目录存储 + 灵魂记忆 + 文风分析"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from story_engine.api.schemas import (
    ApiResponse,
    ChapterCreateRequest,
    ChapterReorderRequest,
    ChapterSaveRequest,
    ChapterStyleRequest,
    ConsistencyRequest,
    MapSaveRequest,
    NovelCreateRequest,
    NovelDetail,
    NovelUpdateRequest,
    StyleAnalyzeRequest,
)
from story_engine.core.models import Novel
from story_engine.tools.fixed_tasks import check_name_consistency
from story_engine.tools.novel_storage import (
    delete_novel,
    list_novels,
    list_style_profiles,
    load_novel,
    load_soul_memory,
    load_user_profile,
    save_novel,
    save_soul_memory,
    save_style_profile,
    save_user_profile,
)
from story_engine.tools.style_analyzer import (
    analyze_text_style,
    build_style_profile,
    extract_techniques,
)

router = APIRouter(prefix="/api/novel", tags=["novel"])


# ── 小说 CRUD ────────────────────────────────


@router.get("/")
def api_list_novels() -> ApiResponse:
    """列出所有小说"""
    novels = list_novels()
    return ApiResponse(success=True, data=novels)


@router.get("/{novel_id}")
def api_get_novel(novel_id: str) -> ApiResponse:
    """获取小说详情"""
    novel = load_novel(novel_id)
    if not novel:
        return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")

    detail = NovelDetail(
        id=novel_id,
        title=novel.title,
        author=novel.author,
        genre=novel.genre,
        synopsis=novel.synopsis,
        characters=list(novel.characters.keys()),
        lorebooks=list(novel.lorebooks.keys()),
        chapters=[ch.model_dump() for ch in novel.chapters],
        word_count=novel.word_count(),
        chapter_count=novel.chapter_count(),
        created=novel.created,
        updated=novel.updated,
    )
    return ApiResponse(success=True, data=detail.model_dump())


@router.post("/")
def api_create_novel(req: NovelCreateRequest) -> ApiResponse:
    """创建新小说（独立目录）"""
    novel = Novel(
        title=req.title,
        author=req.author,
        genre=req.genre,
        synopsis=req.synopsis,
    )
    # 支持自定义保存路径
    custom_path = req.save_path.strip() if req.save_path else ""
    try:
        novel_id = save_novel(novel, custom_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 返回完整详情
    detail = NovelDetail(
        id=novel_id,
        title=novel.title,
        author=novel.author,
        genre=novel.genre,
        synopsis=novel.synopsis,
        characters=[],
        lorebooks=[],
        chapters=[],
        word_count=0,
        chapter_count=0,
        created=novel.created,
        updated=novel.updated,
    )
    return ApiResponse(success=True, message=f"小说 '{req.title}' 已创建", data=detail.model_dump())


@router.delete("/{novel_id}")
def api_delete_novel(novel_id: str) -> ApiResponse:
    """删除整部小说（含所有数据）"""
    if delete_novel(novel_id):
        return ApiResponse(success=True, message=f"已删除: {novel_id}")
    return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")


# ── 小说编辑 ────────────────────────────────


@router.post("/{novel_id}/update")
def api_update_novel(novel_id: str, req: NovelUpdateRequest) -> ApiResponse:
    """更新小说元信息"""
    novel = load_novel(novel_id)
    if not novel:
        return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")
    for k in ("title", "author", "genre", "synopsis"):
        v = getattr(req, k)
        if v is not None:
            setattr(novel, k, v)
    save_novel(novel, novel_id)
    return ApiResponse(success=True, message="已更新")


# ── 章节管理 ────────────────────────────────


@router.post("/{novel_id}/chapters")
def api_add_chapter(novel_id: str, req: ChapterCreateRequest) -> ApiResponse:
    """添加章节"""
    from story_engine.core.models import Chapter

    novel = load_novel(novel_id)
    if not novel:
        return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")

    ch_number = req.chapter_number or (novel.chapter_count() + 1)
    # 重号检查（L12.2）：拒绝同号覆盖，避免静默丢章节
    if any(c.chapter_number == ch_number for c in novel.chapters):
        return ApiResponse(success=False, message=f"章节 {ch_number} 已存在，请使用其它编号")

    ch = Chapter(
        chapter_number=ch_number,
        title=req.title or f"第{ch_number}章",
        content=req.content or "",
    )
    novel.chapters.append(ch)
    save_novel(novel, novel_id)
    return ApiResponse(success=True, data=ch.model_dump())


@router.delete("/{novel_id}/chapters/{chapter_number}")
def api_delete_chapter(novel_id: str, chapter_number: int) -> ApiResponse:
    """删除章节"""
    novel = load_novel(novel_id)
    if not novel:
        return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")

    before = len(novel.chapters)
    novel.chapters = [c for c in novel.chapters if c.chapter_number != chapter_number]
    if len(novel.chapters) == before:
        return ApiResponse(success=False, message=f"章节 {chapter_number} 不存在")

    # 重新编号
    for i, c in enumerate(novel.chapters, 1):
        c.chapter_number = i
    save_novel(novel, novel_id)
    return ApiResponse(success=True, message=f"已删除第{chapter_number}章")


@router.post("/{novel_id}/chapters/reorder")
def api_reorder_chapters(novel_id: str, req: ChapterReorderRequest) -> ApiResponse:
    """重排章节顺序: body = {order: [3, 1, 2, ...]}"""
    novel = load_novel(novel_id)
    if not novel:
        return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")

    order = req.order
    if len(order) != len(novel.chapters):
        return ApiResponse(success=False, message="章节数量不匹配")

    # 集合校验（L12.1）：order 必须与现有章节号一一对应，杜绝静默丢章节
    existing = {c.chapter_number for c in novel.chapters}
    if set(order) != existing:
        return ApiResponse(
            success=False,
            message=f"章节号不匹配：需要包含 {sorted(existing)}",
        )

    # 按新顺序重排
    ch_map = {c.chapter_number: c for c in novel.chapters}
    novel.chapters = [ch_map[num] for num in order]
    for i, c in enumerate(novel.chapters, 1):
        c.chapter_number = i
    save_novel(novel, novel_id)
    return ApiResponse(success=True, message="顺序已更新")


@router.post("/{novel_id}/chapters/{chapter_number}/save")
def api_save_chapter(novel_id: str, chapter_number: int, req: ChapterSaveRequest) -> ApiResponse:
    """保存单章内容"""
    novel = load_novel(novel_id)
    if not novel:
        return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")

    for c in novel.chapters:
        if c.chapter_number == chapter_number:
            if req.title is not None:
                c.title = req.title
            if req.content is not None:
                c.content = req.content
            # 字数统一由正文计算（L13.1）
            c.word_count = len(c.content)
            save_novel(novel, novel_id)
            return ApiResponse(success=True, message=f"第{chapter_number}章已保存")

    return ApiResponse(success=False, message=f"章节 {chapter_number} 不存在")


# ── 灵魂记忆 ────────────────────────────────


@router.get("/{novel_id}/memory")
def api_get_memory(novel_id: str) -> ApiResponse:
    """获取小说的灵魂记忆"""
    mem = load_soul_memory(novel_id)
    return ApiResponse(success=True, data=mem.model_dump())


@router.post("/{novel_id}/memory")
def api_update_memory(novel_id: str, data: dict) -> ApiResponse:
    """更新灵魂记忆"""
    mem = load_soul_memory(novel_id)
    # 更新各字段
    if "character_voice" in data:
        mem.update_character_voice(**data["character_voice"])
    if "plot" in data:
        mem.update_plot(**data["plot"])
    if "style" in data:
        for k, v in data["style"].items():
            if hasattr(mem.style, k):
                setattr(mem.style, k, v)
    if "user_notes" in data:
        mem.user_notes = data["user_notes"]
    if "custom_system_prompt" in data:
        mem.custom_system_prompt = data["custom_system_prompt"]
    if "preferred_model" in data:
        mem.preferred_model = data["preferred_model"]
    if "writing_mode_pref" in data:
        mem.writing_mode_pref = data["writing_mode_pref"]

    save_soul_memory(mem)
    return ApiResponse(success=True, data=mem.model_dump())


# ── 文风分析 ────────────────────────────────


@router.post("/{novel_id}/analyze")
def api_analyze_style(novel_id: str, req: StyleAnalyzeRequest) -> ApiResponse:
    """分析一段文本，生成文风档案"""
    text = req.text
    profile_name = req.name
    source_name = req.source_name
    source_url = req.source_url

    if not text:
        return ApiResponse(success=False, message="文本不能为空")

    profile = build_style_profile(text, novel_id, profile_name, source_name, source_url)
    # 检测写作技法
    techniques = extract_techniques(text)
    profile.writing_techniques = techniques

    save_style_profile(profile)
    return ApiResponse(success=True, data=profile.model_dump())


@router.post("/{novel_id}/analyze/style")
def api_analyze_chapter_style(novel_id: str, req: ChapterStyleRequest) -> ApiResponse:
    """分析章节文本的风格指标 + 写作技法"""
    novel = load_novel(novel_id)
    if not novel:
        return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")

    chapter_number = req.chapter_number
    text = req.text

    # 如果请求体提供了 text，优先使用；否则从章节读取
    if not text:
        chapter = None
        for c in novel.chapters:
            if c.chapter_number == chapter_number:
                chapter = c
                break
        if not chapter:
            return ApiResponse(success=False, message=f"章节 {chapter_number} 不存在")
        text = chapter.content

    if not text:
        return ApiResponse(success=True, data={})

    stats = analyze_text_style(text)
    techniques = extract_techniques(text)

    return ApiResponse(success=True, data={
        **stats,
        "techniques": techniques,
        "chapter_number": chapter_number,
    })


@router.post("/{novel_id}/analyze/consistency")
def api_check_consistency(novel_id: str, req: ConsistencyRequest) -> ApiResponse:
    """检查章节文本中角色名/地名的一致性"""
    novel = load_novel(novel_id)
    if not novel:
        return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")

    chapter_number = req.chapter_number
    text = req.text

    # 如果请求体提供了 text，优先使用；否则从章节读取
    if not text:
        chapter = None
        for c in novel.chapters:
            if c.chapter_number == chapter_number:
                chapter = c
                break
        if not chapter:
            return ApiResponse(success=False, message=f"章节 {chapter_number} 不存在")
        text = chapter.content

    # 收集已知角色名
    known_names = list(novel.characters.keys())

    # 从 lorebook 中提取地名
    known_places: list = []
    for lb in novel.lorebooks.values():
        for entry_id, entry in lb.entries.items():
            # 尝试从分类中识别地名
            if hasattr(entry, 'category') and entry.category in ('地理', '地点', 'location', 'geography', 'place'):
                known_places.extend(entry.keys)

    issues = check_name_consistency(text, known_names, known_places)

    return ApiResponse(success=True, data={
        "issues": issues,
        "chapter_number": chapter_number,
        "checked_names": len(known_names),
        "checked_places": len(known_places),
    })


@router.get("/{novel_id}/styles")
def api_list_styles(novel_id: str) -> ApiResponse:
    """列出一部小说的所有文风档案"""
    profiles = list_style_profiles(novel_id)
    return ApiResponse(success=True, data=profiles)


# ── 用户画像 ────────────────────────────────


@router.get("/user/profile")
def api_get_user_profile() -> ApiResponse:
    """获取用户画像"""
    profile = load_user_profile()
    return ApiResponse(success=True, data=profile.model_dump())


@router.post("/user/profile")
def api_update_user_profile(body: dict) -> ApiResponse:
    """更新用户画像"""
    profile = load_user_profile()
    for k, v in body.items():
        if hasattr(profile, k):
            setattr(profile, k, v)
    save_user_profile(profile)
    return ApiResponse(success=True, data=profile.model_dump())


# ── 世界地图 ──────────────────────────────────


@router.get("/{novel_id}/map")
def api_get_map(novel_id: str) -> ApiResponse:
    """获取小说地图数据"""
    from story_engine.tools.novel_storage import load_map_data
    novel = load_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"小说 '{novel_id}' 不存在")
    data = load_map_data(novel_id)
    return ApiResponse(success=True, data=data)


@router.post("/{novel_id}/map")
def api_save_map(novel_id: str, req: MapSaveRequest) -> ApiResponse:
    """保存小说地图数据"""
    from story_engine.tools.novel_storage import load_map_data, save_map_data
    novel = load_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"小说 '{novel_id}' 不存在")
    save_map_data(
        novel_id,
        req.image_path,
        req.markers,
    )
    data = load_map_data(novel_id)
    return ApiResponse(success=True, data=data)


@router.post("/{novel_id}/map/image")
def api_upload_map_image(novel_id: str) -> ApiResponse:
    """上传地图图片占位 — 返回假路径（后续可升级为真实文件上传）"""
    from story_engine.tools.novel_storage import _novel_dir
    novel = load_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"小说 '{novel_id}' 不存在")
    return ApiResponse(success=True, data={
        "image_path": str(_novel_dir(novel_id) / "map_placeholder.png"),
    })
