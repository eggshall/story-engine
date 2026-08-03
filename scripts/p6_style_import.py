#!/usr/bin/env python3
"""P6 文风画像入库 — 把批量结果写入 style_profiles.db
用法: python3 p6_style_import.py <result.json> [result2.json ...]
"""
import json, sys, time, uuid
sys.path.insert(0, "/home/syzc/story-engine/src")

from story_engine.style.db import StyleDb, StyleProfile

def main():
    files = sys.argv[1:] or ["/tmp/style_batch_result.json"]
    db = StyleDb()
    n_ok, n_fail = 0, 0
    for f in files:
        results = json.load(open(f, encoding="utf-8"))
        for r in results:
            if not r.get("ok"):
                n_fail += 1
                continue
            rec = r["rec"]
            existing = None
            for p in db.list_profiles():
                if p.source_work == rec["source_work"]:
                    existing = p
                    break
            if existing:
                existing.features = rec["features"]
                existing.style_prompt = rec["style_prompt"]
                existing.sample_text = rec["sample_text"]
                existing.genre = rec["genre"]
                existing.author = rec["author"]
                pid = db.save_profile(existing)
                print(f"更新: {rec['name']} → {pid}")
            else:
                profile = StyleProfile(
                    name=rec["name"],
                    author=rec.get("author", ""),
                    source_work=rec["source_work"],
                    genre=rec.get("genre", ""),
                    features=rec["features"],
                    style_prompt=rec.get("style_prompt", ""),
                    sample_text=rec.get("sample_text", ""),
                    id=rec.get("id") or f"style_{int(time.time())}_{uuid.uuid4().hex[:6]}",
                )
                pid = db.save_profile(profile)
                print(f"新增: {rec['name']} → {pid}")
            n_ok += 1
    print(f"\n完成: {n_ok} 本入库, {n_fail} 失败")
    print(f"库内总数: {len(db.list_profiles())}")

if __name__ == "__main__":
    main()
