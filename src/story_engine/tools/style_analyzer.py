"""文风分析器 — 分析外部小说/资料提取风格指纹"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List

from story_engine.tools.memory_models import NovelStyleProfile, WritingSample

_DIALOGUE_RE = re.compile(r'[「」『』""]')
_PSYCH_WORDS = (
    "想", "觉得", "感到", "知道", "认为", "明白", "理解",
    "猜测", "暗想", "心道", "思忖", "盘算", "自问",
)
_ACTION_VERBS = frozenset((
    "走", "跑", "跳", "说", "喊", "叫", "笑", "哭", "看", "望",
    "拿", "放", "提", "抓", "推", "拉", "踢", "打", "杀", "冲",
    "追", "挥", "踏", "翻", "爬", "跃", "坐", "站", "倒", "扶",
    "举", "扔", "抱", "背", "砍", "刺", "挡", "躲", "退", "进",
    "出", "回", "来", "去", "问", "答", "迎", "拜", "跪",
    "转身", "起身", "迈", "跨", "腾", "扑", "掀",
))


def _classify_sentence(sentence: str) -> str:
    """将句子归入互斥四类之一：dialogue / psychological / action / description

    先去掉前导的右引号（前一句被标点切分后残留），避免污染分类。
    """
    s = sentence.lstrip('」』”"')
    if _DIALOGUE_RE.search(s):
        return "dialogue"
    if any(w in s for w in _PSYCH_WORDS):
        return "psychological"
    if any(v in s for v in _ACTION_VERBS):
        return "action"
    return "description"


def analyze_text_style(
    text: str,
    source_name: str = "",
    source_url: str = "",
) -> dict:
    """对一段文本做定量文风分析，返回各项指标

    四类占比（对话/心理/动作/描写）按句子互斥分类后分别统计，
    保证各占比互斥且合计 ≈ 1。
    """
    if not text:
        return {}

    # 清洗
    clean = text.strip()

    # 句子统计（保留标点，避免「」括号与标点错位）
    sentences = re.split(r'(?<=[。！？\n])', clean)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 2]
    total_sentences = len(sentences)
    if total_sentences == 0:
        return {}

    avg_sentence_len = sum(len(s) for s in sentences) / total_sentences
    total_chars = len(clean)

    # 四类互斥占比：每句只归入一类（对话 > 心理 > 动作 > 描写）
    buckets = {"dialogue": 0, "psychological": 0, "action": 0, "description": 0}
    for s in sentences:
        buckets[_classify_sentence(s)] += len(s)
    classified = sum(buckets.values())
    dialogue_pct = buckets["dialogue"] / classified if classified else 0
    psych_pct = buckets["psychological"] / classified if classified else 0
    action_pct = buckets["action"] / classified if classified else 0
    desc_pct = buckets["description"] / classified if classified else 0

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
        "psych_percentage": round(psych_pct, 2),
        "action_percentage": round(action_pct, 2),
        "description_percentage": round(desc_pct, 2),
        "sentence_count": total_sentences,
        "total_chars": total_chars,
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
) -> NovelStyleProfile:
    """从文本构建完整的文风档案"""
    stats = analyze_text_style(text, source_name, source_url)

    profile = NovelStyleProfile(
        novel_id=novel_id,
        name=profile_name,
        avg_sentence_length=stats.get("avg_sentence_length", 0),
        dialogue_percentage=stats.get("dialogue_percentage", 0),
        description_percentage=stats.get("description_percentage", 0),
        psychological_percentage=stats.get("psych_percentage", 0),
        action_percentage=stats.get("action_percentage", 0),
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


def compare_with_profile(profile: NovelStyleProfile, new_text: str) -> Dict[str, str]:
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
