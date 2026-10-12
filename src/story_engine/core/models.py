"""Pydantic 基础模型定义 — 角色卡 / Lorebook / 章节的数据模型"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ==========================================================
# 角色卡系统 — 兼容 Character Card V2 规范
# ==========================================================


class Relationship(BaseModel):
    """角色关系"""
    target: str = Field(description="关联角色名")
    relation: str = Field(description="关系类型（师徒/恋人/仇敌等）")
    description: str = Field(default="", description="关系详细描述")


class CharacterCard(BaseModel):
    """角色卡 — 兼容 SillyTavern V2 规范"""

    # 基础信息
    name: str = Field(description="角色名")
    description: str = Field(default="", description="角色全面描述：外貌/背景/性格")
    personality: str = Field(default="", description="性格摘要")
    scenario: str = Field(default="", description="世界观/场景背景")
    background: str = Field(default="", description="角色背景故事")

    # 写作相关
    first_mes: str = Field(default="", description="出场描写/开场白")
    style_examples: List[str] = Field(default_factory=list, description="写作风格示例")
    appearance: str = Field(default="", description="外貌描写")

    # 关系与分类
    relationships: List[Relationship] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list, description="分类标签")
    lorebook: Optional[LoreBook] = Field(default=None, description="角色专属设定集")

    # 元数据
    creator: str = Field(default="story-engine", description="创建者")
    create_date: str = Field(default_factory=lambda: datetime.now().isoformat())
    version: str = Field(default="2.0", description="规范版本")

    def to_prompt_block(self) -> str:
        """将角色卡转为 LLM 可读的提示词块"""
        lines = [f"【角色名】{self.name}"]
        if self.description:
            lines.append(f"【描述】{self.description}")
        if self.appearance:
            lines.append(f"【外貌】{self.appearance}")
        if self.personality:
            lines.append(f"【性格】{self.personality}")
        if self.background:
            lines.append(f"【背景】{self.background}")
        if self.scenario:
            lines.append(f"【场景】{self.scenario}")
        if self.style_examples:
            lines.append("【风格示例】\n" + "\n---\n".join(self.style_examples))
        if self.relationships:
            rel_lines = [f"  - {r.relation}：{r.target}（{r.description}）" for r in self.relationships]
            lines.append("【关系】\n" + "\n".join(rel_lines))
        if self.first_mes:
            lines.append(f"【出场】{self.first_mes}")
        return "\n".join(lines)

    def to_json_dict(self) -> Dict[str, Any]:
        """导出为 JSON 字典（兼容 ST V2 导出格式）"""
        return self.model_dump(exclude_none=True)


# ==========================================================
# Lorebook 设定管理
# ==========================================================


class LorebookEntry(BaseModel):
    """世界观设定条目"""
    keys: List[str] = Field(description="触发关键词")
    content: str = Field(description="设定内容")
    priority: int = Field(default=10, ge=0, le=100, description="优先级")
    enabled: bool = True
    position: str = Field(default="after_char", pattern=r"^(before_char|after_char)$")
    category: str = Field(default="general", description="分类（地理/历史/魔法/势力等）")


class LoreBook(BaseModel):
    """世界观设定集 (World Book / Lorebook)"""
    name: str = Field(description="设定集名称")
    description: str = Field(default="")
    entries: Dict[str, LorebookEntry] = Field(default_factory=dict, description="条目，key 为条目 ID")
    version: str = Field(default="1.0")


# ==========================================================
# 写作相关模型
# ==========================================================


class ChapterOutline(BaseModel):
    """章节大纲"""
    chapter_number: int
    title: str = ""
    summary: str = Field(description="本章概要")
    beats: List[str] = Field(default_factory=list, description="剧情节拍")
    key_scenes: List[str] = Field(default_factory=list, description="关键场景")
    word_estimate: int = Field(default=2000, description="预估字数")


class Chapter(BaseModel):
    """完成的章节"""
    chapter_number: int
    title: str = ""
    content: str
    outline: Optional[ChapterOutline] = None
    model_used: str = ""
    polished: bool = False
    word_count: int = 0


class PlotThread(BaseModel):
    """伏笔 / 线索（N9）—— 埋设 → 推进 → 回收/放弃。

    「一本书写个三五年，伏笔就记不起来了」是网文作者的真实痛点（阅文产品需求原话），
    同类产品都把它当一等公民模块。此前的实现里伏笔只隐含在 `lore` 的关键词触发里，
    装不下「埋设章 → 回收章」的状态机。

    字段命名对齐马良写作的悬念卡三段式（埋设/强化/回收）+ 双向章节指针。
    `id` 是稳定标识：条目创建后不再改（改 id = 新建条目）。
    """

    id: str = Field(description="稳定标识（创建后不改）")
    title: str = Field(default="", description="一眼能看懂的短句，别只写「神秘老者」")
    status: str = Field(
        default="planted",
        pattern=r"^(planted|developed|paid_off|abandoned)$",
        description="planted 已埋设 / developed 已推进 / paid_off 已回收 / abandoned 已放弃",
    )
    planted_chapter: int = Field(default=0, ge=0, description="埋设章号")
    payoff_chapter: Optional[int] = Field(
        default=None, ge=0, description="回收章号（未回收为 None；改章节顺序时最易失效）"
    )
    strength: int = Field(default=3, ge=1, le=5, description="强度 1–5：越大表示此刻越该让读者感觉到")
    note: str = Field(default="", description="计划怎么回收 / 回收什么")


class Novel(BaseModel):
    """整本小说"""
    title: str
    author: str = ""
    genre: str = ""
    synopsis: str = ""
    characters: Dict[str, CharacterCard] = Field(default_factory=dict)
    lorebooks: Dict[str, LoreBook] = Field(default_factory=dict)
    threads: Dict[str, PlotThread] = Field(
        default_factory=dict, description="伏笔账本（key 为 PlotThread.id）"
    )
    chapters: List[Chapter] = Field(default_factory=list)
    created: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated: str = Field(default_factory=lambda: datetime.now().isoformat())

    def word_count(self) -> int:
        return sum(ch.word_count for ch in self.chapters)

    def chapter_count(self) -> int:
        return len(self.chapters)
