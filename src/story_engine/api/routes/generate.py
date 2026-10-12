"""生成路由 — 大纲/章节写作/自由对话 (SSE 流式)"""

from __future__ import annotations

import copy
import logging
import re
import threading

import anyio
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from story_engine.api.schemas import ApiResponse, ChapterV2Request, ChatRequest
from story_engine.api.sse import done_payload, error_payload, event_stream
from story_engine.core.config import get_config
from story_engine.core.models import Novel
from story_engine.llm.base import TASK_GENERATE, LLMRequest
from story_engine.llm.router import ModelRouter
from story_engine.tools.prompts import get_system_prompt
from story_engine.tools.web_search import format_search_context, search_web

logger = logging.getLogger("story_engine.api")

router = APIRouter(prefix="/api/generate", tags=["generate"])

# 真实 fallback 前缀（见 L5.2 / L13.1）：不计入正文与字数
_FALLBACK_PREFIX_RE = re.compile(r"^\[Fallback → [^\]]+\]\s*")


def strip_fallback_prefix(text: str) -> str:
    """去掉流式/非流式 fallback 前缀，保证正文与字数口径一致。"""
    return _FALLBACK_PREFIX_RE.sub("", text, count=1)

# 全局 Router（懒加载 + 锁 + reload 钩子）
_router: ModelRouter | None = None
_router_lock = threading.Lock()


def _get_router() -> ModelRouter:
    """懒加载全局 router，构建时深拷贝模型配置（杜绝污染共享配置，见 L6.2）。

    ModelRouter 构造为纯同步操作，用 threading.Lock 串行化并发首次构建；
    `reload_config()` 通过 `close_router()` 清空后自动重建。
    """
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                _router = _build_router_locked()
    return _router


def _build_router_locked() -> ModelRouter:
    """在锁内构建 router。"""
    cfg = get_config()
    models = copy.deepcopy(cfg.get("llm.models", []) or [])
    default_model = cfg.get("llm.default_model", "") or ""
    # 全局超时（llm.connect_timeout / llm.read_timeout）作为各模型默认值下发，
    # 模型级配置未显式声明超时时生效，避免配置文件与运行时行为不一致。
    connect_timeout = cfg.get("llm.connect_timeout")
    read_timeout = cfg.get("llm.read_timeout")
    for m in models:
        if not isinstance(m, dict):
            continue
        if connect_timeout is not None and "connect_timeout" not in m:
            m["connect_timeout"] = connect_timeout
        if read_timeout is not None and "read_timeout" not in m:
            m["read_timeout"] = read_timeout
    return ModelRouter(models, default_model=default_model)


async def close_router() -> None:
    """关闭全局 router 并清空，供 lifespan shutdown / reload 使用。"""
    global _router
    router = _router
    _router = None
    if router is not None:
        await router.close_all()


def _load_novel(novel_id: str) -> Novel | None:
    """从独立目录加载小说"""
    from story_engine.tools.novel_storage import load_novel as _storage_load
    return _storage_load(novel_id)


def _save_novel(novel: Novel, novel_id: str = "") -> str:
    """保存小说到独立目录"""
    from story_engine.tools.novel_storage import save_novel as _storage_save
    return _storage_save(novel, novel_id)


@router.post("/outline")
async def generate_outline(novel_id: str = "", chapter_number: int = 1,
                           chapter_title: str = "", model: str = ""):
    """SSE 流式生成大纲"""
    from story_engine.writer.engine import WritingEngine

    engine = WritingEngine(_get_router())

    # 加载小说或创建临时（阻塞 IO 走线程池，见 L10）
    if novel_id:
        novel = await anyio.to_thread.run_sync(_load_novel, novel_id)
        if not novel:
            return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")
    else:
        novel = Novel(title="未命名作品", synopsis="")

    # 加载已有角色
    # N8：不再从全局目录合并角色卡 —— 书里的 `characters` 字典就是本书自己的卡
    # （load_novel 已把它读进模型），装配器/提示词直接用；原来是"所有小说共用一副全局卡组"。

    engine.load_novel(novel)

    return EventSourceResponse(
        event_stream(_stream_outline(engine, chapter_number, chapter_title, model))
    )


async def _stream_outline(engine, ch_num: int, title: str, model: str):
    """生成大纲，结果以 **done 载荷** 回传（N2：结构体不再混在 token 流里）

    理由：前端 `readSSE` 在 done 处收尾，token 事件里的结构体既不是正文、
    也没有明确的接收点（历史上 OutlineView 直接丢弃了它）。
    """
    outline = await engine.generate_outline(ch_num, title, model=model or None)
    if outline:
        yield done_payload(outline=outline.model_dump(exclude_none=True))
    else:
        yield error_payload("大纲生成失败")


@router.post("/chapter")
async def generate_chapter(novel_id: str = "", chapter_number: int = 1,
                            chapter_title: str = "", model: str = ""):
    """SSE 流式生成章节内容"""
    from story_engine.writer.engine import WritingEngine

    engine = WritingEngine(_get_router())
    novel = await anyio.to_thread.run_sync(_load_novel, novel_id) if novel_id else Novel(title="未命名作品")
    if novel_id and not novel:
        return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")
    assert novel is not None

    # N8：不再从全局目录合并角色卡 —— 书里的 `characters` 字典就是本书自己的卡
    # （load_novel 已把它读进模型），装配器/提示词直接用；原来是"所有小说共用一副全局卡组"。

    engine.load_novel(novel)

    return EventSourceResponse(
        event_stream(_stream_chapter(engine, chapter_number, chapter_title, model, novel, novel_id))
    )


async def _stream_chapter(engine, ch_num: int, title: str, model: str, novel: Novel, novel_id: str = ""):
    """先生成大纲，再流式生成章节"""
    from story_engine.core.models import Chapter

    # 1. 生成大纲
    outline = await engine.generate_outline(ch_num, title, model=model or None)
    if not outline:
        yield error_payload("大纲生成失败")
        return

    # 2. 通过流式 API 生成内容
    novel_data = engine.current_novel
    prompt = f"""请根据以下大纲续写小说《{novel_data.title}》第{ch_num}章「{outline.title}」。

{engine._build_character_context(novel_data.characters)}

{engine._build_world_context(ch_num)}

大纲：
{outline.model_dump_json(indent=2, ensure_ascii=False)}

写作要求：
1. 控制在{outline.word_estimate}字左右
2. 保持角色性格一致性
3. 注意场景切换自然
4. 每段不超过300字
5. 章节末尾留悬念"""

    req = LLMRequest(
        system_prompt="你是一位专业的网络小说作家。",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        # max_tokens 直接由字数估算而来（word_estimate*2），思考模式会整体吃掉这个预算 →
        # content 空、HTTP 200、前端"静默空正文"。故正文生成必须显式关闭思考（task='generate'）。
        task="generate",
        max_tokens=outline.word_estimate * 2,
    )

    router = _get_router()
    full_content = ""
    # 客户端断开时释放底层 httpx 流连接（见 L8.2）
    gen = router.chat_stream(req, model_name=model or None)
    try:
        async for token in gen:
            full_content += token
            yield token  # 纯文本，由 event_stream 统一包装
    finally:
        if hasattr(gen, "aclose"):
            await gen.aclose()

    # 3. 保存章节（字数由正文统一计算，排除 fallback 前缀，见 L13.1）
    chapter = Chapter(
        chapter_number=ch_num,
        title=outline.title,
        content=full_content,
        outline=outline,
        model_used=model or "default",
        word_count=len(strip_fallback_prefix(full_content)),
    )
    novel_data.chapters.append(chapter)
    await anyio.to_thread.run_sync(_save_novel, novel_data, novel_id)

    # N2：结果（后端权威章节记录）随 done 载荷下发，前端据此拿到标题/字数与
    # 后续要挂上的注入清单；且这条 done 之后 event_stream 不会再补第二个。
    yield done_payload(chapter=chapter.model_dump(exclude_none=True))


@router.post("/chapter/v2")
async def generate_chapter_v2(req: ChapterV2Request):
    """装配器版章节生成（N4b）：注入清单随 done 载荷返回，作者可核"这次注入了什么"。

    与 `/chapter` 的区别：
    - 不做自动大纲；**节拍/主线/前情是手写的**（MVP-2 边界，见计划书 §2.1/§3）：
      缺省从小说目录读 `mainline.md` / `recap.md` / `beats/ch_XXXX.md`，也可由请求体直接传文本；
    - 上下文由装配器按槽位拼装（含上一章结尾、角色卡、风格块），并做两级预算裁剪；
    - done 载荷 = `{chapter, context_manifest}`（`context_manifest` 是**唯一**的对外键名，
      历史文档里的 `injection_manifest` 已废弃）—— manifest 与真正注入的文本一一对应。
    """
    novel_id = req.novel_id
    novel = await anyio.to_thread.run_sync(_load_novel, novel_id)
    if not novel:
        return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")

    # N8：不再从全局目录合并角色卡 —— 书里的 `characters` 字典就是本书自己的卡
    # （load_novel 已把它读进模型），装配器/提示词直接用；原来是"所有小说共用一副全局卡组"。

    # 风格块：profile_id 优先（与 /chat 同一套渲染）
    style_block = ""
    if req.profile_id:
        from story_engine.style.analyzer import StyleAnalyzer
        from story_engine.style.db import StyleDb

        profile = StyleDb().get_profile(req.profile_id)
        if profile:
            style_block = StyleAnalyzer.render_style_block(profile)
        else:
            logger.warning("文风画像不存在: %s", req.profile_id)

    return EventSourceResponse(
        event_stream(
            _stream_chapter_v2(novel, novel_id, req.chapter_number, req.chapter_title, req.model,
                               style_block, req.beat, req.mainline, req.recap, req.instruction)
        )
    )


async def _stream_chapter_v2(novel: Novel, novel_id: str, ch_num: int, title: str, model: str,
                             style_block: str, beat: str, mainline: str, recap: str,
                             instruction: str = ""):
    """装配 → 流式生成 → 保存章节 → done 载荷带注入清单（N4b）

    两种模式（N6）：
    - **生成**（`instruction` 为空）：按节拍写新章，**落盘**，注入清单同时落盘；
    - **带指令重写**（`instruction` 非空）：拿本章现有正文 + 作者指令重写，**只产出候选稿、绝不落盘**
      —— 作者在审稿页看着预览满意了，再自己点保存（覆盖正文是不可逆动作，不能由模型替作者决定）。
    """
    from story_engine.core.models import Chapter
    from story_engine.writer.context_sources import build_novel_builder
    from story_engine.writer.manifest_store import save_manifest

    rewrite = bool(instruction.strip())

    builder = build_novel_builder(
        novel,
        novel_id,
        chapter_number=ch_num,
        style_block=style_block,
        mainline_text=mainline,
        beat_text=beat,
        recap_text=recap,
    )
    assembled = await anyio.to_thread.run_sync(builder.build, {"novel_id": novel_id,
                                                              "chapter_number": ch_num})

    if rewrite:
        current = next((c for c in novel.chapters if c.chapter_number == ch_num), None)
        # 评审 P2-1：「章存在但正文是空的」也不能重写 —— 空 content 的章节是建章接口允许的
        # 状态，模型拿空正文"重写"只会凭空编一整章。
        if current is None or not (current.content or "").strip():
            yield error_payload(f"第{ch_num}章还没有正文，无法按指令重写（先按节拍生成）")
            return
        prompt = f"""下面是小说《{novel.title}》第{ch_num}章的现有正文：

【现有正文】
{current.content}

【作者的修改指令】
{instruction.strip()}

{assembled.text}

写作要求：
1. 只按【作者的修改指令】改动，其余情节、人物与文风尽量保持不变
2. 输出修改后的**完整章节正文**：不要解释、不要道歉、不要只给片段
3. 每段不超过300字"""
        max_tokens = 8192
    else:
        prompt = f"""请续写小说《{novel.title}》第{ch_num}章{'「' + title + '」' if title else ''}。

{assembled.text}

写作要求：
1. 严格按【本章节拍】推进，不要引入节拍之外的新设定
2. 保持角色性格与文风一致
3. 每段不超过300字
4. 章节末尾留悬念"""
        max_tokens = 8192

    logger.info(
        "章节生成(v2) | novel=%s ch=%s mode=%s 注入槽位=%s 注入token=%s 预算=%s 裁剪=%s 跳过=%s",
        novel_id, ch_num, "rewrite" if rewrite else "generate", len(assembled.manifest.entries),
        assembled.manifest.total_tokens, assembled.manifest.budget_tokens,
        [d.slot_id for d in assembled.manifest.dropped], [s.reason for s in assembled.manifest.skipped],
    )

    req = LLMRequest(
        system_prompt="你是一位专业的网络小说作家。",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        task=TASK_GENERATE,
        # 与 /chapter 的 `word_estimate * 2` 不同：v2 的节拍是手写的、没有字数估算，
        # 固定 8192 给够一次章节的余量（装配器已把输入压到预算内，不需要再按大纲缩放）
        max_tokens=max_tokens,
    )

    router = _get_router()
    full_content = ""
    gen = router.chat_stream(req, model_name=model or None)
    try:
        async for token in gen:
            full_content += token
            yield token
    finally:
        if hasattr(gen, "aclose"):
            await gen.aclose()

    existing = next((c for c in novel.chapters if c.chapter_number == ch_num), None)
    chapter = Chapter(
        chapter_number=ch_num,
        title=title or (existing.title if existing else f"第{ch_num}章"),
        content=full_content,
        model_used=model or "default",
        word_count=len(strip_fallback_prefix(full_content)),
    )

    if rewrite:
        # 候选稿：不 append、不 save —— 作者点保存才落盘。
        # 注入清单同样不落盘（重写没有"注入了什么"的新记录），故 manifest_persisted 缺省不报。
        yield done_payload(chapter=chapter.model_dump(exclude_none=True),
                           context_manifest=assembled.manifest.to_dict(),
                           rewrite=True, saved=False)
        return

    novel.chapters.append(chapter)
    await anyio.to_thread.run_sync(_save_novel, novel, novel_id)
    # 注入清单落盘（旁路，写失败只告警）—— N4b 评审待办，N6 承接。
    # 评审 P1-4：结果必须如实回报给作者，不能让"写盘失败"看起来像"没注入过"。
    persisted = await anyio.to_thread.run_sync(
        save_manifest, novel_id, ch_num, assembled.manifest.to_dict()
    )

    yield done_payload(chapter=chapter.model_dump(exclude_none=True),
                       context_manifest=assembled.manifest.to_dict(),
                       rewrite=False, saved=True,
                       manifest_persisted=persisted is not None)


@router.post("/chat")
async def chat_completion(req: ChatRequest):
    """自由对话 (SSE 流式) — 支持模式切换 + 联网搜索"""

    # 1. 确定系统提示词
    system_prompt = get_system_prompt(req.mode, req.system_prompt)

    # 1.5 文风注入（P5+）：写作模式下携带文风画像时注入 system prompt
    #     profile_id 优先 → 完整注入（量化特征 + 原文示例）；否则用 style_prompt 一句话
    if req.profile_id or req.style_prompt:
        style_block = ""
        if req.profile_id:
            from story_engine.style.analyzer import StyleAnalyzer
            from story_engine.style.db import StyleDb
            profile = StyleDb().get_profile(req.profile_id)
            if profile:
                style_block = StyleAnalyzer.render_style_block(profile)
            else:
                logger.warning("文风画像不存在: %s", req.profile_id)
        if not style_block and req.style_prompt:
            style_block = req.style_prompt
        if style_block:
            system_prompt = f"{system_prompt}\n\n请严格遵循以下文风风格进行创作，保持文风一致：\n{style_block}"

    # 2. 联网搜索（如果需要）
    search_context = ""
    if req.search:
        # 提取用户的最后一条消息作为搜索查询
        user_msgs = [m for m in req.messages if m.get("role") == "user"]
        raw_query = user_msgs[-1]["content"][:200] if user_msgs else ""

        # 查询改写：移除会触发垃圾结果的词
        query = raw_query
        # 移除"今天" → 否则 Bing 会返回"历史上的今天"
        for kw in ['今天', '最新', '最近']:
            query = query.replace(kw, '')
        query = query.strip()

        if not query:
            query = raw_query.strip()

        # 智能补充：中文"人工智能" Bing 理解不好，替换为 "AI"
        if '人工智能' in query:
            query = query.replace('人工智能', 'AI')

        # 如果查询不含年份且是"趋势/进展/新闻"类，追加年份
        need_year = any(kw in query for kw in ['进展', '趋势', '动态', '突破', '新闻', '消息', '技术', '发展'])
        if need_year and not re.search(r'20\d{2}', query):
            query = f"{query} 2026"

        logger.info(
            "搜索查询 | raw=%s cleaned=%s",
            raw_query[:60], query[:80],
        )
        resp = await search_web(query, extract_content=True, max_extract=2)
        search_context = format_search_context(resp)
        if search_context:
            system_prompt = f"{system_prompt}\n\n{search_context}"
            logger.info(
                "搜索注入 | query=%s engine=%s results=%d pages=%d len=%d model=%s",
                query, resp.engine_used, len(resp.results),
                len(resp.extracted_pages), len(search_context),
                req.model or "default",
            )
        else:
            logger.warning("搜索为空 | query=%s model=%s", query, req.model or "default")

    logger.info(
        "聊天请求 | model=%s mode=%s search=%s messages=%d",
        req.model or "default", req.mode, req.search, len(req.messages),
    )

    request = LLMRequest(
        system_prompt=system_prompt,
        messages=req.messages,
        temperature=req.temperature,
        # N3 评审 P1-1：自由对话也是正文（可能整段成文）→ 显式声明任务类型，
        # 不让"模型配置的 task"悄悄把关思考的模式带到这条链路上
        task=TASK_GENERATE,
        max_tokens=req.max_tokens,
    )

    if req.stream:
        return EventSourceResponse(
            event_stream(_stream_chat(request, req.model))
        )

    # 非流式
    router = _get_router()
    response = await router.chat(request, model_name=req.model or None)
    return ApiResponse(
        success=response.success,
        data={"content": response.content, "model": response.model},
        message=response.error if not response.success else "",
    )


async def _stream_chat(request: LLMRequest, model: str):
    router = _get_router()
    gen = router.chat_stream(request, model_name=model or None)
    try:
        async for token in gen:
            yield token
    finally:
        if hasattr(gen, "aclose"):
            await gen.aclose()


@router.post("/depolish")
async def depolish_chapter(novel_id: str = "", chapter_number: int = 1,
                           text: str = "", model: str = ""):
    """SSE 流式去AI味 — 消除AI生成痕迹，让文字回归自然"""
    # 获取文本
    if not text:
        if not novel_id:
            return ApiResponse(success=False, message="缺少 novel_id 或 text")
        novel = await anyio.to_thread.run_sync(_load_novel, novel_id)
        if not novel:
            return ApiResponse(success=False, message=f"小说 '{novel_id}' 不存在")
        chapter = None
        for c in novel.chapters:
            if c.chapter_number == chapter_number:
                chapter = c
                break
        if not chapter:
            return ApiResponse(success=False, message=f"章节 {chapter_number} 不存在")
        text = chapter.content

    if not text:
        return ApiResponse(success=False, message="文本不能为空")

    deai_prompt = (
        "你是一位让文字回归自然的编辑。请修改以下文字，消除AI生成常见的痕迹："
        "过于工整的句式、空洞的修饰词、生硬的排比、套路化表达。"
        "让文字像人类自然书写一样有温度和有呼吸感。只返回修改后的文本。"
    )

    request = LLMRequest(
        system_prompt=deai_prompt,
        messages=[{"role": "user", "content": text}],
        temperature=0.7,
        # N3 评审 P1-1：去 AI 味是改写正文 → 同样显式关思考
        task=TASK_GENERATE,
        max_tokens=4096,
    )

    return EventSourceResponse(
        event_stream(_stream_depolish(request, model))
    )


async def _stream_depolish(request: LLMRequest, model: str):
    router = _get_router()
    gen = router.chat_stream(request, model_name=model or None)
    try:
        async for token in gen:
            yield token
    finally:
        if hasattr(gen, "aclose"):
            await gen.aclose()
