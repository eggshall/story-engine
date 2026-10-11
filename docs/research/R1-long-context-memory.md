# R1 · 2000 万字中文小说长期/永久记忆上下文系统 — 技术路线调研

> 目标：为 story-engine（Python FastAPI + Vue3）评估「长期连载一部 2000 万字级小说、保持前后一致与文风统一」的可行技术路线。
> 现状约束：远程 DeepSeek（128K 上下文）+ 本地 Qwen3.5-9B via Ollama（16GB 显存，实际可用 ~32K）。
> 关键量级：2000 万汉字 ≈ 1500–2000 万 token（约 0.75–1 token/汉字，取决于 tokenizer），远超任何可用上下文窗口（128K），**不可能一次性放入窗口**。
>
> 报告约定：每条结论标注来源 URL；明确区分「论文/工程实证」与「厂商宣传话术」；未找到证据的点直接写「未找到」，不编造数字。

---

## 0. 一页结论（TL;DR）

1. **纯「把全文塞进上下文」路线已被证伪**：即便有 1M token 窗口，有效上下文远小于标称值（RULER、NoLiMa、Chroma Context Rot 三份独立实证一致）。
2. **唯一可行方向是「分层记忆 + 检索 + 递归/代理式上下文工程」**：外部把小说切块索引，运行时按需把「写作当下最相关的一小撮材料」喂进 32K/128K 窗口。
3. 对「人物/事件/伏笔关系」这种强关系型文本，**图谱类检索（GraphRAG/LightRAG/HippoRAG）在多跳问题上有实测优势**，但索引构建的 LLM 调用成本高，20M 字全量建图不现实，需裁剪为「角色/事件/伏笔」结构化层 + 正文向量/关键词检索层。
4. **落地推荐（针对 16GB 显存 + DeepSeek API 的预算）**：正文做「章/场景」级分块 + 本地 embedding（BGE-M3）+ 向量/BM25 混合检索 + 结构化 Lorebook（角色卡/设定/伏笔）+ 增量滚动摘要（每章一章一摘要）。图谱只作用于「关系层」而非全文。
5. 全部成本中，**embedding 是最便宜的（20M 字一次性 < ¥20 或本地免费）**；真正的成本在「摘要/建图的 LLM 调用」与「检索进窗口的 token 预算」，需要显式控制。

---

## 1. 长上下文的真实能力：实证证据

### 1.1 Lost in the Middle（2023，TACL）

- 结论：模型对长上下文的利用呈 **U 形曲线**——相关信息在开头或结尾时表现最好，在**中间显著下降**，即便是「显式长上下文模型」也如此。
- 这直接否定了「只要窗口够大，模型就能均匀利用全文」的假设。
- 来源：Liu et al., *Lost in the Middle: How Language Models Use Long Contexts*, https://arxiv.org/abs/2307.03172

### 1.2 RULER（NVIDIA, 2024, COLM）

- 结论：在普通 NIAH（Needle-in-a-Haystack）上近乎满分的长上下文模型，在扩展任务（多种/多个 needle、多跳追踪、聚合）上**几乎全部随上下文增长大幅掉分**。
- 具体数字：评测 17 个声称 ≥32K 上下文的模型，**只有一半能在 32K 长度维持满意性能**。Yi-34B（标称 200K）在长度与任务复杂度上升时仍有很大改进空间。
- 来源：Hsieh et al., *RULER: What's the Real Context Size of Your Long-Context Language Models?*, https://arxiv.org/abs/2404.06654 （代码 https://github.com/NVIDIA/RULER）

### 1.3 NoLiMa（Adobe, 2025, ICML）

- 结论：去掉「字面匹配」捷径后（needle 与问题只有隐含关联，如「谁去过赫尔辛基 / Yuki 住在 Kiasma 博物馆旁」），模型在 <1K 短上下文表现好，**随上下文增长显著衰减**。
- 具体数字：**在 32K 处，13 个模型里有 11 个跌到其短上下文基线的 50% 以下**；即便是最强的例外 GPT-4o，也从 99.3% 跌到 69.7%。
- 来源：Modarressi et al., *NoLiMa: Long-Context Evaluation Beyond Literal Matching*, https://arxiv.org/abs/2502.05167 （数据/代码 https://github.com/adobe-research/NoLiMa）

### 1.4 Chroma「Context Rot」报告（2025，工程实测）

- 结论：对 18 个模型（含 Claude Sonnet 4、GPT-4.1、Qwen3-32B、Gemini 2.5 Flash）做受控实验（固定任务难度、只变输入长度），发现**所有实验下性能随输入长度一致衰减**，且：
  - needle–question 相似度越低，衰减越快；
  - **干扰项（distractor）的破坏性随上下文长度被放大**；
  - 反直觉地，**结构连贯的 haystack 比打乱的更伤性能**（模型对逻辑流更敏感）。
  - 在 LongMemEval 对话问答上，「聚焦输入（~300 token）」显著优于「全量输入（~113k token）」——多塞无关上下文 = 逼模型同时做「检索+推理」，稳定度下降。
- 来源：Hong, Troynikov & Huber, *Context Rot: How Increasing Input Tokens Impacts LLM Performance*, https://www.trychroma.com/research/context-rot （代码 https://github.com/chroma-core/context-rot）

### 1.5 「有效上下文长度 vs 1M 标称窗口」综述

- 第三方综述明确指出「标称 1M token 窗口 ≠ 1M 有效上下文」，在 NoLiMa / MRCR / RULER / 多跳任务上，有效长度远小于标称值；并指出「全窗口装载 vs 压缩工作集」在最新一代（Claude 4.6+ / GPT-5.5 / Gemini 3.x）上**仍缺少受控对比，是个开放问题而非已解决**。
- 来源：Lumisonde, *Effective Context Length vs the 1M-Token Context Window*, https://lumisonde.com/reports/effective-context-gap

**小结（对 story-engine 的含义）**：DeepSeek 128K 与 Qwen 32K 的「有效可用上下文」只会比标称更小，且「把前文全塞进去」不仅费 token，还会因为 lost-in-the-middle 与干扰项放大而**主动降低写作质量**。结论：必须外部化记忆 + 按需检索。

---

## 2. 递归 / 分层的上下文处理架构

### 2.1 Recursive Language Models（MIT, Alex L. Zhang et al., 2025）

- 思路：把长 prompt 当作「外部环境」，让模型**用代码（编程式）检查、分解、递归调用自己**处理 prompt 片段——即「把长文本当环境用代码去查询」的范式。
- 能力规模：**可处理超出模型上下文窗口两个数量级**的输入。
- 实测数字（论文自报）：在 GPT-5 上，四个长上下文任务相对基线——比 compaction 中位 +26%、比 CodeAct（子调用）+130%、比 Claude Code +13%，成本相当；微调出的 RLM-Qwen3-8B 比原 Qwen3-8B 平均 +28.3%，在三个长上下文任务上接近原版 GPT-5 质量。
- 代价：需要模型具备「工具调用/代码执行」能力；递归调用带来延迟与多次推理成本；DeepSeek 支持 function calling，可行但需工程化。
- 来源：Zhang, Kraska, Khattab, *Recursive Language Models*, https://arxiv.org/abs/2512.24601 （博客 https://alexzhang13.github.io/blog/2025/rlm/ ，代码 https://github.com/alexzhang13/rlm）

### 2.2 递归摘要（Recursive Summarization）+ RAPTOR（Stanford, 2024）

- 思路：把文本切块 → 嵌入 → 聚类 → **逐层生成摘要**，自底向上建一棵「不同抽象层次」的树；检索时从树的不同层级取信息。
- 实测：在 QuALITY 基准上，RAPTOR + GPT-4 相对最佳成绩**绝对准确率 +20%**。
- 代价：建树需要大量 LLM 摘要调用（20M 字全文建树成本高）；但「每章一章一摘要 + 每卷一卷一摘要」的**粗粒度版**非常适合小说（轻量、滚动、增量）。
- 来源：Sarthi et al., *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval*, https://arxiv.org/abs/2401.18059

### 2.3 Chain-of-Agents（NeurIPS 2024）

- 思路：多个 worker 各读一段、传递中间「记忆 cue」，串行解决超长上下文任务；适合「让多个小上下文模型协作啃长文」。
- 来源：Zhang et al., *Chain of Agents: Large Language Models Collaborating on Long-Context Tasks*, https://arxiv.org/abs/2406.02844

**小结**：递归/分层架构是「突破窗口上限」的正解，RLM 提供了最强的「把长文当环境」范式，但工程复杂度高；**对小说最务实的是 RAPTOR 式「章→卷→全书」三级滚动摘要 + 检索**。

---

## 3. Agent 记忆系统

| 系统 | 核心机制 | 实证/规模 | 适用性 | 来源 |
|---|---|---|---|---|
| **MemGPT / Letta** | 受 OS 虚拟内存启发，在「主上下文/外部存储」间做 **paging（分页换入换出）**，管理多级存储 | 论文：能分析远超窗口的文档、多会话对话保持记忆；已产品化为 Letta | 通用对话记忆框架，可直接采用/参考其「上下文分页」思想 | https://arxiv.org/abs/2310.08560 ；https://www.letta.com |
| **Mem0** | 从对话动态**抽取→整合→检索** salient 信息；变体加图谱记忆 | 论文（LOCOMO 基准）：相对 OpenAI 全上下文 LLM-as-Judge **+26%**，p95 延迟 **-91%**，token 成本 **省 >90%**；图谱版再 +2% | 多会话一致性；已开源，可借鉴其抽取层 | https://arxiv.org/abs/2504.19413 ；https://github.com/mem0ai/mem0 |
| **A-MEM** | 仿 Zettelkasten 卡片盒：新记忆生成结构化笔记（描述/关键词/标签），**动态建链、记忆演化** | 论文：六个基座模型上优于 SOTA 基线（NeurIPS 2025） | 「人物/事件卡片 + 动态关联」天然契合小说设定管理 | https://arxiv.org/abs/2502.12110 |
| **MemoryOS / MemOS** | 面向 AI 系统的「记忆操作系统」，分层记忆管理 | 论文（2025） | 框架级参考；偏平台化 | https://arxiv.org/abs/2507.03724 ；https://memoryo.dev |
| **Generative Agents**（斯坦福 2023） | **memory stream（经验流） + 反思（reflection）合成高层记忆 + 动态检索** | 论文：25 个 agent 小镇，涌现社交行为；消融证明 observe/plan/reflect 三组件都关键 | 「记忆流 + 定期反思成高层设定」是小说人物一致性维护的经典范式 | https://arxiv.org/abs/2304.03442 |
| **ACE（Agentic Context Engineering）** | 把上下文当作**演化的 playbook**：生成→反思→策展，增量结构化更新，避免「简短化偏差」与「上下文坍缩」 | 论文（ICLR 2026）：agents **+10.6%**、finance **+8.6%**；AppWorld 上小开源模型追平榜首生产级 agent | 「系统提示/角色卡作为随剧情演化的结构化文档」的直接理论支撑 | https://arxiv.org/abs/2510.04618 |

**小结**：这些系统给出一致的方法论——**不在窗口里存全部记忆，而是「抽取要点 → 存外部 → 检索注入」+「定期反思/整合成高层结构」**。对 story-engine：Mem0/A-MEM 的「抽取+演化」、Generative Agents 的「记忆流+反思」、ACE 的「演化式角色卡/设定文档」可组合。

---

## 4. 知识图谱 / 结构化检索

| 系统 | 机制 | 对「关系型小说文本」的实测结论 | 来源 |
|---|---|---|---|
| **GraphRAG**（微软） | LLM 两阶段建图：实体知识图谱 + 社区摘要；问题→各社区局部回答→汇总 | 论文：**1M token 量级**数据集上，「全局感知型问题」（如"数据集主题是什么"）的 comprehensiveness 与 diversity 显著优于朴素向量 RAG（原文用"substantial improvements"，具体 win-rate 见论文正文图表） | https://arxiv.org/abs/2404.16130 ；https://microsoft.github.io/graphrag/ |
| **LightRAG**（港大） | 图谱+向量**双层检索**，低层/高层知识发现，**增量更新算法** | 论文：检索准确率与效率优于朴素 RAG；增量更新适合「小说逐章追加」 | https://arxiv.org/abs/2410.05779 ；https://github.com/HKUDS/LightRAG |
| **HippoRAG**（OSU，NeurIPS 2024） | 仿海马体索引理论：LLM + 知识图谱 + Personalized PageRank，单步检索实现多跳知识整合 | 论文：多跳 QA **最多 +20%** 优于 SOTA；单步检索达到/超过迭代检索（IRCoT）且**便宜 10–20 倍、快 6–13 倍** | https://arxiv.org/abs/2405.14831 ；https://github.com/osu-nlp-group/hipporag |

**为什么图谱对「人物/事件/伏笔」优于朴素向量 RAG**（实证支撑）：

- 朴素向量 RAG 把每个 passage 孤立编码，**无法回答「需要把分散在多处的两条事实拼起来」的多跳问题**（HippoRAG 论文的动机，明确用「找 Stanford 的阿尔茨海默研究教授」例子说明）。
- 小说的一致性问题几乎全是这种**跨章多跳关系**：「A 在 3 章欠 B 的恩情 → 12 章 A 的行为是否对得上」——正是图谱多跳检索的强项。
- GraphRAG 的「全局问题」能力对应「全书主题/伏笔回收盘点」。

**代价（重要）**：三者的索引构建都要**对全文做 LLM 实体/关系抽取**（GraphRAG 还要社区摘要），对 20M 字全量建图不可行（成本/耗时过高）。务实做法：**只对「角色、地点、组织、物品、事件、伏笔」这一结构化层建图**（量级约几千~几万节点），正文仍走向量/BM25 检索，图谱作为「关系覆盖层」。

---

## 5. 混合检索：向量 + BM25 + 关键词触发（Lorebook 式）+ 结构化过滤

- **混合检索（向量 + BM25）**：VLDB 2026 的实证分析指出，两者各有盲区、需按查询类型权衡融合；BM25 在「精确关键词/专有名词（人名、地名、专有设定名）」上强，向量在「语义改写/近义」上强。小说场景两者互补性极高（人名/专名靠 BM25，情节语义靠向量）。
  - 来源：*Balancing the Blend: An Experimental Analysis of Trade-offs in Hybrid Search*, https://www.vldb.org/pvldb/vol19/p1715-gao.pdf
- **Lorebook / World Info（关键词触发）**：AI 小说社区（KoboldAI / SillyTavern）的成熟工程方案——把角色/设定写成「条目」，按**关键词匹配**注入窗口，触发式而非全量注入，成本可控、可解释。
  - 来源：SillyTavern World Info 文档 https://docs.sillytavern.app/usage/core-concepts/worldinfo/ ；DeepLore（自动管理 lorebook）https://github.com/pixelnull/sillytavern-DeepLore/wiki/What-is-DeepLore
- **针对叙事文本的混合检索实测对比**：**未找到**已发表、可复现的「叙事文本 + 向量/BM25/图谱 + 关键词触发」组合的对照基准。这是研究空白，story-engine 可自行构建评测集（从已连载小说中抽「一致性问答」测召回）。不得引用任何未经证实的厂商声称。

**小结**：混合检索的工程价值有通用实证（BM25+向量互补、图谱多跳优势、Lorebook 触发式注入的社区实践），但「叙事领域组合最优解」无公开实测，需自建评测。

---

## 6. 20M 字符量级的工程落地方案

### 6.1 索引粒度

| 粒度 | 块大小（建议） | 用途 |
|---|---|---|
| 段落/场景 | 300–800 汉字 | 正文向量检索（细节级：对话、动作、环境） |
| 章 | 每章一个「章摘要 + 关键事件 + 出场人物 + 状态变化」 | 滚动摘要、跨章一致性 |
| 卷/篇 | 每卷一个高层摘要 | 长期情节弧线 |
| 结构化条目 | 角色卡 / 地点 / 组织 / 物品 / 伏笔（含「未回收」标记） | 图谱/关键词触发层 |

- 20M 汉字 ÷ 500 字/块 ≈ **4 万块**（若 1000 字/块则 2 万块）。向量库规模完全在单机能力内（Qdrant/Chroma/Milvus-Lite 均可）。

### 6.2 索引成本估算（embedding）

- **本地（推荐，16GB 显存可行）**：BGE-M3（多语言，支持中英，稠密+稀疏+多粒度）或 bge-large-zh-v1.5（中文）。4 万块 × 1024 维 float16 ≈ 80MB，显存占用极小，**零 API 费用**。
  - 来源：BGE-M3 论文 *M3-Embedding*, https://arxiv.org/abs/2402.03216
- **云端（若不本地 embed）**：以 OpenAI text-embedding-3-small（$0.02 / 1M token）估算，20M token ≈ **$0.4（一次性）**；text-embedding-3-large（$0.13 / 1M token）≈ **$2.6**。数量级极低，不是瓶颈。
  - 来源：OpenAI 定价 https://openai.com/api/pricing/ （价格以官网实时为准，此处为量级估算）
- **真正的成本**：不是 embedding，而是「章摘要 + 建图实体抽取」的 LLM 调用。若每章（假设 2000 章）一次摘要调用 + 关系抽取，成本取决于模型单价，需按预算设计（可走本地 Qwen 做摘要抽取，远程 DeepSeek 只做写作与关键关系）。

### 6.3 增量更新

- 逐章追加：新章 → 切块 embed 增量入库 + 更新该章/卷滚动摘要 + 更新结构化条目（角色状态、伏笔「回收」标记）。LightRAG 的增量更新算法是现成参考（https://arxiv.org/abs/2410.05779）。
- 只重算受影响层，不重跑全量。

### 6.4 检索延迟

- 4 万向量 + BM25 混合检索：**毫秒级**（单机向量库标配，无需 GPU）。
- 图谱多跳（Personalized PageRank）：同样毫秒级（HippoRAG 实测比迭代检索快 6–13 倍）。
- 真正的延迟在 LLM 生成与递归调用，不在检索。

---

## 7. 推荐技术路线（story-engine 落地建议）

1. **正文层**：章/场景分块 + 本地 BGE-M3 向量 + BM25（人名/专名关键词）混合检索，单机毫秒级。
2. **结构化 Lorebook 层**（已存在的 lore/characters 模块）：角色卡/设定/伏笔条目，关键词触发 + 图谱关联（参考 A-MEM 的 Zettelkasten 建链 + 伏笔「未回收」状态机）。
3. **滚动摘要层**：章→卷→全书三级递归摘要（RAPTOR 思想），每章增量更新，不重跑。
4. **图谱层（裁剪版）**：只对「人物/事件/伏笔」建图（LightRAG/HippoRAG），支撑多跳一致性查询（「A 的这条行为是否违背第 N 章设定」）。
5. **运行时注入**：写作时把「当前场景上下文 + 触发到的 Lorebook 条目 + 相关记忆检索结果 + 最新滚动摘要」塞进 32K/128K 窗口，**绝不塞全文**（Context Rot / Lost in the Middle 反证了全量注入有害）。
6. **演化式上下文**：角色卡/设定文档按 ACE 思路增量演化，避免「简短化偏差」与「上下文坍缩」。
7. **自建评测**：从连载小说抽「一致性/文风/伏笔」问答集，测各检索组合的召回与一致性（填补第 5 节的公开基准空白）。

---

## 8. 证据分级与「未找到」清单

**有论文/工程实证**：Lost in the Middle、RULER、NoLiMa、Context Rot、RLM、RAPTOR、Chain-of-Agents、MemGPT、Mem0、A-MEM、MemOS、Generative Agents、ACE、GraphRAG、LightRAG、HippoRAG、混合检索（VLDB）、BGE-M3、LongBench（中文长上下文基准，https://arxiv.org/abs/2308.14508）、Ziya-Reader（中文 128K，https://arxiv.org/abs/2312.11193）。

**厂商宣传话术（需打折看待）**：各模型厂商「1M/10M 上下文」标称值（RULER/NoLiMa/Context Rot 证明标称 ≠ 有效）；Mem0/Letta 等商业页面的「生产级」表述（以论文实测数字为准，不采信营销文案）。

**未找到证据的点（如实声明）**：
- 针对**中文长篇小说**叙事文本的混合检索/图谱组合的公开对照基准 —— 未找到，需自建。
- 最新一代模型（Claude 4.6+ / GPT-5.5 / Gemini 3.x）「全窗口装载 vs 压缩工作集」的受控对比 —— 公开文献缺（Lumisonde 明确标注为开放问题）。
- 「20M 字级别」真实小说语料的系统评测 —— 未找到；所有系统均在小得多的规模（1M token 级）验证。

---

## 9. 来源清单（URL）

1. Lost in the Middle — https://arxiv.org/abs/2307.03172
2. RULER — https://arxiv.org/abs/2404.06654
3. NoLiMa — https://arxiv.org/abs/2502.05167
4. Context Rot（Chroma） — https://www.trychroma.com/research/context-rot
5. Effective Context Gap（Lumisonde） — https://lumisonde.com/reports/effective-context-gap
6. Recursive Language Models — https://arxiv.org/abs/2512.24601
7. RAPTOR — https://arxiv.org/abs/2401.18059
8. Chain-of-Agents — https://arxiv.org/abs/2406.02844
9. MemGPT — https://arxiv.org/abs/2310.08560
10. Mem0 — https://arxiv.org/abs/2504.19413
11. A-MEM — https://arxiv.org/abs/2502.12110
12. MemOS — https://arxiv.org/abs/2507.03724
13. Generative Agents — https://arxiv.org/abs/2304.03442
14. ACE — https://arxiv.org/abs/2510.04618
15. GraphRAG — https://arxiv.org/abs/2404.16130
16. LightRAG — https://arxiv.org/abs/2410.05779
17. HippoRAG — https://arxiv.org/abs/2405.14831
18. Hybrid Search（VLDB） — https://www.vldb.org/pvldb/vol19/p1715-gao.pdf
19. BGE-M3 — https://arxiv.org/abs/2402.03216
20. LongBench — https://arxiv.org/abs/2308.14508
21. Ziya-Reader — https://arxiv.org/abs/2312.11193
22. SillyTavern World Info — https://docs.sillytavern.app/usage/core-concepts/worldinfo/
23. DeepLore — https://github.com/pixelnull/sillytavern-DeepLore/wiki/What-is-DeepLore
24. OpenAI Embedding 定价 — https://openai.com/api/pricing/
