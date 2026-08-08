"""固定流程工具集 — 角色/地名一致性检查"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

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

    # 预建 n-gram 索引（L16.1）：按地名长度生成定长子串集合，只扫一遍正文。
    # 后续每个地名只查对应长度桶，O(候选数)，避免全量 O(N×M)。
    lengths = {len(p) for p in known_places if len(p) >= 2}
    ngrams: Dict[int, set] = {
        n: {new_text[i:i + n] for i in range(len(new_text) - n + 1)}
        for n in lengths
    }

    # 检查地名是否被错误改写（阈值：等长且仅差一个字；每地名最多一条 issue）
    for place in known_places:
        if len(place) < 2 or place in new_text:
            continue
        matched_word = _find_similar_word(place, ngrams.get(len(place), set()))
        if matched_word:
            issues.append({
                "type": "place",
                "name": place,
                "issue": f"地名疑似不一致: 文中写「{matched_word}」，设定为「{place}」",
            })

    return issues


def _find_similar_word(place: str, ngram_set: "set") -> Optional[str]:
    """在等长 n-gram 集合里找与 place 仅差一个字的候选词（首命中即返回）。"""
    n = len(place)
    for word in ngram_set:
        if word == place:
            continue
        same = sum(1 for a, b in zip(word, place) if a == b)
        if same >= n - 1:
            return word  # 命中一个即返回，每地名至多一条
    return None
