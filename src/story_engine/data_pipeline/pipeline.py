"""P6 数据管线 — 主流程。

采集 Gutenberg 中文公版书 → 清洗 → 按题材入库 corpus/<题材>/<作者>/<作品>.txt
并登记 meta/index.json。

用法:
    python -m story_engine.data_pipeline.pipeline --list          # 列出书单
    python -m story_engine.data_pipeline.pipeline --collect       # 采集全部书单
    python -m story_engine.data_pipeline.pipeline --collect --genre serious
    python -m story_engine.data_pipeline.pipeline --imports       # 扫描导入通道
    python -m story_engine.data_pipeline.pipeline --stats         # 索引统计
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Dict, List

from .cleaner import clean_text, to_paragraphs
from .config import CORPUS_DIR, GENRES, ensure_dirs
from .fetcher import download_ebook
from .index import add_record
from .index import stats as index_stats

# ── 题材精选书单（Gutenberg 中文公版，ID 已对照书目确认）──────────────
# 格式: {genre: [(eid, 标题, 作者, 备注), ...]}
BOOKLIST: Dict[str, List[tuple]] = {
    "serious": [
        ("24264", "红楼梦", "曹雪芹", "四大名著·世情"),
        ("23950", "三国志演义", "罗贯中", "四大名著·历史"),
        ("23863", "水浒传", "施耐庵", "四大名著·侠义"),
        ("23962", "西游记", "吴承恩", "四大名著·神魔"),
        ("27166", "呐喊", "鲁迅", "现代文学·讽刺"),
        ("51828", "聊斋志异", "蒲松龄", "文言短篇"),
        ("25192", "浮生六记", "沈复", "抒情回忆"),
    ],
    "humor_satire": [
        ("24032", "儒林外史", "吴敬梓", "讽刺巅峰"),
        ("24138", "官场现形记", "李宝嘉", "晚清谴责"),
        ("24099", "二十年目睹之怪现状", "吴趼人", "晚清谴责"),
        ("25128", "孽海花", "曾朴", "晚清谴责"),
        ("23818", "镜花缘", "李汝珍", "奇幻讽刺"),
        ("27331", "飞跎全传", "邹必显", "方言讽刺"),
        ("25328", "豆棚闲话", "艾衲居士", "讽刺短篇"),
        ("27329", "唐钟馗平鬼传", "烟霞散人", "讽刺"),
        ("26161", "醒世姻缘传", "西周生", "世情讽刺"),
    ],
    "tragic": [
        ("52276", "窦娥冤", "关汉卿", "元杂剧·悲剧"),
        ("25246", "琵琶记", "高明", "南戏·悲剧"),
        ("23849", "牡丹亭", "汤显祖", "传奇·至情"),
        ("23906", "西厢记", "王实甫", "元杂剧·爱情"),
        ("52270", "长生殿", "洪昇", "传奇·悲剧"),
        ("24234", "桃花扇", "孔尚任", "传奇·兴亡"),
        ("26872", "海上花列传", "韩邦庆", "吴语·悲情"),
    ],
    "popular": [
        ("24230", "今古奇观", "抱瓮老人", "话本选集"),
        ("27582", "喻世明言", "冯梦龙", "三言之一"),
        ("24141", "警世通言", "冯梦龙", "三言之一"),
        ("24239", "醒世恒言", "冯梦龙", "三言之一"),
        ("25376", "三侠五义", "石玉昆", "公案侠义"),
        ("25393", "施公案", "佚名", "公案小说"),
        ("27686", "狄公案", "佚名", "公案小说"),
        ("25349", "东周列国志", "冯梦龙", "历史演义"),
        ("23835", "隋唐演义", "褚人获", "历史演义"),
        ("57227", "平妖传", "罗贯中", "神魔"),
        ("25327", "儿女英雄传", "文康", "侠情"),
        ("26871", "粉妆楼全传", "佚名", "才子佳人"),
    ],
}


def _genre_dir(genre: str) -> Path:
    return CORPUS_DIR / GENRES.get(genre, "其他")


def collect_one(eid: str, title: str, author: str, genre: str) -> Path:
    """下载 → 清洗 → 入库单本，返回语料路径。"""
    raw_path = download_ebook(eid)
    raw = raw_path.read_text(encoding="utf-8", errors="replace")
    cleaned = clean_text(raw)
    paras = to_paragraphs(cleaned)
    if not paras:
        raise ValueError(f"{title} 清洗后为空")

    author_dir = _genre_dir(genre) / (author or "佚名")
    author_dir.mkdir(parents=True, exist_ok=True)
    out_path = author_dir / f"{title}.txt"
    out_path.write_text("\n\n".join(paras), encoding="utf-8")

    add_record({
        "id": f"gutenberg:{eid}",
        "title": title,
        "author": author,
        "translator": "",
        "source": "gutenberg",
        "gutenberg_id": eid,
        "genre": genre,
        "file": str(out_path.relative_to(CORPUS_DIR.parent)),
        "chars": sum(len(p) for p in paras),
        "paragraphs": len(paras),
    })
    return out_path


def collect(genre_filter: str = "") -> None:
    ensure_dirs()
    total = 0
    for genre, books in BOOKLIST.items():
        if genre_filter and genre != genre_filter:
            continue
        for eid, title, author, note in books:
            t0 = time.time()
            try:
                out = collect_one(str(eid), title, author, genre)
                print(f"  ✅ [{genre}] {title} ({author}) → {out}  {time.time()-t0:.1f}s")
                total += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  ❌ [{genre}] {title}: {exc.__class__.__name__}: {exc}")
    print(f"\n完成: 入库 {total} 本")


def main() -> None:
    ap = argparse.ArgumentParser(description="P6 数据管线")
    ap.add_argument("--list", action="store_true", help="列出书单")
    ap.add_argument("--collect", action="store_true", help="采集书单")
    ap.add_argument("--genre", default="", help="只采集指定题材 (serious/humor_satire/tragic/popular)")
    ap.add_argument("--imports", action="store_true", help="扫描导入通道")
    ap.add_argument("--stats", action="store_true", help="索引统计")
    args = ap.parse_args()

    if args.list or args.collect:
        print("══ 题材精选书单 ══")
        for genre, books in BOOKLIST.items():
            if args.genre and genre != args.genre:
                continue
            print(f"\n[{GENRES[genre]}]")
            for eid, title, author, note in books:
                print(f"  {eid}  {title} — {author} ({note})")
        if args.collect:
            print("\n开始采集...")
            collect(args.genre)
    elif args.imports:
        from .importer import scan_imports
        print("扫描 D:/文章数据/imports/ ...")
        # 导入默认按流行文学处理（网络小说等用户自有文本）
        recs = scan_imports(genre=args.genre or "popular")
        print(f"导入 {len(recs)} 个文件")
    elif args.stats:
        s = index_stats()
        print(json_dumps(s))
    else:
        ap.print_help()


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
