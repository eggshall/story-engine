"""角色卡管理器（N8：按小说绑定 = 每本书一个项目空间）。

**数据归属**：卡属于某一本小说，存 `<小说目录>/characters/<名字>.json`（human-readable 镜像），
真源是 `<小说目录>/novel.json` 里的 `characters` 字典（`Novel` 模型）。

**为什么必须走模型**（踩过的坑）：`novel_storage._write_files` 每次保存都会按模型里的字典
**重建** `characters/` 目录（先 unlink 所有 *.json 再写）。绕过模型直接往镜像目录写文件，
会在下一次保存章节时被整目录清空 —— 用户眼里的"卡莫名其妙没了"。

**全局目录已退役**：这里不再碰 `data/characters/`。原来生成时会把全局卡全部并入当前小说，
导致所有小说共用一副卡组（"角色卡没绑定小说"）。
"""

from __future__ import annotations

import logging
from typing import List, Optional

from story_engine.core.errors import NovelNotFound  # noqa: F401 —— 兼容既有导入点
from story_engine.core.models import CharacterCard, Novel
from story_engine.tools.novel_storage import load_novel, save_novel

logger = logging.getLogger("story_engine.characters.manager")


def _require_novel(novel_id: str) -> Novel:
    novel = load_novel(novel_id)
    if novel is None:
        raise NovelNotFound(f"小说 '{novel_id}' 不存在")
    return novel


def list_cards(novel_id: str) -> List[str]:
    """列出**这本书**的角色卡名（按名字排序）。"""
    return sorted(_require_novel(novel_id).characters.keys())


def load_card(novel_id: str, name: str) -> Optional[CharacterCard]:
    """读一张卡；不存在返回 None（不抛错：调用方常需要"有则用、无则跳过"）。"""
    return _require_novel(novel_id).characters.get(name)


def save_card(novel_id: str, card: CharacterCard, overwrite: bool = False) -> bool:
    """新建/更新一张卡。同名且 `overwrite=False` → 返回 False（不静默覆盖作者的卡）。"""
    novel = _require_novel(novel_id)
    if card.name in novel.characters and not overwrite:
        return False
    novel.characters[card.name] = card
    save_novel(novel, novel_id)
    return True


def delete_card(novel_id: str, name: str) -> bool:
    """删除一张卡；不存在返回 False。"""
    novel = _require_novel(novel_id)
    if name not in novel.characters:
        return False
    del novel.characters[name]
    save_novel(novel, novel_id)
    return True


def search_cards(novel_id: str, query: str) -> List[str]:
    """按关键词搜本书的卡（名字 / 描述 / 性格）。"""
    q = query.strip().lower()
    if not q:
        return list_cards(novel_id)
    hits: List[str] = []
    for name, card in sorted(_require_novel(novel_id).characters.items()):
        haystack = f"{name} {card.description} {card.personality}".lower()
        if q in haystack:
            hits.append(name)
    return hits


def create_example_card() -> CharacterCard:
    """示例卡（仅作为"新建卡时可参考的模板"，不再写任何全局目录）。"""
    from story_engine.core.models import Relationship

    return CharacterCard(
        name="林晓月",
        description="十七岁的修仙宗门天才少女。外表清冷孤傲，内心其实渴望被理解和认可。"
                    "拥有千年难遇的冰凤灵体，修行速度远超同龄人。",
        personality="外冷内热、骄傲但不傲慢、对认定的人极为忠诚",
        scenario="玄幻修仙世界 · 天玄宗",
        background="自幼被天玄宗长老从雪山上捡回，不知父母是谁。八岁筑基，十二岁金丹，"
                   "十六岁元婴——破纪录的速度让她成为宗门焦点，但也因此被同门孤立。"
                   "唯一的朋友是一只灵兽雪狐。",
        first_mes="寒风萧瑟，一袭白衣的身影立于山巅。她回过头，眸中似有寒冰流转："
                  "『你也是来看我笑话的？』",
        appearance="身姿修长，及腰银发，冰蓝色的眼眸如同万年寒玉。"
                   "一袭素白长裙，周身总有淡淡的寒气萦绕。",
        style_examples=[
            "描写细腻，善用意象——『剑光如月华倾泻，冰晶在空中绽放又凋零』",
            "对话简洁有张力，用『……』表达犹豫或未尽之言",
        ],
        relationships=[
            Relationship(target="云逸风", relation="师兄", description="青梅竹马的师兄，也是唯一敢和她开玩笑的人"),
            Relationship(target="雪狐·小白", relation="灵兽伙伴", description="从小一起长大的灵兽，她唯一的倾诉对象"),
        ],
        tags=["修仙", "女主", "天才", "冰山"],
    )
