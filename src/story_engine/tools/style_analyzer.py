"""文风分析器 — 分析外部小说/资料提取风格指纹"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Tuple

from story_engine.tools.memory_models import StyleProfile, WritingSample


def analyze_text_style(
    text: str,
    source_name: str = "",
    source_url: str = "",
) -> dict:
    """对一段文本做定量文风分析，返回各项指标"""
    if not text:
        return {}

    # 清洗
    clean = text.strip()

    # 句子统计
    sentences = re.split(r'[。！？\n]+', clean)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 2]
    total_sentences = len(sentences)
    if total_sentences == 0:
        return {}

    avg_sentence_len = sum(len(s) for s in sentences) / total_sentences

    # 对话占比（检测引号）
    dialogue_chars = len("".join(re.findall(r'「[^」]*」|"[^"]*"|『[^』]*』', clean)))
    total_chars = len(clean)
    dialogue_pct = dialogue_chars / total_chars if total_chars else 0

    # 描述 vs 动作 vs 心理
    desc_chars = 0
    action_indicator = 0
    # 近似的判定: 含有 "了" "着" "过" "把" 等动作标记的句子 = 动作
    # 含有 "想" "觉得" "感到" "知道" = 心理
    psych_chars = 0
    psych_words = re.findall(r'[。！？]([^。！？]*(?:想|觉得|感到|知道|认为|明白|理解|猜测)[^。！？]*[。！？])', clean)
    psych_chars = sum(len(p) for p in psych_words)

    # 高频形容词和动词
    words = re.findall(r'[\u4e00-\u9fff]{2,4}', clean)
    word_freq = Counter(words).most_common(20)
    # 简单区分：常见动词标记
    verb_suffixes = ('了', '着', '过', '到', '出', '起', '上', '下')
    adj_like = []
    verb_like = []
    for w, c in word_freq:
        if any(w.endswith(s) for s in verb_suffixes) or len(w) <= 2:
            verb_like.append(w)
        else:
            adj_like.append(w)

    return {
        "avg_sentence_length": round(avg_sentence_len, 1),
        "dialogue_percentage": round(dialogue_pct, 2),
        "sentence_count": total_sentences,
        "total_chars": total_chars,
        "psych_percentage": round(psych_chars / total_chars, 2) if total_chars else 0,
        "top_adjectives": adj_like[:10],
        "top_verbs": verb_like[:10],
        "source_name": source_name,
        "source_url": source_url,
    }


def build_style_profile(
    text: str,
    novel_id: str,
    profile_name: str,
    source_name: str = "",
    source_url: str = "",
) -> StyleProfile:
    """从文本构建完整的文风档案"""
    stats = analyze_text_style(text, source_name, source_url)

    profile = StyleProfile(
        novel_id=novel_id,
        name=profile_name,
        avg_sentence_length=stats.get("avg_sentence_length", 0),
        dialogue_percentage=stats.get("dialogue_percentage", 0),
        description_percentage=round(1 - stats.get("dialogue_percentage", 0) - stats.get("psych_percentage", 0), 2),
        psychological_percentage=stats.get("psych_percentage", 0),
        action_percentage=round(1 - stats.get("dialogue_percentage", 0), 2),
        top_adjectives=stats.get("top_adjectives", []),
        top_verbs=stats.get("top_verbs", []),
    )

    if source_name:
        profile.samples.append(WritingSample(
            source_name=source_name,
            source_url=source_url,
            text_snippet=text[:500],
        ))

    return profile


def extract_techniques(text: str) -> List[str]:
    """从文本中检测可能使用的写作技法"""
    techniques = []

    # 开头技法
    first_line = text.split("\n")[0].strip() if text else ""
    if first_line and len(first_line) < 30:
        techniques.append("短句开篇（钩子式）")
    elif first_line and len(first_line) > 80:
        techniques.append("长句开篇（铺陈式）")

    # 对话形式
    if re.search(r'「[^」]+」', text):
        techniques.append("中式对话（括号引语）")

    if re.search(r'"[^"]+"\s*说', text):
        techniques.append("西式对话（引导引语）")

    # 段落长度
    paras = [p for p in text.split("\n") if len(p.strip()) > 20]
    if paras:
        avg_para = sum(len(p) for p in paras) / len(paras)
        if avg_para > 300:
            techniques.append("长段落（厚重叙事）")
        elif avg_para < 100:
            techniques.append("短段落（快节奏）")

    # 排比/对仗
    parallels = len(re.findall(r'(?:不(?:能|会|要|是|知道)[^，。]*，不(?:能|会|要|是|知道))', text))
    if parallels > 3:
        techniques.append("排比/对仗强化语气")

    return techniques


def compare_with_profile(profile: StyleProfile, new_text: str) -> Dict[str, str]:
    """比较新文本和已有文风的差异"""
    stats = analyze_text_style(new_text)
    diffs = {}
    if profile.avg_sentence_length and stats.get("avg_sentence_length"):
        diff = stats["avg_sentence_length"] - profile.avg_sentence_length
        if abs(diff) > 5:
            diffs["sentence_length"] = f"偏差{diff:+.1f}字/句（基准{profile.avg_sentence_length}）"
    if profile.dialogue_percentage and stats.get("dialogue_percentage"):
        diff = stats["dialogue_percentage"] - profile.dialogue_percentage
        if abs(diff) > 0.15:
            diffs["dialogue_ratio"] = f"对话占比偏差{diff:+.0%}（基准{profile.dialogue_percentage:.0%}）"
    return diffs
