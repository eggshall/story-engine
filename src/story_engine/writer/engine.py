"""写作引擎 — 大纲/写作/草稿三种模式 + 模板系统"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from story_engine.core.config import data_dir
from story_engine.core.models import Chapter, ChapterOutline, CharacterCard, Novel
from story_engine.llm.base import LLMRequest
from story_engine.llm.router import ModelRouter
from story_engine.lore.lorebook import build_lore_context

# 默认写作提示词模板
DEFAULT_SYSTEM_PROMPT = """你是一位专业的网络小说作家，擅长写引人入胜的故事。
写作要求：
1. 语言生动，有画面感
2. 对话自然，符合角色性格
3. 节奏控制得当，有爽点和悬念
4. 前后连贯，逻辑自洽
5. 避免滥用"然而""但是""毕竟""值得一提的是"等套路词"""

OUTLINE_PROMPT = """请为小说《{title}》第{chapter_num}章撰写大纲。

{character_context}

{world_context}

故事概要：{synopsis}

前情提要：{previous_summary}

请以 JSON 格式输出大纲，包含以下字段：
- title: 本章标题
- summary: 本章概要（200字以内）
- beats: 剧情节拍列表（3-5个关键情节转折）
- key_scenes: 关键场景列表"""

WRITING_PROMPT = """请根据以下大纲续写小说《{title}》第{chapter_num}章「{chapter_title}」。

{character_context}

{world_context}

大纲：
{outline}

前情提要：
{previous_summary}

写作要求：
1. 控制在{word_estimate}字左右
2. 保持角色性格一致性
3. 注意场景切换自然
4. 每段不超过300字
5. 章节末尾留悬念"""

DRAFT_PROMPT = """请为小说《{title}》第{chapter_num}章生成一个快速草稿版本。

{character_context}

{world_context}

大纲：
{outline}

要求：快速生成200-500字的简要版本，涵盖大纲中的关键情节转折。
语言简洁，重点突出剧情推进。"""


class WritingEngine:
    """写作引擎 — 三种模式的核心调度"""

    def __init__(self, router: ModelRouter) -> None:
        self.router = router
        self.current_novel: Optional[Novel] = None

    def load_novel(self, novel: Novel) -> None:
        """加载当前小说"""
        self.current_novel = novel

    def _build_character_context(self, characters: Dict[str, CharacterCard]) -> str:
        """构建角色上下文字符串"""
        if not characters:
            return ""
        lines = ["【角色设定】"]
        for name, card in characters.items():
            lines.append(card.to_prompt_block())
            lines.append("---")
        return "\n".join(lines)

    def _build_previous_summary(self, chapters: List[Chapter], max_chapters: int = 5) -> str:
        """构建前情提要 — 滑动窗口，只看最后 max_chapters 章"""
        recent = chapters[-max_chapters:] if len(chapters) > max_chapters else chapters
        if not recent:
            return "（小说刚开始，尚未有前情）"
        lines = ["【前情提要】"]
        for ch in recent:
            title_part = f"「{ch.title}」" if ch.title else ""
            preview = ch.content[:100].replace("\n", " ") + "..."
            lines.append(f"第{ch.chapter_number}章 {title_part}: {preview}")
        return "\n".join(lines)

    async def generate_outline(
        self,
        chapter_num: int,
        title: str = "",
        model: str = "",
    ) -> Optional[ChapterOutline]:
        """大纲模式：生成章节大纲"""
        if not self.current_novel:
            raise RuntimeError("请先加载小说")

        novel = self.current_novel
        prompt = OUTLINE_PROMPT.format(
            title=novel.title,
            chapter_num=chapter_num,
            character_context=self._build_character_context(novel.characters),
            world_context=self._build_world_context(),
            synopsis=novel.synopsis,
            previous_summary=self._build_previous_summary(novel.chapters),
        )

        request = LLMRequest(
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        response = await self.router.chat(request, model_name=model or None)
        if not response.success:
            return None

        # 尝试从回复中提取 JSON
        import re
        json_match = re.search(r"```(?:json)?\n(.+?)\n```", response.content, re.DOTALL)
        json_str = json_match.group(1) if json_match else response.content

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            data = {"summary": response.content[:200], "beats": [], "key_scenes": []}

        # 兼容两种格式：纯字符串列表 or {name/title}+description 对象列表
        def _extract_strings(items: list) -> list:
            result = []
            for item in items:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict):
                    result.append(item.get("name") or item.get("title") or str(item))
            return result

        return ChapterOutline(
            chapter_number=chapter_num,
            title=data.get("title", title or f"第{chapter_num}章"),
            summary=data.get("summary", ""),
            beats=_extract_strings(data.get("beats", [])),
            key_scenes=_extract_strings(data.get("key_scenes", [])),
            word_estimate=data.get("word_estimate", 2000),
        )

    def _build_world_context(self) -> str:
        """从当前文本中构建世界观上下文"""
        if not self.current_novel:
            return ""
        # 取最新一章内容用于关键词触发
        recent_text = ""
        if self.current_novel.chapters:
            recent_text = self.current_novel.chapters[-1].content
        return build_lore_context(recent_text)

    async def write_chapter(
        self,
        outline: ChapterOutline,
        model: str = "",
    ) -> Optional[Chapter]:
        """写作模式：根据大纲生成章节内容"""
        if not self.current_novel:
            raise RuntimeError("请先加载小说")

        novel = self.current_novel
        world_context = self._build_world_context()
        prompt = WRITING_PROMPT.format(
            title=novel.title,
            chapter_num=outline.chapter_number,
            chapter_title=outline.title,
            character_context=self._build_character_context(novel.characters),
            world_context=world_context,
            outline=outline.model_dump_json(indent=2, ensure_ascii=False),
            previous_summary=self._build_previous_summary(novel.chapters),
            word_estimate=outline.word_estimate,
        )

        request = LLMRequest(
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=outline.word_estimate * 2,
        )

        response = await self.router.chat(request, model_name=model or None)
        if not response.success:
            return None

        content = response.content.strip()
        return Chapter(
            chapter_number=outline.chapter_number,
            title=outline.title,
            content=content,
            outline=outline,
            model_used=response.model,
            word_count=len(content),
        )

    async def draft_chapter(
        self,
        outline: ChapterOutline,
        model: str = "",
        draft_count: int = 3,
    ) -> List[Chapter]:
        """草稿模式：生成多个版本供选择（固定用低成本模型）"""
        if not self.current_novel:
            raise RuntimeError("请先加载小说")

        novel = self.current_novel
        results: List[Chapter] = []

        for i in range(draft_count):
            prompt = DRAFT_PROMPT.format(
                title=novel.title,
                chapter_num=outline.chapter_number,
                character_context=self._build_character_context(novel.characters),
                world_context=self._build_world_context(),
                outline=outline.model_dump_json(indent=2, ensure_ascii=False),
            )

            request = LLMRequest(
                system_prompt=f"你是草稿生成助手。快速输出版本{i+1}。",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9 + i * 0.1,
                max_tokens=1000,
            )

            response = await self.router.chat(request, model_name=model or None)
            content = response.content.strip() if response.success else "(生成失败)"
            results.append(
                Chapter(
                    chapter_number=outline.chapter_number,
                    title=f"{outline.title} (草稿{i+1})",
                    content=content,
                    outline=outline,
                    model_used=response.model,
                    word_count=len(content),
                )
            )

        return results

    def save_novel(self, path: Optional[Path] = None) -> Path:
        """保存当前小说到 JSON 文件"""
        if not self.current_novel:
            raise RuntimeError("没有已加载的小说")

        save_path = path or (data_dir() / "novels" / f"{self.current_novel.title}.json")
        save_path.parent.mkdir(parents=True, exist_ok=True)

        self.current_novel.updated = __import__("datetime").datetime.now().isoformat()
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(
                self.current_novel.model_dump(exclude_none=True),
                f,
                ensure_ascii=False,
                indent=2,
            )
        return save_path
