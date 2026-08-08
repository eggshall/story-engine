"""测试：小说存储引擎 — 独立目录 CRUD"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from story_engine.core.models import Chapter, Novel
from story_engine.tools.memory_models import SoulMemory, StyleProfile
from story_engine.tools.novel_storage import (
    delete_novel,
    list_novels,
    list_style_profiles,
    load_novel,
    load_soul_memory,
    load_user_profile,
    save_novel,
    save_soul_memory,
    save_style_profile,
    save_user_profile,
)


@pytest.fixture
def tmp_novels(monkeypatch):
    """使用临时目录隔离存储"""
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp)
    return tmp


# ── 创建/读取/列表/删除 ──────────────────────


class TestNovelStorage:
    def test_create(self, tmp_novels):
        novel = Novel(title="测试存储", author="作者A", genre="玄幻")
        nid = save_novel(novel)
        assert nid == "测试存储"
        assert (tmp_novels / nid / "novel.json").exists()

    def test_list(self, tmp_novels):
        save_novel(Novel(title="A"))
        save_novel(Novel(title="B"))
        novels = list_novels()
        assert len(novels) == 2
        titles = [n["title"] for n in novels]
        assert "A" in titles
        assert "B" in titles

    def test_list_empty(self, tmp_novels):
        assert list_novels() == []

    def test_load(self, tmp_novels):
        save_novel(Novel(title="加载测试", genre="科幻"))
        novel = load_novel("加载测试")
        assert novel is not None
        assert novel.title == "加载测试"
        assert novel.genre == "科幻"

    def test_load_not_found(self, tmp_novels):
        assert load_novel("不存在") is None

    def test_delete(self, tmp_novels):
        save_novel(Novel(title="待删除"))
        assert delete_novel("待删除") is True
        assert not (tmp_novels / "待删除").exists()
        assert load_novel("待删除") is None

    def test_delete_not_found(self, tmp_novels):
        assert delete_novel("不存在") is False

    def test_create_with_chapters(self, tmp_novels):
        novel = Novel(title="有章节")
        novel.chapters.append(Chapter(chapter_number=1, title="第一章", content="内容"))
        nid = save_novel(novel)
        loaded = load_novel(nid)
        assert loaded is not None
        assert len(loaded.chapters) == 1
        assert loaded.chapters[0].title == "第一章"

    def test_create_and_add_chapter(self, tmp_novels):
        """创建后添加章节再重新加载"""
        novel = Novel(title="逐步添加")
        nid = save_novel(novel)
        novel.chapters.append(Chapter(chapter_number=1, title="新增", content="测试"))
        save_novel(novel, nid)
        loaded = load_novel(nid)
        assert loaded is not None
        assert len(loaded.chapters) == 1

    def test_delete_removes_chapters(self, tmp_novels):
        novel = Novel(title="带章节删除")
        novel.chapters.append(Chapter(chapter_number=1, title="章", content="内容"))
        nid = save_novel(novel)
        delete_novel(nid)
        assert not (tmp_novels / nid).exists()

    def test_save_preserves_characters_and_lore(self, tmp_novels):
        from story_engine.core.models import CharacterCard, LoreBook
        novel = Novel(title="多数据")
        novel.characters["主角"] = CharacterCard(name="主角")
        novel.lorebooks["世界"] = LoreBook(name="世界")
        nid = save_novel(novel)
        loaded = load_novel(nid)
        assert "主角" in loaded.characters
        assert "世界" in loaded.lorebooks


# ── 路径穿越防护 ──────────────────────────────


class TestPathTraversal:
    @pytest.mark.parametrize("bad", ["../../", "..", "%2e%2e", "/etc", "a\\b"])
    def test_load_rejects_traversal(self, tmp_novels, bad):
        with pytest.raises(ValueError):
            load_novel(bad)

    @pytest.mark.parametrize("bad", ["../../", "..", "%2e%2e", "/etc", "a\\b"])
    def test_delete_rejects_traversal(self, tmp_novels, bad):
        with pytest.raises(ValueError):
            delete_novel(bad)

    @pytest.mark.parametrize("bad", ["..", "%2e%2e", "a/b", "a\\b"])
    def test_save_rejects_traversal_id(self, tmp_novels, bad):
        with pytest.raises(ValueError):
            save_novel(Novel(title="穿越测试"), bad)

    @pytest.mark.parametrize("bad", ["/etc", "/mnt/d/evil", "D:\\evil", "/etc/passwd"])
    def test_save_rejects_absolute_custom_path(self, tmp_novels, bad):
        with pytest.raises(ValueError):
            save_novel(Novel(title="绝对路径"), bad)

    def test_save_custom_path_stays_within_root(self, tmp_novels):
        with pytest.raises(ValueError):
            save_novel(Novel(title="越界"), "/../../etc")

    def test_save_plain_relative_id_still_works(self, tmp_novels):
        nid = save_novel(Novel(title="书架小说"), "书架")
        assert nid == "书架"
        assert (tmp_novels / "书架").exists()

    def test_chinese_title_still_works(self, tmp_novels):
        nid = save_novel(Novel(title="你好，世界！"))
        assert nid == "你好，世界！"
        assert (tmp_novels / nid / "novel.json").exists()


class TestNameAsFilename:
    def test_malicious_character_names_do_not_escape(self, tmp_novels):
        from story_engine.core.models import CharacterCard

        novel = Novel(title="恶意角色")
        novel.characters["../../x"] = CharacterCard(name="../../x")
        novel.characters[r"含<>:\"|?*特殊"] = CharacterCard(name=r"含<>:\"|?*特殊")
        nid = save_novel(novel)

        ch_dir = tmp_novels / nid / "characters"
        files = list(ch_dir.glob("*.json"))
        assert files
        for f in files:
            assert f.parent.resolve() == ch_dir.resolve()
        loaded = load_novel(nid)
        assert "../../x" in loaded.characters
        assert r"含<>:\"|?*特殊" in loaded.characters

    def test_malicious_lore_name_does_not_escape(self, tmp_novels):
        from story_engine.core.models import LoreBook

        novel = Novel(title="恶意lore")
        novel.lorebooks["../../世界"] = LoreBook(name="../../世界")
        nid = save_novel(novel)
        assert (tmp_novels / nid / "lore" / ".._.._世界.json").exists()
        assert not (tmp_novels.parent / ".._.._世界.json").exists()

    def test_malicious_style_profile_name_does_not_escape(self, tmp_novels):
        profile = StyleProfile(
            novel_id="s3_test",
            name="../../恶意",
            style_summary="恶意名称",
            avg_sentence_length=10,
        )
        save_style_profile(profile)
        profiles = list_style_profiles("s3_test")
        assert len(profiles) == 1
        assert profiles[0]["name"] == "../../恶意"
        assert not (tmp_novels.parent / ".._.._恶意.json").exists()


# ── 灵魂记忆 ──────────────────────────────────


class TestSoulMemory:
    def test_default_memory(self, tmp_novels):
        mem = load_soul_memory("test_id")
        assert mem.novel_id == "test_id"
        assert len(mem.characters) == 0

    def test_save_and_load(self, tmp_novels):
        mem = SoulMemory(novel_id="save_test", novel_title="记忆测试")
        mem.user_notes = "用户备注"
        mem.update_character_voice("林晓月", "温柔")
        mem.style.tone = "轻松"
        save_soul_memory(mem)

        loaded = load_soul_memory("save_test")
        assert loaded.novel_title == "记忆测试"
        assert loaded.user_notes == "用户备注"
        assert "林晓月" in loaded.characters
        assert loaded.characters["林晓月"].voice == "温柔"
        assert loaded.style.tone == "轻松"

    def test_update_plot(self, tmp_novels):
        mem = SoulMemory(novel_id="plot_test", novel_title="剧情")
        mem.update_plot(chapter_summary="主角进入秘境", threads=["秘境探险", "寻找宝物"])
        save_soul_memory(mem)
        loaded = load_soul_memory("plot_test")
        assert loaded.plot.last_chapter_summary == "主角进入秘境"
        assert "秘境探险" in loaded.plot.active_threads


# ── 用户画像 ──────────────────────────────────


class TestUserProfile:
    def test_default_profile(self, tmp_novels, monkeypatch):
        p = tmp_novels.parent / "test_profile.json"
        monkeypatch.setattr("story_engine.tools.novel_storage.USER_PROFILE_PATH", p)
        if p.exists():
            p.unlink()
        profile = load_user_profile()
        assert profile.preferred_name == ""

    def test_save_and_load(self, tmp_novels, monkeypatch):
        p = tmp_novels.parent / "user_profile.json"
        monkeypatch.setattr("story_engine.tools.novel_storage.USER_PROFILE_PATH", p)
        profile = load_user_profile()
        profile.preferred_name = "测试用户"
        profile.default_writing_mode = "细腻"
        save_user_profile(profile)

        loaded = load_user_profile()
        assert loaded.preferred_name == "测试用户"
        assert loaded.default_writing_mode == "细腻"


# ── 文风档案 ──────────────────────────────────


class TestStyleProfiles:
    def test_list_empty(self, tmp_novels):
        assert list_style_profiles("nonexistent") == []

    def test_save_and_list(self, tmp_novels):
        profile = StyleProfile(
            novel_id="style_test",
            name="金庸风格",
            style_summary="古典武侠文风",
            avg_sentence_length=18.5,
        )
        save_style_profile(profile)
        profiles = list_style_profiles("style_test")
        assert len(profiles) == 1
        assert profiles[0]["name"] == "金庸风格"
