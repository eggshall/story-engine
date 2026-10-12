## [Unreleased] — 进行中（2026-09 ~ 2026-10，P7 节点 N0–N9）

> 本节记录 P7 里程碑的节点级交付（节点流程：①REO 写失败测试 → ②实现 → ③全绿 → ④E2E →
> ⑤opencode 评审归档 `docs/design/reviews/` → ⑥逐条修复 → ⑦一次节点一次提交）。
> 尚未发版：**N7（章摘要+SQLite）未开始，N8 的世界观部分未完成**。

### 节点交付

- ✅ **N0/N1/N2** — 项目骨架、鉴权与 SSE 契约、假上游 E2E 工具链
  （SSE 三事件 `token`/`done`/`error`；**单一 done**；`error` 不落盘）
- ✅ **N3** — config schema 放行 `thinking`/`task`：配置不再被 `model_dump()` **静默剥离**
- ✅ **N4a** — 槽位装配器 v0：`Slot` 注册表 + 注入清单 + **两级预算**（槽位 `max_tokens` + 全局 `budget_tokens`）
- ✅ **N4b** — 真实数据源 + `/api/generate/chapter/v2`；注入清单随 SSE `done` 载荷下发；
  作者手写件 `mainline.md` / `recap.md` / `beats/ch_XXXX.md`
- ✅ **N5** — A 类校验器 5 条（确定性、不调模型）+ `POST /api/check/chapter`；
  两条铁律：**无基线返回 `skipped` 不猜**、**别把正常中文当套话**
- ✅ **N6** — 审稿页（三栏 + 带指令重写）+ 注入清单落盘 `GET /api/check/manifest`
- 🚧 **N8**（部分）— 项目空间：**角色卡按小说绑定**（全局目录退役）+ 素材库（纯复制语义）
  + `/api/novel/{id}/characters` 系列 + 前端接上
- 🚧 **N8 世界观切片** — **世界观（lore）按书绑定** + 装配器新增 `lore` 槽位：
  - 全局 `data/lore/` 退役：`list/load/save/delete_lorebook` 全部带 `novel_id`，
    真源 `novel.json` 的 `lorebooks`，镜像 `lore/`（**只读导出**，与 `characters/` 的非对称是刻意的）
  - 触发引擎改**纯函数**（接收设定集字典，不读盘）；`engine._build_world_context(chapter_number)`
    只用本书 `lorebooks`，章号**必填无默认值**
  - 装配器挂 `lore` 槽位（走既有 `extra_providers`，**不改 `build_novel_builder` 签名**）：
    走 v2 路径从此真的注入世界观；触发源只用**紧邻的前一章**，且与 `chapter_tail` 统一口径
  - `_write_files` 对 `lore/` 改为「先清空再重建」（原为只写不清空，是三个镜像目录里唯一的例外）
  - 接口：`/api/novel/{id}/lorebooks`（GET/POST/PUT/DELETE）+ 素材库 `/api/library/lorebooks`、
    `.../{name}/to-library`、`.../{name}/import`；请求体 `extra="forbid"`（拼错字段 422，不静默丢弃），
    **改名时目标名已被占用会显式失败**（N9 评审 P1-1 那类「删旧建新静默吃掉另一条」的守卫）
  - 评审 `docs/design/reviews/N8-REVIEW.md`（**无 P0**；2 个 P1 + 8 个 P2 全处置，
    含「命中超上限静默丢弃」「`lore` 反向依赖 `characters`」「两套上一章口径」）
  - ⬜ 未做：`WorldView` 设定集区块（现状是页面内写死的假数据）、世界观浏览器 E2E
- 🐛 **修复（N8 缺陷修复切片）** — **镜像文件名身份碰撞 = 静默丢卡**：
  - `_slug` 有损（`"A B"`/`"A_B"`/`"a/b"` 都 → `A_B`），两个身份写同一个镜像文件、后写覆盖先写；
    而 `load_novel` 会**回读** `characters/`，于是先建的那张卡在界面上直接消失（真源里还在）
  - 新增 `novel_storage._mirror_file_names()`：不撞名仍用 slug（保持人类可读），同 slug 的多个身份
    追加「名字的」短 hash（与写入顺序无关、重复保存同名）；并做**全局唯一性自检**，
    防「有人把名字起成 `slug-短hash`」的构造性碰撞（评审实测复现）
  - **`load_novel` 回读 `characters/` 从整体替换改为合并**：残缺镜像不再能吞掉真源里的条目 ——
    否则对升级前已被损坏的书，一次 load→save 就把**仍可恢复**的那张卡永久抹掉
  - `cli.py` 的 `character example` / `lore example` 不再打印按名字猜的路径（撞名时会不符）
  - 评审 `docs/design/reviews/N8-REVIEW.md` 第三轮（**无 P0**；1 个 P1 + 3 个 P2 全处置）
- ✅ **N8 第四切片** — **世界观页（`/world`）接后端** + **地图 404 修复**：
  - 「条目」tab 从**页面内写死的数组**改为走 `/api/novel/{id}/lorebooks`；左侧分类 = 本书**设定集**动态列表
    （原写死的 地理/历史/魔法/势力/人物 退役，「类型」维度留待方案 B）
  - 选书复用角色卡页的三级优先（写作页当前那本 → `story_last_novel` → 最近更新的那本）
  - 地图 tab 原先打 `/novel/current/map`，而服务端**没有 current 这个概念** → 404 被空 `catch` 静默吞
    （**读写都是坏的**）→ 改为按书 `GET/POST /api/novel/{id}/map`，失败**报出来**
  - 编辑条目**以原条目为底合并**写回，杜绝后端字段（`category`/`position`）被默认值打回（评审 P0-1）；
    编辑态禁改设定集名/条目 ID；删条目与删设定集都要确认，删「最后一条」单独说清会连带删设定集
  - 地图图片只在本机预览、**未上传**，界面写清；`blob:` 地址不写进服务端
  - 评审 `docs/design/reviews/N8-REVIEW.md` 第四轮（**1 个 P0 + 3 个 P1 + 9 个 P2 全处置**）
  - E2E：`e2e/worldview.e2e.ts`（落盘 → 刷新仍在 → 换书看不到 → 地图读写 → 删除后不复活）
  - ⬜ 仍未做：关键词触发预览（后端触发引擎已是纯函数，缺预览入口）；Element Plus `zh-CN` locale 未注册
- ✅ **条目「类型」**（第五切片）—— 暴露**早已存在**的 `LorebookEntry.category`：
  - 后端新增 `lore/categories.py`（`DEFAULT_CATEGORY`/`CATEGORY_LABELS`/`PLACE_CATEGORIES`）作为**取值唯一定义处**，
    `api/routes/novel.py` 的地名校验改用它（原先行内元组 + `hasattr`）
  - 前端条目表单加「类型」下拉（地点/物品/规则/势力/世界观/其他）、卡片显示类型、条目区加类型过滤行
  - **修掉一个真 bug**：编辑弹窗 `v-if="editingKey"` 是未定义变量（上一轮 P2-6 漏改）
    → 「删除条目」按钮**永远不显示**，等于弹窗里删不掉条目
  - 澄清一个流传的误判：**不需要动数据模型**，字段与接口早就支持，缺的只是 UI
  - 钉桩两层：后端 `TestCategoryVocabulary`（UI 写的值 = 校验认的值）+ E2E 第 4b 步真 HTTP 跨层
  - 评审 `docs/design/reviews/N8-REVIEW.md` 第五轮（**无 P0；2 个 P1 + 5 个 P2 全处置**），
    其中 P1-1 揭穿了我"取值唯一定义处"的假保障 → 补**跨语言契约测试**（读 `.vue` 源码比对，
    已用 `/tmp/verify_drift.py` 证明 4 类分叉都能抓到）；P1-2 修掉「卡片显示其他、点其他又找不到」
    的自相矛盾（未知类型原样显示 + 过滤行动态列出数据里出现的类型）
  - 决定**不采用**"每本书预置 5 个设定集"那条替代路（会让作者不能自定义分组，而它换来的"零模型变更"本来就成立）
- ✅ **N9** — **伏笔账本 + 注入 + 校验（最小版）**：`PlotThread` + `Novel.threads`
  （真源 `novel.json`，镜像 `threads/`）；装配器 `threads` 槽位（`priority=SUMMARIES`）；
  校验新增 `dangling_threads` / `unknown_payoff`；`/api/novel/{id}/threads` 5 个端点
  （`APIModel` 兼容 camelCase + `extra="forbid"`）
  - 修掉评审实测的**静默覆盖**缺陷：`PUT` 改 id 曾能把另一条伏笔静默改写 → 目标已存在即失败
  - **不改装配器签名、不改 SSE 契约、不引入检索**（走既有 `extra_providers` 口子）
- ⬜ **N7** — 章摘要 + SQLite + 离线串行队列（未开始）

### 质量基线

- 后端：**1013 passed / 3 skipped**，覆盖率 **94.49%**（门禁 75%）；ruff / mypy（69 文件）全绿
- 前端：vitest **124 passed / 15 files**；vue-tsc 0；vite build ✓
- 浏览器 E2E：`e2e/` **7 passed**（n0×4 鉴权 / n2 SSE / n6 审稿 / worldview 世界观页）
- 评审：`docs/design/reviews/N0–N6、N8、N9-REVIEW.md`（各节点均"需补充/修复后通过 → 已逐条处置"；
  N8 含五轮切片评审）
- E2E：后端真实 HTTP 到 `tests/e2e/`（N1/N2/N3/N4b/N5/N6/N8/N9）；前端真实浏览器到 `e2e/`

## [0.8.0] — 2026-08-03

### 新增
- 🎭 **P6 文风画像全库批量生成** — 70 本语料全覆盖 (2405 万字)
  - 模型选型实测: gm4:latest (14GB) 胜出 — 14 维扁平 JSON 稳定输出; qwen3.5:9b-q6-fixed 嵌套结构/偶发空输出, 不适用
  - 每本画像: 14 维量化特征 (词汇水平/平均句长/句长变化/虚词使用/对话比例/叙事视角/排比对仗/疑问句比例/比喻/拟人/引用用典/描写特点/平均段落长度 + 整体风格总结) 含 1-10 评分与细节说明
  - 风格描述 (一句话, 可注入写作 prompt) + 2000 字样本段落
  - 首批 12 本 (每题材 3 代表作) → 第二批 58 本, 分批后台生成
  - 画像存储: `<数据根目录>/style_profiles/style_profiles.db` (SQLite)
  - 题材覆盖: 严肃文学 41 / 幽默讽刺 9 / 悲伤文学 7 / 流行文学 13

### 修复
- 🔧 批量脚本 JSON 解析: 清理全部 `\x00-\x1f` 未转义控制字符 (JSON 字符串内字面换行/制表符非法导致模型偶发输出解析失败)
- 🐛 **P5+ 文风注入链路打通**: 发现并修复 camelCase 字段丢失 bug
  - 前端传 `stylePrompt`/`profileId` (camelCase)，后端 Pydantic 字段为 snake_case，默认不转换 → **文风注入从未生效**（选中文风生成时后端收到空字符串）
  - 修复: `schemas.py` 新增 `APIModel` 基类 (`alias_generator=to_camel` + `populate_by_name`)，同时兼容两种命名
  - 升级: `/generate/chat` 与 `/api/style/generate` 支持 `profile_id` 完整注入

### 新增
- 🎯 **文风完整注入 (P5+)**: 生成时不再只用一句话风格总结，而是三段式完整画像
  - `StyleAnalyzer.render_style_block(profile)`: 【风格总结】+【量化特征】(14维带评分)+【原文示例】(800字 few-shot 锚点)
  - 前端写作模式自动携带 `profileId`（优先）与 `stylePrompt`（兜底）
  - 实测: 红楼梦块 1054 字 vs 全民魔女1994 块 1053 字，风格特征对比鲜明

### 脚本
- `scripts/p6_style_batch.py` — 批量文风分析 (支持 limit/offset/idx: 指定书目)
- `scripts/p6_style_import.py` — 结果入库 (按 source_work 去重更新)

### 测试统计
```text
后端: 234 passed
构建: ✅ 通过
```

## [0.7.0] — 2026-08-02

### 新增
- 📚 **P6 数据采集管线完成** — 公版中文小说采集与清洗 Pipeline
  - 数据源: Gutenberg 中文公版库 (444 本) 国内直连采集
  - 存储: 数据根目录 (raw/原始, corpus/语料, imports/导入区, meta/索引)
  - 首批 35 本入库 (1313 万字)，覆盖四大题材: 严肃文学 7 / 幽默讽刺 9 / 悲伤文学 7 / 流行文学 12
  - 清洗管线: Gutenberg 样板剥离(新版/老式) → 中文起点校验 → 空白规范化 → 繁转简 (OpenCC t2s)
  - 本地导入通道: imports/ 丢入 txt/epub 自动识别编码并清洗入库
    - 子目录=一本书, 自动合并多分卷 (如《全民魔女1994》4卷 455万字合并为1本)
    - 书名清洗 + 导入后源文件归档到 imports/done/
  - 新模块: `src/story_engine/data_pipeline/` (catalog/fetcher/cleaner/importer/index/pipeline)
  - CLI: `python -m story_engine.data_pipeline.pipeline --collect/--imports/--stats`

### 测试统计
```text
后端: 232 passed (新增 10 个数据管线测试)
构建: ✅ 通过
```

## [0.6.1] — 2026-08-01

### 新增
- 🎨 **P5 文风注入生成流程打通** — 写作模式下，右侧面板选中的文风画像自动注入 AI 对话生成
  - 后端 `/api/generate/chat` 新增 `style_prompt` 字段，非空时注入 system prompt
  - 前端 AiChatPanel 在「专业写作」模式自动携带已选文风的 stylePrompt
  - 闲聊模式不注入，保持双模式分工（写作=DeepSeek+文风 / 闲聊=本地模型）

### 测试统计
```text
后端: 224 passed (新增 2 个文风注入测试)
前端:  68 passed (新增 3 个 AiChatPanel 文风注入测试)
构建: ✅ vite build 成功
```

## [0.6.0] — 2026-07-20

### 新增
- 🆕 **文风数据库系统** — 基于本地模型 (Qwen3.5-9B) 的小说文风分析与管理
  - SQLite 存储文风画像：量化特征 + 自然语言风格描述 + 样本段落
  - 18 维文风特征体系：词汇水平、句长、对话比例、叙事视角、修辞手法等
- 🆕 **文风分析 API** — `POST /api/style/analyze` 调用本地模型提取文风特征
- 🆕 **文风一致性检查** — `POST /api/style/check` 检查文本与目标文风匹配度
- 🆕 **文风 CRUD** — 创建/读取/搜索/删除文风画像 (`/api/style/profiles`)
- 🆕 **文风注入生成** — `POST /api/style/generate` 带文风的 SSE 流式生成
- 🆕 **前端文风面板** — WritingView 右侧新增「文风」标签页
  - 文风列表 + 搜索/题材筛选 + 删除
  - 选中文风后高亮显示
  - 「分析当前文本」按钮 → 调用本地模型分析并自动保存
- 🆕 **StylePanel 组件** — 独立的文风管理 Vue 组件

### 技术栈
- 后端: FastAPI + SQLite + Pydantic V2
- 前端: Vue 3 + Pinia + Element Plus
- 本地模型: Qwen3.5-9B (Q6, 7.5GB) via Ollama API

### 测试统计
```text
后端: 222 passed (新增 20 个文风测试)
前端:  65 passed (全部通过)
构建: ✅ vite build 成功
```
