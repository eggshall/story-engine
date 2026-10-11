"""校验路由（N5）— `POST /api/check/chapter`：给一段/一章正文，返回结构化校验报告。

为什么单独一个路由文件（计划书 P0-6）：`generate.py` 的 router 前缀是 `/api/generate`，
校验接口的路径是 `/api/check/chapter`，混在一起会让前缀语义错位。

契约（契约测试就是按这个断言的）：

    POST /api/check/chapter  {text} 或 {novel_id, chapter_number, profile_id?}
    → ApiResponse(data=CheckReportPayload)
      data.level          alert / warn / ok / skipped（整章级别 = 最严重的发现）
      data.findings[]     每条含 rule_id / rule_name / level / suggestion / location{start,end,paragraph_index,excerpt}
      data.summary        各级别计数
      data.baseline_source  profile / previous_chapters / none（none 时对话占比为 skipped，不误报）

基线策略（评审项"漂移基线来源"）：风格画像 > 前序章节中位数 > 无（无基线不报 alert）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from story_engine.api.schemas import ApiResponse, CheckChapterRequest, CheckReportPayload
from story_engine.check.rules import build_baseline, run_rules

logger = logging.getLogger("story_engine.api")

router = APIRouter(prefix="/api/check", tags=["check"])

# 自动模式下最多用多少章做基线（再多只是拖慢请求，中位数早就稳定了）
AUTO_BASELINE_CHAPTERS = 10


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

    report = run_rules(text, baseline)
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
    # 说明：校验报告目前是**即时返回**（确定性、可重算，不必落盘）。
    # `context_manifest` 的落盘待办（计划书 §8）由 N6 承接，与本接口无关。
    return ApiResponse(success=True, data=payload.model_dump())
