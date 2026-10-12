"""世界观设定集路由（N8）—— 设定集属于某一本小说。

与 `characters.py` 同构（角色卡那套先做，这里照抄语义）；单独一个文件的原因同 `threads.py`：
资源语义独立，混进 `novel.py` 会让那一坨更重。

契约：

    GET    /api/novel/{novel_id}/lorebooks                      列出本书的设定集（含全部条目）
    POST   /api/novel/{novel_id}/lorebooks                      新建（同名已存在 → success=false）
    PUT    /api/novel/{novel_id}/lorebooks/{name}               更新（改名 = 删旧建新；目标已存在则失败）
    DELETE /api/novel/{novel_id}/lorebooks/{name}               删除
    GET    /api/library/lorebooks                               素材库列表
    POST   /api/novel/{novel_id}/lorebooks/{name}/to-library    把本书的设定集另存为素材（纯复制）
    POST   /api/novel/{novel_id}/lorebooks/import               从素材库/别的书复制一个进来

**「不静默覆盖」是本项目反复强调的原则**（N9 评审 P1-1 在伏笔上正是这条）：同名新建必须
显式失败；改名时若目标名已被占用也必须失败 —— 否则「删旧建新」会把另一条设定静默吃掉。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import ConfigDict, Field

from story_engine.api.schemas import APIModel, ApiResponse
from story_engine.core.models import LoreBook, LorebookEntry
from story_engine.lore import library
from story_engine.lore.lorebook import (
    NovelNotFound,
    delete_lorebook,
    find_matching_entries,
    list_lorebooks,
    load_lorebook,
    save_lorebook,
)

logger = logging.getLogger("story_engine.api")

router = APIRouter(prefix="/api", tags=["lorebooks"])


class LorebookEntryRequest(LorebookEntry):
    """请求专用的条目模型：**拒绝未知字段**。

    只在请求边界加 `extra="forbid"`，**不动 `core.models.LorebookEntry`** —— 那是磁盘数据模型，
    对旧文件里多出来的键保持宽容才不会让老书加载失败（N8 评审 P2-2）。
    """

    model_config = ConfigDict(extra="forbid")


class LoreBookRequest(APIModel):
    """请求体（**独立的边界模型**，不是 `LoreBook` 的子类）。

    为什么不继承：`LoreBook.entries` 是 `Dict[str, LorebookEntry]`，子类想换成更严格的
    `Dict[str, LorebookEntryRequest]` 会撞上「可变类型不协变」（类型检查器报
    `reportIncompatibleVariableOverride`）；独立模型 + `to_book()` 更直白，也顺带把
    「请求模型实例被存进 `Novel.lorebooks`」这种混用挡掉。

    边界上做三件事（都是 N8 评审的处置）：
    ① 顶层拼错字段 → 422；② 条目里拼错字段也 → 422（`LorebookEntryRequest`）；
    ③ `name` 非空 —— 空名的镜像会落成 `untitled.json`，与任何 slug 为 `untitled` 的名字碰撞。
    只约束请求，**不动磁盘模型** `LoreBook`/`LorebookEntry`（对旧文件多出来的键保持宽容，
    否则老书会加载失败）。
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="设定集名称")
    description: str = Field(default="", description="设定集描述")
    entries: dict[str, LorebookEntryRequest] = Field(default_factory=dict, description="条目")
    version: str = Field(default="1.0")

    def to_book(self) -> LoreBook:
        """转成磁盘模型（嵌套条目降级为 `LorebookEntry`）。"""
        return LoreBook(
            name=self.name,
            description=self.description,
            entries={k: LorebookEntry(**e.model_dump()) for k, e in self.entries.items()},
            version=self.version,
        )


class ImportLoreBookRequest(APIModel):
    """从素材库（或别的书）复制一个设定集进来。

    继承 `APIModel` 以兼容 camelCase（`newName`）—— 前端按项目约定发驼峰，
    用普通 `BaseModel` 会让 `newName` 被静默忽略（N8 评审 P2-3）。
    """

    source: str = Field(default="library", description="library = 素材库；否则视为源小说 ID")
    name: str = Field(min_length=1, description="源设定集名")
    new_name: str = Field(default="", description="导入后的新名字（留空=沿用原名）")
    overwrite: bool = Field(default=False, description="同名已存在时是否覆盖")


def _books_payload(novel_id: str) -> dict:
    names = list_lorebooks(novel_id)
    books = [load_lorebook(novel_id, n) for n in names]
    return {
        "novel_id": novel_id,
        "names": names,
        "books": [b.model_dump(exclude_none=True) for b in books if b is not None],
    }


def _books_map(novel_id: str) -> dict[str, LoreBook]:
    """本书的设定集映射（`find_matching_entries` 要的形态）。"""
    return {n: b for n in list_lorebooks(novel_id) if (b := load_lorebook(novel_id, n)) is not None}


class LorebookPreviewRequest(APIModel):
    """触发预览请求：给一段文本，问"哪些设定条目会被注入"。"""

    text: str = Field(default="", max_length=200_000)


@router.post("/novel/{novel_id}/lorebooks/preview")
def api_preview_lorebooks(novel_id: str, req: LorebookPreviewRequest) -> ApiResponse:
    """关键词触发预览（只读，不写盘）。

    **为什么在后端算而不是前端**：匹配的真源是 `lore/lorebook.py::find_matching_entries`
    （纯函数），装配器 `_lore_provider` 用的就是它。前端再实现一遍就会出现
    "预览说会注入、真写时却不注入"的分叉 —— 正是第五切片评审 P1-1 批评的那类"两处定义"。
    这里复用同一个函数、同一个上限 `LORE_MAX_ENTRIES`，并把**超出上限被丢掉的条数如实报出来**
    （与装配器 `lore:overflow` 同一口径：不许静默截断）。

    与真实写作的差别（必须说清）：真实触发源是**紧邻的上一章正文**（`previous_chapter_text`），
    这里用的是作者自己输入的文本 —— 所以这是"预览"，不是"本次一定会注入的清单"。
    """
    # 懒导入：`context_sources` 会连带拉起装配器那一坨，放在函数里避免把 API 启动路径变重
    from story_engine.writer.context_sources import LORE_MAX_ENTRIES

    try:
        books = _books_map(novel_id)
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))

    text = req.text or ""
    matched = find_matching_entries(books, text, max_results=None)
    kept = matched[:LORE_MAX_ENTRIES]
    return ApiResponse(
        success=True,
        data={
            "matches": [
                {
                    "book": book_name,
                    "entry_id": entry_id,
                    "keys_hit": [k for k in entry.keys if k in text],
                    "priority": entry.priority,
                    "content": entry.content,
                }
                for book_name, entry_id, entry in kept
            ],
            "count": len(kept),
            "overflow": max(0, len(matched) - LORE_MAX_ENTRIES),
            "text_length": len(text),
        },
    )


@router.get("/novel/{novel_id}/lorebooks")
def api_list_lorebooks(novel_id: str) -> ApiResponse:
    """列出本书的设定集（含全部条目，供前端直接渲染）。"""
    try:
        return ApiResponse(success=True, data=_books_payload(novel_id))
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))


@router.post("/novel/{novel_id}/lorebooks")
def api_create_lorebook(novel_id: str, req: LoreBookRequest) -> ApiResponse:
    """新建设定集。同名已存在必须显式失败 —— 不能把作者的设定悄悄覆盖掉。"""
    book = req.to_book()
    try:
        if not save_lorebook(novel_id, book):
            return ApiResponse(
                success=False,
                message=f"设定集「{book.name}」已存在；要改请走更新（PUT），或先删掉",
            )
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))
    return ApiResponse(success=True, data=book.model_dump(exclude_none=True))


@router.put("/novel/{novel_id}/lorebooks/{name}")
def api_update_lorebook(novel_id: str, name: str, req: LoreBookRequest) -> ApiResponse:
    """更新设定集（改名字 = 删旧建新）。

    改名时目标名**必须未被占用**才允许：`save_lorebook(..., overwrite=True)` 会无条件写，
    配上「删旧建新」就能把另一条设定静默吃掉（N9 评审 P1-1 类缺陷）。
    """
    book = req.to_book()
    try:
        if load_lorebook(novel_id, name) is None:
            return ApiResponse(success=False, message=f"设定集「{name}」不存在")
        if book.name != name:
            if load_lorebook(novel_id, book.name) is not None:
                return ApiResponse(
                    success=False,
                    message=f"已存在「{book.name}」，改名会覆盖它；请换个名字或先删掉那条",
                )
            delete_lorebook(novel_id, name)
        save_lorebook(novel_id, book, overwrite=True)
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))
    return ApiResponse(success=True, data=book.model_dump(exclude_none=True))


@router.delete("/novel/{novel_id}/lorebooks/{name}")
def api_delete_lorebook(novel_id: str, name: str) -> ApiResponse:
    try:
        if not delete_lorebook(novel_id, name):
            return ApiResponse(success=False, message=f"设定集「{name}」不存在")
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))
    return ApiResponse(success=True, data={"deleted": name})


@router.get("/library/lorebooks")
def api_list_library() -> ApiResponse:
    """素材库里的设定集（只用于复制，不是任何书的运行时依赖）。"""
    names = library.list_library()
    return ApiResponse(success=True, data={
        "names": names,
        "books": [
            b.model_dump(exclude_none=True)
            for b in (library.load_from_library(n) for n in names) if b is not None
        ],
    })


@router.post("/novel/{novel_id}/lorebooks/{name}/to-library")
def api_export_to_library(
    novel_id: str, name: str, new_name: str = "", overwrite: bool = False
) -> ApiResponse:
    """把本书的一个设定集**复制**成素材库条目（源设定集不受影响）。

    `new_name` 走 **query**（与角色卡那条端点一致 —— 前端 `exportCharacterToLibrary`
    就是这么发的）。返回值是素材的**身份名**，不是请求里的原始字符串。

    失败原因分开说（N8 评审 P1-2）：**源不存在**与**文件名被别的身份占用**是两回事，
    混成一个 `success=false` 会让界面提示撒谎。同名同身份重复另存是幂等的；只有不同名字
    映射到同一文件名（`_slug` 有损，如 `"A B"` 与 `"A_B"`）才需要 `overwrite=true`。
    """
    try:
        result = library.export_to_library(novel_id, name, new_name=new_name, overwrite=overwrite)
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))

    if result == "source_missing":
        return ApiResponse(success=False, message=f"设定集「{name}」不存在")
    if result == "name_taken":
        taken = new_name or name
        return ApiResponse(
            success=False,
            message=f"素材库里已有另一份设定集占用了「{taken}」对应的文件名"
                    f"（不同名字可能映射到同一文件）；换个名字或加 overwrite=true",
        )
    if result == "write_failed":
        return ApiResponse(success=False, message="素材写盘失败，详见服务端日志")
    return ApiResponse(success=True, data={"saved_to_library": new_name or name})


@router.post("/novel/{novel_id}/lorebooks/import")
def api_import_lorebook(novel_id: str, req: ImportLoreBookRequest) -> ApiResponse:
    """从素材库或另一本书**复制**一个设定集进这本书。

    「素材库里没有这份设定集」与「本书已有同名设定集」必须给**不同**提示：原来两者都返回
    False，界面于是对着一份根本不存在的素材反复让人勾「覆盖」（N8 评审 P1-2）。
    """
    try:
        if req.source == "library":
            result = library.import_from_library(
                novel_id, req.name, new_name=req.new_name, overwrite=req.overwrite
            )
            origin_msg = "素材库"
        else:
            src = load_lorebook(req.source, req.name)
            if src is None:
                return ApiResponse(success=False, message=f"源小说「{req.source}」里没有「{req.name}」")
            book = src.model_copy(update={"name": req.new_name}) if req.new_name else src
            result = "ok" if save_lorebook(novel_id, book, overwrite=req.overwrite) else "target_exists"
            origin_msg = f"《{req.source}》"
    except NovelNotFound as e:
        return ApiResponse(success=False, message=str(e))
    except ValueError:
        # `source` 不是合法小说 id（如 "../../etc/passwd"）时 `_safe_novel_id` 抛 ValueError。
        # 用户可控输入不该变成 HTTP 500（N8 评审 P1-3）。
        return ApiResponse(success=False, message=f"源标识非法：{req.source}")

    if result == "source_missing":
        return ApiResponse(success=False, message=f"素材库里没有「{req.name}」")
    if result == "target_exists":
        return ApiResponse(
            success=False,
            message=f"导入失败：本书已有同名设定集「{req.new_name or req.name}」（可勾选覆盖）",
        )
    logger.info("设定集导入 | %s → %s | 源=%s", req.name, novel_id, req.source)
    return ApiResponse(
        success=True,
        data={"name": req.new_name or req.name, "from": origin_msg},
        message=f"已从{origin_msg}复制「{req.new_name or req.name}」进本书",
    )
