"""镜像文件名必须能区分身份（N8 评审新发现的 P1，探针实测）。

`novel_storage._write_files` 用 `_slug(名字)` 当镜像文件名，而 `_slug` 是**有损**的 ——
`"A B"`、`"A_B"`、`"a/b"` 都变成 `A_B`。两个身份于是写同一个文件、后写覆盖先写；而
`load_novel` **会回读** `characters/` 镜像并**替换** `novel.json` 里的 `characters`
（`lore/` 不回读，所以真源即所见 —— 这个非对称是刻意的，别去「对齐」它）。

后果（探针实测，隔离 NOVELS_ROOT 后）：

    create 'A B' → True；create 'A_B' → True
    to-library 'A B' → success=False「角色卡「A B」不存在」

也就是说：**先建的那张卡在界面上直接消失**，虽然真源 `novel.json` 里两张都在。

本文件钉住三件事：

1. 会撞车的两个名字都能各自落盘、都能被 `load_novel` 读回来（不再静默丢一张）；
2. **不冲突时文件名保持原样** —— 修 bug 不能让所有用户的镜像目录都变成带 hash 的丑名字；
3. 同一份数据重复保存得到同样的文件名（与写入顺序无关，不能来回改名留残影）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from story_engine.characters.manager import list_cards, load_card, save_card
from story_engine.core.models import (
    CharacterCard,
    LoreBook,
    LorebookEntry,
    Novel,
    PlotThread,
)
from story_engine.threads.manager import save_thread
from story_engine.tools.novel_storage import _novel_dir, load_novel, save_novel


@pytest.fixture(autouse=True)
def _tmp_roots(tmp_path, monkeypatch):
    """小说根 + 素材库根都指到 tmp（别碰真实 data/）。"""
    monkeypatch.setattr("story_engine.tools.novel_storage.NOVELS_ROOT", tmp_path / "novels")
    monkeypatch.setattr(
        "story_engine.characters.library.LIBRARY_DIR", tmp_path / "library" / "characters"
    )
    return tmp_path


def _card(name: str, description: str = "d") -> CharacterCard:
    return CharacterCard(name=name, description=description)


def _mirror_names(novel_id: str, sub: str = "characters") -> list[str]:
    return sorted(p.name for p in (_novel_dir(novel_id) / sub).glob("*.json"))


class TestCollidingNamesSurvive:
    def test_both_cards_land_and_load_back(self):
        save_novel(Novel(title="A"), "novel_a")
        save_card("novel_a", _card("A B", description="第一份"))
        save_card("novel_a", _card("A_B", description="第二份"))

        reloaded = load_novel("novel_a")

        assert reloaded is not None
        assert set(reloaded.characters) == {"A B", "A_B"}, "撞车的两个名字必须都在"
        assert reloaded.characters["A B"].description == "第一份"
        assert reloaded.characters["A_B"].description == "第二份"
        assert len(_mirror_names("novel_a")) == 2, "两个身份必须各占一个镜像文件"

    def test_project_space_api_still_sees_the_first_card(self):
        """界面/接口看得到先建的那张 —— 这是探针里最先暴露的症状。"""
        save_novel(Novel(title="A"), "novel_a")
        save_card("novel_a", _card("A B", description="第一份"))
        save_card("novel_a", _card("A_B", description="第二份"))

        assert list_cards("novel_a") == ["A B", "A_B"]
        assert load_card("novel_a", "A B") is not None

    def test_threads_mirrors_are_distinct_too(self):
        """同一个助手用在三个镜像目录上：伏笔账本也不许撞车。"""
        save_novel(Novel(title="A"), "novel_a")
        save_thread("novel_a", PlotThread(id="t 1", title="甲", planted_chapter=1))
        save_thread("novel_a", PlotThread(id="t_1", title="乙", planted_chapter=1))

        assert len(_mirror_names("novel_a", "threads")) == 2

    def test_lore_mirrors_are_distinct_too(self):
        save_novel(Novel(title="A"), "novel_a")
        novel = load_novel("novel_a")
        assert novel is not None
        for name in ("L B", "L_B"):
            novel.lorebooks[name] = LoreBook(
                name=name, entries={"e": LorebookEntry(keys=["k"], content="c")}
            )
        save_novel(novel, "novel_a")

        assert len(_mirror_names("novel_a", "lore")) == 2


class TestPlainNamesStayPretty:
    def test_non_colliding_name_keeps_its_plain_filename(self):
        """绝大多数书没有撞车名字 —— 它们的镜像文件名必须保持人类可读。"""
        save_novel(Novel(title="A"), "novel_a")
        save_card("novel_a", _card("沈约"))
        save_card("novel_a", _card("林晓月"))

        assert _mirror_names("novel_a") == ["林晓月.json", "沈约.json"]

    def test_space_in_a_lone_name_still_slugs_to_underscore(self):
        """只有**一个** `"A B"` 时不冲突 → 文件名仍是 `A_B.json`（保持既有观感）。"""
        save_novel(Novel(title="A"), "novel_a")
        save_card("novel_a", _card("A B"))

        assert _mirror_names("novel_a") == ["A_B.json"]


class TestStableAcrossSaves:
    def test_repeated_saves_do_not_rename_mirrors(self):
        """同一份数据重复保存 → 文件名必须一模一样（否则每存一次就换名+留残影）。"""
        save_novel(Novel(title="A"), "novel_a")
        save_card("novel_a", _card("A B"))
        save_card("novel_a", _card("A_B"))
        first = _mirror_names("novel_a")

        novel = load_novel("novel_a")
        assert novel is not None
        save_novel(novel, "novel_a")
        second = _mirror_names("novel_a")

        assert first == second
        assert len(second) == 2

    def test_name_with_slash_does_not_escape_the_mirror_dir(self):
        save_novel(Novel(title="A"), "novel_a")
        save_card("novel_a", _card("a/b"))
        save_card("novel_a", _card("a b"))

        files = _mirror_names("novel_a")

        assert len(files) == 2
        assert not any(Path(f).parent.name for f in files)   # 没有子目录被拖进来
        assert all(Path(f).name == f for f in files)


class TestLegacyDamagedBooksHealInsteadOfBeingWiped:
    """修复前损坏的书不能在升级后被 load→save **抹掉真源**（第三轮评审 P1-1）。

    遗留状态（旧实现后写覆盖先写的结果）：`novel.json` 里 `"A B"` 与 `"A_B"` 两张都在，
    但 `characters/` 只剩 `A_B.json`。

    `load_novel` 原来用镜像**整体替换** `data["characters"]` → 内存里只剩一张；
    紧接着任何一次保存（编辑章节、改卡都会触发）就把另一张从 `novel.json` **永久删掉** ——
    而此刻它的内容其实仍完好在真源里、完全可恢复。所以「回读」必须是**合并**：
    以真源字典为底，镜像只覆盖**同名**项，绝不删除只存在于真源里的条目。
    """

    def _damaged_book(self) -> None:
        save_novel(Novel(title="A"), "novel_a")
        novel = load_novel("novel_a")
        assert novel is not None
        novel.characters = {
            "A B": _card("A B", description="第一份"),
            "A_B": _card("A_B", description="第二份"),
        }
        save_novel(novel, "novel_a")

        mirror_dir = _novel_dir("novel_a") / "characters"
        for f in mirror_dir.glob("*.json"):
            f.unlink()
        (mirror_dir / "A_B.json").write_text(
            json.dumps(_card("A_B", description="第二份").to_json_dict(), ensure_ascii=False),
            encoding="utf-8",
        )

    def test_load_keeps_the_entry_that_the_mirror_lost(self):
        self._damaged_book()

        loaded = load_novel("novel_a")

        assert loaded is not None
        assert set(loaded.characters) == {"A B", "A_B"}, "残缺镜像不许吞掉真源里的另一张"
        assert loaded.characters["A B"].description == "第一份"

    def test_save_after_load_does_not_destroy_the_recoverable_entry(self):
        self._damaged_book()
        loaded = load_novel("novel_a")
        assert loaded is not None

        save_novel(loaded, "novel_a")

        raw = json.loads(
            (_novel_dir("novel_a") / "novel.json").read_text(encoding="utf-8")
        )
        assert set(raw["characters"]) == {"A B", "A_B"}, "真源被这次 load→save 抹掉了"

    def test_mirror_still_overrides_the_same_name(self):
        """合并语义不能把镜像的手改能力弄丢：同名项仍以镜像为准。"""
        save_novel(Novel(title="A"), "novel_a")
        save_card("novel_a", _card("沈约", description="真源版"))
        mirror = _novel_dir("novel_a") / "characters" / "沈约.json"
        mirror.write_text(
            json.dumps(_card("沈约", description="手改版").to_json_dict(), ensure_ascii=False),
            encoding="utf-8",
        )

        loaded = load_novel("novel_a")

        assert loaded is not None
        assert loaded.characters["沈约"].description == "手改版"


class TestConstructiveCollisionIsStillImpossible:
    """构造性反例：有人把卡名恰好起成 `slug-短hash` 形式时也不许撞车（第三轮评审 P2-1）。

    单成员组直接用 slug，而多成员组产出 `slug-<8位digest>`；两者字符集相同，所以
    `"A_B-8aabb8bc"` 这种名字可能与多成员组的产出**逐字节相同** → 又一个静默覆盖。
    """

    def test_name_shaped_like_a_hashed_mirror_file(self):
        colliding = "A_B-" + hashlib.sha1("A B".encode("utf-8")).hexdigest()[:8]
        save_novel(Novel(title="A"), "novel_a")
        for name in ("A B", "A_B", colliding):
            save_card("novel_a", _card(name))

        files = _mirror_names("novel_a")
        loaded = load_novel("novel_a")

        assert len(files) == 3, files
        assert loaded is not None
        assert set(loaded.characters) == {"A B", "A_B", colliding}, loaded.characters.keys()
