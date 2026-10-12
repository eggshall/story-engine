"""伏笔账本管理器（N9）—— 按小说绑定，**必须走模型保存**。

**数据归属**：真源是 `<小说目录>/novel.json` 的 `threads` 字典（`Novel` 模型），
镜像在 `<小说目录>/threads/<id>.json`（human-readable）。

**为什么必须走模型**（与 N8 角色卡同源的坑）：`novel_storage._write_files` 每次保存都会
按模型里的字典**重建**镜像目录（先 unlink 所有 *.json 再写）。绕过模型直接往镜像目录写
文件，会在下一次保存章节时被整目录清空 —— 作者眼里是「伏笔莫名其妙没了」。
回归用例：`tests/test_threads/test_threads_survive_save.py`。

**本期是规则过滤，不是检索**（`docs/design/P7-MVP-PLAN.md` §9.1.1 的非目标）：
`select_open_threads` 只按「未回收 + 已埋设」筛，按「距埋设的章数」降序排，
不做向量/语义召回，也不从正文自动抽取伏笔。
"""

from __future__ import annotations

import logging
from typing import List, Optional

# 复用共享异常类型（同一个类，跨路由的 `except NovelNotFound` 才能通用）
from story_engine.core.errors import NovelNotFound  # noqa: F401
from story_engine.core.models import Novel, PlotThread
from story_engine.tools.novel_storage import load_novel, save_novel

logger = logging.getLogger("story_engine.threads.manager")

#: 合法状态（与 `PlotThread.status` 的 pattern 一致，这里给代码一个可校验的白名单）
THREAD_STATUSES = ("planted", "developed", "paid_off", "abandoned")

#: 视为「未回收」的状态 —— 只有这些会进注入与悬空检测
OPEN_STATUSES = ("planted", "developed")


def _require_novel(novel_id: str) -> Novel:
    novel = load_novel(novel_id)
    if novel is None:
        raise NovelNotFound(f"小说 '{novel_id}' 不存在")
    return novel


# ── CRUD ─────────────────────────────────────────────────

def list_threads(novel_id: str) -> List[str]:
    """列出**这本书**的伏笔 id（排序，结果确定）。"""
    return sorted(_require_novel(novel_id).threads.keys())


def load_thread(novel_id: str, thread_id: str) -> Optional[PlotThread]:
    """读一条伏笔；不存在返回 None（调用方常需「有则用、无则跳过」）。"""
    return _require_novel(novel_id).threads.get(thread_id)


def save_thread(novel_id: str, thread: PlotThread, overwrite: bool = False) -> bool:
    """新建/更新一条伏笔。同名且 `overwrite=False` → False（不静默覆盖作者的账本）。"""
    novel = _require_novel(novel_id)
    if thread.id in novel.threads and not overwrite:
        return False
    novel.threads[thread.id] = thread
    save_novel(novel, novel_id)
    return True


def delete_thread(novel_id: str, thread_id: str) -> bool:
    """删除一条伏笔；不存在返回 False。"""
    novel = _require_novel(novel_id)
    if thread_id not in novel.threads:
        return False
    del novel.threads[thread_id]
    save_novel(novel, novel_id)
    return True


def advance_thread(
    novel_id: str,
    thread_id: str,
    status: str,
    chapter_number: Optional[int] = None,
) -> Optional[PlotThread]:
    """推进一条伏笔的状态。

    - `status` 不在白名单 → 抛 `ValueError`（由调用方转成用户可读的失败响应）
    - 只有 `paid_off` 才写 `payoff_chapter`：**推进 ≠ 回收**，不能顺手把回收章填上
    - 条目不存在 → 返回 None
    """
    if status not in THREAD_STATUSES:
        raise ValueError(
            f"非法状态 {status!r}（可用: {list(THREAD_STATUSES)}）"
        )
    novel = _require_novel(novel_id)
    current = novel.threads.get(thread_id)
    if current is None:
        return None

    updates: dict = {"status": status}
    if status == "paid_off" and chapter_number is not None:
        updates["payoff_chapter"] = chapter_number
    updated = current.model_copy(update=updates)
    novel.threads[thread_id] = updated
    save_novel(novel, novel_id)
    logger.info("伏笔推进 | %s/%s → %s", novel_id, thread_id, status)
    return updated


# ── 注入用的筛选（规则过滤，非检索）──────────────────────

def open_threads_of(novel: Novel, chapter_number: int) -> List[PlotThread]:
    """从**已加载的 Novel 对象**里挑出本章该带的伏笔。

    抽成公共函数的理由（评审 P2-5 / 同 N5 评审 P1-8 的教训）：装配器的 provider 已经拿到
    `Novel`，不该把「未回收 + 已埋设 + 排序」再抄一遍 —— 两套等价规则并存必然漂移。
    排序键是「本章 − **埋设**章」降序（不是"距上次推进"：模型里没有"上次推进章"字段，
    那句话是实现时的笔误，评审 P2-6 已更正），同距按 id 升序（结果确定）。
    """
    candidates = [
        t
        for t in (getattr(novel, "threads", None) or {}).values()
        if t.status in OPEN_STATUSES and (t.planted_chapter or 0) <= chapter_number
    ]
    return sorted(
        candidates, key=lambda t: (-(chapter_number - (t.planted_chapter or 0)), t.id)
    )


def select_open_threads(novel_id: str, chapter_number: int) -> List[PlotThread]:
    """按 id 从磁盘读账本，再走 `open_threads_of` 的同一口径。

    - 未回收 = `status ∈ {planted, developed}`
    - 已埋设 = `planted_chapter <= chapter_number`（还没埋的不能提前泄漏）
    """
    return open_threads_of(_require_novel(novel_id), chapter_number)
