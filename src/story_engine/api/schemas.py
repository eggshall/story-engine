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


class ChapterV2Request(APIModel):
    """装配器版章节生成请求（N4b）。

    用请求体而不是 query string：手写的 `beat`/`mainline`/`recap` 可能很长，
    塞进 URL 会撞请求行长度上限（评审 P2-4）。
    """

    novel_id: str = Field(min_length=1, description="小说 ID")
    chapter_number: int = Field(default=1, ge=1)
    chapter_title: str = ""
    model: str = Field(default="", description="模型名称，为空使用默认")
    profile_id: str = Field(default="", description="文风画像 ID（可选）")
    beat: str = Field(default="", description="本章节拍（手写；留空则读 beats/ch_XXXX.md）")
    mainline: str = Field(default="", description="主线（手写；留空则读 mainline.md）")
    recap: str = Field(default="", description="前情（手写；留空则读 recap.md）")
    instruction: str = Field(
        default="",
        description="作者的修改指令（N6）。非空 = **带指令重写**：拿本章现有正文按指令重写，"
                    "只返回候选稿（done 载荷 saved=false），不落盘；作者满意后自行保存。",
    )


class CheckChapterRequest(APIModel):
    """章节校验请求（N5）。

    二选一给正文来源：`text` 直接给文本（作者粘一段就能查），或 `novel_id + chapter_number`
    从小说目录读取已保存的章节。
    """

    text: str = Field(default="", description="直接校验的文本（与 novel_id/chapter_number 二选一）")
    novel_id: str = ""
    chapter_number: int = Field(default=0, ge=0)
    profile_id: str = Field(default="", description="风格画像 ID：作为对话占比基线（可选）")
    baseline_chapters: int = Field(
        default=0, ge=0, le=20, description="用前 N 章做基线；0 = 自动（该章之前的全部，最多 10 章）"
    )


class CheckLocationPayload(APIModel):
    """定位：字符区间 + 段落序号 + 摘录（审稿页据此跳转/展示）。"""

    start: int
    end: int
    paragraph_index: Optional[int] = None
    excerpt: str = ""


class CheckFindingPayload(APIModel):
    """一条校验发现：级别 + 定位 + 建议（缺一不可，否则审稿页无法处置）。"""

    rule_id: str
    rule_name: str
    level: str = Field(description="alert / warn / ok / skipped")
    suggestion: str = ""
    location: Optional[CheckLocationPayload] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class CheckReportPayload(APIModel):
    """校验报告（`/api/check/chapter` 的 data 字段）。

    - `level`：整章**可执行结论**（alert / warn / ok）。规则因缺基线而跳过**不算**问题
      （评审 P1-5：干净文本不该显示成 skipped）。
    - `incomplete` / `skipped_rules`：本次有规则没判定（例如无基线）；审稿页应提示"这部分没判定"。
    - `location` 可能为 null：只有能定位的规则（段长/视角/AI 味/章末钩子）保证非空，
      相对指标（对话占比）不给定位。
    """

    level: str
    findings: List[CheckFindingPayload] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)
    by_rule: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    incomplete: bool = False
    skipped_rules: List[str] = Field(default_factory=list)
    baseline_source: str = "none"
    text_length: int = 0
    rules_run: List[str] = Field(default_factory=list)


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
