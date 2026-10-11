# R2 · 长篇小说 AI 写作的文风统一(style consistency)技术方案调研

> 面向 story-engine(Python FastAPI + Vue3 中文长篇小说写作系统)的技术选型调研。
> 背景痛点:一本书几百万字,写到第 100 章时文风漂移、AI 味词汇回归、叙事视角/句长/对话比例变化。
> 调研日期:2026-10-11。所有结论附来源 URL;每条标注证据等级:**【论文】**(同行评审/预印本带实验)、**【工程实证】**(带实测数据的工具/评测文)、**【主观经验】**(无严格实验的从业者/社区经验)。

---

## 0. 结论速览(TL;DR)

1. 文风漂移是被**实证确认**的现象,但它与"事实/时间线漂移"是**两个不同的失效机制**——ConStory-Bench 发现文风类错误与事实/角色类错误相关性接近零。这意味着"修事实一致性"和"修文风一致性"需要**分开的工具链**。
2. 长上下文的"长度本身"就会损害生成质量(与信息是否在上下文里无关);Qwen2.5-7B 在 40-50% 上下文长度处出现临界崩塌。因此**无限堆上下文不是文风稳定的解**。
3. few-shot 样段的收益曲线:分类任务约 2-5 例即饱和;创作任务收益持续到"许多段",但**关键不在数量而在样本多样性**(安静/动作/对话/内心独白各类型都要有)。
4. 检索式(RAG)动态注入风格样本**优于固定 few-shot**,有实证(医学报告领域:动态检索在 k=10、temperature=0 时全面优于固定随机 few-shot)。
5. 结构化约束(句长分布/对话占比/虚词比例/禁用词表)作为**运行时可检验的硬约束 + 生成后自动检测重写**,是当前工程上成本最低、最可落地的路径;其"风格分数 rerank(best-of-n)"有扎实的论文与工具支持。
6. 模型侧固化:个人 16GB 显存可跑 QLoRA/LoRA(7B 级模型 4-bit 即可,实测 6-8GB VRAM),但**风格 LoRA 需要 2-5 万词以上高质量单一作者语料**才有效;数据不足时 LoRA 收益 < 好 prompt + 样本注入。DPO/GRPO 风格对齐有论文,但成本/复杂度对个人项目偏高。
7. "风格向量/激活工程"路线(style vectors、sNeuron-TST、n-gram logit 注入)轻量但**脆弱**,现阶段被 prompt 和 LoRA 稳定支配,不建议作为主方案。
8. 专业写作工具的一致性实践高度趋同:**手动/自动维护的"故事圣经 + 关键词触发的上下文注入 + 生成后校验"**三层结构;Sudowrite 用真实文段样本注入(而非风格描述)、Novelcrafter 用 Codex 词条、NovelAI 用关键词触发的 Lorebook。
9. 一致性检查已有成熟开源基准与检测器:ConStory-Bench / ConStory-Checker(5 大类 19 子类,含"叙事与文风"的视角混淆/语气不一致/文风偏移)可直接借鉴其分类与检测 prompt。
10. 对 story-engine 的最优组合建议:**(a) 风格样本库按场景 RAG 检索注入(替换固定注入)+(b) 14 维量化特征做成生成后自动检测 + 超阈值触发重写/rerank +(c) 禁用词表 + AI 味词表硬过滤 +(d) 文风类一致性检查并入 ConStory 式分类检测**。LoRA 留作数据攒够 3 万字以上后的可选增强。

---

## 1. 文风漂移的成因与量化

### 1.1 漂移是被实证确认的普遍现象

- **语义漂移(semantic drift)**:Spataru et al. (NAACL 2024)首次系统测量了长文本生成中的漂移——模型先生成正确事实、后逐渐"漂走"生成错误事实,并提出"semantic drift score"量化正确/错误事实的分离程度。漂移位置呈 U 形分布,更多发生在生成前 10% 的段落。**这确认了"越写越偏"不是错觉,而是有测量工具的普遍现象。**【论文】 https://aclanthology.org/2024.naacl-long.202
- **长度崩塌(length collapse)**:IS-CoT (ACL 2026)发现推理增强模型在目标超过 2000 词时性能急剧下降,原因是"初始计划随长度增加引导力递减"。**对长篇小说 = 大纲/风格约束的引导力随章节推进会衰减。**【论文】 https://aclanthology.org/2026.acl-long.911.pdf
- **文风漂移是独立机制**:ConStory-Bench (arXiv 2603.05890)定义 5 大类 19 子类一致性错误,其中"叙事与文风"类含**视角混淆、语气不一致、文风偏移**三个子类;关键发现是**文风类错误与其他四类(时间线/角色/世界观/事实)相关性接近零**,说明文风漂移通过区别于事实遗忘的机制发生——事实记住不代表文风不漂。**【论文】** https://arxiv.org/html/2603.05890v1
- **"上下文长度本身"有害**:Qwen2.5-7B 在达到最大上下文 40-50% 处 F1 从 0.55-0.56 骤降到 0.3(45.5% 退化),即使信息仍然相关——退化由上下文长度本身引起,而非信息缺失。**【论文】** https://arxiv.org/abs/2601.15300
- **计划跟随度随章节衰减**:Towards Human-Level Book-Writing Capability (arXiv 2605.17064)逐章比较生成章节与章节计划,发现**计划跟随分数随生成推进持续下降**,后期章节中相当部分计划内容不再被实现——作者明确把"长程脚手架跟随度退化"列为未来工作。**【论文】** https://arxiv.org/html/2605.17064
- **长期风格退化的机制解释**:LongReD (ACL 2025)在上下文扩展训练中发现两个因素——**隐藏状态与注意力得分的分布漂移(distribution drift)+ 持续预训练中的灾难性遗忘**——导致长上下文模型在短文本任务上退化。**提示:风格一致性在长上下文中受损,机制层面是分布漂移。**【论文】** https://aclanthology.org/2025.acl-long.524.pdf

### 1.2 few-shot 锚点数量的收益曲线

- **分类式任务**:PromptHub 综述指出"2 例后收益大幅、随后平台期",引 GPT-3 原文与 Analogical Prompting 实验;实用建议"至少 2 例、通常不需要超过 5 例"。**【主观经验+引论文】** https://www.prompthub.us/blog/the-few-shot-prompting-guide
- **many-shot 区段(数十到上千例)**:Many-Shot ICL (NeurIPS 2024)发现从 few-shot 到 many-shot 有**大幅跳升**,但 MATH500 上约 125 例见顶后回落;Reinforced ICL 约 25 例平台期。**注意:这些结论来自分类/推理任务,直接迁移到"风格锚定"需谨慎。**【论文】 https://arxiv.org/pdf/2404.11018
- **创作/风格场景的实际样本数(工程经验)**:Sudowrite 官方称 Style Examples 最多 1000 词(约 5-10 段),建议"至少 5 段、覆盖安静/动作/对话/内心独白四类场景,越多越好,整章最佳"。**【工程实证/主观经验】** https://sudowrite.com/blog/ai-voice-matching ; https://sudowrite.com/blog/why-ai-writing-sounds-the-same
- **voice 匹配的样本量经验值**:socialnexis 汇总——prompt 式 voice 匹配 10-20 个高质量样本(≥3000 词)为实用目标;fine-tuning 工具下限 1000 词;**全量微调 2-3 万词是最小可行语料,5-10 万词为强匹配区间**。**【主观经验】** https://socialnexis.com/guides/ai-voice-sample-requirements
- **样本多样性 > 数量**:上述多个来源一致强调"类型覆盖"(对话/叙述/内心独白/描写)比单纯堆量更重要;单一场景的大量样本稀释而非增强风格画像。**【主观经验】**

> **对 story-engine 的含义**:已有 14 维量化特征 + 样本文段的设计方向正确;但固定注入同一段会失效——见第 2 节。

---

## 2. 检索式风格锚定(RAG 风格样本)

### 2.1 实证支持:动态检索 > 固定 few-shot

- **直接对比证据**:PLOS ONE 2025 医学报告研究在 11,998 份 CTPA 报告中对比"动态检索 few-shot vs 零样本 vs 固定随机 few-shot",结论:**动态检索在所有配置下显著优于固定 few-shot(p<0.05),最优在 temperature=0、k=10**;ROUGE-1 F1 从 0.35-0.37(零样本)提到 0.44-0.47。作者明确指出固定 few-shot"笨拙:样本可能与当前场景无关",动态检索把 few-shot 从"随机样本"变成"这就是我们如何写这类场景"。**【论文/工程实证】** https://dx.plos.org/10.1371/journal.pone.0354688
- **风格迁移场景的 RAG 增补**:TST-LLM (arXiv 2602.15013)在文本风格迁移中把 RAG 用于微调与推理两端,发现检索增强**有效维持术语/名称一致性与长期风格一致性**。**【论文】** https://arxiv.org/html/2602.15013v1
- **工程侧结论**(Fine-tuning vs RAG 对比文,inferensys):RAG 以样本为 prompt 的风格一致性(0.78)低于微调(0.94),且"长篇语气一致性在 2k token 后退化";但 RAG 零重训成本、可追踪。**即:检索注入是低成本首选,但长篇稳定性弱于微调。**【工程实证,厂商数据需审慎】** https://inferensys.com/differences/domain-specific-ai-model-delivery-stacks/domain-specific-rag-vs-fine-tuning/fine-tuning-for-domain-style-and-tone-vs-rag-for-domain-style-and-tone

### 2.2 与 story-engine 现有设计的关系

- story-engine 已有"风格样本库 + 推荐 API",但按当前调研,**推荐逻辑应从"给整本书推荐一个风格"升级为"按当前章节场景(视角、对话/动作/描写占比、情绪)检索最相近的样本段注入 prompt"**。
- 检索粒度建议对齐医学报告的结论:top-k 采样段(而非全文)+ 低温度;样本段按"场景类型"标签索引(安静/动作/对话/内心独白),与 14 维特征向量做混合检索。

---

## 3. 结构化文风约束(可检验约束 + 生成后检测/重写)

### 3.1 style-constrained decoding(解码期约束)

- **Reward-Augmented Decoding (RAD, EMNLP 2023)**:用小单向奖励模型在生成过程中打分并重缩放采样概率,在无毒性/情感控制上"在不改训练的方法中最优,匹敌重训方法"。**这是"用风格分数在解码期纠偏"的直接理论支撑。**【论文】** https://aclanthology.org/2023.emnlp-main.721
- **COLD Decoding (NeurIPS 2022)**:能量函数 + Langevin 动力学,把关键词/风格等软硬约束统一成可微能量函数,无需任务微调。**【论文】** https://proceedings.neurips.cc/paper_files/paper/2022/hash/3e25d1aff47964c8409fd5c8dc0438d7-Abstract-Conference.html
- **MUCOCO (NeurIPS 2021)**:连续优化 + 拉格朗日乘子做多约束解码,在风格迁移/形式化控制上显著优于基线。**【论文】** https://proceedings.neurips.cc/paper/2021/file/79ec2a4246feb2126ecf43c4a4418002-Paper.pdf
- **INSTRUCTCTG (ICML 2023)**:把风格/句法/长度等约束"言语化"成自然语言指令而非改解码器,风格约束用风格分类器构造训练对。**即"把约束写成可检验指令"同样有效,不一定要改解码。**【论文】** http://proceedings.mlr.press/v202/zhou23g/zhou23g.pdf
- **动态多奖励加权 (EMNLP 2024)**:多风格可控生成中,用判别器梯度幅度动态加权多个风格奖励,优于静态加权。**对"14 维特征"的启示:多维度约束需要动态加权,不能等权。**【论文】** https://aclanthology.org/2024.emnlp-main.386

> **落地含义**:story-engine 的 14 维量化特征(句长、对话占比、虚词比例等)天然适合做成**可微/可打分的约束函数**,在 (a) 生成后检测、(b) best-of-n rerank、(c) 触发重写三个环节使用,不必重训模型。

### 3.2 生成后重写(post-hoc rewrite)

- Writer-R1 (arXiv 2603.15061):"生成-反思-修订"闭环 + 从用户 prompt 动态构造可复用的细粒度检查清单与分层评分规则,把"难定义的写作质量"变成可执行结构。**是"生成后自动检测+重写"的完整框架模板。**【论文】** https://arxiv.org/pdf/2603.15061
- IS-CoT (ACL 2026):Plan-Write-Reflect 动态循环,在超 2000 词时维持长度与连贯性,优于静态计划。**【论文】** https://aclanthology.org/2026.acl-long.911.pdf

### 3.3 best-of-n 按风格分 rerank

- **BoN 有效性**:Revisiting Best-of-N (ICML 2025)证明在 win-rate 目标下,适当调参的 BoN **统计与计算上均最优**,解释其工程普遍成功;但要注意**奖励攻击(reward hacking)**。**【论文】** https://raw.githubusercontent.com/mlresearch/v336/main/assets/sriraman26a/sriraman26a.pdf
- **防奖励攻击**:Regularized BoN (RBoN, arXiv 2404.01054)在选样时加邻近正则化,代理奖励与真实目标相关性低时显著优于朴素 BoN;BoNBoN 提出把 BoN 分布蒸馏进模型以省推理成本。**【论文】** https://arxiv.org/html/2404.01054v2 ; https://www.proceedings.com/content/079/079017-0094open.pdf
- **工程含义**:用 14 维特征构造"风格分"(与目标画像的相似度)做 n 选 1 rerank 是低成本高收益手段;建议 n 取 3-5,并加正则防"高分但不像人写"的奖励攻击。**风格分数本身要与样本文段锚定,避免模型刷分。**

---

## 4. 模型侧固化(LoRA/DPO/风格向量)

### 4.1 LoRA/QLoRA 在个人 16GB 显存的可行性(实测)

- **实测数据**:RTX 4060 (8GB) 上 Qwen2.5-1.5B QLoRA,峰值 VRAM 6.2-8.1GB,长序列(2048 token)+ PagedAdamW 可跑;吞吐 360-628 tok/s。**结论:16GB 显存可轻松跑 7B 级 QLoRA,8B 级需谨慎、32B 需要 24GB。**【论文/工程实证】** https://arxiv.org/pdf/2509.12229
- **参考换算**:QLoRA 4-bit 在 24GB(RTX 4090)可微调 33B,单 T4 可微调 7B;7B LoRA 成本约 $5-50。**【工程实证】** https://meta-intelligence.tech/en/insight-lora-finetuning
- **数据需求(风格微调)**:全量风格微调最小可行语料 **2-3 万词,5-10 万词为强匹配**;但注意这些是"voice 匹配"经验值,文学风格微调需单一作者/单一作品的高质量语料。**【主观经验】** https://socialnexis.com/guides/ai-voice-sample-requirements
- **文学风格 LoRA 有论文**:WriterAgent + WriterLoRA (Findings ACL 2026)在《哈利波特》《红楼梦》上做模仿式小说生成,用分层 LoRA(冻结共享 A 矩阵、任务专属 B 矩阵)+ 课程学习(语言风格→世界观→情节→润色),显著优于 Multi-LoRA 基线。**关键技巧:冻结 A 矩阵保预训练文风。**【论文】** https://aclanthology.org/2026.findings-acl.968.pdf
- **StyleAdaptedLM (arXiv 2507.18294)**:LoRA 在**非结构化风格语料**上训(无指令-回复对),再与指令模型合并,无需配对数据即可注入品牌/作者文风。**对"只有小说正文、没有成对指令数据"的场景直接适用。**【论文】** https://arxiv.org/pdf/2507.18294

### 4.2 DPO / 风格偏好对齐

- **DPO 基础**:标准后训练对齐方法,省去奖励模型与 RL;β 控制对齐强度。**【论文】** https://arxiv.org/abs/2305.18290
- **风格对齐的 DPO/GRPO 实例**:GRPO 作者风格微调 (CoNLL 2026)——训练"风格相似度裁判"(作者验证监督微调 sentence-transformer,校准到 [0,1] 奖励),再用 GRPO 微调 8B 生成器,四位经典作家(马克·吐温/简·奥斯汀/狄更斯/哈代)平均风格分 0.893,超越开源基线;避免了 DPO 需要 accept/reject 监督的问题。**关键:风格分可被做成可优化标量。**【论文】** https://aclanthology.org/2026.conll-main.31.pdf
- **务实判断**:DPO/GRPO 需要偏好对/奖励裁判,数据与算力成本对个人项目偏高;**优先级低于"好 prompt + 样本注入 + 生成后校验"**。有论文支撑但门槛高。

### 4.3 风格 token / 风格向量 / in-context style transfer

- **Style Vectors (EACL 2024 Findings)**:在隐藏层激活上叠加风格向量(激活工程),无需训练即可连续可调地控制风格强度;激活式风格向量(聚合目标风格句子的层激活)优于训练式。**轻量、可调,是"风格旋钮"路线。**【论文】** https://aclanthology.org/2024.findings-eacl.52.pdf
- **sNeuron-TST (arXiv 2410.00593)**:识别风格专属神经元并关闭源风格神经元 + 对比解码,6 个基准上有效;发现**风格相关层集中在后几层**。**【论文】** https://arxiv.org/html/2410.00593v1
- **n-gram 风格先验 logit 注入 (arXiv 2601.16224)**:冻结模型 + n-gram 先验注入 logit,**结论是"脆弱":仅在极窄 λ 区间(Don Quixote, λ=0.1)改善,其余场景被 prompt 和 LoRA 稳定支配**。**这条路线不推荐。**【论文】** https://arxiv.org/html/2601.16224
- **软提示适配 (PERSOMA, arXiv 2408.00960)**:把用户历史压缩成软提示 token 注入冻结 LLM,参数高效;但面向个性化对话,迁移到文风需适配。**【论文】** https://arxiv.org/html/2408.00960

> **落地判断**:风格向量/激活工程是"低数据、免训练"的诱人路线,但当前证据显示其脆弱且被 prompt/LoRA 支配;建议作为**实验性探索**,不作为 story-engine 的主路径。

---

## 5. 网文连载的工程实践

### 5.1 专业写作工具如何维持长篇一致性

三款主流工具的一致性机制高度趋同,都围绕"**故事圣经(Story Bible/Codex)+ 关键词触发的上下文注入 + (部分)生成后校验**":

| 工具 | 一致性机制 | 是否自动抽取 | 是否生成后校验 | 来源 |
|---|---|---|---|---|
| Sudowrite | Story Bible(角色/设定/文风样本)+ Style Examples 注入真实文段(非风格描述)+ Rewrite 微调 | 手动 | 无(靠人工编辑) | https://sudowrite.com/blog/ai-voice-matching |
| Novelcrafter | Codex(角色/地点/物品/关系词条 wiki)+ 场景级自动引用;beat-to-scene 工作流 | 手动维护,自动检测提及 | 无 | https://fast.io/resources/best-ai-for-writing-books-2026 |
| NovelAI | Lorebook 关键词触发注入 + 专有小说模型(Kayra 13B/Erato 70B) | 手动 | 无(约 15 章后一致性开始退化) | https://novarrium.com/blog/best-sudowrite-alternatives-novel-writers-2026 |
| Novarrium | Logic-Locking:每章后自动抽取事实 + 相关度加权注入 + 输出校验 | **自动** | **有**(矛盾即标记) | 同上 |

- **关键共识**(多篇评测一致):**手动 Story Bible 是被动引用,AI 可以读但不强制遵循,约 15-25 章后矛盾开始渗入**;自动事实抽取 + 生成后校验是拉开差距的分水岭。**【工程实证/主观经验】**
- **文风样本 vs 风格描述**(Sudowrite 官方):"prompt 是描述,样本是实物;描述会丢信息。"Style Examples 注入真实文段是 voice 匹配的核心杠杆,5 段跨场景样本即可,越多越好。**【工程实证】** https://sudowrite.com/blog/ai-voice-matching
- **角色语音**:Sudowrite 角色卡建议每个角色 3+ 段对话样本(而非"性格形容词列表"),才能教出语气/词汇/态度。**【主观经验】** https://sudowrite.com/blog/how-to-develop-fictional-characters-with-ai-sudowrites-characters-feature

### 5.2 中文网文作者/工作室的公开经验

- **AI 味/文风适配是中文网文头号痛点**:CSDN 网文编辑实测称"90% 通用模型生成文字带翻译腔",垂直工具因语料含起点/番茄热门作品而更"对味";**"AI 辅助+人工优化"过稿率 67% vs AI 纯生成不足 3%**。**【主观经验】** https://bbs.csdn.net/weixin_29061509/article/details/100194364
- **上下文记忆 + 自然文风双难题**:百度智能云文章指出 70% 以上作者写 50 万字以上需手动维护设定文档,平均每 3 万字回溯检查设定;AI 痕迹段落跳出率比人工高 42%。**【主观经验/行业数据】** https://intl.cloud.baidu.com/zh/article/8803271
- **"把声音当规格文档,不当感觉"**:Jenova 中文调研引作者经验——"六行硬性约束,其中至少两条'绝不'规则,产生的对话辨识度远高于三段赞美性角色描述";并建议"把每次生成限定为单个节拍、明确哪些必须保持未解决"。**与结构化约束(第 3 节)互相印证。**【主观经验】** https://www.jenova.ai/zh/resources/do-general-ai-chatbots-or-specialized-ai-writing-assistants-give-you-more-control-over-plot-character-and-voice
- **中文开源实践**:马良写作 AINoval(多智能体网文平台,30 万字连载)采用"三级大纲 + 知识图谱一致性 + 番茄小说拆书建库";提示词可由用户配置原生发送。**与"知识图谱做实体一致性"呼应。**【工程实践】** https://github.com/Deng-m1/MaliangAINovalWriter
- **去 AI 味提示词**:知乎/Threads 流传的"去 AI 味"技巧(避免晦涩词汇、口语化、禁用"值得注意的是"等)与 story-engine 现有"精修去 AI 味"一致,但**属提示词层面,无法防止第 100 章回归**——需配合硬约束/禁词表。**【主观经验】** https://zhuanlan.zhihu.com/p/692546989

---

## 6. 一致性检查的自动化

### 6.1 人物/设定/文风三类不一致的检测

- **ConStory-Bench / ConStory-Checker**(最直接可借鉴的基准与检测器):5 大类 19 子类——**时间线与情节逻辑**(绝对时间/时长/同时性/无因之果/因果违例/弃置情节)、**角色刻画**(记忆/知识/技能波动/遗忘能力)、**世界观设定**(核心规则/社会规范/地理)、**事实与细节**(外貌/命名/数量)、**叙事与文风**(视角混淆/语气不一致/文风偏移)。检测器用 LLM-as-judge 输出结构化 JSON(fact_quote/location/contradiction_pair/error_category),**每条判断都锚定原文引文**。开源:https://github.com/Picrew/ConStory-Bench 。**【论文+开源】** https://arxiv.org/html/2603.05890v1
- **ConWriter**(训练无关的一致性控制框架):场景级增量写作 + 双记忆(静态故事承诺 vs 动态事件/实体/关系/时间线)+ 符号状态转移校验 + 不确定性风险监控 + 句级局部修补;**在生成过程中就控制一致性,而非事后**。**【论文】** https://arxiv.org/abs/2608.05169
- **NstAgent**(Narrative State Tracking Agent):训练无关,跟踪结构化叙事状态(角色/过去事件/未来需求),10K-100K 词故事上一致性与质量不随长度退化。**【论文】** https://arxiv.org/html/2609.35759
- **Awesome-Story-Generation**:故事生成论文清单,含 FlawedFictions(合成剧情漏洞测 LLM 叙事推理)等资源入口。**【开源索引】** https://github.com/yingpengma/Awesome-Story-Generation
- **AI 味/文风检测**:HART (arXiv 2503.00258)把检测解耦成"内容 vs 语言表达"二维,表达维度捕获风格特征;AI 文本检测研究确认 AI 文本有更多名词/动词/介词/助词及连接词。**对"AI 味词汇回归"提供了可自动化的检测特征依据。**【论文】** https://arxiv.org/abs/2503.00258 ; https://arxiv.org/pdf/2601.03812

### 6.2 对 story-engine 现有能力的映射

- 项目已有 `style/analyzer.py`(LLM 文风一致性)与 `fixed_tasks.check_name_consistency`(角色/地名正则)——**正则只能查命名一致性,查不了视角/语气/文风漂移**。
- 建议:新增文风一致性检测器,直接复用 ConStory-Checker 的"叙事与文风"类检测 prompt(视角混淆/语气不一致/文风偏移),并让 14 维量化特征与"目标画像"对比生成漂移告警(句长分布 KL 距离、对话占比偏移、虚词比例偏移、禁用词命中数)。

---

## 7. 证据等级总表(核心来源)

| 主题 | 关键来源 | 等级 |
|---|---|---|
| 语义漂移/长文退化 | aclanthology.org/2024.naacl-long.202 | 论文 |
| 长度崩塌(>2000词) | aclanthology.org/2026.acl-long.911.pdf | 论文 |
| 文风漂移=独立机制(5类19子类) | arxiv.org/html/2603.05890v1 | 论文+开源 |
| 上下文长度本身有害(临界阈值) | arxiv.org/abs/2601.15300 | 论文 |
| 计划跟随度随章节衰减 | arxiv.org/html/2605.17064 | 论文 |
| 分布漂移+灾难性遗忘 | aclanthology.org/2025.acl-long.524.pdf | 论文 |
| few-shot 2-5 例平台期 | prompthub.us/blog/the-few-shot-prompting-guide | 主观+引论文 |
| many-shot 约125例见顶 | arxiv.org/pdf/2404.11018 | 论文 |
| 动态检索 > 固定 few-shot (k=10, T=0) | dx.plos.org/10.1371/journal.pone.0354688 | 论文/工程实证 |
| RAG 维风格一致性 | arxiv.org/html/2602.15013v1 | 论文 |
| RAD 奖励增强解码 | aclanthology.org/2023.emnlp-main.721 | 论文 |
| COLD/MUCOCO/INSTRUCTCTG/动态多奖励 | (见第3节) | 论文 |
| 生成-反思-修订框架 | arxiv.org/pdf/2603.15061 | 论文 |
| BoN 最优性/RBoN 防奖励攻击 | (见第3.3节) | 论文 |
| QLoRA 8GB 实测 | arxiv.org/pdf/2509.12229 | 论文/工程实证 |
| 风格微调语料量(2-5万词) | socialnexis.com/guides/ai-voice-sample-requirements | 主观经验 |
| WriterLoRA(冻结A矩阵) | aclanthology.org/2026.findings-acl.968.pdf | 论文 |
| StyleAdaptedLM(非结构化语料LoRA) | arxiv.org/pdf/2507.18294 | 论文 |
| GRPO 风格对齐(风格裁判+8B) | aclanthology.org/2026.conll-main.31.pdf | 论文 |
| 风格向量/神经元/n-gram注入(脆弱) | aclanthology.org/2024.findings-eacl.52.pdf ; arxiv.org/html/2410.00593v1 ; arxiv.org/html/2601.16224 | 论文 |
| Sudowrite 文风样本注入 | sudowrite.com/blog/ai-voice-matching | 工程实证 |
| Novelcrafter/NovelAI/Novarrium 机制 | fast.io / novarrium.com 评测 | 工程实证/主观 |
| 中文网文痛点与经验 | bbs.csdn.net / intl.cloud.baidu.com / jenova.ai | 主观经验 |
| ConStory-Checker 开源 | github.com/Picrew/ConStory-Bench | 论文+开源 |
| ConWriter/NstAgent | arxiv.org/abs/2608.05169 ; arxiv.org/html/2609.35759 | 论文 |

---

## 8. 对 story-engine 的落地建议(优先级排序)

**P0(低成本、立即做)**
1. 禁用词表 + AI 味词表做成**生成后硬过滤/告警**(把现有"精修去 AI 味"从一次性提示词升级为可执行规则)。
2. 14 维量化特征做成**章节级自动检测**:句长分布、对话占比、虚词比例与"目标画像"对比,超阈值告警 + 触发重写。
3. 风格样本注入从"固定一段"改为**按当前章节场景的 RAG 检索注入**(场景类型标签 + 特征向量混合检索,top-k 段,低温度)。

**P1(有论文支撑、投入中等)**
4. **best-of-n 按风格分 rerank**(n=3-5):用 14 维特征算"与目标画像相似度"打分选优,加正则防奖励攻击。
5. 文风一致性检测器:复用 ConStory-Checker 的"叙事与文风"类 prompt(视角/语气/文风偏移),并入现有 consistency 检查。

**P2(数据攒够再做)**
6. 风格 LoRA:攒够 3 万字以上单一作品高质量语料后,用 StyleAdaptedLM 思路(非结构化语料 LoRA + 合并),16GB 显存可行;冻结 A 矩阵技巧借鉴 WriterLoRA。

**暂缓/实验性**
7. DPO/GRPO 风格对齐:成本与数据门槛高,有论文但非个人项目首选。
8. 风格向量/激活工程/n-gram 注入:轻量但脆弱,被 prompt 和 LoRA 支配,仅作实验。

---

*本报告所有 URL 均来自检索结果原文,已在对应条目标注;标注【主观经验】的结论无严格实验支撑,仅供决策参考,不构成科学断言。*
