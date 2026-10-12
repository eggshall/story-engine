# P7 设计总纲 — 长篇一致性记忆层（Long-Form Consistency & Memory Layer）

> 目标：让 story-engine 能**正常持续地**写一本 2000 万字级中文长篇，并且**全书文风统一**。
> 日期：2026-10-11 ｜ 状态：设计定稿，M1 已落地
> 调研依据：`docs/research/R1-long-context-memory.md`（长上下文与记忆系统）、
> `docs/research/R2-style-consistency.md`（文风统一）、
> `docs/research/R3-prior-art-wiki.md`（先例与"每本小说一个知识库"评估）
> 任务追踪：`PLAN.md` → Phase 4 (P7)

---

## 0. 一页结论

1. **20M 字进不了任何上下文窗口，这不是工程问题而是已证伪的路线。** 2000 万汉字 ≈ 1500–2000 万 token；标称 1M 的窗口实测有效长度远小于标称（Chroma 18 模型受控实验：性能随长度一致衰减，加干扰项更差，且**结构连贯的长文本比打乱的更伤性能**；NoLiMa：32K 处 13 个模型里 11 个跌到短基线 50% 以下；RULER：17 个自称 ≥32K 的模型只有一半能在 32K 维持性能）。
2. **正解是「分层压缩 + 检索注入 + 结构化状态」**：把 20M 字压成**常驻 ~1.8 万字摘要骨架**，写作时再按需把最相关的原文片段（2–3 万字）拉进窗口。
3. **文风漂移是独立失效机制**（ConStory-Bench：文风类错误与时间线/角色/世界观/事实类错误相关性接近零）。修事实一致性不会顺带修好文风，必须独立工具链。
4. **Karpathy LLM Wiki 模式用于小说可行，但必须三处改造**（R3.B）：① 页面加时间/状态维度（人物会死、关系会变、伏笔会回收）；② 从"查询时读"改成"写作时注入"；③ 溯源从外部 source 改成"哪一章确立了这条设定"。
5. **本项目最优组合**（依据 + 成本 + 16GB 显存约束）：
   章→组→卷→全书四级滚动摘要 + 每本小说一个 markdown 知识库（人物/地点/事件/伏笔状态机）+ 本地 embedding 与 BM25 混合检索 + 现有 14 维文风画像 × 动态风格锚点 × 生成后漂移检测。
   全部分析类调用走本地模型（`gm4` 做 JSON 抽取、`bge-m3` 做 embedding），远程 DeepSeek 只负责写作本身。

---

## 1. 量级基线（本项目真实数据，非估算）

来自 `<数据根目录>/corpus`（70 本，2424 万字）实测统计：

| 统计项 | 实测值 |
|---|---|
| 可解析章节的书 | 27 / 70 |
| 单章平均字数 | 6542（中位数 6261） |
| 《全民魔女1994》 | 455 万字 / 1711 章 |

按 2000 万字长篇推算（单章 6500 字）：

| 层 | 规模 | token 估算（1 汉字 ≈ 1.2 tok） |
|---|---|---|
| L0 原文 | 2000 万字 / ~3077 章 | ≈ 2400 万 tok — **永不进上下文** |
| L1 章摘要 | 3077 × 250 字 = 77 万字 | ≈ 92 万 tok — 只做检索索引 |
| L2 组摘要（10 章） | 308 × 500 字 = 15 万字 | ≈ 18.5 万 tok |
| L3 卷摘要（100 章） | 31 × 1500 字 = 4.6 万字 | ≈ 5.6 万 tok |
| L4 全书主线 arc | 1 × 8000 字 | ≈ 9.6K tok |

**常驻骨架 = L4(9.6K) + 当前卷(1.8K) + 最近 10 章摘要(3K) + 状态层(3.6K) ≈ 1.8 万 tok**，再叠加检索原文 6×3000 字（≈21.6K tok）与锚点，单次写作输入落在 35–45K tok 区间 —— DeepSeek 128K 里还剩 ~85K 给正文生成与多轮规划。

> 结论：**"支持 20M 文本"= 让 20M 文本可以被检索与压缩，而不是可以被装进 prompt。**

---

## 2. 现状缺口（对应到现有代码）

| 能力 | 现状 | 缺口 |
|---|---|---|
| 前情提要 | `writer/engine.py::_build_previous_summary` 滑动窗口 **5 章**，纯字符串拼接 | 无分层摘要、无增量、写到 3000 章时窗口外全丢 |
| 设定注入 | `lore/lorebook.py` 关键词触发（扫描近期文本） | 无别名/递归链/scan depth/token 预算守卫；条目无状态与时间维度 |
| 持久记忆 | `tools/memory_models.py::SoulMemory`：`last_chapter_summary` + `active_threads` | 无随时间演化的实体状态（生死/位置/已知信息/关系强度）、无伏笔状态机 |
| 文风 | `style/db.py` 14 维画像 + 800 字样段锚点，**固定注入** | 不随场景变化；无生成后检测；无漂移告警 |
| 检索 | 无 | pyproject 里连 embedding 依赖都没有；跨 3000 章无法定位"第 200 章埋的伏笔" |
| 一致性检查 | `polish.check_continuity` 只做命名正则 | 查不了视角/语气/文风偏移，查不了时间线与设定冲突 |

---

## 3. 架构总览

```
                    ┌──────────────── 写作请求（第 N 章）────────────────┐
                    │                                                  │
  L4 主线 arc ──────┤                                                  │
  L3 卷摘要   ──────┤        ┌───────────────────────────┐             │
  L1 章摘要   ──────┼───────▶│  上下文装配器 (budgeted)   │───▶ LLM ──▶ 草稿
  L2 状态层   ──────┤        └───────────────────────────┘             │
  L3 检索片段 ──────┤                    ▲                             │
  风格锚点    ──────┘                    │                             │
                                        │                             ▼
   ┌─────────────────── 写后固化 (Consolidation, 本地模型) ───────────────────┐
   │ ① 场景切块 → embed 入库   ② 章摘要 JSON   ③ 状态/伏笔 diff → 知识库页更新 │
   │ ④ 组/卷/arc 摘要滚动更新   ⑤ 文风指标入库   ⑥ 增量 lint + 待确认队列       │
   └──────────────────────────────────────────────────────────────────────┘
```

三层存储分工（**避免双写漂移的关键**）：

| 存储 | 角色 | 谁写 |
|---|---|---|
| `novels/<id>/novel.json` + `chapters/` | 正文 source of truth（现状不变） | 写作流程 |
| `novels/<id>/novel-kb/`（markdown 知识库） | **设定 canon 的权威源**，可 git、可 Obsidian 打开 | 固化流水线（agent）+ 作者 |
| `data/index/*.sqlite` | **派生索引**（摘要树 / 向量 / BM25 / 实体表），随时可重建 | 固化流水线（程序） |

规则：md 是权威，SQLite 是索引；索引不一致时以 md 重建，而不是反向覆盖。

---

## 4. 上下文装配器（Context Assembly）

按槽位装配，每个槽位有独立预算与填充策略。**预算硬上限 45K token**，超预算时按优先级降级（先砍检索片段，再砍组摘要，绝不砍状态层与文风锚点）。

| 槽 | 内容 | 预算 | 策略 | 位置 |
|---|---|---|---|---|
| S0 | 系统指令 + 本章任务 + **硬约束**（视角/人称/禁词/人物生死） | 1.5K | 固定 | **开头**（抗 lost-in-the-middle） |
| S1 | 文风块：总结 + 量化特征 + 2–3 段**按场景检索**的样本 | 3K | 动态 | 开头（与硬约束同区） |
| S2 | 全书主线 arc（L4） | 9.6K | 常驻 | 中部 |
| S3 | 当前卷 + 上一卷摘要（L3） | 2.5K | 常驻 | 中部 |
| S4 | 最近 8–10 章摘要（L1） | 3K | 常驻 | 中部（越近越靠后） |
| S5 | 状态层：本章出场人物当前状态卡 + 未回收伏笔表 + 命中设定条目 | 4K | 动态（实体命中） | 中部 |
| S6 | 检索原文片段 top-6 × 3000 字（L0） | 18K | 动态（混合检索） | 中部，**按相关度升序**（最相关贴近尾部） |
| S7 | 上一章结尾原文 2000 字 | 2.4K | 常驻 | **尾部**（接续锚点） |
| S8 | 本章大纲 / 节拍 | 1.5K | 常驻 | **尾部** |

位置原则来自实证：上下文**开头与结尾最有效**（Lost in the Middle），干扰项随长度放大（Context Rot）→ 硬约束与接续信息钉在两端，检索材料按相关度贴近尾部，且**宁少勿满**（Chroma：同一任务下"只放相关片段"显著优于"放全量"）。

### 4.1 场景类型路由（同一章内也要切）

超 2000 词的目标文本会出现"长度崩塌"与计划跟随衰减（IS-CoT / book-writing 论文），因此**按场景/节拍分段生成再拼接**，每段单独装配（战斗段多检索动作类锚点，对话段多检索对话样本与人物语气卡）。

---

## 5. 数据模型

### 5.1 知识库目录（每本小说一个，参照 R3.C）

```
novels/<novel_id>/novel-kb/
├── SCHEMA.md                  # 约定 + frontmatter 规范 + tag 分类法 + 建页阈值
├── index.md                   # 分类目录（一行一页, agent/程序先读它）
├── log.md                     # 追加式操作日志 [YYYY-MM-DD] action | subject
├── raw/                       # 不可变源: 大纲v1 / 灵感 / 拆书笔记（带 sha256）
├── entities/{characters,locations,organizations,items}/
├── timeline/{events/, timeline.md}
├── plot/{foreshadowing/, subplots/, arcs/}
└── style/anchors/             # 文风锚点（带 applies_when 触发条件）
```

### 5.2 页面 frontmatter（程序可解析的稳定 schema）

通用：`id`（稳定 slug，程序主键）、`type`、`title`、`aliases`（触发/别名回链）、`tags`、`status`（active/dormant/retconned）、`confidence`（confirmed/draft/conflict —— 语义是**作者确认度**，不是证据度）、`established_in`（哪一章确立，canon 溯源）、`established_by`（author/ai/draft）、`updated`。

类型特有：

| 类型 | 关键字段 |
|---|---|
| character | `alive`、`role`、`relationships[{to,kind,since,until}]`、`appearance_snapshot[{in,note}]`（supersedes 上一版）、`voice_anchor` |
| location/org/item | `region`、`contained_by`、`era_valid`、`significance` |
| event | `inworld_time`（书内时间）、`chapter`、`participants`、`causes`、`effects` |
| **foreshadow** | `foreshadow_status`（planted/developed/payed_off/abandoned）、`planted_in`、`payoff_in`、`payoff_plan`、`related_entities` |
| subplot/arc | `thread_status`（active/resolved/dropped）、`started_in`、`milestones[]` |
| style-anchor | `dimension`（战斗/对话/抒情/心理/环境）、`applies_when`、`register`、`sample`、`score` |

### 5.3 派生索引（SQLite）

```
summaries(work_id, level, idx, chapter_from, chapter_to, summary, tokens, updated_at)
chunks(work_id, chapter_no, scene_idx, text, char_count, vec_id, updated_at)
entities(work_id, entity_id, type, title, aliases, status, established_in, updated_at)
entity_states(entity_id, chapter_no, field, value, supersedes)      -- 时间维度解析
foreshadows(work_id, foreshadow_id, status, planted_in, payoff_in)
style_metrics(work_id, chapter_no, metrics_json, level, score)      -- 漂移巡检留痕
```

`entities/chunks` 表是**可重建**的派生数据；`markdown` 页永远优先。

---

## 6. 文风统一：三道闸 + 实测调参

### 6.1 三道闸

| 闸 | 时机 | 做法 | 依据 |
|---|---|---|---|
| 闸 1 生成前 | 装配 S1 | 风格总结 + 14 维量化特征 + **按当前场景动态检索**的样本段（替代固定注入同一段） + 硬禁词表 | PLOS ONE（11,998 份报告：动态检索 few-shot 全面优于固定 few-shot，p<0.05）；Sudowrite 经验：样本 > 描述 |
| 闸 2 生成中 | 生成时 | 低温度 + 把约束**写成可检验指令**（不改解码器）+ 分场景分段生成 | INSTRUCTCTG（约束言语化同样有效）；IS-CoT（>2000 词长度崩塌） |
| 闸 3 生成后 | 落地后 | `metrics.py` 确定性指标 + `drift.py` 漂移分级 + AI 套话命中 + 禁用词硬告警 → 超阈值触发**定点重写**（只重写命中段落）或 best-of-n(3) 按风格分 rerank | ConStory-Bench（文风是独立失效维度）；BoN 统计最优 + RBoN 防奖励攻击 |

### 6.2 M1 已落地：`style/metrics.py` + `style/drift.py`

- **17 项确定性指标**（无新依赖，纯 `re` + `statistics`）：句长均值/标准差、短句/长句占比、对话占比（支持 “” 弯引号）、段长、单句段落占比、感叹/疑问句比例、省略号密度、标点种类数、虚词比例、人称分布。
- **漂移检测**：基线中位数 + 容差（相对/绝对 + **地板值**）+ 聚合分级 + AI 套话按位置去重 + 禁用词硬告警 + 中文整改建议。

### 6.3 关键设计决策：聚合分级，而非逐指标判级

真实语料实测（《全民魔女1994》1711 章，抽 300 章，基线=前 12 章）：

| 策略 | ok | warn | alert | 平均分 |
|---|---|---|---|---|
| 逐指标判级（任一指标超阈值即 alert） | 2.3% | 39.7% | **58.0%** | 46.4 |
| 聚合分级 + 容差地板值（M1 实现） | 5.7% | 84.7% | **9.7%** | 53.2 |
| 聚合 + **滚动窗口基线**（推荐） | 16.0% | 83.3% | **0.7%** | 65.6 |
| 聚合 + 滚动窗口 + 场景分桶 | 15.7% | 84.0% | 0.3% | 65.9 |

- **结论 1（必做）**：逐指标判级不可用 —— 会把作者本人 58% 的章节判成 alert。
- **结论 2（必做）**：**基线必须用滚动窗口（被检章之前 10 章）**，而不是全书固定基线。alert 率 9.7% → 0.7%。
- **结论 3（不做）**：场景分桶（对话主导/动作短句/叙述长句）只带来 0.3pp 收益，**不值得实现的复杂度**。
- **结论 4**：`warn` 在 83% 的章节出现 —— 它天然是"观测记录"而非"待办告警"。**生产使用时只有 `alert` 触发人工/重写动作**，`warn` 写进 `style_metrics` 表做趋势观测。
- AI 味伪作（碎句 + 对话灌水 + 套话）在三种基线下均 **100% alert，score ≈ 0** —— 检出能力没有被调参牺牲。
- 仍最易偏离的指标（滚动基线下）：感叹句比例 8.3%、省略号密度 7.3%、第三人称占比 6.3%、对话占比 5.7% —— 都是"当下场景驱动"的指标，符合预期。

复现命令：`.venv/bin/python scripts/eval_style_drift.py`（改容差后必须重跑）。

### 6.4 下一步（M5）

best-of-n(3) 风格分 rerank；LoRA 待单作品语料 ≥3 万字后（16GB 可跑 QLoRA 7B 级，参考 StyleAdaptedLM 非结构化语料路线、WriterLoRA 冻结 A 矩阵技巧）；DPO/GRPO 与 n-gram logit 注入/激活向量**暂缓**（门槛高或证据显示脆弱）。

---

## 7. 一致性 lint（复用 ConStory-Bench 分类）

ConStory-Bench（ACL 2026, arXiv 2603.05890，开源 `Picrew/ConStory-Bench`）给出 5 大类 19 子类，本项目的 lint 直接按此分档：

| 类别 | 子类 | 本项目实现 |
|---|---|---|
| 时间线与情节 | 绝对时间/时长/同时性矛盾、无因之果、因果违例、**弃置情节** | 知识库 `timeline/` + arc `milestones` 交叉校验 |
| 角色刻画 | 记忆矛盾、知识冲突、能力波动、遗忘 | `entity_states` 时间维度 + 状态卡对比 |
| 世界观设定 | 核心规则/社会规范/地理违背 | `SCHEMA.md` 规则页 + 结构化校验 |
| 事实与细节 | 外貌不符、命名混淆、数量错误 | 现有 `check_name_consistency` + 别名表（扩展） |
| **叙事与文风** | **视角混淆、语气不一致、文风偏移** | **M1 `drift.py`（已实现）** |
| 伏笔（本系统加档） | planted 未 payoff 超过 N 章、payoff 无 plant | `plot/foreshadowing/` 状态机（M3） |

lint 输出必须锚定引文（ConStory-Checker 的 `fact_quote / location / contradiction_pair` 范式），且区分 `contradiction_kind: plot_hole | intentional_reveal | unreliable_narrator` —— 否则会把刻意伏笔（人物撒谎、记忆篡改）误报成 bug。

---

## 8. 分期与验收标准

| 期 | 内容 | 验收（可测） |
|---|---|---|
| **M1** ✅ | metrics + drift + 评测脚本 | 15 单测绿；ruff/mypy 绿；同书 300 章 alert ≤ 2%；AI 伪作 100% alert |
| **M2** | 章摘要 schema + 摘要树 + SQLite + 装配器 v1 | 20M 级装配输入 ≤ 45K tok（单测断言 token 数）；第 N 章可正确复述第 N−100 章主线 |
| **M3** | novel-kb 知识库 + 状态机 + 注入器 + lint | 写完一章后 index/log/命中页被增量更新且 lint 无断链；悬空伏笔可报出 |
| **M4** | 场景分块 + 本地 bge-m3 + BM25 混合检索 | 自建评测集（一致性/伏笔/文风问答）召回率达标；单次检索 < 100ms |
| **M5** | rerank / ConStory lint / 图谱 / LoRA | 按需，不阻塞 |

---

## 9. 明确不做（边界）

- ❌ 把 20M 字塞进上下文（已被三份独立实证证伪）。
- ❌ 对全文做 LLM 实体/关系抽取建图（20M 字成本不可行）→ 图谱只覆盖知识库实体层（几千~几万节点）。
- ❌ DPO/GRPO 风格对齐、n-gram logit 注入、激活向量/风格向量作为主方案（门槛高或实测脆弱）。
- ❌ 全自动"agent 自己改设定"—— **作者是唯一 canon 权威**，agent 只做增量维护与待确认标记（`confidence: draft`）。

## 10. 风险与对策

| 风险 | 对策 |
|---|---|
| 摘要的摘要累积失真 | 每卷末从**原文**重新生成 arc 摘要，而非只做滚动压缩 |
| md / SQLite / novel.json 三方漂移 | md 权威 + 索引可重建 + 增量 lint 校验；写路径统一走固化流水线 |
| 本地模型做 JSON 抽取不稳 | 复用既有实测结论：结构化抽取用 `gm4`（14 维扁平 JSON 稳定），中文创作才用 Qwen；控制字符清洗 + 幂等入库 |
| 成本 | 摘要/抽取/embedding 全本地；远程费用只花在正文生成 |
| 评测无公开基准 | R1/R2 均指出"中文长篇叙事 + 混合检索"无公开对照基准 → 必须自建评测集（M2/M4 验收的一部分） |

## 11. 证据与核验状态

| 结论 | 来源 | 核验 |
|---|---|---|
| 性能随输入长度一致衰减；结构连贯的长文本比打乱的更差；focused 优于 full input（113k tok） | Chroma, *Context Rot*（2025-07-14，18 模型） | ✅ 已核验原文 |
| 32K 处 11/13 模型跌破短基线 50%；GPT-4o 99.3%→69.7% | NoLiMa, arXiv 2502.05167 | ✅ 已核验摘要 |
| 17 个自称 ≥32K 的模型只有一半在 32K 维持性能 | RULER, arXiv 2404.06654 | ⚠️ 采信调研报告 |
| 文风类错误与事实/时间线/角色类相关性接近零（5 类 19 子类，证据锚定 JSON） | ConStory-Bench, ACL 2026, arXiv 2603.05890 | ✅ 已核验（含开源仓库） |
| 递归上下文可处理超窗口两个数量级输入；GPT-5 上相对 compaction 中位 +26% | RLM, arXiv 2512.24601（MIT CSAIL） | ✅ 已核验（v1 表述为"more than an order of magnitude"，v2 为"up to two orders"，取保守解读） |
| 动态检索 few-shot 全面优于固定 few-shot（p<0.05） | PLOS ONE, journal.pone.0354688 | ✅ 已核验结论；k=10/T=0 与 ROUGE 具体数值未逐项核验 |
| 多跳 QA 最多 +20%；单步检索达迭代检索水平，在线成本低一个数量级、快 6–13 倍 | HippoRAG, arXiv 2405.14831 | ✅ 已核验（论文不同版本表述为 10-20× 与 10-30×） |
| canon.md 硬事实库 + 伏笔台账 + ANTI-SLOP 词表层级 | NousResearch/autonovel（1.5k stars） | ✅ 已核验仓库与 PIPELINE.md |
| 其余 arXiv 2026 编号（2601.15300、2605.17064、2608.05169、2609.35759 等） | R2 报告转引 | ⚠️ 未逐条核验，引用时标注为"调研转引" |
| 每条断言的可验证 URL 清单 | — | 见 `docs/research/R1–R3` 各节 |
