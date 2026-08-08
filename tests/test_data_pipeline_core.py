"""P6 数据管线核心流程测试 — fetcher / importer / pipeline / catalog（E3.4）。

原覆盖为 0%，本轮补齐核心流程（全部离线 mock，不联网、不触碰 /mnt/d 真实数据）。
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

# ── 通用 fixture ──────────────────────────────────────────

def _noop_dirs() -> None:
    """替换 ensure_dirs：避免测试触碰 /mnt/d 真实目录。"""


@pytest.fixture
def no_ensure_dirs(monkeypatch):
    """把各模块的 ensure_dirs 替换为空操作。"""
    for mod in ("fetcher", "importer", "pipeline", "catalog"):
        monkeypatch.setattr(
            f"story_engine.data_pipeline.{mod}.ensure_dirs", _noop_dirs
        )


# ══════════════════════════════════════════════════════════
# fetcher — Gutenberg 全文下载
# ══════════════════════════════════════════════════════════


class FakeResp:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self) -> None:
        import httpx

        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"error {self.status_code}", request=None, response=None
            )


class FakeClient:
    """同步 httpx.Client 替身，记录请求参数并返回固定响应。"""

    instances: list = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.resp: FakeResp | None = None
        FakeClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url: str):
        self.url = url
        return self.resp or FakeResp("Gutenberg 正文内容" * 100)


class TestFetcher:
    def test_download_new(self, tmp_path, monkeypatch, no_ensure_dirs):
        import story_engine.data_pipeline.fetcher as fetcher

        monkeypatch.setattr(fetcher.httpx, "Client", FakeClient)
        path = fetcher.download_ebook("24264", tmp_path)
        assert path == tmp_path / "pg24264.txt"
        assert path.exists()
        assert path.stat().st_size > 1000
        assert "Gutenberg" in path.read_text(encoding="utf-8")
        assert "https://www.gutenberg.org/cache/epub/24264/pg24264.txt" in FakeClient.instances[-1].url

    def test_download_skip_existing(self, tmp_path, monkeypatch, no_ensure_dirs):
        import story_engine.data_pipeline.fetcher as fetcher

        monkeypatch.setattr(fetcher.httpx, "Client", FakeClient)
        target = tmp_path / "pg123.txt"
        target.write_text(
            "*** START OF THE PROJECT GUTENBERG EBOOK 三国志演义 ***\n\n" + "正文" * 600,
            encoding="utf-8",
        )
        n_before = len(FakeClient.instances)
        path = fetcher.download_ebook("123", tmp_path)
        assert path == target
        assert len(FakeClient.instances) == n_before  # 未发起下载

    def test_download_redownloads_incomplete_content(self, tmp_path, monkeypatch, no_ensure_dirs):
        """已存在但内容不完整（无正文特征）→ 重新下载（L15.2）"""
        import story_engine.data_pipeline.fetcher as fetcher

        monkeypatch.setattr(fetcher.httpx, "Client", FakeClient)
        target = tmp_path / "pg789.txt"
        target.write_text("x" * 2000, encoding="utf-8")  # 无中文/无 START 标记
        path = fetcher.download_ebook("789", tmp_path)
        assert path == target
        assert "Gutenberg" in target.read_text(encoding="utf-8")  # 已重新下载

    def test_download_redownload_when_too_small(self, tmp_path, monkeypatch, no_ensure_dirs):
        import story_engine.data_pipeline.fetcher as fetcher

        monkeypatch.setattr(fetcher.httpx, "Client", FakeClient)
        target = tmp_path / "pg456.txt"
        target.write_text("short", encoding="utf-8")
        fetcher.download_ebook("456", tmp_path)
        assert target.stat().st_size > 1000

    def test_download_http_error(self, tmp_path, monkeypatch, no_ensure_dirs):
        import httpx

        import story_engine.data_pipeline.fetcher as fetcher

        client = FakeClient()
        client.resp = FakeResp("", status=500)
        monkeypatch.setattr(fetcher.httpx, "Client", lambda *a, **k: client)
        with pytest.raises(httpx.HTTPStatusError):
            fetcher.download_ebook("999", tmp_path)


# ══════════════════════════════════════════════════════════
# importer — 本地导入通道
# ══════════════════════════════════════════════════════════


@pytest.fixture
def import_env(tmp_path, monkeypatch, no_ensure_dirs):
    """隔离 importer 的 corpus/imports 目录与索引写入。"""
    import story_engine.data_pipeline.importer as importer

    corpus = tmp_path / "corpus"
    imports_dir = tmp_path / "imports"
    corpus.mkdir()
    imports_dir.mkdir()
    monkeypatch.setattr(importer, "CORPUS_DIR", corpus)
    monkeypatch.setattr(importer, "IMPORTS_DIR", imports_dir)
    monkeypatch.setattr(importer, "add_record", lambda rec: None)
    return {"corpus": corpus, "imports": imports_dir}


class TestImporter:
    def test_clean_title(self):
        from story_engine.data_pipeline.importer import _clean_title

        assert _clean_title("凡人修仙传(第1-500章)") == "凡人修仙传"
        assert _clean_title(" 书名... ") == "书名"
        assert _clean_title("（注释）正文") == "正文"
        assert _clean_title("") == "未命名"

    def test_detect_and_decode(self):
        from story_engine.data_pipeline.importer import _detect_and_decode

        assert _detect_and_decode("中文".encode("utf-8")) == "中文"
        assert _detect_and_decode("中文".encode("gbk")) == "中文"
        # 无效字节回退 replace
        out = _detect_and_decode(b"\xff\xfe\x00")
        assert isinstance(out, str)

    def test_detect_utf8_not_misdetected_as_gbk(self):
        """L15.3: round-trip 校验 — 纯 ASCII/UTF-8 文本不应被误判为 GBK"""
        from story_engine.data_pipeline.importer import _detect_and_decode

        ascii_text = "Hello, World! Story Engine test. " * 20
        assert _detect_and_decode(ascii_text.encode("utf-8")) == ascii_text
        utf8_text = "这是一段 UTF-8 中文，包含标点，。！？"
        assert _detect_and_decode(utf8_text.encode("utf-8")) == utf8_text

    def test_import_dir_not_archived_on_failure(self, import_env):
        """L15.4: 子项失败时目录不归档，源文件保留"""
        from story_engine.data_pipeline.importer import import_dir

        book_dir = import_env["imports"] / "失败书"
        book_dir.mkdir()
        # 一个无效编码文件（GBK 字节 round-trip 失败且不可解 → 触发失败）
        (book_dir / "坏卷.txt").write_bytes(b"\xff\xfe\x00\x01\x02")
        import_dir(book_dir)
        assert book_dir.exists()  # 未归档
        assert (book_dir / "坏卷.txt").exists()  # 源文件保留

    def test_html_to_text(self):
        from story_engine.data_pipeline.importer import _html_to_text

        html = "<html><script>var x=1;</script><body><p>第一段 &amp; 测试</p><p>第二段</p></body></html>"
        out = _html_to_text(html)
        assert "var x" not in out
        assert "第一段 & 测试" in out
        assert "第二段" in out

    def test_safe_filename(self):
        from story_engine.data_pipeline.importer import _safe_filename

        assert _safe_filename("../../evil") == ""
        assert _safe_filename("A\\B") == "A_B"
        assert _safe_filename("正常书名") == "正常书名"

    def test_import_file_txt(self, import_env):
        from story_engine.data_pipeline.importer import import_file

        f = import_env["imports"] / "我的书.txt"
        f.write_text("第一章 开始。\n\n这是正文内容，讲述故事的发展与推进。", encoding="utf-8")

        rec = import_file(f)
        assert rec is not None
        assert rec["title"] == "我的书"
        out = import_env["corpus"] / "imports" / "我的书.txt"
        assert out.exists()
        assert "这是正文" in out.read_text(encoding="utf-8")
        # 源文件被归档到 imports/done/
        assert not f.exists()
        assert (import_env["imports"] / "done" / "我的书.txt").exists()

    def test_import_file_gbk(self, import_env):
        from story_engine.data_pipeline.importer import import_file

        f = import_env["imports"] / "gbk书.txt"
        f.write_bytes("小说正文，使用 GBK 编码保存。".encode("gbk"))
        rec = import_file(f)
        assert rec is not None
        out = import_env["corpus"] / "imports" / "gbk书.txt"
        assert "使用 GBK" in out.read_text(encoding="utf-8")

    def test_import_dir_merges_volumes(self, import_env):
        from story_engine.data_pipeline.importer import import_dir

        book_dir = import_env["imports"] / "多卷书"
        book_dir.mkdir()
        (book_dir / "第一卷.txt").write_text("第一卷正文，讲述故事的开始与发展推进。", encoding="utf-8")
        (book_dir / "第二卷.txt").write_text("第二卷正文，承接上卷继续展开新的情节。", encoding="utf-8")

        recs = import_dir(book_dir)
        assert len(recs) == 1
        rec = recs[0]
        assert rec["title"] == "多卷书"
        out = import_env["corpus"] / "imports" / "多卷书.txt"
        text = out.read_text(encoding="utf-8")
        assert "第一卷正文" in text and "第二卷正文" in text
        assert not book_dir.exists()  # 已归档

    def test_import_epub_non_collection(self, import_env):
        from story_engine.data_pipeline.importer import import_file

        epub = import_env["imports"] / "单本.epub"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "OEBPS/text/ch1.html",
                "<html><body><p>第一章的内容，讲述故事的开端与人物登场。</p></body></html>",
            )
        epub.write_bytes(buf.getvalue())

        rec = import_file(epub)
        assert rec is not None
        assert rec["title"] == "单本"
        out = import_env["corpus"] / "imports" / "单本.txt"
        assert "第一章的内容" in out.read_text(encoding="utf-8")

    def test_extract_epub_books_collection(self, import_env):
        """合集 epub：toc.ncx + part 文件 → 按卷拆分"""
        from story_engine.data_pipeline.importer import extract_epub_books

        epub = import_env["imports"] / "合集.epub"
        ncx = (
            '<?xml version="1.0"?>'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">'
            "<navMap>"
            '<navPoint><navLabel><text>卷一</text></navLabel><content src="text/part1.html"/></navPoint>'
            '<navPoint><navLabel><text>卷二</text></navLabel><content src="text/part2.html"/></navPoint>'
            "</navMap></ncx>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("toc.ncx", ncx)
            zf.writestr("text/part1.html", "<html><body><p>卷一内容</p></body></html>")
            zf.writestr("text/part2.html", "<html><body><p>卷二内容</p></body></html>")
        epub.write_bytes(buf.getvalue())

        books = extract_epub_books(epub)
        assert len(books) == 2
        assert books[0]["title"] == "卷一"
        assert "卷一内容" in books[0]["text"]
        assert "卷二内容" in books[1]["text"]

    def test_scan_imports_handles_failures(self, import_env):
        """扫描时单个失败不中断；跳过 done/隐藏项"""
        from story_engine.data_pipeline.importer import scan_imports

        done = import_env["imports"] / "done"
        done.mkdir()
        (done / "已处理.txt").write_text("x", encoding="utf-8")
        (import_env["imports"] / ".hidden").mkdir()
        (import_env["imports"] / ".hidden" / "a.txt").write_text("y", encoding="utf-8")

        good = import_env["imports"] / "好书.txt"
        good.write_text("这是内容足够长的一段正文，讲述故事的发展与推进，情节逐步展开。", encoding="utf-8")

        bad_dir = import_env["imports"] / "空目录"
        bad_dir.mkdir()  # 无文件 → 返回空，不崩溃

        recs = scan_imports()
        assert len(recs) == 1
        assert recs[0]["title"] == "好书"

    def test_save_corpus_empty_cleaned_raises(self, import_env):
        """清洗后无有效段落 → ValueError（不落盘）"""
        from story_engine.data_pipeline.importer import _save_corpus

        with pytest.raises(ValueError):
            _save_corpus("空书", ["   \n\n  "], "other", "")

    def test_import_dir_epub_per_book(self, import_env):
        """目录内 epub 合集 → 每卷一本入库"""
        from story_engine.data_pipeline.importer import import_dir

        book_dir = import_env["imports"] / "合集目录"
        book_dir.mkdir()
        epub = book_dir / "合集.epub"
        ncx = (
            '<?xml version="1.0"?>'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">'
            "<navMap>"
            '<navPoint><navLabel><text>上卷</text></navLabel><content src="text/part1.html"/></navPoint>'
            '<navPoint><navLabel><text>下卷</text></navLabel><content src="text/part2.html"/></navPoint>'
            "</navMap></ncx>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("toc.ncx", ncx)
            zf.writestr("text/part1.html", "<p>上卷正文内容，足够长的段落。</p>")
            zf.writestr("text/part2.html", "<p>下卷正文内容，足够长的段落。</p>")
        epub.write_bytes(buf.getvalue())

        recs = import_dir(book_dir)
        assert len(recs) == 2
        titles = {r["title"] for r in recs}
        assert titles == {"上卷", "下卷"}
        assert not book_dir.exists()  # 已归档

    def test_archive_overwrites_existing(self, import_env):
        """归档目标已存在时先清理再移动"""
        from story_engine.data_pipeline.importer import _archive

        src = import_env["imports"] / "重名.txt"
        src.write_text("新内容" * 100, encoding="utf-8")
        done = import_env["imports"] / "done"
        done.mkdir()
        (done / "重名.txt").write_text("旧内容", encoding="utf-8")

        _archive(src)
        assert not src.exists()
        assert "新内容" in (done / "重名.txt").read_text(encoding="utf-8")

    def test_epub_bad_ncx_falls_back_whole(self, import_env):
        """ncx 损坏 → 按整本导入"""
        from story_engine.data_pipeline.importer import extract_epub_books

        epub = import_env["imports"] / "坏ncx.epub"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("toc.ncx", "not-valid-xml")
            zf.writestr("text/ch1.html", "<p>整本正文内容，足够长。</p>")
        epub.write_bytes(buf.getvalue())

        books = extract_epub_books(epub)
        assert len(books) == 1
        assert "整本正文" in books[0]["text"]


# ══════════════════════════════════════════════════════════
# pipeline — 主流程
# ══════════════════════════════════════════════════════════


class TestPipeline:
    def test_genre_dir_known_and_fallback(self, monkeypatch, tmp_path):
        import story_engine.data_pipeline.pipeline as pl

        monkeypatch.setattr(pl, "CORPUS_DIR", tmp_path)
        assert pl._genre_dir("serious") == tmp_path / "严肃文学"
        # L17.2: 未知题材与 config "other" 统一回退到 "其他"
        assert pl._genre_dir("未知题材") == tmp_path / "其他"
        assert pl._genre_dir("other") == tmp_path / "其他"

    def test_data_root_env_override(self, monkeypatch):
        """L17.3: STORY_ENGINE_DATA_ROOT 环境变量注入数据根目录"""
        import story_engine.data_pipeline.config as cfg_mod

        monkeypatch.setenv("STORY_ENGINE_DATA_ROOT", "/tmp/story_data_root")
        assert cfg_mod._resolve_data_root() == __import__("pathlib").Path("/tmp/story_data_root")

    def test_data_root_env_relative_ignored(self, monkeypatch):
        """L17.3: 相对路径 env 被忽略并回退默认"""
        import story_engine.data_pipeline.config as cfg_mod

        monkeypatch.setenv("STORY_ENGINE_DATA_ROOT", "relative/path")
        assert cfg_mod._resolve_data_root() == __import__("pathlib").Path("/mnt/d/文章数据")

    def test_collect_one(self, tmp_path, monkeypatch, no_ensure_dirs):
        """下载→清洗→入库→登记索引 单本全流程"""
        import story_engine.data_pipeline.pipeline as pl

        corpus = tmp_path / "corpus"
        monkeypatch.setattr(pl, "CORPUS_DIR", corpus)
        raw = tmp_path / "pg24264.txt"
        raw.write_text(
            "*** START OF THE PROJECT GUTENBERG EBOOK 儒林外史 ***\n\n"
            "第一回　說楔子敷陳大義。\n\n正文開始，講述故事。\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(pl, "download_ebook", lambda eid: raw)
        records = []
        monkeypatch.setattr(pl, "add_record", records.append)

        out = pl.collect_one("24264", "儒林外史", "吴敬梓", "serious")
        assert out == corpus / "严肃文学" / "吴敬梓" / "儒林外史.txt"
        assert out.exists()
        text = out.read_text(encoding="utf-8")
        assert text.startswith("第一回　说楔子敷陈大义")  # 繁转简已生效
        assert "eBook" not in text
        assert len(records) == 1
        assert records[0]["id"] == "gutenberg:24264"
        assert records[0]["genre"] == "serious"

    def test_collect_one_empty_cleaned(self, tmp_path, monkeypatch, no_ensure_dirs):
        """清洗后为空 → 抛 ValueError 不落盘"""
        import story_engine.data_pipeline.pipeline as pl

        monkeypatch.setattr(pl, "CORPUS_DIR", tmp_path / "corpus")
        raw = tmp_path / "empty.txt"
        raw.write_text("   \n\n     \n  ", encoding="utf-8")
        monkeypatch.setattr(pl, "download_ebook", lambda eid: raw)
        with pytest.raises(ValueError):
            pl.collect_one("1", "空书", "", "serious")

    def test_collect_filters_genre(self, tmp_path, monkeypatch, no_ensure_dirs):
        """collect(genre) 只处理指定题材；单本失败不中断"""
        import story_engine.data_pipeline.pipeline as pl

        corpus = tmp_path / "corpus"
        monkeypatch.setattr(pl, "CORPUS_DIR", corpus)
        raw = tmp_path / "raw.txt"
        raw.write_text(
            "*** START OF THE PROJECT GUTENBERG EBOOK 三国志演义 ***\n\n"
            "第一回 宴桃園豪傑三結義。\n\n正文內容。\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(pl, "download_ebook", lambda eid: raw)
        monkeypatch.setattr(pl, "add_record", lambda rec: None)

        calls = []
        real_collect_one = pl.collect_one
        monkeypatch.setattr(pl, "collect_one", lambda *a, **k: calls.append(a) or real_collect_one(*a, **k))

        pl.collect("serious")  # 只采 serious 题材
        assert len(calls) == len(pl.BOOKLIST["serious"])

        # 验证真实落盘一本
        out = corpus / "严肃文学" / "曹雪芹" / "红楼梦.txt"
        assert out.exists()

    def test_main_list_and_stats(self, monkeypatch, capsys):
        """main() 的 --list / --stats 分支"""
        import story_engine.data_pipeline.pipeline as pl

        monkeypatch.setattr(pl, "index_stats", lambda: {"total": 3})
        monkeypatch.setattr("sys.argv", ["pipeline", "--list"])
        pl.main()
        out = capsys.readouterr().out
        assert "红楼梦" in out
        assert "三国志演义" in out

        monkeypatch.setattr("sys.argv", ["pipeline", "--stats"])
        pl.main()
        out = capsys.readouterr().out
        assert '"total": 3' in out

    def test_main_collect_with_genre(self, monkeypatch, capsys):
        """main() 的 --collect --genre 分支（收集调用 + 打印）"""
        import story_engine.data_pipeline.pipeline as pl

        calls = []
        monkeypatch.setattr(pl, "collect", lambda g: calls.append(g))
        monkeypatch.setattr("sys.argv", ["pipeline", "--collect", "--genre", "popular"])
        pl.main()
        out = capsys.readouterr().out
        assert "开始采集" in out
        assert "流行文学" in out  # 书单标题打印
        assert calls == ["popular"]

    def test_collect_survives_single_failure(self, tmp_path, monkeypatch, no_ensure_dirs):
        """collect() 单本失败打日志不中断，其余照常入库"""
        import story_engine.data_pipeline.pipeline as pl

        monkeypatch.setattr(pl, "CORPUS_DIR", tmp_path / "corpus")
        raw = tmp_path / "raw.txt"
        raw.write_text(
            "*** START OF THE PROJECT GUTENBERG EBOOK 红楼梦 ***\n\n"
            "第一回 甄士隐梦幻识通灵。\n\n正文内容足够长。\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(pl, "download_ebook", lambda eid: raw)
        monkeypatch.setattr(pl, "add_record", lambda rec: None)

        real_collect_one = pl.collect_one

        def _flaky(eid, title, author, genre):
            if title == "三国志演义":
                raise RuntimeError("下载失败")
            return real_collect_one(eid, title, author, genre)

        monkeypatch.setattr(pl, "collect_one", _flaky)
        pl.collect("serious")  # 不应抛异常
        assert (tmp_path / "corpus" / "严肃文学" / "曹雪芹" / "红楼梦.txt").exists()

    def test_main_imports(self, monkeypatch, capsys):
        import story_engine.data_pipeline.importer as importer
        import story_engine.data_pipeline.pipeline as pl

        # main() 内部 `from .importer import scan_imports`，需 mock 该模块级函数
        monkeypatch.setattr(importer, "scan_imports", lambda genre="other": [{"title": "导入书"}])
        monkeypatch.setattr("sys.argv", ["pipeline", "--imports"])
        pl.main()
        out = capsys.readouterr().out
        assert "导入 1 个文件" in out

    def test_main_no_args_prints_help(self, monkeypatch, capsys):
        import story_engine.data_pipeline.pipeline as pl

        monkeypatch.setattr("sys.argv", ["pipeline"])
        pl.main()  # 无动作分支打印帮助，不抛异常
        out = capsys.readouterr().out
        assert "P6 数据管线" in out
        assert "--collect" in out


# ══════════════════════════════════════════════════════════
# catalog — Gutenberg 中文书目
# ══════════════════════════════════════════════════════════


class FakeCatalogClient:
    def __init__(self, *a, **k):
        self.resp = FakeResp(
            '<html><a href="/ebooks/24264">紅樓夢</a>'
            '<a href="/ebooks/24032">儒林外史</a></html>'
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        return self.resp


class TestCatalog:
    def test_fetch_catalog_parses(self, monkeypatch):
        import story_engine.data_pipeline.catalog as cat

        monkeypatch.setattr(cat.httpx, "Client", FakeCatalogClient)
        catalog = cat.fetch_catalog()
        assert catalog == {"24264": "紅樓夢", "24032": "儒林外史"}

    def test_save_and_load_catalog(self, tmp_path, monkeypatch, no_ensure_dirs):
        import story_engine.data_pipeline.catalog as cat

        catalog_file = tmp_path / "gutenberg_catalog.json"
        monkeypatch.setattr(cat, "CATALOG_FILE", catalog_file)
        cat.save_catalog({"1": "书一"})
        assert json.loads(catalog_file.read_text(encoding="utf-8")) == {"1": "书一"}

        loaded = cat.load_catalog()
        assert loaded == {"1": "书一"}

    def test_load_catalog_fetches_when_missing(self, tmp_path, monkeypatch, no_ensure_dirs):
        import story_engine.data_pipeline.catalog as cat

        catalog_file = tmp_path / "gutenberg_catalog.json"
        monkeypatch.setattr(cat, "CATALOG_FILE", catalog_file)
        monkeypatch.setattr(cat.httpx, "Client", FakeCatalogClient)
        loaded = cat.load_catalog()
        assert loaded == {"24264": "紅樓夢", "24032": "儒林外史"}
        assert catalog_file.exists()  # 抓取后已落盘

    def test_load_catalog_corrupt_refetches(self, tmp_path, monkeypatch, no_ensure_dirs):
        """L15.7: 书目缓存损坏 → 防御式重新抓取"""
        import story_engine.data_pipeline.catalog as cat

        catalog_file = tmp_path / "gutenberg_catalog.json"
        catalog_file.write_text("{broken json", encoding="utf-8")
        monkeypatch.setattr(cat, "CATALOG_FILE", catalog_file)
        monkeypatch.setattr(cat.httpx, "Client", FakeCatalogClient)
        loaded = cat.load_catalog()
        assert loaded == {"24264": "紅樓夢", "24032": "儒林外史"}
        assert json.loads(catalog_file.read_text(encoding="utf-8")) == loaded


class TestIndexRobustness:
    """L15.1: 索引并发/损坏容错 + 原子落盘"""

    def test_load_index_corrupt_returns_empty(self, tmp_path, monkeypatch):
        import story_engine.data_pipeline.index as idx

        index_file = tmp_path / "index.json"
        index_file.write_text("{broken", encoding="utf-8")
        monkeypatch.setattr(idx, "INDEX_FILE", index_file)
        assert idx.load_index() == []

    def test_load_index_non_list_returns_empty(self, tmp_path, monkeypatch):
        import story_engine.data_pipeline.index as idx

        index_file = tmp_path / "index.json"
        index_file.write_text('{"a": 1}', encoding="utf-8")
        monkeypatch.setattr(idx, "INDEX_FILE", index_file)
        assert idx.load_index() == []

    def test_save_index_atomic_no_temp_left(self, tmp_path, monkeypatch):
        import story_engine.data_pipeline.index as idx

        index_file = tmp_path / "index.json"
        monkeypatch.setattr(idx, "INDEX_FILE", index_file)
        idx.save_index([{"id": "1"}])
        assert index_file.exists()
        assert not index_file.with_name(index_file.name + ".tmp").exists()
        assert idx.load_index() == [{"id": "1"}]


class TestFetcherContentValidation:
    """L15.2: 下载内容校验"""

    def test_invalid_content_marker(self):
        import story_engine.data_pipeline.fetcher as fetcher

        assert fetcher._is_valid_gutenberg_text("x" * 5000) is False  # 无中文/无样板标记
        assert fetcher._is_valid_gutenberg_text("正文" * 600) is True  # 中文且够长
        assert fetcher._is_valid_gutenberg_text(
            "*** START OF THE PROJECT GUTENBERG EBOOK xxx ***\nbody") is False  # 有标记但太短
        assert fetcher._is_valid_gutenberg_text(
            "*** START OF THE PROJECT GUTENBERG EBOOK xxx ***\n" + "正文" * 600) is True


class TestCleanerFallback:
    """L15.6: cleaner START 无换行截取 + 段落兜底"""

    def test_start_marker_no_newline(self):
        from story_engine.data_pipeline.cleaner import _find_start_marker

        text = "*** START OF THE PROJECT GUTENBERG EBOOK 书名 ***\n正文开始。"
        idx = _find_start_marker(text)
        assert idx > 0
        assert text[idx:].startswith("正文")

    def test_start_marker_without_newline_takes_first_char(self):
        from story_engine.data_pipeline.cleaner import _find_start_marker

        # START 标记后无换行：从首个可见字符截取，不丢正文（不再整体丢弃到文件末尾）
        text = "*** START OF THE PROJECT GUTENBERG EBOOK 书名 *** 正文开始。"
        idx = _find_start_marker(text)
        assert idx < len(text)  # 不再是 len(text)（整体丢弃）
        assert "正文开始" in text[idx:]

    def test_to_paragraphs_single_newline_fallback(self):
        import warnings

        from story_engine.data_pipeline.cleaner import to_paragraphs

        text = "第一段正文，讲述故事的开始与人物登场。\n第二段正文，承接上卷继续展开新的情节。\n第三段正文，为后续冲突埋下伏笔。\n"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            paras = to_paragraphs(text)
        assert len(paras) == 3

    def test_to_paragraphs_blank_line_normal(self):
        from story_engine.data_pipeline.cleaner import to_paragraphs

        text = "第一段正文，内容足够长。\n\n第二段正文，内容足够长。\n\n"
        paras = to_paragraphs(text)
        assert len(paras) == 2
