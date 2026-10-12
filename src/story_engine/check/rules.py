"""A 类校验器（N5）— 确定性、可定位、不误报的结构化检查。

对应计划书 MVP-2 的 2.2：**章末钩子 / 对话占比 / 段落长度 / 视角一致性 / 禁词与 AI 味**。

设计要点（都是前面节点踩出来的教训）：

- **可定位**：每条发现都带 `location`（字符区间 + 段落序号 + 摘录），审稿页才能"点一下就跳过去"。
- **确定性优先**：全部用 `style/metrics.py`（确定性指标）与 `polish`（词表）算，不调模型；
  这样同一个文本永远给同一个报告，作者才敢把它当闸门用（2.2 的验收就是"构造样例 → 逐条命中"）。
- **无基线不报 alert**：对话占比这类"相对"指标必须有基线（风格画像或前序章节）。
  没有基线时返回 `skipped`（附原因），而不是拿一个拍脑袋的阈值去误报
  —— 这是漂移检测校准时的真实教训：固定基线会把作者 58% 的章节误标为异常。
- **级别语义**：`alert` 必须处理 / `warn` 建议处理 / `ok` 通过 / `skipped` 本次无法判定（缺基线或样本不足）。
"""

from __future__ import annotations

import logging
import re
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from story_engine.polish import HOOK_KEYWORDS, SOFT_PATTERNS, SUSPENSE_PATTERNS
from story_engine.style import metrics
from story_engine.style.drift import DEFAULT_TOLERANCES
from story_engine.threads.manager import OPEN_STATUSES

logger = logging.getLogger("story_engine.check")

# ── 阈值（集中在此，便于按真实稿子调；每一条都注明依据）──
CHAPTER_HOOK_WINDOW = 200       # 章末钩子检查窗口（字）
PARAGRAPH_MAX_CHARS = 300       # 单段上限：与写作提示词"每段不超过300字"一致
# 对话占比容差**直接取自漂移检测的同一常量**（N5 评审 P1-8：两套阈值并存必然漂移）
DIALOGUE_TOLERANCE_PP = float(DEFAULT_TOLERANCES["dialogue_ratio"][1])
SOFT_FLAVOR_MIN_HITS = 3        # 软性 AI 味词出现次数达到多少才提示
POV_MIN_MARKERS = 2             # 段落里人称标记少于这个数就不判视角（避免短句误伤）
THREAD_DANGLE_THRESHOLD = 30    # 伏笔埋了这么多章还没回收 → 提示（可被 ThreadContext 覆盖）

# 真正算"AI 腔"的套话（**不用** polish.AI_PATTERNS：那是给 DeAIFilter.clean 的替换表，
# 里面含"然而，/但是，/在…的…下"这类正常中文，原样当硬告警会把好文字全标红 —— N5 评审 P0-2）
HARD_AI_TELLS = (
    "值得注意的是",
    "值得一提的是",
    "毋庸置疑",
    "不可否认",
    "毫无疑问",
    "从某种角度来说",
    "在一定程度上",
    "某种程度",
    "可以说是",
    "不禁让人",
)


@dataclass
class Location:
    """定位：字符区间 + 段落序号 + 摘录（供审稿页跳转与粘贴展示）。"""

    start: int
    end: int
    paragraph_index: Optional[int] = None
    excerpt: str = ""


@dataclass
class Finding:
    rule_id: str
    rule_name: str
    level: str                  # alert / warn / ok / skipped
    suggestion: str
    location: Optional[Location] = None
    details: Dict[str, object] = field(default_factory=dict)


@dataclass
class CheckReport:
    findings: List[Finding] = field(default_factory=list)
    baseline_source: str = "none"       # profile / previous_chapters / none
    text_length: int = 0
    rules_run: List[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        """整章级别 = 只反映**可执行结论**（alert > warn > ok）。

        评审 P1-5：`skipped`（例如没有基线）不是"这一章有问题"，把它混进级别会让干净文本显示成
        skipped、作者读成"没校验"。跳过信息用 `incomplete` / `skipped_rules` 单独表达。
        """
        actionable = [f for f in self.findings if f.level in ("alert", "warn", "ok")]
        if not actionable:
            return "ok"
        return "alert" if any(f.level == "alert" for f in actionable) else (
            "warn" if any(f.level == "warn" for f in actionable) else "ok"
        )

    @property
    def skipped_rules(self) -> List[str]:
        """本次**没能给出判定**的规则（含原因由 finding.suggestion 说明）。"""
        return sorted({f.rule_id for f in self.findings if f.level == "skipped"})

    @property
    def incomplete(self) -> bool:
        """有规则跳过 → 本次校验不完整（审稿页应提示"这部分没判定"，而不是当成通过）。"""
        return bool(self.skipped_rules)

    def summary(self) -> Dict[str, int]:
        counts = {"alert": 0, "warn": 0, "ok": 0, "skipped": 0}
        for f in self.findings:
            counts[f.level] = counts.get(f.level, 0) + 1
        return counts

    def by_rule(self) -> Dict[str, Dict[str, int]]:
        """按规则聚合（评审 P2：审稿页中栏要规则清单，逐条 flat 列表会刷屏）。"""
        agg: Dict[str, Dict[str, int]] = {}
        for f in self.findings:
            bucket = agg.setdefault(f.rule_id, {"alert": 0, "warn": 0, "ok": 0, "skipped": 0})
            bucket[f.level] = bucket.get(f.level, 0) + 1
        return agg

    def to_dict(self) -> Dict[str, object]:
        return {
            "level": self.level,
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "rule_name": f.rule_name,
                    "level": f.level,
                    "suggestion": f.suggestion,
                    "location": asdict(f.location) if f.location else None,
                    "details": f.details,
                }
                for f in self.findings
            ],
            "summary": self.summary(),
            "by_rule": self.by_rule(),
            "incomplete": self.incomplete,
            "skipped_rules": self.skipped_rules,
            "baseline_source": self.baseline_source,
            "text_length": self.text_length,
            "rules_run": self.rules_run,
        }


@dataclass
class Baseline:
    """校验基线：来自风格画像或前序章节；没有就是 `none`（对应规则会 skipped）。"""

    dialogue_ratio: Optional[float] = None
    source: str = "none"

    @property
    def has_dialogue(self) -> bool:
        return self.dialogue_ratio is not None


@dataclass
class ThreadContext:
    """伏笔账本上下文（N9）—— 与 `Baseline` 同一思路：**没有就不判，而不是猜**。

    文本规则只看 `text` 就够，但「悬空伏笔」「回收章不存在」这两条要账本本身才能判。
    所以它们不进 `DEFAULT_RULES`，只有调用方（`/api/check/chapter` 拿到 `novel_id` 时）
    显式传 `thread_context` 才跑 —— 这样既不改变既有 5 条规则的行为，也不会在缺账本时误报。
    """

    threads: Mapping[str, Any] = field(default_factory=dict)   # id -> PlotThread
    chapter_number: Optional[int] = None
    known_chapters: Sequence[int] = ()
    dangle_threshold: int = THREAD_DANGLE_THRESHOLD


def _profile_dialogue_ratio(profile_features: Optional[Mapping[str, Any]]) -> Optional[float]:
    """从风格画像 features 里取对话占比（0–1）。

    真实画像用的是**中文键 + 分数字典**（`style/db.py::StyleFeatureKeys.DIALOGUE_RATIO = "对话比例"`，
    值是 `{"value": "...", "score": n}`，score 已归一化到 0–1，见 `style/recommend.py::_feature_vector`）。
    N5 评审 P0-1：原本只找英文键 `dialogue_ratio`，而没有任何写入方产出该键 → "画像优先"是**死代码**。
    这里先认中文键的 `score`，再兼容英文数值键；都取不到就返回 None（由下层降级并告警）。
    """
    if not profile_features:
        return None

    entry = profile_features.get("对话比例")
    if isinstance(entry, dict):
        score = entry.get("score")
        if isinstance(score, (int, float)) and 0 <= float(score) <= 1:
            return float(score)
    direct = profile_features.get("dialogue_ratio")
    if isinstance(direct, (int, float)) and 0 <= float(direct) <= 1:
        return float(direct)
    return None


def build_baseline(
    profile_features: Optional[Mapping[str, Any]] = None,
    previous_texts: Optional[Sequence[str]] = None,
    min_previous: int = 2,
) -> Baseline:
    """按"风格画像 > 前序章节中位数"的顺序取基线；都不够就 none。

    `min_previous`：前序章节少于 2 章时中位数不可信 → 宁可不判（避免误报）。
    """
    from_profile = _profile_dialogue_ratio(profile_features)
    if from_profile is not None:
        return Baseline(dialogue_ratio=from_profile, source="profile")
    if profile_features:
        logger.debug("画像里没有可用的对话占比数值，基线降级到前序章节")

    texts = [t for t in (previous_texts or []) if t and t.strip()]
    if len(texts) >= min_previous:
        ratios = [metrics.dialogue_ratio(t) for t in texts]
        return Baseline(dialogue_ratio=float(statistics.median(ratios)), source="previous_chapters")

    return Baseline()


# ── 5 条规则 ─────────────────────────────────────────────

def _paragraph_spans(text: str) -> List[tuple[int, int, str]]:
    """返回 [(start, end, 段落文本)]（按空行切分，保留原始偏移）。"""
    spans: List[tuple[int, int, str]] = []
    for match in re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", text):
        para = match.group(0)
        if para.strip():
            spans.append((match.start(), match.end(), para))
    return spans


def check_chapter_hook(text: str) -> Finding:
    """R1 章末钩子：结尾窗口里要有悬念句或钩子词，否则读者不会点下一章。"""
    tail_start = max(0, len(text) - CHAPTER_HOOK_WINDOW)
    tail = text[tail_start:]
    hit = ""
    for kw in HOOK_KEYWORDS:
        if kw in tail:
            hit = kw
            break
    if not hit:
        for pattern in SUSPENSE_PATTERNS:
            m = re.search(pattern, tail)
            if m:
                hit = m.group(0)
                break
    if hit:
        return Finding(
            rule_id="chapter_hook",
            rule_name="章末钩子",
            level="ok",
            suggestion="",
            details={"hits": [hit]},
        )
    return Finding(
        rule_id="chapter_hook",
        rule_name="章末钩子",
        level="warn",
        suggestion=(
            "章末没找到钩子/悬念词：如果这是有意的文学性收尾，可忽略；"
            "想留读者则给最后一段加一个未解的问题、突发变化或反转"
        ),
        location=Location(start=tail_start, end=len(text), excerpt=tail[-60:]),
        details={"window": CHAPTER_HOOK_WINDOW},
    )


def check_paragraph_length(text: str) -> List[Finding]:
    """R3 段落长度：超长段拖节奏也不利于手机阅读（写作提示词里也是 300 字上限）。"""
    findings: List[Finding] = []
    for idx, (start, end, para) in enumerate(_paragraph_spans(text)):
        if len(para) > PARAGRAPH_MAX_CHARS:
            findings.append(
                Finding(
                    rule_id="paragraph_length",
                    rule_name="段落长度",
                    level="warn",
                    suggestion=(
                        f"这一段 {len(para)} 字超过 {PARAGRAPH_MAX_CHARS} 字："
                        "按「一个动作 / 一个说话人」拆成 2–3 段"
                    ),
                    location=Location(start=start, end=end, paragraph_index=idx, excerpt=para[:60]),
                    details={"chars": len(para), "max": PARAGRAPH_MAX_CHARS},
                )
            )
    if not findings:
        findings.append(
            Finding(rule_id="paragraph_length", rule_name="段落长度", level="ok", suggestion="")
        )
    return findings


def check_pov_consistency(text: str) -> Finding:
    """R4 视角一致性：段落里的人称与全章主视角冲突时提示（供"视角突跳"场景）。"""
    spans = _paragraph_spans(text)
    if len(spans) < 2:
        return Finding(
            rule_id="pov_consistency",
            rule_name="视角一致性",
            level="skipped",
            suggestion="段落太少，不足以判断视角一致性",
        )

    per_para: List[tuple[int, str]] = []
    for idx, (_start, _end, para) in enumerate(spans):
        # 先剥掉引号内对白（对白里的"他/她"是在说别人，不构成叙述视角 —— P1-1）
        narrative = metrics.strip_quoted_spans(para)
        # 只按 他/她 判视角（`它/祂` 是物件/神祇，第一人称写物件不代表视角切换 —— P1-2）
        counts = metrics.pov_counts(narrative, include_objects=False)
        first = counts["pov_first_count"]
        third = counts["pov_third_count"]
        if first < POV_MIN_MARKERS and third < POV_MIN_MARKERS:
            continue
        per_para.append((idx, "first" if first > third else "third"))

    if len(per_para) < 2:
        return Finding(
            rule_id="pov_consistency",
            rule_name="视角一致性",
            level="skipped",
            suggestion="带明显人称标记的段落不足，无法判断主视角",
        )

    counts = {"first": sum(1 for _i, p in per_para if p == "first"),
              "third": sum(1 for _i, p in per_para if p == "third")}
    dominant = "first" if counts["first"] >= counts["third"] else "third"
    jumps = [(idx, pov) for idx, pov in per_para if pov != dominant]

    if not jumps:
        return Finding(
            rule_id="pov_consistency",
            rule_name="视角一致性",
            level="ok",
            suggestion="",
            details={"dominant": dominant, "paragraphs": len(per_para)},
        )

    idx, jump_pov = jumps[0]
    start, end, para = spans[idx]
    jump_label = "第一人称" if jump_pov == "first" else "第三人称"
    dominant_label = "第一人称" if dominant == "first" else "第三人称"
    return Finding(
        rule_id="pov_consistency",
        rule_name="视角一致性",
        level="warn",
        suggestion=(
            f"全章主视角是{dominant_label}，但第 {idx + 1} 段（剥掉对白后）只有{jump_label}标记："
            "确认是有意的（回忆/转场）还是视角突跳"
        ),
        location=Location(start=start, end=end, paragraph_index=idx, excerpt=para[:60]),
        details={"dominant": dominant, "jump_paragraphs": [i + 1 for i, _p in jumps]},
    )


def check_dialogue_ratio(text: str, baseline: Baseline) -> Finding:
    """R2 对话占比：**相对指标**，必须有基线；无基线返回 skipped 而不是误报。

    注意：这是相对指标，**不给 location**（"整章偏多/偏少"没有单点可定位）。
    审稿页与前端必须容忍 `location == null`（只有能定位的规则才保证非空）。
    """
    if not baseline.has_dialogue:
        return Finding(
            rule_id="dialogue_ratio",
            rule_name="对话占比",
            level="skipped",
            suggestion="没有基线（风格画像或至少 2 章前序章节）→ 本次不判对话占比，避免误报",
            details={"baseline_source": baseline.source},
        )

    actual = metrics.dialogue_ratio(text)
    expected = float(baseline.dialogue_ratio or 0.0)
    delta = actual - expected
    details = {
        "actual": round(actual, 4),
        "expected": round(expected, 4),
        "delta_pp": round(delta * 100, 2),
        "tolerance_pp": round(DIALOGUE_TOLERANCE_PP * 100, 1),
        "baseline_source": baseline.source,
    }
    if abs(delta) <= DIALOGUE_TOLERANCE_PP:
        return Finding(
            rule_id="dialogue_ratio",
            rule_name="对话占比",
            level="ok",
            suggestion="",
            details=details,
        )
    direction = "偏少" if delta < 0 else "偏多"
    return Finding(
        rule_id="dialogue_ratio",
        rule_name="对话占比",
        level="warn",
        suggestion=(
            f"本章对话占比 {actual:.0%}，比基线（{expected:.0%}）{direction} "
            f"{abs(delta) * 100:.0f} 个百分点：确认节奏是否偏离你自己的惯常写法"
        ),
        details=details,
    )


def check_ai_flavor(text: str) -> List[Finding]:
    """R5 禁词 / AI 味：只标**真正的套话**（`HARD_AI_TELLS`），软性词聚合提示。

    刻意不用 `polish.AI_PATTERNS`：那是 `DeAIFilter.clean` 的替换表，含"然而，/但是，/在…的…下"
    这类正常中文，当硬告警会大面积误报（N5 评审 P0-2）。软性词表（`SOFT_PATTERNS`）保留，
    但只做**聚合**提示，不逐条报警。
    """
    findings: List[Finding] = []
    for tell in HARD_AI_TELLS:
        hits = [m for m in re.finditer(re.escape(tell), text)]
        if not hits:
            continue
        first = hits[0]
        findings.append(
            Finding(
                rule_id="ai_flavor",
                rule_name="AI 味/套话",
                level="warn",
                suggestion=(
                    f"AI 套话「{tell}」（出现 {len(hits)} 次）：换成具体动作或直接删掉更自然"
                ),
                location=Location(
                    start=first.start(), end=first.end(), excerpt=first.group(0)
                ),
                details={"tell": tell, "count": len(hits)},
            )
        )

    soft_hits: List[str] = []
    for pattern in SOFT_PATTERNS:
        soft_hits.extend(re.findall(pattern, text))
    if len(soft_hits) >= SOFT_FLAVOR_MIN_HITS:
        first_soft = re.search("|".join(SOFT_PATTERNS), text)
        findings.append(
            Finding(
                rule_id="ai_flavor",
                rule_name="AI 味/套话",
                level="warn",
                suggestion=(
                    f"软性套话出现 {len(soft_hits)} 次（{', '.join(sorted(set(soft_hits))[:5])}）："
                    "这类词一多就有「AI 腔」，建议保留最必要的 1–2 处"
                ),
                location=Location(
                    start=first_soft.start() if first_soft else 0,
                    end=first_soft.end() if first_soft else 0,
                    excerpt=first_soft.group(0) if first_soft else "",
                ),
                details={"soft_hits": len(soft_hits), "threshold": SOFT_FLAVOR_MIN_HITS},
            )
        )

    if not findings:
        findings.append(
            Finding(rule_id="ai_flavor", rule_name="AI 味/套话", level="ok", suggestion="")
        )
    return findings


# ── 伏笔账本规则（N9，需要 ThreadContext 才跑）─────────────

def check_dangling_threads(
    threads: Optional[Mapping[str, Any]],
    chapter_number: Optional[int] = None,
    threshold: int = THREAD_DANGLE_THRESHOLD,
) -> List[Finding]:
    """R6 悬空伏笔：埋了太久没回收，读者早忘了 —— 网文作者的真实痛点。

    没有账本 / 没有章号 → `skipped`（说明原因），不拿拍脑袋的阈值误报。
    `alert` 表示「远超阈值，该处理了」，`warn` 表示「该留意」。
    """
    ledger = dict(threads or {})
    if not ledger:
        return [
            Finding(
                rule_id="dangling_threads",
                rule_name="悬空伏笔",
                level="skipped",
                suggestion="本书还没有伏笔账本 → 本次不判悬空（先建账本，校验才有依据）",
            )
        ]
    if chapter_number is None:
        return [
            Finding(
                rule_id="dangling_threads",
                rule_name="悬空伏笔",
                level="skipped",
                suggestion="缺少当前章号 → 无法判断伏笔悬了多久",
            )
        ]

    dangling: List[tuple[int, Any]] = []
    for t in ledger.values():
        if getattr(t, "status", "") not in OPEN_STATUSES:
            continue                      # 已回收 / 已放弃不算悬空
        planted = getattr(t, "planted_chapter", 0) or 0
        if planted > chapter_number:
            continue                      # 本章还没埋到它
        gap = chapter_number - planted
        if gap > threshold:
            dangling.append((gap, t))

    if not dangling:
        return [
            Finding(rule_id="dangling_threads", rule_name="悬空伏笔", level="ok", suggestion="")
        ]

    dangling.sort(key=lambda item: (-item[0], getattr(item[1], "id", "")))
    gap, worst = dangling[0]
    level = "alert" if gap > threshold * 2 else "warn"
    title = getattr(worst, "title", "") or getattr(worst, "id", "")
    return [
        Finding(
            rule_id="dangling_threads",
            rule_name="悬空伏笔",
            level=level,
            suggestion=(
                f"「{title}」埋于第 {worst.planted_chapter} 章，已 {gap} 章没回收"
                f"（阈值 {threshold}）：要么安排回收，要么标记为 abandoned"
            ),
            details={
                "count": len(dangling),
                "threshold": threshold,
                "thread_ids": [getattr(t, "id", "") for _g, t in dangling],
            },
        )
    ]


def check_unknown_payoff(
    threads: Optional[Mapping[str, Any]],
    known_chapters: Sequence[int] = (),
) -> List[Finding]:
    """R7 回收章不存在：改章节顺序后，`payoff_chapter` 指向的章可能已经没了。

    这是位置信息的典型失效模式（马良写作把「埋设章节 ID / 回收章节 ID」列为
    「千万别偷懒不填」的字段，也正是最容易随改章号失效的字段）。

    **只判 `status == "paid_off"` 的条目**（评审 P2-2）：作者常按「计划」提前把回收章填成
    一个还没写到的未来章号（`status=planted`），那不是错误；只有「声称已回收、但那一章不存在」
    才是真问题。账本为空或不知道有哪些章 → `skipped`，不猜。
    """
    ledger = dict(threads or {})
    if not ledger:
        return [
            Finding(
                rule_id="unknown_payoff",
                rule_name="回收章有效性",
                level="skipped",
                suggestion="本书还没有伏笔账本 → 本次不判回收章",
            )
        ]
    chapters = {int(c) for c in (known_chapters or [])}
    if not chapters:
        return [
            Finding(
                rule_id="unknown_payoff",
                rule_name="回收章有效性",
                level="skipped",
                suggestion="无法确认哪些章已存在（没有章节列表）→ 本次不判回收章",
            )
        ]

    bad = [
        t
        for t in ledger.values()
        if getattr(t, "status", "") == "paid_off"
        and getattr(t, "payoff_chapter", None) is not None
        and t.payoff_chapter not in chapters
    ]
    if not bad:
        return [
            Finding(rule_id="unknown_payoff", rule_name="回收章有效性", level="ok", suggestion="")
        ]

    bad.sort(key=lambda t: getattr(t, "id", ""))
    worst = bad[0]
    title = getattr(worst, "title", "") or getattr(worst, "id", "")
    return [
        Finding(
            rule_id="unknown_payoff",
            rule_name="回收章有效性",
            level="alert",
            suggestion=(
                f"「{title}」的回收章第 {worst.payoff_chapter} 章不存在："
                "多半是改章节顺序后失效了，请改成实际回收的那一章"
            ),
            details={
                "count": len(bad),
                "thread_ids": [getattr(t, "id", "") for t in bad],
                "known_chapters": sorted(chapters),
            },
        )
    ]


DEFAULT_RULES = ("chapter_hook", "dialogue_ratio", "paragraph_length", "pov_consistency", "ai_flavor")

# 需要账本上下文的规则：**不进 DEFAULT_RULES**（保持既有 5 条的行为完全不变）
THREAD_RULES = ("dangling_threads", "unknown_payoff")


def run_rules(
    text: str,
    baseline: Optional[Baseline] = None,
    rules: Sequence[str] = DEFAULT_RULES,
    *,
    thread_context: Optional[ThreadContext] = None,
) -> CheckReport:
    """跑一组 A 类规则（确定性：同输入同报告）。

    `thread_context`（N9）：伏笔账本类规则（`THREAD_RULES`）需要它。
    不传时这两条规则返回 `skipped`（进 `skipped_rules` / `incomplete`），
    **不会**变成 alert —— 「没依据就不判」是 N5 定下的铁律。
    """
    baseline = baseline or Baseline()
    findings: List[Finding] = []
    for rule in rules:
        if rule == "chapter_hook":
            findings.append(check_chapter_hook(text))
        elif rule == "dialogue_ratio":
            findings.append(check_dialogue_ratio(text, baseline))
        elif rule == "paragraph_length":
            findings.extend(check_paragraph_length(text))
        elif rule == "pov_consistency":
            findings.append(check_pov_consistency(text))
        elif rule == "ai_flavor":
            findings.extend(check_ai_flavor(text))
        elif rule == "dangling_threads":
            ctx = thread_context or ThreadContext()
            findings.extend(
                check_dangling_threads(ctx.threads, ctx.chapter_number, ctx.dangle_threshold)
            )
        elif rule == "unknown_payoff":
            ctx = thread_context or ThreadContext()
            findings.extend(check_unknown_payoff(ctx.threads, ctx.known_chapters))
        else:
            raise ValueError(
                f"未知校验规则: {rule!r}（可用: {list(DEFAULT_RULES) + list(THREAD_RULES)}）"
            )

    return CheckReport(
        findings=findings,
        baseline_source=baseline.source,
        text_length=len(text),
        rules_run=list(rules),
    )
