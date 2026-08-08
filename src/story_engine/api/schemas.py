"""Pydantic 请求/响应模型 — API Schema"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class APIModel(BaseModel):
    """API 基类：接受 camelCase 别名（前端 JS 约定），同时兼容 snake_case"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


# ── 请求 ──────────────────────────────────────────────

_MODE_RE = r"^(chat|write)$"


class ChatRequest(APIModel):
    """AI 对话请求"""
    messages: List[Dict[str, str]] = Field(min_length=1, description="消息列表 [role, content]")
    system_prompt: str = ""
    model: str = Field(default="", description="模型名称，为空使用默认")
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1)
    stream: bool = True
    mode: str = Field(default="chat", pattern=_MODE_RE, description="模式: chat=普通闲聊 / write=专业写作")
    search: bool = Field(default=False, description="是否启用联网搜索")
    style_prompt: str = Field(default="", max_length=4000, description="文风描述，非空时注入 system prompt")
    profile_id: str = Field(default="", max_length=100, description="文风画像 ID，优先于 style_prompt（完整注入特征+样本）")


class GenerateOutlineRequest(BaseModel):
    """大纲生成请求"""
    novel_id: str = ""
    chapter_number: int = 1
    chapter_title: str = ""
    model: str = ""


class WriteChapterRequest(BaseModel):
    """章节写作请求"""
    novel_id: str = ""
    chapter_number: int
    chapter_title: str = ""
    model: str = ""


class NovelCreateRequest(BaseModel):
    """创建小说请求"""
    title: str
    author: str = ""
    genre: str = ""
    synopsis: str = ""
    save_path: str = Field(default="", description="自定义保存路径，空使用默认")


class ModelConfigRequest(BaseModel):
    """模型配置请求 — 全部可选实现部分更新"""
    name: Optional[str] = None
    enabled: Optional[bool] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1)


class ResearchRequest(BaseModel):
    """资料检索请求"""
    query: str = Field(min_length=1, max_length=200, description="检索问题")
    save_to_lore: bool = False
    lore_category: str = Field(default="research", max_length=50)


class ExportRequest(BaseModel):
    """导出请求"""
    novel_id: str = Field(default="", max_length=200)
    output_dir: str = Field(default="", max_length=500)
    format: str = Field(default="md", pattern=r"^(md|json)$")
    export_all: bool = True
    chapter_numbers: List[int] = []


# ── 响应 ──────────────────────────────────────────────

class ModelInfo(BaseModel):
    """模型信息（不含 api_key，避免泄漏）"""
    name: str
    provider: str
    model_id: str
    base_url: str = ""
    enabled: bool
    temperature: float
    max_tokens: int


class NovelBrief(BaseModel):
    """小说摘要"""
    id: str
    title: str
    author: str
    genre: str
    word_count: int
    chapter_count: int
    created: str
    updated: str


class NovelDetail(BaseModel):
    """小说详情"""
    id: str
    title: str
    author: str
    genre: str
    synopsis: str
    characters: List[str]
    lorebooks: List[str]
    chapters: List[Dict[str, Any]]
    word_count: int
    chapter_count: int
    created: str
    updated: str


class ResearchResult(BaseModel):
    """检索结果"""
    query: str
    summary: str
    sources: List[Dict[str, str]]
    saved_to: str = ""


class ExportResult(BaseModel):
    """导出结果"""
    success: bool
    path: str
    format: str
    chapters_exported: int
    word_count: int


class ImportRequest(BaseModel):
    """导入请求"""
    json_data: str = Field(description="JSON 项目数据（字符串）")
    restore_path: str = Field(default="", description="可选：导入到的自定义路径")
    force: bool = Field(default=False, description="覆盖已存在的小说")


class NovelUpdateRequest(APIModel):
    """更新小说元信息 — 全部可选"""
    title: Optional[str] = Field(default=None, max_length=200)
    author: Optional[str] = Field(default=None, max_length=100)
    genre: Optional[str] = Field(default=None, max_length=50)
    synopsis: Optional[str] = Field(default=None, max_length=20000)


class ChapterCreateRequest(APIModel):
    """添加章节请求"""
    chapter_number: Optional[int] = Field(default=None, ge=1)
    title: str = Field(default="", max_length=200)
    content: Optional[str] = Field(default="", max_length=1000000)


class ChapterReorderRequest(APIModel):
    """章节重排请求"""
    order: List[int] = Field(description="新的章节号顺序")


class ChapterSaveRequest(APIModel):
    """保存单章请求"""
    title: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = Field(default=None, max_length=1000000)


class StyleAnalyzeRequest(APIModel):
    """文风档案分析请求"""
    text: str = Field(min_length=1, max_length=200000, description="待分析文本")
    name: str = Field(default="未命名文风", max_length=100)
    source_name: str = Field(default="", max_length=200)
    source_url: str = Field(default="", max_length=1000)


class ChapterStyleRequest(APIModel):
    """章节风格分析请求"""
    chapter_number: int = Field(default=1, ge=1)
    text: str = Field(default="", max_length=200000)


class ConsistencyRequest(APIModel):
    """章节一致性检查请求"""
    chapter_number: int = Field(default=1, ge=1)
    text: str = Field(default="", max_length=200000)


class MapSaveRequest(APIModel):
    """保存小说地图请求"""
    image_path: str = Field(default="", max_length=1000)
    markers: List[Dict[str, Any]] = Field(default_factory=list)


class ApiResponse(BaseModel):
    """通用 API 响应"""
    success: bool = True
    message: str = ""
    data: Any = None


class UpdateSettingsRequest(BaseModel):
    """更新默认写作参数请求 — 全部可选"""
    default_model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1)
