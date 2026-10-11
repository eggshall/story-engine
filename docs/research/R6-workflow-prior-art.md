# R6 流程层先例调研：作者审大纲/设定 → AI 介入写作的闸门设计

> 调研目标：不抄字段，抄**流程与分工**。归纳"人工审核闸门（gate）"应设在哪里、每个闸门的输入/输出/验收标准，以及哪些环节最容易导致后期返工。
> 调研对象：现成高质量 AI 写作工具（Sudowrite / Novelcrafter / NovelAI / AI Dungeon / 中文工具若干）+ 学术上多阶段长篇写作流程结论。
> 日期：2026-10-11

---

## 0. 一句话结论（先读这个）

所有成熟工具/论文收敛到同一条主线：**把长篇写作拆成"设定 → 总纲 → 章节/场景细纲 → 正文草稿 → canon 回写"的逐层展开链，每一层产出都要经作者审核通过后才允许下一层展开**。闸门数量在 3~5 个，粒度从"整本书"逐层下钻到"~500 字的 beat"。学术结论补了一条关键反面证据：**静态计划在超长生成中会"跟随度衰减"（guidance decay / 计划被模型忽略）**，所以光有一个审过的大纲不够，必须在每个分段写作前"刷新计划 + 反思上一段"，而不是把大纲一次性喂进去就不管。

---

## 1. Sudowrite：Braindump → Outline → Scenes → Draft

**来源**（官方文档）：
- What is Story Bible：https://docs.sudowrite.com/using-sudowrite/1owq1kGqof9rtcyGnrWUBS/what-is-story-bible/jmWepHcQdJetNrE991fjJC
- Outline：https://docs.sudowrite.com/using-sudowrite/1owq1kGqof9rtcyGnrWUBS/outline/3owKyHXUm1bCdp41b2Npjk
- Scenes & Draft：https://docs.sudowrite.com/using-sudowrite/1owq1kGqof9rtcyGnrWUBS/scenes--draft/49p5MTVxTKkVFEC5rVUzpY
- 官方博客总览：https://sudowrite.com/blog/how-sudowrite-works/

### 1.1 完整流程链（Story Bible 顺序字段）

```
Braindump → Synopsis → Genre/Style → Characters → Worldbuilding → Outline → Scenes → Draft(正文)
```

这是一个**显式的依赖 DAG**：每个字段"被谁影响、又影响谁"官方文档逐条写明：

| 字段 | 由谁影响 | 影响谁 |
|---|---|---|
| Braindump | 仅手动（不可生成） | Synopsis（若 Synopsis 为空，则下游字段回退读 Braindump） |
| Genre | 仅手动 | Synopsis / Outline / Scenes / Draft 正文 |
| Style | 手动 或 Match My Style | Beat / Draft 正文 |
| Synopsis | Braindump + Genre | Characters / Worldbuilding / Outline / Scenes |
| Characters | Synopsis | Outline / Scenes / Draft |
| Worldbuilding | Synopsis | Outline / Scenes / Draft |
| Outline | Genre+Synopsis+Characters+Worldbuilding | Scenes |
| Scenes | Genre+Style+Synopsis+Outline+Characters+Worldbuilding（最多上下文） | Draft 正文 |
| Draft | Style+Genre+Characters+Worldbuilding+Scenes | — |

### 1.2 作者在哪几步介入（关键：每一步都可"Rewrite 带指令"）

1. **任何生成字段都有 Rewrite 按钮**：不满意 → 在 Rewrite 框里写具体指令（例："End in a cliffhanger"）→ 再跑一遍。作者是在"接受/驳回 + 给反馈"层面介入，而非逐字写。
2. **Outline 级**：可整本一次生成，也可 `+ Add Chapter` 逐章生成（每章可附 Custom Instructions）；可对单章 Rewrite。Act 只是可拖动分隔符（Part/Book/Episode），非强制。
3. **Scenes 级**：可手动写、也可 `Generate Scenes`（基于已 link 的章节摘要）。生成/手写后 Story Bible Detection 会把**已识别的角色/世界观元素加下划线**——让作者肉眼确认"AI 有没有正确命中 canon"。
4. **Draft 前有一道自动"预检"**：点 Generate 后 AI 先分析 Scenes 是否"太短/太散/覆盖事件过多"，给出 Quick Fix（拆分场景等）供作者接受或忽略，并给出字数/credit 预估。
5. **Draft 级**：`Extra Instructions` 框可加剧情注记（如"End on a cliffhanger"）与风格强调。**正文字数不由字数参数控制，而由 Scene 数量决定**——想短就合并成 1 条 scene。
6. **"Start Chapter" 建立 linked document**：把某章摘要与具体文档绑定，Write/Draft 才知道写什么。

### 1.3 Story Bible 何时更新

- **手动改 / Rewrite**：作者随时改。
- **"Update" 回写**：正文写跑偏大纲后，点章节摘要的 `Update` 一键用正文反向更新大纲里那条章节摘要（承认"正文即事实"，回写大纲而非强制改正文）。
- 这是关键设计：**大纲不是铁律，正文跑偏时系统提供"反向回写"路径，由作者选择改哪边**。

### 1.4 提炼
Sudowrite 的闸门 = **逐层"生成 → 作者审核(可带指令重跑) → 通过后展开下一层"**。作者不写正文，但每层结构（尤其 Outline 和 Scenes）都过作者的手/眼。Scene 是正文前最后一道、也是上下文最全的一道闸门。

---

## 2. Novelcrafter：Codex + Chapter beats / Scene beats + Progressions

**来源**（官方文档）：
- Where do I put beats：https://docs.novelcrafter.com/en/articles/9419387-where-do-i-put-my-scene-chapter-act-book-summary-what-about-my-beats
- Progressions/Additions：https://docs.novelcrafter.com/en/articles/8675593-progression-additions
- Codex 特性页：https://novelcrafter.com/features/codex
- Plan 界面：https://www.novelcrafter.com/help/docs/plan/the-plan-interface
- Write 界面：https://www.novelcrafter.com/help/docs/write/the-write-interface
- Adding scene beats：https://novelcrafter.com/help/faq/write/adding-scene-beats

### 2.1 谁生成什么、作者审什么

- **Plan 界面（作者主导）**：Acts → Chapters → Scenes 三层，作者建结构、写 scene synopsis、设 POV、可把某些 scene 排除出 AI 上下文（附录/前言）。**AI 只做辅助**：写完后生成章节摘要、review 章节并检测出现的角色。
- **Scene Beats（作者当"导演"）**：在 Write 界面用 `/` 打开，作者写的是**指令而非正文**——"Include the setting, time of day, and the characters present. Give one of the characters a goal." 一条 beat ≈ 500 字正文；一个 scene 通常 6+ 条 beat。官方明确："You are the director, telling your characters what to do."
- **Codex（设定库）**：作者维护条目；**Smart Detection** 在作者打字时即时识别名字/别名/昵称并链接（下划线式命中可见），Global Mapping 展示某元素在正文/chat/snippet 的所有出现。
- **谁生成正文**：作者在 Write 界面基于 beats 让 AI 生成（或自己写）。分工是：**结构 = 作者（AI 辅助），beat 指令 = 作者，正文 = AI（作者可改）**。

### 2.2 Progressions / Detection 机制（对"设定中途变更"的处理）

这是 Novelcrafter 最值得抄的机制：

- **Progressions = 带时间点的 Codex 附录**：角色中途被附身、脸上多了道疤——不能直接改原始 Codex（否则 AI 会在前文场景提前剧透），而是加一条 Progression，**只有在该场景"创建时间点之后"的场景才会看到它**；回到更早场景时它不进上下文。
- Progression 支持 **replace / addition 两种模式**（覆盖旧设定 vs 追加），可挂在某场景上，并 link 到某 Codex 条目。
- 官方限定用途："为重大进展/变化而设，**不用于替代情节点**（情节点写进 scene 指令）"。例：结婚/离婚、地点被洗劫、角色升职、显著外貌改变、重要物品丢失。
- 配套的 **Smart Highlighting**：标出高频词、crutch phrases、AI 生成痕迹、对话标签——把"改稿"变成可扫描的标记而非通读。

### 2.3 提炼
Novelcrafter 的核心分工 = **作者写 beat（结构决策层），AI 填 500 字正文（执行层）**；设定的"时间维度"用 Progressions 显式建模，避免"改了设定污染前文"这一最经典的返工源。

---

## 3. NovelAI / AI Dungeon：memory + lorebook 注入的"作者介入点"

（此部分承接已有调研，只补"作者在哪介入"。）

**来源**：
- NovelAI Lorebook：https://docs.novelai.net/en/text/lorebook/
- NovelAI Advanced Settings（Stages/Insertion Order）：https://docs.novelai.net/en/text/editor/advancedsettings/
- AI Dungeon Memory System：https://help.aidungeon.com/faq/the-memory-system

### 3.1 注入机制概览

- **NovelAI**：上下文 = 系统提示 + Memory（置顶）+ Author's Note + 被触发的 Lorebook 条目 + 故事正文。Lorebook 条目 = Entry Text + Keys；正文命中 Key → 条目注入。控制项：Search Range（往前读多少字符找 Key）、Force Activation（永远在上下文）、Key-Relative Insertion（插到 Key 最近出现处而非固定位置）、Cascading Activation（也到其它条目/Memory/Author's Note 里找 Key）、Phrase Bias Stages（按 Insertion Order 分阶段拼上下文）。
- **AI Dungeon**：上下文 = 故事文本 + AI Instructions + Plot Essentials（原 Memory）+ Author's Note + 相关 Story Cards。**始终包含**：AI Instructions / Story Summary / Plot Essentials / Author's Note；**关键词触发**：Story Cards。另有 **Memory Bank**（embedding 检索）：把历史记忆按相关性检索进上下文，并检查是否已在 Story Summary 里（去重）。

### 3.2 作者介入点（对照 story-engine 已有 Lorebook/角色卡）

| 介入点 | NovelAI / AI Dungeon 的做法 | 对 story-engine 的启示 |
|---|---|---|
| **写条目** | 作者手写 Entry Text + Keys（AI 有 Lorebook Generator 可辅助生成，但作者编辑） | 角色卡/Lorebook 由作者写，AI 可"生成建议"但需作者批准 |
| **决定谁常驻** | Memory / Plot Essentials / Author's Note / AI Instructions 常驻；Lorebook/Story Cards 触发式 | 区分"常驻设定"与"关键词触发设定"，作者显式归类 |
| **命中可见性** | 触发/命中在编辑器中可见，作者能看出"这条设定有没有被带进当前生成" | **必须给作者看"这次生成注入了哪些设定"**——这是排错的关键 |
| **命中范围/位置** | Search Range、Insertion Order、Key-Relative 都由作者可调 | 注入位置/命中范围做成可配置，而非黑盒 |
| **手动强制** | Force Activation 让某条目永远在上下文 | 关键设定可"置顶常驻" |

### 3.3 提炼
AI Dungeon/NovelAI 的"闸门"不在大纲而在**上下文组装**：作者通过"常驻 vs 触发、插入位置、命中范围、强制激活"这些开关，控制"AI 这次到底带着什么去写"。对"作者审大纲后 AI 介入"的直接启示是——**审核通过的大纲/设定必须能可靠地注入到每次分段写作里，且作者要能看见注入结果**，否则"审过"形同虚设。

---

## 4. 中文工具 / 项目对照（各自的"人工审核闸门"）

### 4.1 马良写作 AINoval — Deng-m1/MaliangAINovalWriter
- 仓库：https://github.com/Deng-m1/MaliangAINovalWriter
- **层级**：四级内容树 `作品 → 卷 → 章节 → 场景`；**三级大纲**（作品→卷→章节）为招牌能力；知识图谱一致性（角色/势力/伏笔）跨 30 万字连载。
- **闸门设计**：
  - 设定层：AI 一键生成"结构化世界观设定树" → **作者微调设定节点**（不满意可局部重生成）→ 每次生成会话存**历史快照**（版本对比/恢复）。
  - 大纲层：**剧情推演（Next Outline）**——AI 给出**多个**后续剧情大纲选项，作者挑一个，**对不满意的选项可独立重生成**（"gacha" 多模型并行出结果让作者选）。
  - 正文层：**场景摘要**（AI 压缩已有长场景）+ **摘要扩写**（把摘要/大纲扩写成完整场景）。
- 分工总结：**设定树、大纲都是"AI 出多个候选 → 作者选/改"**，不是 AI 一次定死；正文用"摘要→扩写"两段式（先审摘要再扩写）。

### 4.2 墨狐AI（mohuai.com）
- 产品介绍（AIHub）：https://www.aihub.cn/tools/writing/inkfox-ai/
- **流程**：输入灵感（任意字数）→ `开始创作` → AI 生成 **【导语】【世界观】【角色卡】+ 作品目录**；**"如果觉得不满意，还可以自定义修改生成的设定内容"**。
- **续写**：给上文 + 在编辑器右侧**选择/自定义剧情走向** → 得不同画风续写文本。
- **剧情树图解**：把已有设定交给 AI → 得到后续节点脉络（只梳理思路，不生成正文）。
- 分工总结：**设定/大纲生成后明确留"作者自定义修改"这一步**；续写前作者"选剧情走向"。

### 4.3 笔灵 / 蛙蛙写作
- 测评（cnblogs）：https://www.cnblogs.com/xielunwen/articles/21595141
- **笔灵**：`AI 写全篇小说`——作者**先梳理好整部小说的大致剧情脉络**，其余正文交给 AI 一键生成。即：**闸门在"作者先定剧情脉络"**，之后是整本自动展开（最松的闸门模式，适合爽文流水线）。
- **蛙蛙写作**：偏短篇平台向工具。两者定位是"国产大模型写正文性价比"。
- 分工总结：笔灵代表**"作者只审大纲，正文全自动"**的极端形态——闸门数量最少、返工风险最高，只适合结构高度模板化的题材。

### 4.4 91写作 — ponysb/91Writing
- 仓库：https://github.com/ponysb/91Writing
- 纯前端（Vue3 + Element Plus + WangEditor），本地数据，自带 API Key，无后端。
- **流程链**（官方 README）：`选择类型模板 → AI 生成大纲 → 章节式创作 → 智能续写润色 → 状态管理发布`。
- **闸门设计**：
  - 章节三状态管理：**草稿(橙) / 完成(绿) / 发表(蓝)**——作者在章节列表显式流转状态。
  - 续写：作者**自定义续写方向 + 字数(200-5000字)**，流式输出可随时停止，一键复制/追加。
  - 润色：选语法/文风/情感/逻辑四类，选中或整文。
  - 世界观：模板化（核心设定/关键元素/故事背景）+ **AI 一致性检查**。
  - 事件时间线（可编辑）；10 大工具（细纲/角色/脑洞/世界观/黄金开篇/冲突等生成器）+ **拆书分析**（5 维度拆爆款）。
- 分工总结：**正文创作是"作者写开头 + 设方向 + AI 续写 + 作者润色"的交互式循环**，而非整本自动；章节状态流转就是最轻量的人工闸门。

### 4.5 inkos — Narcooo/inkos（多智能体 + 显式 human review gate）
- 仓库：https://github.com/Narcooo/inkos
- **这是"人工审核闸门"设计最显式的一个开源项目**，直接对标本调研主题。
- **Agent 分工**：Radar（扫平台趋势，可跳过）/ Architect（章节结构、scene beats、节奏目标）/ Writer（按 plan + 当前世界状态写正文）/ Continuity Auditor（对照 canonical truth files 校验草稿）。
- **治理链**：`plan chapter → compose chapter → write next`（plan→compose→write 治理链为默认）。
- **显式人工闸门**：`inkos review list <book>` → `inkos review approve-all <book>`；`inkos export` 前需通过 review。**Draft → audit → auto-revise → human approve** 是完整闭环。
- **自动审计（不拦人，但标记）**：Continuity Auditor **33 个维度**检查每章草稿（角色记忆、物资连续性、伏笔回收、大纲偏离、叙事节奏、情感弧线），内置 **AI 痕迹检测**维度；Post-Write Validator 用 **11 条确定性规则（零 LLM 成本）**在每章后立即触发；默认长篇链路最多自动修订一次（`writing.reviewRetries` 可调）。
- **去 AI 味前置**：疲劳词表、禁用句式、文风指纹注入**内置进 Writer agent 的 prompt 层**（源头减痕），另有 `revise --mode anti-detect` 事后补救。
- **意图/聚焦文件**：`story/author_intent.md`（长线目标）+ `story/current_focus.md`（未来 1-3 章聚焦点），`plan chapter --context` 可注入作者创作指导。
- 分工总结：**机器负责 draft/audit/auto-revise 的循环，人只在 review gate 处 approve**；设定用 truth files 固化，大纲偏离被审计员显式检测。

### 4.6 wordflowlab/novel-writer（规格驱动 SDD）
- 仓库：https://github.com/wordflowlab/novel-writer ；skills 版：https://github.com/wordflowlab/novel-writer-skills
- 把软件工程 **Spec-Driven Development** 七步法搬到小说：`constitution → specify → clarify → plan → tasks → write → analyze`，通过 slash 命令在 Claude Code / Cursor / Gemini 里执行。
- **闸门 = 每个 slash 命令都是一次人机交接**：
  - `/constitution` 创作原则（含"AI味/爽文/无毒点"等风格约束）→ 写进 specification.md
  - `/specify` 故事规格 → `/clarify` **澄清模糊点**（plan 之前强制澄清，防返工）→ `/plan` → `/tasks` 任务分解 → `/write` → `/analyze` 质量验证
  - 最小流程：`/constitution → /specify → /write`。
- **config-driven 单一事实源**：所有写作参数汇入 specification.md，保证 30+ 章长项目 AI 行为一致；genre 知识/质量检查按需自动激活。
- 分工总结：**"先 clarify 再 plan"是明确的防返工闸门**；作者在每步之间审查并确认产物，spec 文件是贯穿全程的"审过的设定"。

### 4.7 NousResearch/autonovel（全自动管线的参照系）
- 仓库：https://github.com/NousResearch/autonovel
- 定位："从 seed 概念到可印刷 PDF/ePub/有声书的**全自动**小说管线"，灵感来自 karpathy/autoresearch 的 **modify-evaluate-keep/discard 循环**。
- 模板：`world.md / characters.md / outline.md / canon.md / voice.md / MYSTERY.md`（作者专用）+ `state.json`（管线状态追踪）。
- 阶段：draft_chapter → evaluate（机械 slop 评分器 + LLM judge）→ adversarial_edit（"砍 500 词"分析）→ compare（Elo 锦标赛）→ reader_panel（4 人格小说级评价）→ review（Opus 双人格评审 + **停止条件**）→ gen_brief → gen_revision。
- **关键参照**：autonovel 的"闸门"不是人，而是**评估循环 + 停止条件**（evaluate 到满足条件才停）。它证明了"作者缺席"时靠什么兜底：把"作者审美"拆成可机械化的评分器 + 多角色评审 + 对抗式删减。对"人机协作"项目的启示是——**作者不盯的环节，必须有一个等价的可执行验收器**。

---

## 5. 学术结论：多阶段长篇写作流程

### 5.1 Plan-Write-Reflect 循环 + "Length Collapse / guidance decay"
- IS-CoT（arXiv 2606.09709，OpenReview kAAuNFXDkE）：https://arxiv.org/pdf/2606.09709v1
  - 核心发现：**静态计划在超长生成中会失效（Length Collapse / guidance decay）**——"a static initial plan is insufficient for effective long-form generation"。
  - 方案：把生成组织成 **全局计划 → 局部计划 → 内容生成 → 反思(reflection)** 的**递归循环**，每写一段就 plan+reflect，而不是只在开头计划一次。
  - **对 story-engine 的直接启示**：作者审过的大纲 ≠ 一劳永逸。每次分段写作前应"基于大纲 + 前文状态刷新本段局部计划"，写后反思是否偏离大纲（这正是 inkos 的 `plan chapter --context` + 审计员在做的事）。
- Plan-and-Write（arXiv 2511.01807）：生成拆成 **planning（显式计数、长度感知）** + **verification/coherence** 两阶段，验证约束不靠"一次性说明"而靠"过程化跟踪"。
- WritingPath（NAACL 2025 Industry，aclanthology.org/2025.naacl-industry.20）：大纲引导生成五步，先建"一致性聚焦的计划"再扩充，强调**结构化大纲显著影响成文质量**。

### 5.2 场景级增量写作 + 提交前校验（ConWriter）
- ConWriter（arXiv 2608.05169）：https://arxiv.org/pdf/2608.05169v2
  - **场景级增量生成**：不把长篇当一次 free-form 解码，而是**逐场景写**，维护"静态故事要求（不可变）+ 动态叙事记忆（事件/实体状态/关系/时间线/待办约束）"双记忆。
  - **每场景生成前推导 symbolic 转移约束，生成后校验该场景是否实现了合法叙事转移**，不确定处用 uncertainty-aware 风险信号优先校验 + **句级 patch 修补**，**通过后才 commit 进动态记忆**。
  - **对 story-engine 的直接启示**：这是"提交前闸门"的学术实现——每个场景是一个"状态转移"，写出来先验证再入库，防止局部错误向后传播（这正是长篇返工的根源）。

### 5.3 课程学习式分层写作（WriterAgent / WriterLoRA）
- Pastiche Novel Generation / WriterAgent（arXiv 2502.15616）：https://arxiv.org/html/2502.15616v1
  - **课程学习（curriculum learning）**：从**低层文风掌握**逐步到**高层叙事连贯**，按序训练四个任务：①语言风格学习 ②世界观/角色构建 ③情节规划 ④风格化写作。
  - **WriterLoRA**：LoRA 扩展，**层次化 + 累积的任务专用模块**，每个模块专精一个叙事维度（风格/角色/情节）。
  - **对 story-engine 的直接启示**：写作能力本身就该**分层、分模块**——文风、角色、情节是独立的可插拔组件，与 story-engine 已有的"14 维文风画像 + 样本文段 + 角色卡 + Lorebook"架构天然对齐；流程设计上应让"设定→大纲→正文"各阶段各用其专用上下文/模块，而非一个大 prompt 包打天下。

### 5.4 分层规划脚手架（book-length writing，arXiv 2605.17064）
- Towards Human-Level Book-Writing Capability（arXiv 2605.17064）：https://arxiv.org/abs/2605.17064
  - **Planning Scaffold（多分辨率规划脚手架）**：把整本书**逐级摘要**成 `书级 → 章级 → 场景级` 的层次结构；训练时**倒转这个层次**：模型学的是"把 prompt 展开成越来越细的计划，最后展开成人类原著正文"。
  - **摘要用 bullet-point 列表而非散文**，每条约 10-20 词、上限 45 词——目的是保留可聚合、可重组的事实，而非漂亮句子。
  - 生成顺序**层次化**：书级计划 → 早期首章计划 → 首章正文 → 后续章节计划 → 章节正文（把"书级→章级→场景级"的展开显式建模为监督信号）。
  - **对 story-engine 的直接启示**：①大纲应按"书→卷→章→场景"做**多分辨率分层**，每层粒度有明确上限（bullet 式、可重组）；②写作任务应建模为**逐层展开（staged expansion）**而非单步续写；③"计划跟随度衰减"的解法不是"更长的计划"而是"分层监督 + 每层展开时重新锚定"。

### 5.5 计划跟随度衰减的早期证据（2018 已出现）
- Hierarchical Neural Story Generation（Fan et al., ACL 2018，arXiv 1805.04833）：https://arxiv.org/pdf/1805.04833
  - seq2seq 直接做故事生成会**退化成"几乎不看 prompt 的语言模型"**；层次化生成 + gated multi-scale self-attention + model fusion 才能显著提升对 prompt 的遵循（人类评测偏好 2:1）。
  - **对 story-engine 的启示**：长程下模型天然倾向"忘掉大纲自己写"——这必须被机制性对抗（分段锚定、审计、re-plan），不能靠"写得更好"。

---

## 6. 归纳：人工审核大纲/设定 → AI 介入写作的闸门设计

### 6.1 五道闸门（gate）模型

| # | 闸门 | 输入 | 输出 | 验收标准（作者视角） | 出处锚点 |
|---|---|---|---|---|---|
| **G0 设定/世界观闸门** | 作者脑洞/资料 + AI 生成的设定树/角色卡/世界观草案 | **冻结的 canon 快照**（角色卡、Lorebook、设定树） | 作者逐项确认或微调后批准；未批准不得进入写作；变更走 progression/快照，不直接改 canon | Sudowrite Characters/Worldbuilding、Novelcrafter Codex、Maliang 设定树快照、story-engine 已有角色卡 |
| **G1 总纲闸门（书→卷→章）** | canon + 作者主线意图 | 分卷/章三级大纲（每章一句话~一段，bullet 式） | 作者审章节级走向，可重生成/改写不满意章节；**这是最贵的返工点，必须人审** | Sudowrite Outline(Rewrite)、Maliang 三级大纲/剧情推演、wordflowlab /plan、2605.17064 书→章→场景 |
| **G2 场景/细纲闸门（beat 级）** | 已批准的章节大纲 + canon | 场景级 beats（每 beat ≈ 300-500 字正文当量；POV/地点/目标/冲突/转折） | 作者确认场景目标与转折；AI 预检"太散/覆盖太多事件"并给拆分建议 | Novelcrafter scene beats（作者当导演）、Sudowrite Scenes(+Quick Fix 预检)、ConWriter 转移约束 |
| **G3 正文草稿闸门** | 已批准 beats + 前文上下文 + canon 注入 | 本章正文草稿 | 自动审计（大纲偏离/连续性/AI味/伏笔）**标记问题** → 作者审阅 → 批准或重写 | inkos 33 维审计 + review approve、autonovel evaluate/review、ConWriter 提交前校验 |
| **G4 canon 回写闸门** | 正文与大纲的偏离 | canon/大纲的更新（或驳回正文） | 作者决定"改正文还是改大纲"；回写需显式确认 | Sudowrite "Update" 回写、Novelcrafter Progressions |

### 6.2 闸门设计的四条铁律（跨工具/论文收敛）

1. **每层产出必须"可重生成 + 可带指令驳回"**：Sudowrite 的 Rewrite、Maliang 的剧情推演重生成、wordflowlab 的 /clarify，全部支持"不满意 → 给指令重跑"。闸门不是"是/否"，而是"接受 / 带反馈重跑"。
2. **正文前最后一道结构闸门（Scene/Beat）上下文最全、责任最重**：Sudowrite Scenes 吃最多字段、Novelcrafter beat 是作者亲自写的导演指令。**别让 AI 直接从章节大纲跳正文，中间必须有场景/beat 层。**
3. **审核通过的设定/大纲必须能可靠注入、且作者能看见注入结果**：NovelAI/AI Dungeon 的命中可见性 + 常驻/触发开关，Sudowrite 的 Detection 下划线，Novelcrafter 的 Smart Detection。**"审过了但没注入进去"是隐性返工源。**
4. **静态计划会衰减，必须分段 re-plan + reflect**：IS-CoT 的 Plan-Write-Reflect 递归循环、ConWriter 的逐场景转移校验、Fan 2018 的退化证据——三者共同指向：**每段写作前基于大纲刷新本段计划，写后校验偏离**，而非一次性喂入。

### 6.3 常见返工来源（按"改动成本/发生概率"排序）

| 返工源 | 为什么发生 | 对应闸门/对策 |
|---|---|---|
| **设定/canon 中途被迫改**（角色关系、能力体系） | G0 没审清，或变更直接覆盖旧设定污染前文 | G0 严格审批；用 Progressions/历史快照做**时间隔离**，不直接改 canon（Novelcrafter/Maliang） |
| **大纲层级缺失导致正文自由发挥** | 直接从章节大纲跳正文，AI 无 beat 约束 | 增加 G2 场景/beat 层；beat 粒度 ~500 字（Novelcrafter） |
| **计划跟随度衰减** | 静态计划在长程失效，模型"忘掉大纲自己写" | 分段 re-plan + reflect（IS-CoT）；审计员显式查"大纲偏离"（inkos） |
| **一致性错误向后传播** | 早期场景错误未被拦截，污染后续记忆 | 场景提交前校验 + 句级局部修补（ConWriter）；双记忆（静态要求 vs 动态状态） |
| **AI 味/文风后期才处理** | 去味在正文生成后才做，逐章返工 | 去味规则前置到 Writer prompt 层（inkos）；文风指纹注入源头（story-engine 已有文风库可复用） |
| **上下文注入遗漏** | 关键词未触发、注入位置不对 | 命中可见性 + 常驻/触发开关 + Force Activation（NovelAI/AI Dungeon） |
| **长度/节奏不可控** | 直接指定字数，模型无法稳定遵循 | 用场景/beat **数量**控长度，而非字数参数（Sudowrite Scenes→length；Plan-and-Write 过程化长度控制） |

---

## 附：来源索引

**工具（官方文档/仓库）**
1. Sudowrite — What is Story Bible：https://docs.sudowrite.com/using-sudowrite/1owq1kGqof9rtcyGnrWUBS/what-is-story-bible/jmWepHcQdJetNrE991fjJC
2. Sudowrite — Outline：https://docs.sudowrite.com/using-sudowrite/1owq1kGqof9rtcyGnrWUBS/outline/3owKyHXUm1bCdp41b2Npjk
3. Sudowrite — Scenes & Draft：https://docs.sudowrite.com/using-sudowrite/1owq1kGqof9rtcyGnrWUBS/scenes--draft/49p5MTVxTKkVFEC5rVUzpY
4. Sudowrite 博客：https://sudowrite.com/blog/how-sudowrite-works/
5. Novelcrafter — Beats：https://docs.novelcrafter.com/en/articles/9419387-where-do-i-put-my-scene-chapter-act-book-summary-what-about-my-beats
6. Novelcrafter — Progressions：https://docs.novelcrafter.com/en/articles/8675593-progression-additions
7. Novelcrafter — Codex 特性页：https://novelcrafter.com/features/codex
8. Novelcrafter — Plan/Write 界面：https://www.novelcrafter.com/help/docs/plan/the-plan-interface 、https://www.novelcrafter.com/help/docs/write/the-write-interface
9. NovelAI — Lorebook：https://docs.novelai.net/en/text/lorebook/
10. NovelAI — Advanced Settings：https://docs.novelai.net/en/text/editor/advancedsettings/
11. AI Dungeon — Memory System：https://help.aidungeon.com/faq/the-memory-system
12. MaliangAINovalWriter：https://github.com/Deng-m1/MaliangAINovalWriter
13. 墨狐AI（AIHub 介绍）：https://www.aihub.cn/tools/writing/inkfox-ai/
14. 笔灵/蛙蛙写作测评：https://www.cnblogs.com/xielunwen/articles/21595141
15. 91Writing：https://github.com/ponysb/91Writing
16. inkos：https://github.com/Narcooo/inkos
17. wordflowlab/novel-writer：https://github.com/wordflowlab/novel-writer （skills：https://github.com/wordflowlab/novel-writer-skills）
18. NousResearch/autonovel：https://github.com/NousResearch/autonovel

**学术**
19. IS-CoT（Plan-Write-Reflect / Length Collapse）：https://arxiv.org/pdf/2606.09709v1
20. Plan-and-Write：https://arxiv.org/pdf/2511.01807
21. WritingPath（NAACL 2025 Industry）：https://aclanthology.org/2025.naacl-industry.20.pdf
22. ConWriter：https://arxiv.org/pdf/2608.05169v2
23. WriterAgent/WriterLoRA：https://arxiv.org/html/2502.15616v1
24. Towards Human-Level Book-Writing Capability：https://arxiv.org/abs/2605.17064
25. Hierarchical Neural Story Generation：https://arxiv.org/pdf/1805.04833
