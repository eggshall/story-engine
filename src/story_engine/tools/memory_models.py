"""灵魂记忆 / 用户画像 / 文风分析 — 数据模型"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════
# 灵魂记忆 (Soul Memory) — 每部小说独立
# ═══════════════════════════════════════════════

class CharacterMemory(BaseModel):
    """模型对某个角色的认知记忆"""
    name: str
    voice: str = Field(default="", description="角色语气/说话风格的描述")
    personality_notes: str = Field(default="", description="对角色性格的理解")
    key_traits: List[str] = Field(default_factory=list, description="关键特质标签")
    relationship_memo: str = Field(default="", description="角色关系网络摘要")


class PlotMemory(BaseModel):
    """剧情进度记忆"""
    last_chapter_summary: str = Field(default="", description="上一章结尾状态")
    active_threads: List[str] = Field(default_factory=list, description="未完结的剧情线")
    unresolved_hooks: List[str] = Field(default_factory=list, description="未回收的伏笔")
    next_direction: str = Field(default="", description="下一步剧情意向")


class WritingStyleMemory(BaseModel):
    """模型对当前小说写作风格的认知"""
    vocabulary_tags: List[str] = Field(default_factory=list, description="偏好用词风格标签")
    sentence_style: str = Field(default="", description="句式特点（长短句/排比等）")
    dialogue_ratio: float = Field(default=0.0, description="对话占比估算 0-1")
    tone: str = Field(default="", description="整体语气（沉重/轻松/幽默/严肃）")
    pov: str = Field(default="", description="视角（第三人称/第一人称）")
    pacing: str = Field(default="", description="节奏（快/慢/张弛有度）")
    taboo_words: List[str] = Field(default_factory=list, description="需避免的 AI 套话")
    style_references: List[str] = Field(default_factory=list, description="参考的作家/作品风格")


class SoulMemory(BaseModel):
    """灵魂记忆 — 模型对一部小说的持久化认知"""
    novel_id: str
    novel_title: str
    created: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated: str = Field(default_factory=lambda: datetime.now().isoformat())

    # 记忆模块
    characters: Dict[str, CharacterMemory] = Field(default_factory=dict)
    plot: PlotMemory = Field(default_factory=PlotMemory)
    style: WritingStyleMemory = Field(default_factory=WritingStyleMemory)

    # 用户偏好
    user_notes: str = Field(default="", description="用户给模型的备注/要求")
    preferred_model: str = Field(default="", description="这部小说倾向使用的模型")
    writing_mode_pref: str = Field(default="", description="写作偏好: 细腻/简洁/平衡")
    custom_system_prompt: str = Field(default="", description="自定义系统提示词补充")

    # 标签
    tags: List[str] = Field(default_factory=list)

    def update_character_voice(self, name: str, voice_desc: str) -> None:
        """更新角色记忆"""
        if name not in self.characters:
            self.characters[name] = CharacterMemory(name=name)
        self.characters[name].voice = voice_desc
        self.updated = datetime.now().isoformat()

    def update_plot(self, chapter_summary: str = "", threads: Optional[List[str]] = None) -> None:
        """更新剧情记忆"""
        if chapter_summary:
            self.plot.last_chapter_summary = chapter_summary
        if threads:
            self.plot.active_threads = threads
        self.updated = datetime.now().isoformat()


# ═══════════════════════════════════════════════
# 用户画像 (User Profile) — 全局通用
# ═══════════════════════════════════════════════

class UserProfile(BaseModel):
    """用户的全局写作画像"""
    # 基本偏好
    preferred_name: str = ""
    default_writing_mode: str = "balance"   # 细腻/简洁/平衡
    default_model_for_write: str = ""
    default_model_for_chat: str = ""

    # 写作习惯
    common_genres: List[str] = Field(default_factory=list)
    typical_word_count_per_chapter: int = 2000
    preferred_pov: str = ""
    preferred_tense: str = ""  # 过去/现在

    # 个人化词汇
    favorite_openings: List[str] = Field(default_factory=list)
    pet_phrases: List[str] = Field(default_factory=list, description="个人常用语")
    avoid_phrases: List[str] = Field(default_factory=list, description="讨厌的用词")

    # 自定义
    personal_system_prompt: str = Field(default="", description="全局自定义提示词补充")
    notes: str = Field(default="")

    updated: str = Field(default_factory=lambda: datetime.now().isoformat())


# ═══════════════════════════════════════════════
# 文风剖析 (Style Profile) — 从外部文本提取
# ═══════════════════════════════════════════════

class WritingSample(BaseModel):
    """一条写作样本（来自外部小说或用户上传）"""
    source_name: str = Field(description="来源名称")
    source_url: str = ""
    text_snippet: str = Field(description="文本片段")
    analyzed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class StyleProfile(BaseModel):
    """从外部资料分析的文风画像"""
    novel_id: str = Field(description="关联小说")
    name: str = Field(description="文风档案名称")

    # 定量指标
    avg_sentence_length: float = 0.0
    dialogue_percentage: float = 0.0
    description_percentage: float = 0.0
    action_percentage: float = 0.0
    psychological_percentage: float = 0.0

    # 词汇层面
    top_adjectives: List[str] = Field(default_factory=list)
    top_verbs: List[str] = Field(default_factory=list)
    common_phrases: List[str] = Field(default_factory=list)
    distinctive_words: List[str] = Field(default_factory=list, description="区分度高的词")

    # 风格描述
    style_summary: str = Field(default="", description="LLM 生成的风格总结")
    writing_techniques: List[str] = Field(default_factory=list, description="识别到的技法")
    suitable_for: List[str] = Field(default_factory=list, description="适合的题材")

    # 样本
    samples: List[WritingSample] = Field(default_factory=list)
    created: str = Field(default_factory=lambda: datetime.now().isoformat())
