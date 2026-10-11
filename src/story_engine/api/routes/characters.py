"""角色卡路由（N8）—— 卡属于某一本小说（不再有全局卡目录）。

为什么单独一个文件：`novel.py` 的前缀是 `/api/novel`，但素材库的两个端点不属于"某本小说"
（`/api/library/characters`），混在同一个前缀下语义会错位（同 N5 的 check.py 处理方式）。

契约：

    GET    /api/novel/{novel_id}/characters                     列出本书的卡（含全部字段）
    POST   /api/novel/{novel_id}/characters                     新建（同名已存在 → success=false，不静默覆盖）
    PUT    /api/novel/{novel_id}/characters/{name}              更新（不存在 → success=false）
    DELETE /api/novel/{novel_id}/characters/{name}              删除
    GET    /api/library/characters                              素材库列表
    POST   /api/novel/{novel_id}/characters/{name}/to-library    把本书的卡另存为素材（纯复制）
    POST   /api/novel/{novel_id}/characters/import              从素材库/别的书复制一张进来

「复制」语义（用户定的方案 A）：素材库只是**复制来源**，不是共享引用 ——
导入之后两边各自独立，改任一边都不影响另一边。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from story_engine.api.schemas import ApiResponse
from story_engine.characters import library
from story_engine.characters.manager import (
    NovelNotFound,
    delete_card,
    list_cards,
    load_card,
    save_card,
    search_cards,
)
from story_engine.core.models import CharacterCard

logger = logging.getLogger("story_engine.api")

router = APIRouter(prefix="/api", tags=["characters"])


class ImportCardRequest(BaseModel):
    """从素材库（或别的书）复制一张卡进来。"""

    source: str = Field(default="library", description="library = 素材库；否则视为源小说 ID")
    name: str = Field(min_length=1, description="源卡名")
    new_name: str = Field(default="", description="导入后的新名字（留空=沿用原名）")
    overwrite: bool = Field(default=False, description="同名已存在时是否覆盖")


def _cards_payload(novel_id: str) -> dict:
    names = list_cards(novel_id)
    cards = [load_card(novel_id, n) for n in names]
    return {
        "novel_id": novel_id,
        "names": names,
        "cards": [c.model_dump(exclude_none=True) for c in cards if c is not None],
    }


@router.get("/novel/{novel_id}/characters")
def api_list_characters(novel_id: str, q: str = "") -> ApiResponse:
    """列出本书的角色卡（`q` 给了就按关键词过滤：名字/描述/性格）。"""
    try:
        if q.strip():
            hits = search_cards(novel_id, q)
            return ApiResponse(success=True, data={
                "novel_id": novel_id,
                "names": hits,
                "cards": [
                    c.model_dump(exclude_none=True)
                    for c in (load_card(novel_id, n) for n in hits) if c is not None
                ],
            })
        return ApiResponse(success=True, data=_cards_payload(novel_id))
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))


@router.post("/novel/{novel_id}/characters")
def api_create_character(novel_id: str, card: CharacterCard) -> ApiResponse:
    """新建角色卡。同名已存在必须显式失败 —— 不能把作者的卡悄悄覆盖掉。"""
    try:
        if not save_card(novel_id, card):
            return ApiResponse(
                success=False,
                message=f"角色卡「{card.name}」已存在；要改请走更新（PUT），或先删掉",
            )
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))
    return ApiResponse(success=True, data=card.model_dump(exclude_none=True))


@router.put("/novel/{novel_id}/characters/{name}")
def api_update_character(novel_id: str, name: str, card: CharacterCard) -> ApiResponse:
    """更新角色卡（改名字 = 删旧建新，避免目录里留下两张）。"""
    try:
        if load_card(novel_id, name) is None:
            return ApiResponse(success=False, message=f"角色卡「{name}」不存在")
        if card.name != name:
            delete_card(novel_id, name)
        save_card(novel_id, card, overwrite=True)
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))
    return ApiResponse(success=True, data=card.model_dump(exclude_none=True))


@router.delete("/novel/{novel_id}/characters/{name}")
def api_delete_character(novel_id: str, name: str) -> ApiResponse:
    try:
        if not delete_card(novel_id, name):
            return ApiResponse(success=False, message=f"角色卡「{name}」不存在")
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))
    return ApiResponse(success=True, data={"deleted": name})


@router.get("/library/characters")
def api_list_library() -> ApiResponse:
    """素材库里的角色卡（只用于复制，不是任何书的运行时依赖）。"""
    names = library.list_library()
    return ApiResponse(success=True, data={
        "names": names,
        "cards": [
            c.model_dump(exclude_none=True)
            for c in (library.load_from_library(n) for n in names) if c is not None
        ],
    })


@router.post("/novel/{novel_id}/characters/{name}/to-library")
def api_export_to_library(novel_id: str, name: str, new_name: str = "") -> ApiResponse:
    """把本书的一张卡**复制**成素材库条目（源卡不受影响）。"""
    try:
        if not library.export_to_library(novel_id, name, new_name=new_name):
            return ApiResponse(success=False, message=f"角色卡「{name}」不存在")
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))
    return ApiResponse(success=True, data={"saved_to_library": new_name or name})


@router.post("/novel/{novel_id}/characters/import")
def api_import_character(novel_id: str, req: ImportCardRequest) -> ApiResponse:
    """从素材库或另一本书**复制**一张卡进这本书。"""
    try:
        if req.source == "library":
            ok = library.import_from_library(
                novel_id, req.name, new_name=req.new_name, overwrite=req.overwrite
            )
            origin_msg = "素材库"
        else:
            src = load_card(req.source, req.name)
            if src is None:
                return ApiResponse(success=False, message=f"源小说「{req.source}」里没有「{req.name}」")
            card = src.model_copy(update={"name": req.new_name}) if req.new_name else src
            ok = save_card(novel_id, card, overwrite=req.overwrite)
            origin_msg = f"《{req.source}》"
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))

    if not ok:
        return ApiResponse(
            success=False,
            message=f"导入失败：本书已有同名角色卡「{req.new_name or req.name}」（可勾选覆盖）",
        )
    logger.info("角色卡导入 | %s → %s | 源=%s", req.name, novel_id, req.source)
    return ApiResponse(
        success=True,
        data={"name": req.new_name or req.name, "from": origin_msg},
        message=f"已从{origin_msg}复制「{req.new_name or req.name}」进本书",
    )
