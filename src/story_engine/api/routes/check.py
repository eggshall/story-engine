"""校验路由（N5）— `POST /api/check/chapter`：给一段/一章正文，返回结构化校验报告。

为什么单独一个路由文件（计划书 P0-6）：`generate.py` 的 router 前缀是 `/api/generate`，
校验接口的路径是 `/api/check/chapter`，混在一起会让前缀语义错位。

契约（契约测试就是按这个断言的）：

    POST /api/check/chapter  {text} 或 {novel_id, chapter_number, profile_id?}
    → ApiResponse(data=CheckReportPayload)
      data.level          alert / warn / ok（整章级别 = 最严重的**可执行结论**；跳过不进级别）
      data.findings[]     每条含 rule_id / rule_name / level / suggestion / location{start,end,paragraph_index,excerpt}
      data.summary        各级别计数
      data.by_rule        按规则聚合的级别计数（审稿页中栏按此分组）
      data.incomplete     是否有规则因缺基线被跳过（true 时 skipped_rules 说明是哪些）
      data.baseline_source  profile / previous_chapters / none（none 时对话占比为 skipped，不误报）

    GET  /api/check/manifest?novel_id=&chapter_number=
    → ApiResponse(data=<生成时落盘的注入清单>)

基线策略（评审项"漂移基线来源"）：风格画像 > 前序章节中位数 > 无（无基线不报 alert）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from story_engine.api.schemas import ApiResponse, CheckChapterRequest, CheckReportPayload
from story_engine.check.rules import (
    DEFAULT_RULES,
    THREAD_RULES,
    ThreadContext,
    build_baseline,
    run_rules,
)
from story_engine.writer.manifest_store import load_manifest

logger = logging.getLogger("story_engine.api")

router = APIRouter(prefix="/api/check", tags=["check"])

# 自动模式下最多用多少章做基线（再多只是拖慢请求，中位数早就稳定了）
AUTO_BASELINE_CHAPTERS = 10


@router.get("/manifest")
def get_manifest(novel_id: str, chapter_number: int) -> ApiResponse:
    """读回某章生成时落盘的注入清单（N6）。

    存在的意义：`context_manifest` 随 SSE `done` 只下发一次，刷新即丢；作者事后要核
    "这一章到底注入了哪些设定/技法/前情"时得有地方查。生成时由 `POST /api/generate/chapter/v2`
    旁路写盘（`<小说目录>/manifests/ch_XXXX.json`）。

    语义边界（评审 P1-4 / P2-5）：
    - 清单是**"生成时注入了什么"的记录**，作者保存候选稿不会改写它；
    - 读不到时给的是**中性**原因（可能写盘失败，也可能这章确实不是装配器生成的），
      不能说成"肯定没注入"；写盘是否成功会在 v2 的 done 载荷里用 `manifest_persisted` 如实回报；
    - `novel_id` 先过 `_safe_novel_id`：非法 id 会让 `manifest_path` 抛 ValueError（500），
      这里直接给可读的失败响应。
    """
    from story_engine.tools.novel_storage import _safe_novel_id

    try:
        novel_id = _safe_novel_id(novel_id)
    except (ValueError, TypeError) as e:
        return ApiResponse(success=False, message=f"小说 ID 不合法：{e}")
    if chapter_number < 1:
        return ApiResponse(success=False, message=f"章节号必须 ≥ 1，收到 {chapter_number}")

    manifest = load_manifest(novel_id, chapter_number)
    if manifest is None:
        return ApiResponse(
            success=False,
            message=f"第{chapter_number}章没有注入清单（可能写盘失败，或该章不是装配器生成的）",
        )
    return ApiResponse(success=True, data=manifest)


def _load_chapter_text(novel_id: str, chapter_number: int) -> tuple[str, list[str]]:
    """读取指定章节正文 + 它之前各章的正文（用于基线）。返回 (text, previous_texts)。"""
    from story_engine.tools.novel_storage import load_novel

    novel = load_novel(novel_id)
    if not novel:
        return "", []
    chapters = sorted(getattr(novel, "chapters", []) or [], key=lambda c: c.chapter_number)
    target = next((c for c in chapters if c.chapter_number == chapter_number), None)
    if target is None:
        return "", []
    previous = [c.content or "" for c in chapters if c.chapter_number < chapter_number]
    return target.content or "", previous


def _load_previous_texts(novel_id: str, chapter_number: int) -> list[str]:
    """只取前序章节正文（做基线用）。

    为什么单独一个函数（N6 评审 P1-2）：审稿页校验的是**候选稿文本**，正文得用请求里的
    `text`，但基线仍应来自这本书的前序章节。原来 text 非空就完全不走磁盘，
    于是"对话占比"这条相对指标在审稿页永远 skipped —— 作者永远拿不到它。
    """
    from story_engine.tools.novel_storage import load_novel

    novel = load_novel(novel_id)
    if not novel:
        return []
    chapters = sorted(getattr(novel, "chapters", []) or [], key=lambda c: c.chapter_number)
    return [c.content or "" for c in chapters if c.chapter_number < chapter_number]


def _profile_features(profile_id: str) -> dict:
    if not profile_id:
        return {}
    try:
        from story_engine.style.db import StyleDb

        profile = StyleDb().get_profile(profile_id)
    except Exception as e:  # noqa: BLE001 —— 画像读不到不该让校验失败
        logger.warning("读取风格画像失败（基线降级）: %s", e)
        return {}
    if not profile:
        logger.warning("文风画像不存在: %s", profile_id)
        return {}
    features = getattr(profile, "features", None)
    if isinstance(features, dict):
        return features
    return {}


def _load_thread_context(novel_id: str, chapter_number: int | None) -> ThreadContext | None:
    """读这本书的伏笔账本；**没有账本返回 None**（调用方据此不跑伏笔规则）。

    为什么是 None 而不是"空 ThreadContext"（N9 的取舍）：账本为空时若照跑那两条规则，
    每本还没用过账本的旧书都会在报告里凭空多出两条 `skipped` 规则，改变 N5 既定的响应形状。
    取最小影响：**没账本 → 这两条规则不参与**，既有 5 条规则的行为一字不变。
    """
    if not novel_id:
        return None
    from story_engine.tools.novel_storage import load_novel

    novel = load_novel(novel_id)
    if novel is None:
        return None
    threads = getattr(novel, "threads", None) or {}
    if not threads:
        return None
    chapters = getattr(novel, "chapters", []) or []
    return ThreadContext(
        threads=threads,
        # 缺省/0 一律规范成 None（评审 P2-8）：否则 `planted_chapter > 0` 会把条目
        # 全判成"还没埋到"，悬空规则给出 `ok` —— 而它的本意是"缺章号就不判"
        chapter_number=chapter_number or None,
        known_chapters=sorted(c.chapter_number for c in chapters),
    )


@router.post("/chapter")
def check_chapter(req: CheckChapterRequest) -> ApiResponse:
    """校验一章（或一段）正文，返回级别 + 定位 + 建议。

    同步 `def`（不是 async）：规则是纯 CPU 短计算，FastAPI 会自动丢线程池，
    省掉手写 `anyio.to_thread.run_sync`（N5 评审 P2）。

    偏移契约（评审 P1-4）：`location.start/end` 是相对**请求原文**的字符偏移 ——
    这里不做 `strip()`（只判空），否则前端拿原文按 start:end 跳转会整体错位。
    """
    raw_text = req.text or ""
    text = raw_text
    previous_texts: list[str] = []

    # 基线与前序章节：只要给了 novel_id + chapter_number 就去读（**不管**正文是不是请求里带的）
    # —— 审稿页校验的是候选稿，正文用 text，基线用这本书自己的前序章节（评审 P1-2）。
    if req.novel_id and req.chapter_number:
        previous_texts = _load_previous_texts(req.novel_id, req.chapter_number)

    if not text.strip():
        if not req.novel_id or not req.chapter_number:
            return ApiResponse(
                success=False,
                message="需要 text，或 novel_id + chapter_number（二选一）",
            )
        text, previous_texts = _load_chapter_text(req.novel_id, req.chapter_number)
        if not text:
            return ApiResponse(
                success=False,
                message=f"小说 '{req.novel_id}' 的第 {req.chapter_number} 章不存在或内容为空",
            )

    limit = req.baseline_chapters or AUTO_BASELINE_CHAPTERS
    profile_features = _profile_features(req.profile_id)
    baseline = build_baseline(profile_features, previous_texts[-limit:] if previous_texts else [])

    # 伏笔账本规则（N9）：有账本才加进来（见 _load_thread_context 的取舍说明）
    rules: list[str] = list(DEFAULT_RULES)
    thread_context = _load_thread_context(req.novel_id, req.chapter_number)
    if thread_context is not None:
        rules += list(THREAD_RULES)

    report = run_rules(text, baseline, rules=rules, thread_context=thread_context)
    # 用 schema 过一遍：字段漂移会在这里炸掉，而不是让前端拿到 undefined
    payload = CheckReportPayload.model_validate(report.to_dict())

    logger.info(
        "章节校验 | novel=%s ch=%s len=%d level=%s 基线=%s 不完整=%s 发现=%s",
        req.novel_id or "-",
        req.chapter_number or "-",
        payload.text_length,
        payload.level,
        payload.baseline_source,
        payload.incomplete,
        payload.summary,
    )
    # 说明：校验报告目前是**即时返回**（确定性、可重算，不必落盘）；
    # 要长期回看的是**注入清单**，它由 v2 生成时写盘、经 GET /api/check/manifest 读回。
    return ApiResponse(success=True, data=payload.model_dump())
