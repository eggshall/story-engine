# R3 · 现有小说写作工具与知识库方案调研 &「每本小说一个 LLM Wiki」改造评估

> 目标：评估把 Karpathy「LLM Wiki」模式改造成 **story-engine 每本小说一个知识库** 的可行性，并给出目录结构与 frontmatter 草案。
> 调研日期：2026-10-11 · 所有机制描述均附来源 URL；未找到的直说。

---

## 0. 摘要（TL;DR）

1. **结论可行，但要做三处关键改造**：① 给每页加「时间/状态」维度（人物生死、地点、关系、伏笔状态会随时间变化，静态 wiki 页会过期）；② 把 wiki 的「query 时按需读」改造成「写作时按场景**注入**」（复用 lorebook 的关键词触发 + token 预算）；③ 把「来源溯源」从外部 source 改成「哪一章确立了这条设定」（canon 溯源）。
2. 最值得直接抄的两个先例：**SillyTavern World Info 的注入机制**（关键词触发 + 递归扫描 + scan depth + token 预算）和 **NousResearch/autonovel 的 canon.md**（跨层硬事实库 + 伏笔台账 + 设定改动向下传播）。
3. Karpathy wiki 的**双向链接 + index/log + SCHEMA + lint** 骨架全部可直接复用；「lint 找孤儿页/断链/矛盾」恰好能检测**伏笔悬空、设定冲突**这类小说一致性 bug。
4. 商业产品（Novelcrafter Codex / Sudowrite Story Bible）的最大借鉴点不是字段本身，而是 **Progressions / Detection**：设定条目是「活文档」，能随时间线更新并自动回写。

---

## A. 参考实现逐一调研

### A1. SillyTavern World Info / Lorebook（最成熟的注入式设定系统）

- 官方文档：https://docs.sillytavern.app/usage/core-concepts/worldinfo/
- 深度指南（社区 World Info Encyclopedia）：https://rentry.co/world-info-encyclopedia
- 插入顺序与 depth 讲解（sillycard 社区）：https://sillycard-web.pages.dev/blog/sillytavern-lorebook-order-guide

**机制要点（可借鉴）：**

| 机制 | 说明 | 对 story-engine 的借鉴 |
|---|---|---|
| **关键词触发** | 扫描最近聊天文本，命中 key 就把 entry 的 Content 注入 prompt | 写作前扫「最近 N 章 + 本章草稿」命中实体 → 拉取对应知识页 |
| **递归扫描 (Recursive scanning)** | 一个 entry 的内容里提到另一个 entry 的 key，会连锁触发 | 人物页里 `[[关系]]` 链式拉取关联人物/地点/组织 |
| **Scan Depth** | 0=只评估递归条目与 Author's Note；1=最后 1 条消息；2=最后 2 条… | 对应「回溯最近几章」的检索窗口参数 |
| **Insertion Position** | 决定内容插在 prompt 的哪一段（before/after char 等） | 设定放 system 区 vs 正文前 vs 正文后，影响模型重视程度 |
| **Strategy（蓝/绿/链）** | 蓝=恒常注入(不需要 key)；绿=关键词；链=embedding 相似度触发 | 核心设定「常驻」、普通设定「按需」、语义相近「软触发」三级 |
| **Token 预算 / Alert on overflow** | 激活条目超出预算时告警，按 priority/order 裁剪 | 组装上下文时做 token 预算守卫，超限降级 |
| **regex key、Automation ID、Vector Storage Matching** | 正则匹配、脚本联动、向量存储匹配 | regex 匹配别名/称谓变体；向量召回中文近义实体 |

> 说明：任务里提到的 `@depth` / `position` 字段，在 ST 的 character-card 内嵌 lorebook（V2 spec）中体现为 entry 的 `depth` 与 `insertion_order`/`position` 字段；官方 World Info 文档用「Scan Depth / Insertion Position / Insertion Order」表述同一语义（见上述 sillycard 与 encyclopedia 链接）。Story-engine 现有 Lorebook 已实现「关键词触发 + priority 注入」，与 ST 同源，可直接对照补上 **递归扫描、scan depth、token 预算守卫** 三项。

### A2. NovelAI Lorebook

- 官方文档：https://docs.novelai.net/en/text/lorebook/

**字段设计：** Entry Title（仅组织用，AI 看不到——正文里必须重述标题）、Entry Text、Activation Keys（大小写不敏感；`/.../` 为 regex；`A & B` 表示两 key 需同窗出现）、Always On（恒常注入）、Enabled/Hide 开关、Insertion order、Phrase Bias（激活时对某些词/短语加权）。

**可借鉴：**
- **条件触发系统**比 ST 更丰富：AND/OR/NOT 组、Numeric Comparison（如 `currentStep`、`paragraphCount` 倒计时触发事件）、String Comparison、Random Chance。这直接对应小说的「到第 N 章才揭示」「章节数达到某值触发伏笔回收」需求。
- **Always On** 字段 = 「核心设定常驻上下文」的开关，与「按需注入」互补。
- **Lore Generator**：让 AI 从名字/一句话自动生成设定条目（可与 story-engine 现有 AI 生成角色卡打通）。

### A3. AI Dungeon：Memory + World Info + Author's Note（三层记忆）

- Memory 系统：https://help.aidungeon.com/faq/the-memory-system
- Author's Note：https://help.aidungeon.com/faq/what-is-the-authors-note
- World Info：https://help.aidungeon.com/faq/all-about-world-info

**机制要点：**
- **三层上下文组装**：AI Instructions（system prompt，最前）→ Plot Essentials(旧称 Memory，**恒常注入**，放正文前) → Story Cards/World Info（**关键词触发**，放正文前）→ Author's Note（**放正文末尾**，用 `[方括号]` 包裹，作为「给模型的写作指令」）。位置的语义：靠前的=世界观/事实，靠后的=直接指令，影响力不同。
- **Memory 压缩 + Memory Bank 语义检索**：每 6 条动作压缩成一条摘要 Memory；新「Memory Bank」按语义相似度打分，取 top-N 塞进上下文预算。
- **关键教训（官方原文）**：World Info/Memory 过长会挤掉正文上下文——"every word you add to a World Info entry takes away from how far back the AI can see"。**→ 这就是「不能靠长上下文硬塞」的直接证据，也是 token 预算守卫的必要性来源。**

### A4. Novelcrafter Codex（字段设计 + 时间线进展）

- 特性页：https://novelcrafter.com/features/codex
- Codex 类型：https://novelcrafter.com/help/docs/codex/codex-types
- 字段细节：https://novelcrafter.com/help/docs/codex/character-codex-details
- Progressions/Additions：https://www.novelcrafter.com/help/docs/codex/progressions-additions

**类型（系统固定）：** Characters / Locations / Objects-Items / Lore / Subplot / Other。

**字段设计：** 每个 entry = 名称 + **Aliases/Nicknames**（关联别名触发）+ 描述 + **Custom Details**（Occupation、Story Role、Pronouns、Backstory、Character Conflict、Strengths、Weaknesses、Goals、Voice Sheet 等，可自定义，含 dropdown 类型）+ **AI Scope**（哪些 detail 注入 AI；「Always Include」= 恒常注入所有 prompt）。

**最关键的机制——Progressions / Additions：**
> "Static notes kill dynamic stories. Use Progressions to document how characters age, relationships shift, and world politics change." —— 条目详情可挂在**时间线**上，用 **replace（覆盖旧设定）/ addition（追加新设定）** 两种模式更新；到「当前故事时刻」AI 拿到的是**最新版本**。Codex 还会**自动索引**正文里对条目的每次提及（Automatic Mentions / Global Mapping）。

**对 LLM Wiki 改造的直接启发：** 这正是 wiki 模式缺的「时间维度」——给设定加 `valid_from / supersedes` 字段 + 按「当前写到第几章」取最新版本，等于把 Codex Progressions 落到 markdown 上。

### A5. Sudowrite Story Bible

- 官方文档：https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/what-is-story-bible/jmWepHcQdJetNrE991fjJC
- 原理综述：https://sudowrite.com/blog/how-sudowrite-works

**机制要点：**
- Story Bible = 每个 project 一个的「活知识库」：**synopsis、genre、style notes、characters、worldbuilding、outline、scenes**。所有核心工具（Write/Draft/Expand/Chat）生成前都会先 consult Story Bible。
- **Braindump 引导式填表**：从零开始逐字段填（synopsis → outline → scenes），各字段之间有级联关系（Braindump 影响 Synopsis 等）。
- **Story Bible Detection**：正文里提到已在 Story Bible 中的人物/世界观元素会被下划线标出（= 与 Novelcrafter 的 Automatic Mentions 同类的「实体识别回链」）。
- **量级**：单 Story Bible 最多 2000 个条目，可导入 6 万字已有设定；**Series Folder** 跨系列共享人物/世界观（对应 story-engine 的「文风库/跨书共享」需求）。
- Canvas：把最多 25 个章节文档链接，让 AI 跨章节携带上下文。

### A6. 开源「AI 写小说」项目（记忆/一致性方案与不足）

| 项目 | Stars 量级 | 记忆/一致性方案 | 不足 / 借鉴点 |
|---|---|---|---|
| **NousResearch/autonovel** https://github.com/NousResearch/autonovel | 高 | **canon.md（硬事实库，"WHAT IS TRUE"）+ world.md/characters.md/outline.md/voice.md/MYSTERY.md 五层同变**；`gen_outline_part2.py` 生成**伏笔台账 (Foreshadowing ledger)**；`state.json` 记录跨层传播债务；设定改动「向下传播」（lore→outline→chapter 修订） | **最接近目标**。但它是一份按 book 分支的模板文件，不是可程序查询的双链 wiki；无 lint/索引自动化。story-engine 可把 canon.md 升级为带 frontmatter 的双链页面 |
| **EthanYoQ/AI-Novel-Writer** https://github.com/EthanYoQ/AI-Novel-Writer | 755 | 本地优先桌面；「角色表接收蓝图中确认的新角色，并**持续记录角色状态**」；前提→角色→世界观→章节蓝图→草稿→审稿→修稿全流程可追溯 | 桌面 Electron，设定是应用内结构而非可 grep 的 markdown；无跨书知识库抽象 |
| **PenglongHuang/chinese-novelist-skill** https://github.com/PenglongHuang/chinese-novelist-skill | 高 | **三层递进问答 + 偏好记忆（跨会话）+ 中断续写 + 每章「更新摘要」**；子 Agent 并行 | 记忆偏「流程状态 + 章末摘要」，非实体级世界知识库；无双链/一致性 lint |
| **Deng-m1/MaliangAINovalWriter** https://github.com/Deng-m1/MaliangAINovalWriter | 中 | **知识图谱一致性 + 三级大纲 + 世界观设定树（可增量修改、历史快照）** | 设定树存后端(SpringBoot)，非开放 markdown；「知识图谱一致性」是正确方向但实现封闭 |
| **ExplosiveCoderflome/AI-Novel-Writing-Assistant (Biz Novel Studio)** https://github.com/ExplosiveCoderflome/AI-Novel-Writing-Assistant | 中 | LangGraph 编排 + **Qdrant RAG**；**拆书知识库、写法引擎、角色资源账本、世界手册**都做成「可召回长期资产」；角色档案按 25/50/75/100% 覆盖率增量扫描、提取外貌/状态/场景锚点 | 架构最接近「生产系统」，但走的是 **向量 RAG 路线**而非编译式 wiki；知识库是 DB 内对象，非可 git 的 markdown |
| **wordflowlab/novel-writer** https://github.com/wordflowlab/novel-writer | 低 | 参考 Spec-kit 的规格驱动（SDD）：用斜杠命令+规格文件驱动创作 | 设定=规格 markdown，方向对但生态小 |
| **BlinkDL/AI-Writer** https://github.com/BlinkDL/AI-Writer | 高(历史) | RWKV 生成模型（2022），无设定管理 | 过时，仅历史参考 |

> **gbrain**：任务提到的 gbrain 实为 **Garry Tan 的 agent 记忆系统** https://github.com/garrytan/gbrain ——「graph 遍历 + 向量检索 + 综合回答 + gap 分析」的知识脑，**不是小说写作工具**，但对「知识库/agent 记忆」部分（见 A7）有参考价值。
> **storywriter**：未能在 GitHub 找到明确的同名高星项目；最接近的是 **storycraftr**（https://github.com/raestrada/storycraftr）与 **datacrystals/AIStoryWriter**（https://github.com/datacrystals/AIStoryWriter）。特此说明未确认。

### A7. 开源知识库 / agent 记忆方案

| 项目 | 链接 | 模型 | 可借鉴点 |
|---|---|---|---|
| **llm-wiki-compiler** | https://github.com/atomicstrata/llm-wiki-compiler | Node CLI：把 `sources/` 编译成**类型化、逐段引用的 markdown 页**（Obsidian 兼容）；`lint` 检测 stale/orphan/contradicted；`export --target json` 桥接到内存层 | Karpathy 模式最完整的工程实现；**stale/orphan 检测 + JSON 导出桥**直接可抄（wiki 页 → 可程序解析的结构化内存记录） |
| **AtomicMemory** | https://github.com/atomicstrata/atomicmemory | 「可纠错的 agent 记忆」：supersede/clarify/delete 而不是 append-only；MCP/SDK/CLI；`@atomicmemory/llmwiki` 桥把 wiki 页导入成可查询记录 | **correction-aware（可覆盖/澄清/删除）** 正是小说设定「随剧情更新」需要的；BEAM/LoCoMo 长程记忆基准表明其 temporal 检索领先 |
| **basic-memory** | https://github.com/basicmachines-co/basic-memory | markdown = Entity，含 **Observations（事实）+ Relations（有向关系）**；MCP 工具（write_note/read_note/search_notes/build_context）；**项目级 scope** | 「实体-观察-关系」三件套 + **build_context 按图遍历装上下文**，是 wiki 注入层的现成范式；project 隔离 = 每本小说一个项目 |
| **Khoj** | https://github.com/khoj-ai/khoj | 自托管「第二大脑」：语义检索 + 自定义 agent（带独立 knowledge base）+ Obsidian 插件 + 定时自动化 | 证明了「每 agent/每知识库 scope 隔离 + 语义检索」可自托管跑通；可作 story-engine 的**语义召回后端**备选 |
| **Obsidian + Dataview** | https://blacksmithgu.github.io/obsidian-dataview/ | YAML frontmatter 字段自动成为可查询字段；DQL 查询（TABLE/LIST/FROM/WHERE/SORT）动态生成表 | 给 wiki 页配 frontmatter 后，人可以用 Dataview 生成「所有伏笔状态表」「所有悬空人物表」——**人看的部分**免费获得 |
| **gbrain (Garry Tan)** | https://github.com/garrytan/gbrain | 知识脑：graph + 向量 + BM25/RRF 三层检索 + MCP 30+ 工具 | 检索侧（三层混合 + 综合回答）与「每本小说知识库的召回层」同构；但偏 agent 个人知识，非小说领域 |

---

## B. Karpathy LLM Wiki 模式用于小说设定的适配性评估

**Karpathy gist（模式原文）**：https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
（已全文落盘于本仓库的 `llm-wiki` skill，核心：raw/entities/concepts/comparisons + index + log + SCHEMA + lint + 双向链接。）

### B1. 可直接复用的部分

1. **双向链接 `[[wikilink]]`**：人物↔人物、人物↔组织、地点↔事件、伏笔↔回收点，天然是「关系图」。Obsidian Graph View 直接可视化世界关系网。
2. **index.md / log.md**：index 按类型分节的目录（agent 查询先读 index）；log 追加式时间线（可 grep `## [` 前缀）——两者都是「100+ 页仍能导航」的骨架，无需嵌入向量库。
3. **SCHEMA.md**：约定命名、frontmatter 字段、tag 分类法、建页阈值——这是把「一个通用 chatbot」变成「自律的设定维护者」的关键配置。
4. **lint 健康检查**：孤儿页（没有入链）、断链、矛盾标记、超长页拆分、tag 审计——**几乎 1:1 映射小说一致性检查**：
   - 孤儿页 ≈ 写了但正文没提过的废设定；
   - 断链 ≈ 提到但没建页的实体；
   - `contradictions:` 字段 ≈ 设定冲突（既可以是 plot hole，也可以是刻意伏笔——见 B2 第 3 点）；
   - 超长页 ≈ 需要拆子页的复杂人物。
5. **raw/ 不可变 + sha256 漂移检测**：把「大纲 v1」「拆书笔记」「灵感原文」当 raw 源，wiki 页当编译产物——源改了能发现。
6. **Obsidian/Dataview + git**：知识库即 git 仓库，版本历史、分支（试写不同走向）免费获得。

### B2. 不适用 / 需改造的部分

1. **检索时机相反：wiki 是「query 时读」，小说是「写作时注入」。**
   Karpathy wiki 假设「人提问→agent 查 index→读页→综合」。小说写作是**生成时**要把相关设定塞进 prompt（见 A1/A3 的注入机制）。改造：保留 wiki 作为**存储与编译层**，在其上叠一层**注入器**（关键词触发 + 递归 + scan depth + token 预算），写作前把「当前场景命中」的页面渲染成 prompt 片段。**wiki 是 source of truth，注入器是读它的窗口。**
2. **状态/时间线会变：静态页会过期。**
   Karpathy wiki 的实体页是「关于 X 的事实」累积，隐含假设事实相对稳定（哪怕有矛盾也并置保留）。小说的「林小雨是否还活着」「她此刻在哪个城市」「她和 A 是否已决裂」是**随章节推进变化的**。必须加时间维度：
   - 页级 `status`（alive/dead/unknown/retconned）+ `last_seen_in`；
   - 字段级 `valid_from / valid_until / supersedes`（借鉴 Novelcrafter Progressions 的 replace/addition，A4）；
   - 「按当前写到第 N 章」解析出**当下有效版本**。
3. **矛盾语义不同：wiki 的矛盾=待人工裁决；小说的矛盾=plot hole 或刻意伏笔。**
   Wiki 把冲突标记出来让人裁决；小说里「前后不一致」可能是**蓄意的反转/伏笔**（人物在撒谎、记忆被篡改）。需要额外区分：`contradiction_kind: plot_hole | intentional_reveal | unreliable_narrator`，否则 lint 会把伏笔误报为 bug。
4. **溯源对象不同：wiki 溯源到外部 source，小说溯源到「章」。**
   小说没有外部文献，事实是作者创造的 canon。`sources:` 字段应改为 `established_in: ch_xxx`（哪一章确立）+ `established_by: author | ai | draft`，让 agent 能回答「这条设定是哪来的、可信度多高」。
5. **伏笔是一等公民实体，wiki 没有对应类型。**
   autonovel（A6）专门有「Foreshadowing ledger」：伏笔需要 plant(埋) → develop(发展) → payoff(回收) 状态机，以及 `pay_off_plan`（回收计划）。这是 Karpathy wiki 完全没有、但小说最需要的类型。
6. **文风锚点需要「何时适用」条件。**
   「文风」不是静态实体，是「在某类场景（战斗/对话/抒情）用某种腔调」。文风页要带 `applies_when`（触发条件）+ `sample`（原文样本，few-shot 锚点），与 story-engine 现有文风库打通。
7. **人类在环的职责不同。**
   Wiki：人筛 source、agent 维护页。小说：**作者本人是唯一 canon 权威**，agent 不得「综合外部来源」改写设定，只能按作者指令增量维护并标记待确认项（confidence 字段语义从「证据支撑度」变成「作者确认度」）。

### B3. 改造建议（落地路线）

1. **存储层 = 每本小说一个 wiki 目录**（见 C），纯 markdown + frontmatter，git 管理。
2. **编译层 = 复用 llm-wiki-compiler 的 stale/orphan/lint + JSON export 桥**（A7），把 wiki 页导出为结构化「设定记录」，供后端解析。
3. **注入层 = 移植 ST World Info 的触发语义**（A1）：关键词/regex 触发 + 递归 + scan depth（=回溯最近 N 章）+ token 预算守卫 + 三级策略（恒常/关键词/语义）。
4. **时间层 = Novelcrafter Progressions 语义**（A4）：`valid_from/supersedes` + 按章节解析当前版本；伏笔走 plant/develop/payoff 状态机。
5. **一致性层 = lint + 伏笔台账**：lint 找悬空伏笔（planted 未 payoff）、孤儿设定、设定冲突；`contradiction_kind` 区分 plot hole 与刻意反转。
6. **人机界面 = Obsidian + Dataview**：作者在 Obsidian 里看关系图、用 Dataview 生成「伏笔状态表/人物状态表」；agent 在后台维护 markdown。二者读同一批文件（basic-memory 的「人类与 AI 写同一文件」理念，A7）。

---

## C. 「一本小说的知识库」目录结构草案

```
novels/<novel_id>/
├── novel.json                  # story-engine 现有：正文+章节（source of truth for prose）
└── wiki/                       # ★ 新增：本书知识库（纯 markdown，可 git、可 Obsidian 打开）
    ├── SCHEMA.md               # 约定 + frontmatter 规范 + tag 分类法 + 建页阈值
    ├── index.md                # 分类型目录，每页一行摘要（agent 查询先读它）
    ├── log.md                  # 追加式操作日志（ingest/update/query/lint）
    ├── raw/                    # 不可变源：大纲v1、拆书笔记、灵感、设定来源
    │   ├── outlines/
    │   ├── inspirations/
    │   └── sources/            # 拆书/资料（带 source_url + sha256）
    ├── entities/               # 实体页
    │   ├── characters/  lin-xiaoyu.md
    │   ├── locations/   wangcheng.md
    │   ├── organizations/ tianji-lou.md
    │   └── items/       hanjian.md
    ├── timeline/               # 时间线
    │   ├── events/     e001-shi-mo-jie.md
    │   └── timeline.md         # 全书时间轴聚合页（按 in-world 时间排序）
    ├── plot/                   # 剧情结构
    │   ├── foreshadowing/ f001-hanjian.md   # 伏笔台账（plant/develop/payoff）
    │   ├── subplots/    s001-xiaoyu-shenshi.md
    │   └── arcs/        a001-protagonist.md
    ├── style/                  # 文风锚点
    │   └── anchors/     an001-battle.md
    ├── queries/                # 已存档的问答/分析（值得留存的综合结果）
    └── _meta/                  # topic-map.md、关系图导出、Dataview 查询页
```

### frontmatter 字段规范（可程序解析）

**通用字段（所有页面必填）：**
```yaml
---
id: char-lin-xiaoyu              # 稳定 slug（程序主键，永不改名）
type: character                  # character|location|organization|item|event|foreshadow|subplot|arc|style-anchor
title: 林小雨
aliases: [小雨, 阿雨, 林警官]     # 关键词触发/别名回链用
tags: [主角, 女性, 悬疑]         # 必须来自 SCHEMA.md 分类法
created: 2026-10-11
updated: 2026-10-11
status: active                   # 见各类型；通用 active|dormant|retconned
confidence: confirmed            # confirmed|draft|conflict（作者确认度，非证据度）
established_in: ch_001           # 首次确立章节（canon 溯源）
established_by: author           # author|ai|draft
---
```

**人物（character）追加：**
```yaml
role: 主角                        # 主角|反派|配角|龙套
alive: true                       # 生死（可随章节变，见 status 快照）
relationships:                    # 关系边（双链）
  - { to: char-su-ming, kind: 师徒, since: ch_003, until: ch_020 }
arc: arc-a001                     # 所属人物弧
voice_anchor: an003               # 说话腔调锚点
appearance_snapshot:              # 时间线快照（借鉴 Novelcrafter Progressions）
  - { in: ch_001, note: 短发、灰外套 }
  - { in: ch_014, note: 左眼留疤 }     # supersedes 上一版
```

**地点/组织/物品（location/organization/item）追加：**
```yaml
region: 江南                      # 地理/层级
contained_by: loc-wangcheng       # 所属上级（双链）
founded_in / era_valid: 前朝      # 时间有效性
significance: 主线关键地点         # 重要度
```

**时间线事件（event）：**
```yaml
inworld_time: 天启三年·三月       # 书内时间（非现实时间）
chapter: ch_004                   # 出现章节
participants: [char-lin-xiaoyu, char-su-ming]
causes: [event-e001]
effects: [event-e003, foreshadow-f001]
```

**伏笔（foreshadow，一等公民）：**
```yaml
foreshadow_status: planted        # planted|developed|payed_off|abandoned
planted_in: ch_002                # 埋设章节
payoff_in: ch_018                 # 回收章节（未定可空）
payoff_plan: 汉剑在结局决斗中崩断，呼应开篇预言   # 回收计划（作者私密）
related_entities: [item-hanjian, char-su-ming]
```

**支线/人物弧（subplot/arc）：**
```yaml
thread_status: active             # active|resolved|dropped
started_in: ch_001
milestones:                       # 关键节点（时间线）
  - { in: ch_006, note: 小雨得知身世 }
```

**文风锚点（style-anchor）：**
```yaml
dimension: 战斗描写                # 维度（战斗/对话/抒情/心理/环境）
applies_when: 出现打斗或对峙场景     # 触发条件（自然语言，供注入器匹配）
register: 冷峻克制                  # 腔调
sample: "……"                      # 原文样本（few-shot 锚点，可多段）
score: 8                          # 与 style_db 风格画像的强度分（可选）
```

### 增量维护与解析保证

- **可增量维护**：agent 每次 ingest 一章/一个设定来源，只 touch 命中的页 + index + log；`updated` 字段 bump；伏笔状态机随章节推进推进 `foreshadow_status`。
- **可程序解析**：① 每页 YAML frontmatter 是稳定 schema（上表）；② `index.md` 一行一条可 grep；③ `log.md` `## [YYYY-MM-DD]` 前缀可解析；④ 可选 `llmwiki export --target json` 把全部页导出成结构化 JSON（A7），或后端直接解析 frontmatter 建 SQLite 索引（复用 story-engine 现有 novel_storage 模式）。
- **与现有系统对接**：`wiki/entities/*` 与现有 `characters/*.json`、`lore/*.json` 是**同一批设定**的两种表示——建议以 wiki markdown 为**编译源**，JSON 为**运行时注入格式**（写入时从 md 解析，生成时按 lorebook 语义组装），避免双写漂移。

---

## 来源链接汇总

**Karpathy 模式**
- LLM Wiki gist：https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

**注入式设定系统（商业）**
- SillyTavern World Info：https://docs.sillytavern.app/usage/core-concepts/worldinfo/
- SillyTavern World Info Encyclopedia：https://rentry.co/world-info-encyclopedia
- Sillycard lorebook order/depth：https://sillycard-web.pages.dev/blog/sillytavern-lorebook-order-guide
- NovelAI Lorebook：https://docs.novelai.net/en/text/lorebook/
- AI Dungeon Memory：https://help.aidungeon.com/faq/the-memory-system
- AI Dungeon Author's Note：https://help.aidungeon.com/faq/what-is-the-authors-note
- AI Dungeon World Info：https://help.aidungeon.com/faq/all-about-world-info

**商业写作工具的设定字段**
- Novelcrafter Codex 特性：https://novelcrafter.com/features/codex
- Novelcrafter Codex 类型：https://novelcrafter.com/help/docs/codex/codex-types
- Novelcrafter Codex 字段：https://novelcrafter.com/help/docs/codex/character-codex-details
- Novelcrafter Progressions：https://www.novelcrafter.com/help/docs/codex/progressions-additions
- Sudowrite Story Bible：https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/what-is-story-bible/jmWepHcQdJetNrE991fjJC
- Sudowrite 原理：https://sudowrite.com/blog/how-sudowrite-works

**开源小说项目**
- NousResearch/autonovel：https://github.com/NousResearch/autonovel
- EthanYoQ/AI-Novel-Writer：https://github.com/EthanYoQ/AI-Novel-Writer
- PenglongHuang/chinese-novelist-skill：https://github.com/PenglongHuang/chinese-novelist-skill
- Deng-m1/MaliangAINovalWriter：https://github.com/Deng-m1/MaliangAINovalWriter
- ExplosiveCoderflome/AI-Novel-Writing-Assistant：https://github.com/ExplosiveCoderflome/AI-Novel-Writing-Assistant
- wordflowlab/novel-writer：https://github.com/wordflowlab/novel-writer
- BlinkDL/AI-Writer：https://github.com/BlinkDL/AI-Writer

**开源知识库 / agent 记忆**
- llm-wiki-compiler：https://github.com/atomicstrata/llm-wiki-compiler
- AtomicMemory：https://github.com/atomicstrata/atomicmemory
- basic-memory：https://github.com/basicmachines-co/basic-memory
- Khoj：https://github.com/khoj-ai/khoj
- Obsidian Dataview：https://blacksmithgu.github.io/obsidian-dataview/
- gbrain (Garry Tan)：https://github.com/garrytan/gbrain
