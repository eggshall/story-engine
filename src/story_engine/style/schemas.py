"""文风系统 Pydantic Schema — API 请求/响应"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class StyleFeatureRequest(BaseModel):
    """文风分析请求"""
    text: str = Field(..., min_length=50, description="要分析的文本")
    name: str = Field("", description="保存为文风画像的名称（空则不保存）")
    author: str = Field("", description="作者")
    source_work: str = Field("", description="来源作品")
    genre: str = Field("", description="题材分类")


class StyleFeatureSet(BaseModel):
    """文风特征集"""
    features: Dict[str, Any] = Field(default_factory=dict, description="量化特征")
    style_prompt: str = Field("", description="风格描述")
    sample_text: str = Field("", description="样本段落")


class StyleConsistencyRequest(BaseModel):
    """一致性检查请求"""
    text: str = Field(..., min_length=50)
    profile_id: str = Field("", description="文风画像 ID（与 style_prompt 二选一）")
    style_prompt: str = Field("", description="风格描述文本（与 profile_id 二选一）")


class StyleConsistencyResult(BaseModel):
    """一致性检查结果"""
    consistency_score: int = Field(ge=1, le=10)
    consistent_aspects: List[str] = Field(default_factory=list)
    inconsistent_aspects: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    conclusion: str = ""


class StyleProfileResponse(BaseModel):
    """文风画像响应"""
    id: str = ""
    name: str
    author: str = ""
    source_work: str = ""
    genre: str = ""
    features: Dict[str, Any] = Field(default_factory=dict)
    style_prompt: str = ""
    sample_text: str = ""
    tags: List[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    model_config = {"from_attributes": True}


class StyleListResponse(BaseModel):
    """文风列表响应"""
    profiles: List[StyleProfileResponse]
    total: int


class StyleAnalyzeResponse(BaseModel):
    """分析结果响应"""
    features: Dict[str, Any]
    style_prompt: str = ""
    profile_id: str = ""


class StyleSaveRequest(BaseModel):
    """保存文风画像请求"""
    name: str = Field(..., min_length=1)
    author: str = ""
    source_work: str = ""
    genre: str = ""
    features: Dict[str, Any] = Field(default_factory=dict)
    style_prompt: str = ""
    sample_text: str = ""
    tags: List[str] = Field(default_factory=list)


class StyleGenerateRequest(BaseModel):
    """带文风的小说内容生成请求"""
    novel_id: str = ""
    chapter_number: int = 1
    chapter_title: str = ""
    profile_id: str = ""  # 文风画像 ID
    style_prompt: str = ""  # 也可直接传风格描述
    outline: str = ""  # 大纲提示
    model: str = "deepseek-v4-pro"  # 写作模型: 默认 DeepSeek 专业写作 (本地 qwen 思考块会吃掉 token)


class StyleRecommendItem(BaseModel):
    """题材匹配推荐项"""
    profile: StyleProfileResponse
    score: float = 0.0  # 与题材原型的相似度 (0-1)
    same_genre: bool = False  # 是否属于目标题材


class StyleRecommendResponse(BaseModel):
    """题材匹配推荐响应"""
    genre: str = ""  # 目标题材
    recommendations: List[StyleRecommendItem] = Field(default_factory=list)
    total: int = 0
    note: str = ""  # 说明（如题材无画像时的提示）
