"""P6 数据管线测试: cleaner / importer / index / catalog 解析。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_engine.data_pipeline import cleaner  # noqa: E402
from story_engine.data_pipeline.cleaner import (  # noqa: E402
    clean_text,
    normalize_whitespace,
    to_paragraphs,
)
from story_engine.data_pipeline.index import add_record, load_index  # noqa: E402

# ── cleaner ──────────────────────────────────────────────

def test_new_format_strip():
    """新版 Gutenberg 格式: 标题行 + 版权声明 + 元数据 + START 标记。"""
    raw = (
        "The Project Gutenberg eBook of 儒林外史\n"
        "\n"
        "This eBook is for the use of anyone anywhere in the United States\n"
        "you will have to check the laws of the country where you are located\n"
        "\n"
        "Title: 儒林外史\n"
        "\n"
        "Author: Jingzi Wu\n"
        "\n"
        "Language: Chinese\n"
        "\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK 儒林外史 ***\n"
        "\n"
        "Produced by Hoi Man Man\n"
        "\n"
        "第一回　說楔子敷陳大義\n"
        "\n"
        "正文開始……\n"
        "\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK 儒林外史 ***\n"
        "更新歷史……"
    )
    out = clean_text(raw)
    assert out.startswith("第一回　说楔子敷陈大义")
    assert "eBook" not in out
    assert "END OF THE" not in out
    assert "Produced by" not in out
    assert "正文开始" in out


def test_legacy_format_strip():
    """老式格式: 版权声明 + Title/Author 元数据块（无 START 标记）。"""
    raw = (
        "This eBook is for the use of anyone anywhere in the United States and\n"
        "most other parts of the world.\n"
        "\n"
        "Title: 竇娥冤\n"
        "\n"
        "Author: Hanqing Guan\n"
        "\n"
        "Language: Chinese\n"
        "\n"
        "楔子\n"
        "〔卜儿蔡婆上〕正文開始。\n"
        "\n"
        "End of Project Gutenberg's 竇娥冤"
    )
    out = clean_text(raw)
    assert out.startswith("楔子")
    assert "Title:" not in out
    assert "Author:" not in out
    assert "End of Project" not in out


def test_body_start_fallback():
    """兜底: 开头英文残留过多时前移到中文密集段落。"""
    raw = (
        "Some English text here that is long enough to pass the filter\n"
        "and continues on the next line as well for good measure\n"
        "with yet another line of english filler content\n"
        "\n"
        "這是一段足夠長的中文正文，講述故事的開始與發展，內容充實。\n"
        "繼續講述更多內容，情節逐步推進。\n"
    )
    out = clean_text(raw)
    assert out.startswith("这是一段足够长的中文正文")


def test_normalize_whitespace():
    assert normalize_whitespace("a\r\nb\r\n\r\n\r\nc") == "a\nb\n\nc"
    assert normalize_whitespace(" 行尾空格  \n下一行") == "行尾空格\n下一行"


def test_to_simplified():
    """繁转简 (OpenCC t2s)。"""
    out = cleaner.to_simplified("說楔子敷陳大義　借名流隱括全文")
    assert out == "说楔子敷陈大义　借名流隐括全文"
    assert cleaner.to_simplified("竇娥冤") == "窦娥冤"


def test_clean_text_simplified():
    """完整清洗含繁转简。"""
    raw = (
        "*** START OF THE PROJECT GUTENBERG EBOOK 儒林外史 ***\n"
        "\n"
        "第一回　說楔子敷陳大義\n"
        "\n"
        "正文開始，講述故事。\n"
    )
    out = clean_text(raw)
    assert out.startswith("第一回　说楔子敷陈大义")
    assert "說" not in out


def test_to_paragraphs():
    paras = to_paragraphs("第一段。\n\n第二段。\n\n短", min_len=3)
    assert paras == ["第一段。", "第二段。"]
    assert to_paragraphs("", min_len=3) == []


# ── index ────────────────────────────────────────────────

def test_index_dedup(tmp_path, monkeypatch):
    from story_engine.data_pipeline import index as idx
    monkeypatch.setattr(idx, "INDEX_FILE", tmp_path / "index.json")
    idx.save_index([])
    add_record({"id": "gutenberg:1", "title": "A", "chars": 100})
    add_record({"id": "gutenberg:1", "title": "A", "chars": 200})  # 同 id 覆盖
    add_record({"id": "gutenberg:2", "title": "B", "chars": 50})
    recs = load_index()
    assert len(recs) == 2
    assert [r["id"] for r in recs] == ["gutenberg:1", "gutenberg:2"]
    assert idx.find_by_id("gutenberg:1")["chars"] == 200


def test_index_stats(tmp_path, monkeypatch):
    from story_engine.data_pipeline import index as idx
    monkeypatch.setattr(idx, "INDEX_FILE", tmp_path / "index.json")
    idx.save_index([
        {"id": "a", "genre": "serious", "source": "gutenberg", "chars": 100},
        {"id": "b", "genre": "serious", "source": "gutenberg", "chars": 200},
        {"id": "c", "genre": "popular", "source": "import", "chars": 300},
    ])
    s = idx.stats()
    assert s["total"] == 3
    assert s["total_chars"] == 600
    assert s["by_genre"] == {"serious": 2, "popular": 1}
    assert s["by_source"] == {"gutenberg": 2, "import": 1}


# ── catalog 解析逻辑 ─────────────────────────────────────

def test_catalog_parse():
    """HTML 书目页解析。"""
    html = (
        '<a href="/ebooks/24264">紅樓夢</a>\n'
        '<a href="/ebooks/24032">儒林外史</a>\n'
        '<a href="/ebooks/24264">紅樓夢(重复)</a>\n'
    )
    import re
    items = re.findall(r'<a href="/ebooks/(\d+)"[^>]*>(.*?)</a>', html, re.S)
    cat = {}
    for bid, title in items:
        t = re.sub(r"<[^>]+>", "", title).strip()
        cat.setdefault(bid, t)
    assert cat == {"24264": "紅樓夢", "24032": "儒林外史"}
