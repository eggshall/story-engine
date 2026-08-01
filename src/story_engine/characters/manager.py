"""角色卡管理器 — CRUD + 搜索 + 导出"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from story_engine.core.config import data_dir
from story_engine.core.models import CharacterCard


CHARACTERS_DIR = data_dir() / "characters"


def _ensure_dir() -> None:
    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)


def _card_path(name: str) -> Path:
    return CHARACTERS_DIR / f"{name}.json"


def list_cards() -> List[str]:
    """列出所有角色卡名称"""
    _ensure_dir()
    return sorted(p.stem for p in CHARACTERS_DIR.glob("*.json"))


def load_card(name: str) -> Optional[CharacterCard]:
    """加载指定角色卡"""
    path = _card_path(name)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return CharacterCard(**data)


def save_card(card: CharacterCard, overwrite: bool = False) -> bool:
    """保存角色卡。若已存在且 overwrite=False 则返回 False"""
    _ensure_dir()
    path = _card_path(card.name)
    if path.exists() and not overwrite:
        return False
    with open(path, "w", encoding="utf-8") as f:
        json.dump(card.to_json_dict(), f, ensure_ascii=False, indent=2)
    return True


def delete_card(name: str) -> bool:
    """删除角色卡"""
    path = _card_path(name)
    if not path.exists():
        return False
    path.unlink()
    return True


def search_cards(query: str) -> List[str]:
    """按关键词搜索角色卡名称"""
    results = []
    for name in list_cards():
        if query.lower() in name.lower():
            results.append(name)
            continue
        card = load_card(name)
        if card and (query.lower() in card.description.lower() or
                     query.lower() in card.personality.lower()):
            results.append(name)
    return results


def create_example_card() -> CharacterCard:
    """创建一个示例角色卡"""
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
