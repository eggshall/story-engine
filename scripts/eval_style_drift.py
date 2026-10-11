"""文风漂移容差标定与基线策略对照实验（可复现）

用途: 修改 `story_engine/style/drift.py` 的容差 / 聚合规则后, 重新跑一遍,
      确认"作者本人章节不被误报"与"AI 味伪作必被拦截"两个指标同时成立。

用法:
    .venv/bin/python scripts/eval_style_drift.py            # 默认用 全民魔女1994
    .venv/bin/python scripts/eval_style_drift.py <语料.txt>

对照三种基线策略:
    A 固定基线   —— 全书前 12 章中位数（早期实现, 误报率高）
    B 滚动窗口   —— 被检章之前 10 章中位数（推荐）
    C 滚动 + 场景分桶 —— 窗口内按 对话主导/动作短句/叙述长句 分桶后再取中位数

结论（2026-10 实测, 《全民魔女1994》1711 章, 抽 300 章）:
    A: alert 9.7%  B: alert 0.7%  C: alert 0.3%  → 用 B; 分桶无额外收益, 不实现。
    AI 味伪作在 A/B/C 下均 100% alert。
"""

from __future__ import annotations

import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_engine.style.drift import build_baseline, detect_drift  # noqa: E402
from story_engine.style.metrics import measure  # noqa: E402

DEFAULT_BOOK = Path("/mnt/d/文章数据/corpus/imports/全民魔女1994.txt")
CH = re.compile(r"(?:^|\n)\s*第\s*[0-9零一二三四五六七八九十百千两]+\s*[章回]")
WINDOW = 10
SAMPLE = 300


def chapter_texts(text: str) -> list[str]:
    marks = [m.start() for m in CH.finditer(text)]
    outs: list[str] = []
    for i in range(len(marks) - 1):
        chunk = text[marks[i]:marks[i + 1]].strip()
        if 800 <= len(chunk) <= 20000:
            outs.append(chunk)
    return outs


def bucket_of(m: dict[str, float]) -> str:
    if m["dialogue_ratio"] >= 0.35:
        return "dialogue"
    if m["avg_sentence_length"] <= 22:
        return "action"
    return "narrative"


def eval_levels(samples: list[dict]) -> dict[str, float]:
    levels = {"ok": 0, "warn": 0, "alert": 0}
    scores = []
    for report in samples:
        levels[report["level"]] += 1
        scores.append(report["score"])
    n = len(samples) or 1
    return {
        "n": n,
        "ok": levels["ok"] / n,
        "warn": levels["warn"] / n,
        "alert": levels["alert"] / n,
        "avg_score": sum(scores) / n,
    }


def show(name: str, r: dict[str, float]) -> None:
    print(
        f"  {name:8s} ok={r['ok']:6.1%} warn={r['warn']:6.1%} alert={r['alert']:6.1%} "
        f"平均分={r['avg_score']:5.1f}"
    )


def fake_text() -> str:
    return (
        "他愣住了。真的。太突然了。\n"
        "「你说什么？」他问。「我不知道。」她说。「别问了。」他答。「为什么？」她追问。\n"
        "然而，事情并没有那么简单。值得注意的是，这一切都变了。毋庸置疑，从某种角度来说，"
        "这一切都在某种程度上发生了变化。\n"
    )


def main() -> None:
    book = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BOOK
    if not book.exists():
        print(f"语料不存在: {book}")
        return

    text = book.read_text(encoding="utf-8", errors="ignore")
    chapters = chapter_texts(text)
    print(f"《{book.stem}》 {len(chapters)} 章可解析 (原文 {len(text):,} 字)")

    random.seed(0)
    picked = sorted(random.sample(range(30, len(chapters)), min(SAMPLE, len(chapters) - 30)))
    global_base = build_baseline(chapters[:12])

    a, b, c = [], [], []
    for i in picked:
        ch = chapters[i]
        window = chapters[max(0, i - WINDOW):i]
        b_base = build_baseline(window)
        bucket = bucket_of(measure(ch))
        same = [chunk for chunk in window if bucket_of(measure(chunk)) == bucket]
        c_base = build_baseline(same) if len(same) >= 2 else b_base

        a.append(detect_drift(ch, global_base))
        b.append(detect_drift(ch, b_base))
        c.append(detect_drift(ch, c_base))

    print(f"\n── 同书抽样 {len(picked)} 章（作者本人文字, 期望 alert 尽量低）──")
    show("A 固定", eval_levels(a))
    show("B 滚动", eval_levels(b))
    show("C 滚动+桶", eval_levels(c))

    fake = fake_text()
    i = 900
    window = chapters[i - WINDOW:i]
    bucket = bucket_of(measure(fake))
    same = [chunk for chunk in window if bucket_of(measure(chunk)) == bucket]
    print("\n── AI 味伪作检出（必须 100% alert）──")
    show("A 固定", eval_levels([detect_drift(fake, global_base)]))
    show("B 滚动", eval_levels([detect_drift(fake, build_baseline(window))]))
    show("C 滚动+桶", eval_levels([
        detect_drift(fake, build_baseline(same) if len(same) >= 2 else build_baseline(window))
    ]))

    counter: Counter[str] = Counter()
    for report in b:
        for key, detail in report["metrics"].items():
            if detail["severity"] != "ok":
                counter[key] += 1
    print(f"\n── 滚动基线下各指标偏离比例（{len(picked)} 章）──")
    for key, n in counter.most_common():
        print(f"  {key:34s} {n:4d}  ({n / len(picked):5.1%})")


if __name__ == "__main__":
    main()
