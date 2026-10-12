"""伏笔账本路由（N9）—— 账本属于某一本小说。

单独一个文件的原因与 `characters.py` 相同：资源语义独立，混进 `novel.py` 会让那一坨更重。

契约：

    GET    /api/novel/{novel_id}/threads                        列出本书的伏笔
    POST   /api/novel/{novel_id}/threads                        新建（同 id 已存在 → success=false）
    PUT    /api/novel/{novel_id}/threads/{thread_id}            更新
    DELETE /api/novel/{novel_id}/threads/{thread_id}            删除
    POST   /api/novel/{novel_id}/threads/{thread_id}/advance    推进状态（埋设 → 推进 → 回收/放弃）

「不静默覆盖」与角色卡一致：同 id 新建必须显式失败，否则会把作者记的伏笔悄悄改掉。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import ConfigDict, Field

from story_engine.api.schemas import APIModel, ApiResponse
from story_engine.core.models import PlotThread
from story_engine.threads.manager import (
    NovelNotFound,
    advance_thread,
    delete_thread,
    list_threads,
    load_thread,
    save_thread,
)

logger = logging.getLogger("story_engine.api")

router = APIRouter(prefix="/api", tags=["threads"])

_THREAD_STATUS_RE = r"^(planted|developed|paid_off|abandoned)$"


class PlotThreadRequest(APIModel):
    """请求体：兼容 camelCase / snake_case，且**拒绝未知字段**。

    评审 P2-1（实测）：原来直接复用 core 的 `PlotThread`（普通 BaseModel），前端按文档发
    `plantedChapter` 会被**静默丢弃**（存成 0 且 `success=true`）—— 正是 AGENTS 里点名的
    camelCase 静默失效。这里在边界上补两件事：① `APIModel` 给 camelCase 别名；
    ② `extra="forbid"` 让拼错的字段直接 422，而不是悄悄丢掉作者的数据。

    字段清单必须与 `core.models.PlotThread` 一致；有测试钉死（`test_request_model_matches_core`）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = ""
    status: str = Field(default="planted", pattern=_THREAD_STATUS_RE)
    planted_chapter: int = Field(default=0, ge=0)
    payoff_chapter: Optional[int] = Field(default=None, ge=0)
    strength: int = Field(default=3, ge=1, le=5)
    note: str = ""

    def to_model(self) -> PlotThread:
        return PlotThread(**self.model_dump())


class AdvanceThreadRequest(APIModel):
    """推进伏笔状态。`chapter_number` 只在 `paid_off` 时用于记回收章（推进 ≠ 回收）。

    这里**刻意不给 `status` 加 pattern**：非法状态由 `advance_thread` 抛 `ValueError` 并转成
    `success=false` + 可读原因（契约测试 `test_invalid_status_is_rejected_not_500` 钉死了这一点），
    加 pattern 会变成 422 而丢掉那句人话。
    """

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="planted / developed / paid_off / abandoned")
    chapter_number: Optional[int] = Field(default=None, ge=0, description="发生变化的章号")


def _threads_payload(novel_id: str) -> dict:
    ids = list_threads(novel_id)
    threads = [load_thread(novel_id, t) for t in ids]
    return {
        "novel_id": novel_id,
        "ids": ids,
        "threads": [t.model_dump(exclude_none=True) for t in threads if t is not None],
    }


@router.get("/novel/{novel_id}/threads")
def api_list_threads(novel_id: str) -> ApiResponse:
    """列出本书的伏笔账本（含全部字段）。"""
    try:
        return ApiResponse(success=True, data=_threads_payload(novel_id))
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))


@router.post("/novel/{novel_id}/threads")
def api_create_thread(novel_id: str, thread: PlotThreadRequest) -> ApiResponse:
    """新建伏笔。同 id 已存在必须显式失败 —— 不能把作者的账本悄悄覆盖掉。"""
    thread_model = thread.to_model()
    try:
        if not save_thread(novel_id, thread_model):
            return ApiResponse(
                success=False,
                message=f"伏笔「{thread_model.id}」已存在；要改请走更新（PUT），或先删掉",
            )
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))
    return ApiResponse(success=True, data=thread_model.model_dump(exclude_none=True))


@router.put("/novel/{novel_id}/threads/{thread_id}")
def api_update_thread(novel_id: str, thread_id: str, thread: PlotThreadRequest) -> ApiResponse:
    """更新伏笔。

    改 id = 删旧建新，但**目标 id 已存在时必须失败** —— 评审 P1-1：原来这里直接
    `save_thread(overwrite=True)`，于是 PUT `/threads/t1` 且 body 里 id 写 `t2` 会把
    `t2` 静默改写掉（`success=true`），违背本节点「不静默覆盖作者的账本」这条原则。
    """
    thread_model = thread.to_model()
    try:
        if load_thread(novel_id, thread_id) is None:
            return ApiResponse(success=False, message=f"伏笔「{thread_id}」不存在")
        if thread_model.id != thread_id:
            if load_thread(novel_id, thread_model.id) is not None:
                return ApiResponse(
                    success=False,
                    message=(
                        f"改 id 失败：伏笔「{thread_model.id}」已存在，不能覆盖它；"
                        "请换一个 id，或先把那条删掉"
                    ),
                )
            delete_thread(novel_id, thread_id)
            ok = save_thread(novel_id, thread_model, overwrite=False)
        else:
            ok = save_thread(novel_id, thread_model, overwrite=True)
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))

    if not ok:
        return ApiResponse(success=False, message=f"伏笔「{thread_model.id}」保存失败")
    return ApiResponse(success=True, data=thread_model.model_dump(exclude_none=True))


@router.delete("/novel/{novel_id}/threads/{thread_id}")
def api_delete_thread(novel_id: str, thread_id: str) -> ApiResponse:
    try:
        if not delete_thread(novel_id, thread_id):
            return ApiResponse(success=False, message=f"伏笔「{thread_id}」不存在")
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))
    return ApiResponse(success=True, data={"deleted": thread_id})


@router.post("/novel/{novel_id}/threads/{thread_id}/advance")
def api_advance_thread(
    novel_id: str, thread_id: str, req: AdvanceThreadRequest
) -> ApiResponse:
    """推进状态。非法状态返回 `success=false`（**不是 500** —— 这是用户输入问题）。"""
    try:
        updated = advance_thread(novel_id, thread_id, req.status, req.chapter_number)
    except ValueError as e:
        return ApiResponse(success=False, message=str(e))
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))

    if updated is None:
        return ApiResponse(success=False, message=f"伏笔「{thread_id}」不存在")
    return ApiResponse(success=True, data=updated.model_dump(exclude_none=True))
