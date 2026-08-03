#!/usr/bin/env python3
"""P6 文风画像批量生成 — 第一批 12 本，本地模型 gm4:latest
用法: python3 p6_style_batch.py [limit] [offset]  # limit=本数, offset=跳过前N本
"""
import json, re, sys, time, uuid
import urllib.request

OLLAMA = "http://localhost:11434"
MODEL = "gm4:latest"
GENRE_CN = {'serious': '严肃文学', 'humor_satire': '幽默讽刺',
            'tragic': '悲伤文学', 'popular': '流行文学'}

ANALYZE_PROMPT = """你是一位专业的文学风格分析专家。请分析以下小说片段（用 ===TEXT=== 包裹）的文风特征。

请从以下几个维度进行分析，每个维度用「特征名: 值」格式输出，保持客观可量化：

1. **词汇水平**: 通俗/典雅/古朴/华丽/口语化/书面化 — 并给出 1-10 评分
2. **平均句长**: 估计每句平均字符数（范围值即可）
3. **句长变化**: 统一/中等/丰富 — 句长是否多变
4. **虚词使用**: 多/中等/少 — 的/了/着/过 等虚词频率
5. **对话比例**: 估计对话文字占比百分比
6. **叙事视角**: 第一人称/第三人称/全知视角/有限视角
7. **排比对仗**: 多/中等/少 — 排比/对仗句频率
8. **疑问句比例**: 多/中等/少
9. **比喻使用**: 多/中等/少 — 明喻/暗喻频率
10. **拟人使用**: 多/中等/少
11. **引用用典**: 多/中等/少 — 是否常用典
12. **描写特点**: 简练/细腻/华丽/写意 — 环境/外貌/心理描写的风格
13. **平均段落长度**: 短/中/长
14. **整体风格一句话总结**: 20 字以内概括

===TEXT===
{text}
===TEXT===

按以下 JSON 格式输出（只输出 JSON）：
{{
  "词汇水平": {{"value": "通俗", "score": 7, "detail": "..."}},
  "平均句长": {{"value": "20-30字", "score": 5, "detail": "..."}},
  "句长变化": {{"value": "中等", "score": 6, "detail": "..."}},
  "虚词使用": {{"value": "多", "score": 7, "detail": "..."}},
  "对话比例": {{"value": "40%", "score": 6, "detail": "..."}},
  "叙事视角": {{"value": "第三人称全知", "score": 8, "detail": "..."}},
  "排比对仗": {{"value": "少", "score": 3, "detail": "..."}},
  "疑问句比例": {{"value": "少", "score": 3, "detail": "..."}},
  "比喻使用": {{"value": "多", "score": 8, "detail": "..."}},
  "拟人使用": {{"value": "中等", "score": 5, "detail": "..."}},
  "引用用典": {{"value": "多", "score": 8, "detail": "..."}},
  "描写特点": {{"value": "细腻", "score": 8, "detail": "..."}},
  "平均段落长度": {{"value": "中", "score": 6, "detail": "..."}},
  "整体风格总结": "一句话描述"
}}"""


def call_model(text):
    prompt = ANALYZE_PROMPT.format(text=text)
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": 2048, "stream": False,
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    content = data["message"]["content"]
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    m = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not m:
        return None, content[:200]
    # 清理未转义控制字符（模型偶发输出字面换行/制表符）
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", m.group(0))
    try:
        return json.loads(raw), ""
    except Exception as e:
        return None, f"JSON解析失败: {e}"


def process_book(book):
    """处理一本书，返回 (features, sample, error)"""
    path = f"/mnt/d/文章数据/{book['file']}"
    try:
        with open(path, encoding="utf-8") as f:
            full = f.read()
    except Exception as e:
        return None, None, f"读文件失败: {e}"

    sample = full[:4000]
    # 取中段另一个样本做校验（可选：此处只用开头）
    features, err = call_model(sample)
    if features is None:
        return None, None, f"模型分析失败: {err}"
    return features, sample[:2000], ""


def main():
    # 用法: python3 p6_style_batch.py [limit] [offset] | python3 p6_style_batch.py idx:0,8,10
    batch = json.load(open("/tmp/batch1.json", encoding="utf-8"))
    if len(sys.argv) > 1 and sys.argv[1].startswith("idx:"):
        idxs = [int(x) for x in sys.argv[1][4:].split(",")]
        books = [batch[i] for i in idxs]
    else:
        limit = int(sys.argv[1]) if len(sys.argv) > 1 else 12
        offset = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        books = batch[offset:offset + limit]
    print(f"批次: {len(books)} 本", flush=True)

    results = []
    for i, book in enumerate(books, 1):
        t0 = time.time()
        title = book["title"] or book["file"].split("/")[-1].replace(".txt", "")
        print(f"[{i}/{len(books)}] {title} ...", flush=True)
        features, sample, err = process_book(book)
        if err:
            print(f"  ✗ {err}", flush=True)
            results.append({"title": title, "ok": False, "error": err})
            continue
        # 生成 profile 记录
        rec = {
            "name": f"{title}风格",
            "author": book.get("author", ""),
            "source_work": title,
            "genre": GENRE_CN.get(book.get("genre", ""), book.get("genre", "")),
            "features": features,
            "style_prompt": features.get("整体风格总结", ""),
            "sample_text": sample,
            "id": f"style_{int(time.time())}_{i}",
        }
        results.append({"title": title, "ok": True, "rec": rec,
                        "time_s": round(time.time() - t0, 1)})
        print(f"  ✓ {features.get('整体风格总结', '(无总结)')} ({round(time.time()-t0,1)}s)",
              flush=True)

    # 汇总保存
    ok = [r for r in results if r["ok"]]
    out = "/tmp/style_batch_result.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\n完成: {len(ok)}/{len(books)} 成功 → {out}", flush=True)
    for r in results:
        if not r["ok"]:
            print(f"  失败: {r['title']}: {r['error']}", flush=True)


if __name__ == "__main__":
    main()
