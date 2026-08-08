"""固定流程工具集 — 角色/地名一致性检查"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

# ── 一致性检查 ────────────────────────────────

def check_name_consistency(
    new_text: str,
    known_names: List[str],
    known_places: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """检查新文本中已知角色/地名是否保持一致

    返回:
        [{"type": "character"|"place"|"typo", "name": str, "issue": str}, ...]

    性能（L16.1）：预先对正文建定长 n-gram 索引，模糊匹配只查对应长度桶而非
    全量扫描 O(N×M)；每个地名最多报一条 issue；阈值收紧为等长且仅差一个字
    才算疑似，降低误报。
    """
    issues: List[Dict[str, Any]] = []
    known_places = known_places or []

    # 检查角色名是否被错误改写
    for name in known_names:
        # 拆分角色名各部分
        parts = list(name)
        for i in range(1, len(parts)):
            alt = name[:i] + "了" + name[i:]
            if alt in new_text:
                issues.append({
                    "type": "typo",
                    "name": name,
                    "issue": f"可能存在错字「{alt}」，应为「{name}」",
                })
                break

    if not known_places:
        return issues

    # 预分词建倒排索引（L16.1）：对正文每个定长 n-gram 生成「去掉第 k 位」的
    # 签名，倒排到出现该签名的词集合。查询时地名只查自身 n 个签名桶，
    # 桶内候选天然满足「仅差一字」，总复杂度 O((N+M)×n) 而非 O(N×M)。
    lengths = {len(p) for p in known_places if len(p) >= 2}
    index = _build_ngram_index(new_text, lengths)

    # 检查地名是否被错误改写（阈值：等长且仅差一个字；每地名最多一条 issue）
    for place in known_places:
        if len(place) < 2 or place in new_text:
            continue
        matched_word = _find_similar_word(place, index)
        if matched_word:
            issues.append({
                "type": "place",
                "name": place,
                "issue": f"地名疑似不一致: 文中写「{matched_word}」，设定为「{place}」",
            })

    return issues


def _build_ngram_index(text: str, lengths: Set[int]) -> Dict[Tuple[int, str], Set[str]]:
    """建「去一位签名」倒排索引: (k, 去掉第 k 位后的子串) → 出现该签名的词集合。"""
    index: Dict[Tuple[int, str], Set[str]] = {}
    for n in lengths:
        for i in range(len(text) - n + 1):
            word = text[i:i + n]
            for k in range(n):
                sig = (k, word[:k] + word[k + 1:])
                index.setdefault(sig, set()).add(word)
    return index


def _find_similar_word(place: str, index: Dict[Tuple[int, str], Set[str]]) -> Optional[str]:
    """查询与 place 等长且仅差一个字的候选词（首命中即返回）。

    阈值收紧为「恰好差一字」：地名与候选词在同一位置去掉同一位后签名一致，
    即只有该位可不同，其余位必须相同。
    """
    n = len(place)
    for k in range(n):
        sig = (k, place[:k] + place[k + 1:])
        for word in index.get(sig, ()):
            if word != place:
                return word  # 首命中即返回，每地名至多一条
    return None
