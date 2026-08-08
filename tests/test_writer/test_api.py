"""测试：API 路由"""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from story_engine.api.main import app


@pytest.fixture(autouse=True)
def setup_test_env(test_config, reset_router):
    """确保测试环境有最小配置（统一 conftest fixture）"""
    yield


client = TestClient(app)


class TestHealth:
    def test_root(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "故事引擎" in data["service"]

    def test_health(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestModelsAPI:
    def test_list_models(self):
        resp = client.get("/api/models/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        assert len(data["data"]) > 0

    def test_default_model(self):
        resp = client.get("/api/models/default")
        assert resp.status_code == 200
        assert resp.json()["data"]["default_model"] == "test-model"


class TestNovelAPI:
    def test_list_empty(self):
        resp = client.get("/api/novel/")
        assert resp.status_code == 200
        assert resp.json()["success"]

    def test_create_and_get(self, monkeypatch):
        # 使用临时 novels 目录
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)

        resp = client.post("/api/novel/", json={
            "title": "测试小说", "author": "作者", "genre": "玄幻",
        })
        assert resp.status_code == 200
        assert resp.json()["success"]

        resp = client.get("/api/novel/测试小说")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "测试小说"

    def test_delete(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)

        # 先创建
        client.post("/api/novel/", json={"title": "待删除"})
        # 再删除
        resp = client.delete("/api/novel/待删除")
        assert resp.status_code == 200
        assert resp.json()["success"]

        # 确认已删除
        resp = client.get("/api/novel/待删除")
        assert not resp.json()["success"]

    def test_create_returns_full_detail(self, monkeypatch):
        """创建返回完整 NovelDetail（修复前端白屏问题）"""
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        resp = client.post("/api/novel/", json={
            "title": "完整详情", "author": "测试", "genre": "仙侠",
        })
        data = resp.json()
        assert data["success"]
        detail = data["data"]
        assert detail["title"] == "完整详情"
        assert detail["author"] == "测试"
        assert detail["genre"] == "仙侠"
        assert "id" in detail
        assert detail["chapter_count"] == 0
        assert detail["word_count"] == 0

    def test_update_novel(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "改名测试"})
        resp = client.post("/api/novel/改名测试/update", json={"title": "新名字", "author": "新作者"})
        assert resp.json()["success"]
        resp2 = client.get("/api/novel/改名测试")
        assert resp2.json()["data"]["title"] == "新名字"
        assert resp2.json()["data"]["author"] == "新作者"

    def test_get_nonexistent(self):
        resp = client.get("/api/novel/不存在的")
        assert not resp.json()["success"]


class TestChapterAPI:
    def test_add_chapter(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "章测"})
        resp = client.post("/api/novel/章测/chapters", json={"title": "第一章"})
        assert resp.json()["success"]
        assert resp.json()["data"]["title"] == "第一章"
        assert resp.json()["data"]["chapter_number"] == 1

    def test_delete_chapter(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "del_ch"})
        client.post("/api/novel/del_ch/chapters", json={"title": "第一章"})
        resp = client.delete("/api/novel/del_ch/chapters/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"], f"删除失败: {data.get('message', '')}"
        novel = client.get("/api/novel/del_ch").json()["data"]
        assert len(novel["chapters"]) == 0

    def test_delete_nonexistent_chapter(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "无章"})
        resp = client.delete("/api/novel/无章/chapters/99")
        assert not resp.json()["success"]

    def test_save_chapter(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "保存章"})
        client.post("/api/novel/保存章/chapters", json={"title": "第一章"})
        resp = client.post("/api/novel/保存章/chapters/1/save", json={
            "title": "第一章·改", "content": "正文内容测试",
        })
        assert resp.json()["success"]
        novel = client.get("/api/novel/保存章").json()["data"]
        assert novel["chapters"][0]["title"] == "第一章·改"
        assert novel["chapters"][0]["content"] == "正文内容测试"

    def test_reorder_chapters(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "排序"})
        client.post("/api/novel/排序/chapters", json={"title": "章A"})
        client.post("/api/novel/排序/chapters", json={"title": "章B"})
        # 翻转顺序
        resp = client.post("/api/novel/排序/chapters/reorder", json={"order": [2, 1]})
        assert resp.json()["success"]
        novel = client.get("/api/novel/排序").json()["data"]
        assert novel["chapters"][0]["chapter_number"] == 1
        assert novel["chapters"][0]["title"] == "章B"  # 原来顺序2的变成第1章

    def test_reorder_rejects_missing_number(self, monkeypatch):
        """L12.1: order 集合与现有章节号不一致时拒绝，杜绝静默丢章节"""
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "排序缺号"})
        client.post("/api/novel/排序缺号/chapters", json={"title": "章A"})
        client.post("/api/novel/排序缺号/chapters", json={"title": "章B"})
        resp = client.post("/api/novel/排序缺号/chapters/reorder", json={"order": [2, 3]})
        assert not resp.json()["success"]
        assert "章节号不匹配" in resp.json()["message"]

    def test_add_duplicate_chapter_number_rejected(self, monkeypatch):
        """L12.2: 新增章节使用已存在编号时拒绝，避免同号覆盖"""
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "重号"})
        resp = client.post("/api/novel/重号/chapters", json={
            "chapter_number": 5, "title": "第五章",
        })
        assert resp.json()["success"]
        resp = client.post("/api/novel/重号/chapters", json={
            "chapter_number": 5, "title": "重复",
        })
        assert not resp.json()["success"]
        assert "已存在" in resp.json()["message"]

    def test_chat_rejects_empty_messages(self):
        """L11.1: messages 为空被输入校验拒绝"""
        resp = client.post("/api/generate/chat", json={"messages": [], "stream": False})
        assert resp.status_code == 422

    def test_chat_rejects_invalid_temperature(self):
        """L11.1: temperature 超出 [0,2] 被拒绝"""
        resp = client.post("/api/generate/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 5,
            "stream": False,
        })
        assert resp.status_code == 422

    def test_chat_rejects_invalid_mode(self):
        """L11.1: mode 非 chat/write 被拒绝"""
        resp = client.post("/api/generate/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "mode": "bogus",
            "stream": False,
        })
        assert resp.status_code == 422


class TestMemoryAPI:
    def test_get_default_memory(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "记忆测"})
        resp = client.get("/api/novel/记忆测/memory")
        assert resp.json()["success"]
        assert resp.json()["data"]["novel_id"] == "记忆测"

    def test_update_memory(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "记忆改"})
        resp = client.post("/api/novel/记忆改/memory", json={
            "user_notes": "多写内心戏",
            "custom_system_prompt": "偏好古风",
            "writing_mode_pref": "细腻",
            "preferred_model": "test-model",
        })
        assert resp.json()["success"]
        data = resp.json()["data"]
        assert data["user_notes"] == "多写内心戏"
        assert data["custom_system_prompt"] == "偏好古风"
        assert data["writing_mode_pref"] == "细腻"


class TestUserProfileAPI:
    def test_get_default(self):
        resp = client.get("/api/novel/user/profile")
        assert resp.status_code == 200
        assert resp.json()["success"]

    def test_update_profile(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.USER_PROFILE_PATH",
                           tmp / "user_profile.json")
        resp = client.post("/api/novel/user/profile", json={
            "preferred_name": "作家A",
            "default_writing_mode": "简洁",
        })
        assert resp.json()["success"]
        resp2 = client.get("/api/novel/user/profile")
        assert resp2.json()["data"]["preferred_name"] == "作家A"
        assert resp2.json()["data"]["default_writing_mode"] == "简洁"


class TestWordCountMetric:
    def test_strip_fallback_prefix(self):
        """L13.1: fallback 前缀不计入正文/字数"""
        from story_engine.api.routes.generate import strip_fallback_prefix

        assert strip_fallback_prefix("[Fallback → backup]\n正文内容") == "正文内容"
        assert strip_fallback_prefix("无前缀正文") == "无前缀正文"


class TestChatAPI:
    def test_chat_with_mode(self, monkeypatch):
        """验证 mode/search 参数能正常传递到后端"""
        from story_engine.llm.base import LLMResponse

        class FakeRouter:
            async def chat(self, request, model_name=None):
                return LLMResponse(content="ok", model="test-model")

        monkeypatch.setattr(
            "story_engine.api.routes.generate._get_router", lambda: FakeRouter()
        )

        resp = client.post("/api/generate/chat", json={
            "messages": [{"role": "user", "content": "你好"}],
            "mode": "chat",
            "search": False,
            "stream": False,
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["data"]["content"] == "ok"

    def test_chat_with_write_mode(self, monkeypatch):
        """验证写作模式参数"""
        from story_engine.llm.base import LLMResponse

        class FakeRouter:
            async def chat(self, request, model_name=None):
                return LLMResponse(content="开篇", model="test-model")

        monkeypatch.setattr(
            "story_engine.api.routes.generate._get_router", lambda: FakeRouter()
        )

        resp = client.post("/api/generate/chat", json={
            "messages": [{"role": "user", "content": "写个开头"}],
            "mode": "write",
            "stream": False,
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_chat_with_style_prompt(self, monkeypatch):
        """P5: style_prompt 非空时注入 system prompt"""
        from story_engine.llm.base import LLMResponse
        captured = {}

        class FakeRouter:
            async def chat(self, request, model_name=None):
                captured["system_prompt"] = request.system_prompt
                return LLMResponse(content="ok", model="x")

        monkeypatch.setattr(
            "story_engine.api.routes.generate._get_router", lambda: FakeRouter()
        )

        resp = client.post("/api/generate/chat", json={
            "messages": [{"role": "user", "content": "写个开头"}],
            "mode": "write",
            "stream": False,
            "style_prompt": "冷峻犀利，多用短句。",
        })
        assert resp.status_code == 200
        assert "冷峻犀利" in captured["system_prompt"]

    def test_chat_without_style_prompt(self, monkeypatch):
        """无 style_prompt 时 system prompt 不含文风注入"""
        from story_engine.llm.base import LLMResponse
        captured = {}

        class FakeRouter:
            async def chat(self, request, model_name=None):
                captured["system_prompt"] = request.system_prompt
                return LLMResponse(content="ok", model="x")

        monkeypatch.setattr(
            "story_engine.api.routes.generate._get_router", lambda: FakeRouter()
        )

        resp = client.post("/api/generate/chat", json={
            "messages": [{"role": "user", "content": "你好"}],
            "mode": "write",
            "stream": False,
        })
        assert resp.status_code == 200
        assert "文风" not in captured["system_prompt"]


class TestStyleAnalysisAPI:
    def test_analyze_text(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "文风测试"})
        resp = client.post("/api/novel/文风测试/analyze", json={
            "text": "张三丰走上武当山。山间云雾缭绕。仙鹤齐鸣。",
            "name": "武侠风",
            "source_name": "测试",
        })
        assert resp.json()["success"]
        data = resp.json()["data"]
        assert data["name"] == "武侠风"
        assert data["avg_sentence_length"] > 0

    def test_list_style_profiles(self, monkeypatch):
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
        client.post("/api/novel/", json={"title": "风格列表"})
        client.post("/api/novel/风格列表/analyze", json={
            "text": "测试。", "name": "风格A",
        })
        resp = client.get("/api/novel/风格列表/styles")
        assert resp.json()["success"]
        assert len(resp.json()["data"]) >= 1


class TestExportAPI:
    def test_export_missing_novel(self):
        resp = client.post("/api/export/md", json={"novel_id": "nonexistent"})
        assert resp.status_code == 404

    def test_export_md(self, monkeypatch):
        import story_engine.tools.novel_storage as storage_mod
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr(storage_mod, "NOVELS_ROOT", tmp)

        # 创建测试小说（使用新目录结构）
        from story_engine.core.models import Chapter, Novel
        novel = Novel(title="导出测试")
        novel.chapters.append(Chapter(chapter_number=1, title="第一章", content="内容"))
        nid = storage_mod.save_novel(novel)

        resp = client.post("/api/export/md", json={"novel_id": nid})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        assert data["data"]["format"] == "md"
        assert data["data"]["chapters_exported"] == 1


class TestResearchAPI:
    def test_empty_query(self):
        resp = client.post("/api/research/", json={"query": ""})
        assert resp.status_code == 422

    def test_research(self, monkeypatch):
        import story_engine.api.routes.research as research_mod
        tmp = Path(tempfile.mkdtemp())
        monkeypatch.setattr(research_mod, "RESEARCH_DIR", tmp)

        resp = client.post("/api/research/", json={"query": "修仙境界"})
        assert resp.status_code == 200
        assert resp.json()["success"]
