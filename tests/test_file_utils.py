"""测试：file_utils — resolve_within 路径安全校验 (S2) 及基础文件工具"""
from __future__ import annotations

import pytest

from story_engine.utils.file_utils import (
    detect_encoding,
    list_text_files,
    read_text,
    resolve_within,
    write_text,
)


class TestResolveWithin:
    """S2.1 resolve_within 防目录穿越"""

    def test_accepts_relative_path(self, tmp_path):
        out = resolve_within(tmp_path, "a/b")
        assert out == (tmp_path / "a" / "b").resolve()

    def test_accepts_single_component(self, tmp_path):
        assert resolve_within(tmp_path, "novel") == (tmp_path / "novel").resolve()

    def test_rejects_empty(self, tmp_path):
        for bad in ("", "   "):
            with pytest.raises(ValueError):
                resolve_within(tmp_path, bad)

    def test_rejects_absolute_path(self, tmp_path):
        with pytest.raises(ValueError):
            resolve_within(tmp_path, "/etc")
        with pytest.raises(ValueError):
            resolve_within(tmp_path, "/tmp/evil")

    def test_rejects_windows_drive(self, tmp_path):
        with pytest.raises(ValueError):
            resolve_within(tmp_path, "D:\\evil")
        with pytest.raises(ValueError):
            resolve_within(tmp_path, "C:/Users/evil")

    def test_rejects_parent_traversal(self, tmp_path):
        for bad in ("..", "../..", "a/../../etc", "../novel"):
            with pytest.raises(ValueError):
                resolve_within(tmp_path, bad)

    def test_rejects_symlink_escape(self, tmp_path):
        """symlink 指向 root 之外应被 resolve() 拦截"""
        outside = tmp_path / ".." / "outside_target"
        outside.mkdir(parents=True, exist_ok=True)
        link = tmp_path / "link"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("当前环境不支持 symlink")
        with pytest.raises(ValueError):
            resolve_within(tmp_path, "link")

    def test_root_itself_ok(self, tmp_path):
        assert resolve_within(tmp_path, ".") == tmp_path.resolve()


class TestReadWriteText:
    def test_roundtrip(self, tmp_path):
        p = tmp_path / "f.txt"
        assert write_text(p, "hello")
        assert read_text(p) == "hello"

    def test_read_missing_returns_none(self, tmp_path):
        assert read_text(tmp_path / "nope.txt") is None

    def test_read_bad_encoding_returns_none(self, tmp_path):
        p = tmp_path / "bad.txt"
        p.write_bytes(b"\xff\xfe\x00bad")
        assert read_text(p) is None

    def test_write_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "deep" / "f.txt"
        assert write_text(p, "x")
        assert p.exists()

    def test_write_to_bad_path_returns_false(self, tmp_path):
        # 目录被文件占位，无法在其中建子目录
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file")
        assert write_text(blocker / "f.txt", "x") is False


class TestListTextFiles:
    def test_returns_only_matching(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.md").write_text("b")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.txt").write_text("c")
        files = list_text_files(tmp_path, ".txt")
        assert [f.name for f in files] == ["a.txt"]

    def test_missing_dir_returns_empty(self, tmp_path):
        assert list_text_files(tmp_path / "nope") == []


class TestDetectEncoding:
    def test_utf8(self, tmp_path):
        p = tmp_path / "u.txt"
        p.write_text("中文", encoding="utf-8")
        assert detect_encoding(p) == "utf-8"

    def test_utf8_sig(self, tmp_path):
        p = tmp_path / "sig.txt"
        p.write_bytes(b"\xef\xbb\xbf" + "中文".encode("utf-8"))
        assert detect_encoding(p) == "utf-8-sig"

    def test_gbk(self, tmp_path):
        p = tmp_path / "g.txt"
        p.write_bytes("中文".encode("gbk"))
        assert detect_encoding(p) == "gbk"

    def test_fallback_latin1(self, tmp_path):
        p = tmp_path / "l.txt"
        p.write_bytes(b"\xff\xfe\xfd")
        assert detect_encoding(p) == "latin-1"
