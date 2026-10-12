# AI 小说生成系统 — 故事引擎 (Story Engine)
## Phase 2 — Web 前端 + 后端加固

> 参考设计：91Writing (Vue3+ElementPlus)、SillyTavern、Obsidian Graph View、inkos

---

## 参考项目与技术选型

| 参考项目 | 借鉴点 |
|----------|--------|
| [91Writing](https://github.com/ponysb/91Writing) | Vue3+ElementPlus 架构、Chat 式写作界面、模型切换 |
| [SillyTavern](https://github.com/SillyTavern/SillyTavern) | 角色卡编辑、Lorebook 管理、世界观注入 |
| [Obsidian](https://obsidian.md/) | Graph View 人物关系图、节点进度、Markdown 原生 |
| [inkos](https://github.com/Narcooo/inkos) | Agent 多角色协作、写作管线 |

**技术栈：**
```
前端：Vue 3 + TypeScript + Element Plus + ECharts/D3-force
后端：FastAPI (async, SSE 流式) + Pydantic
通信：REST API + SSE (Server-Sent Events) 流式输出
存储：JSON 文件 (当前) + 可选 SQLite 升级
```

---

## 任务清单

### Phase 2.1 — 后端加固与 API 层 (优先级: P0) ✅

- [x] **修复本地模型超时问题**
  - qwen3.5-9b-q6 首次加载需要预热
  - ModelRouter 增加 connect_timeout/read_timeout 可配
  - 本地模型失败时明确报错而非静默 fallback

- [x] **重构：拆为后端 API 服务**
  - 创建 `src/story_engine/api/` 目录
  - FastAPI 应用入口 `src/story_engine/api/main.py`
  - 基础路由结构：
    ```
    POST /api/novel               — 创建/加载小说
    GET  /api/novel/{id}          — 获取小说详情
    POST /api/generate/outline    — 生成章节大纲 (流式 SSE)
    POST /api/generate/chapter    — 生成章节内容 (流式 SSE)
    GET  /api/models              — 列出可用模型
    POST /api/chat                — 自由对话 (流式 SSE)
    ```

- [x] **SSE 流式输出支持**
  - ModelRouter 增加 stream_chat 方法
  - FastAPI SSE endpoint 转发 token 流到前端

- [x] **MD 格式导出/保存**
  - `POST /api/export/md` — 将小说导出为 Markdown
  - 支持指定保存目录 (用户可配置)
  - 单章导出 / 全书合并导出

- [x] **资料检索接口**
  - `POST /api/research` — 接收问题，调用联网搜索，保存结果
  - 搜索结果自动存入 Lorebook 或参考资料文件夹

### Phase 2.2 — 前端核心 (优先级: P0)

- [x] **项目初始化**
  - Vue 3 + TypeScript + Vite + Element Plus
  - 路由结构：`/writing` `/characters` `/world` `/outline` `/settings`
  - Pinia 状态管理 (novel, characters, settings, chat)

- [x] **写作界面 (`/writing`)**
  - 左侧：小说目录树 + 章节列表
  - 中间：Markdown 编辑器 (tui.editor 或 vditor)
  - 右侧：AI 对话面板，输入想法/指令
  - 底部状态栏：当前模型、字数、token 消耗
  - 模型切换下拉菜单 (deepseek-pro / deepseek-flash / qwen3.5-local / claude)

- [x] **流式展示**
  - AI 回复实时逐 token 展示 (SSE)
  - 打字机效果
  - 可随时中断生成

- [x] **角色卡界面 (`/characters`)**
  - 角色列表 (卡片式布局)
  - 编辑面板：名称、外貌、性格、背景、出场描写
  - 角色关系编辑 (拖拽连线或表单)
  - 多角色切换查看

- [x] **大纲界面 (`/outline`)**
  - 左侧：章节大纲树 (折叠/展开)
  - 右侧：当前章节详情 (标题/概要/节拍/场景列表)
  - 拖拽排序调整章节顺序
  - "生成大纲" 按钮 → 触发 AI 生成

### Phase 2.3 — 世界观与可视化 (优先级: P1)

- [x] **世界观管理 (`/world`)**
  - Lorebook 条目列表 + 编辑
  - 关键词触发预览 (输入文本，高亮匹配关键词)
  - 分类筛选 (地理/历史/魔法/势力/人物)

- [x] **人物关系图谱**
  - ECharts 力导向图，节点 = 角色，连线 = 关系类型
  - 点击节点查看角色卡片
  - 筛选/缩放/拖拽

- [x] **世界地图**
  - 支持用户上传地图图片 + 标注地点
  - 地点关联 Lorebook 条目

- [x] **写作进度面板**
  - 已完成章节 / 总计划章节 (可调节)
  - 字数统计 (日/周/月/总)
  - 当前阶段标记 / 目标字数设定

### Phase 2.4 — 资料检索与 AI 辅助 (优先级: P1)

- [x] **联网资料检索面板**
  - 输入问题 → 调用检索 → 结果摘要展示
  - 支持保存到项目资料库
  - 参考资料列表 (来源链接 + 摘要)

- [x] **写作辅助工具**
  - 选中文段 → 右键菜单：润色/扩写/缩写 ✅
  - 去AI味一键清理 ✅ (工具栏按钮 + SSE 流式整章处理)
  - 节奏分析/风格一致性检查 ✅ (工具栏按钮 + 后端分析端点)

### Phase 2.5 — 设置与管理 (优先级: P2)

- [x] **模型管理界面**
  - 查看已配模型、切换启用/禁用
  - 修改 API Key、Base URL、参数 (temperature/max_tokens)
  - 测试连接按钮

- [x] **项目导出**
  - Markdown 单章 / 全书导出
  - JSON 项目文件导出/导入
  - 自定义保存目录 (支持 Windows/MAC/Linux 路径)

- [x] **项目设置**
  - 小说元信息 (标题/作者/类型/简介)
  - 默认写作参数
  - 保存目录配置

---

## 项目目录结构 (新增)

```
story-engine/
├── src/
│   ├── story_engine/
│   ├── ... (现有后端代码)
│   ├── style/                    # 新增：文风系统
│   │   ├── __init__.py
│   │   ├── db.py                 # SQLite 数据库
│   │   ├── analyzer.py           # 本地模型文风分析
│   │   └── schemas.py            # Pydantic 请求/响应
│   └── api/                     # 新增：FastAPI 后端
│   │       ├── __init__.py
│   │       ├── main.py           # FastAPI 应用入口
│   │       ├── routes/
│   │       │   ├── novel.py
│   │       │   ├── generate.py
│   │       │   ├── models.py
│   │       │   ├── research.py
│   │       │   ├── export.py
│   │       │   └── style.py      # 新增：文风 API
│   │       ├── schemas.py        # Pydantic request/response
│   │       └── sse.py            # SSE 工具
│   └── frontend/                 # 新增：Vue3 前端
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json
│       ├── index.html
│       └── src/
│           ├── App.vue
│           ├── router/
│           ├── stores/
│           ├── views/
│           │   ├── WritingView.vue
│           │   ├── CharactersView.vue
│           │   ├── WorldView.vue
│           │   ├── OutlineView.vue
│           │   └── SettingsView.vue
│           ├── components/
│           │   ├── NovelTree.vue
│           │   ├── CharacterCard.vue
│           │   ├── RelationshipGraph.vue
│           │   ├── WorldMap.vue
│           │   ├── AiChatPanel.vue
│           │   └── ProgressPanel.vue
│           └── utils/
│               └── api.ts
├── config/config.yaml
├── data/                         # 数据存储
│   ├── novels/
│   ├── characters/
│   ├── lore/
│   ├── research/                 # 新增：资料检索结果
│   └── exports/                  # 新增：MD 导出目录
└── pyproject.toml
```

---

## 开发顺序

```
第一阶段 (P0) —— 核心管线
  API 层搭建 → SSE 流式 → 写作界面 → 大纲界面 → 角色卡界面

第二阶段 (P1) —— 可视化扩展
  人物关系图 → 世界观管理 → 资料检索 → 写作辅助工具

第三阶段 (P2) —— 完善与设置
  模型管理 → 导出功能 → 项目设置 → 世界地图

第四阶段 (P3) —— 文风系统
  [x] 文风数据库 + 量化特征模型 (SQLite + FeatureKeys)
  [x] 后端文风 CRUD API + 分析/一致性检查 API
  [x] 文风注入生成 API
  [x] 前端文风面板 (StylePanel + Pinia store)
  [x] 文风注入生成流程 (P5) — 写作模式自动携带已选文风 (v0.6.1)
  [x] 公版中文小说数据采集与清洗 Pipeline (P6) — v0.7.0 数据源: Gutenberg 中文公版库 (444本) 直连采集; 数据根目录存储 (STORY_ENGINE_DATA_ROOT); 35本首批入库 (1316万字, 覆盖严肃/幽默讽刺/悲伤/流行四大题材); 本地导入通道 (txt/epub 自动清洗)
  [x] 文风画像自动批量生成 (P6) — gm4 本地模型 70 本全库画像 (v0.8.0)
  [ ] 文风 vs 题材匹配推荐
```

---

| 当前项目状态 (更新于 2026-08-08)

### Phase 3 — opencode 多 Agent 全流程体检优化 (2026-08-08) ✅
> 流水线: requirements → decomposer → coder → tester → fixer (opencode subagent)
> 详细任务追踪: docs/plan.md (93 项) / 测试报告: docs/test-report.md

- [x] P0 安全红线 (S1-S7): novel_id 路径穿越、save_path/output_dir 任意写、名称作文件名穿越、importer 越界写、无鉴权+CORS 通配、SSRF、api_key 泄漏
- [x] P1 正确性/健壮性 (L1-L9): 超时配置失效、close_all 连接泄漏、fallback 吞诊断、SSE 双重编码、async 阻塞 IO、竞态锁、reasoning_content 回退
- [x] P2 工程健康 (E1-E6): GitHub Actions CI、伪测试隔离、conftest fixture、弱断言清理、覆盖率门禁 75%、README/版本 0.8.0
- [x] P3 清理重构 (C1-C5): 死代码删除、双 StyleProfile 统一、数据管线原子写/编码校验/损坏容错 (L15)
- [x] 测试: 246 → 622 passed, 覆盖率 67% → 92.62%, ruff/mypy 全绿
- [x] 剩余项完成: L16.1 fixed_tasks 性能优化、L17 Windows 盘符路径/DATA_ROOT 环境变量注入 (docs/plan.md 93 项全部勾选)
- [x] 后端 API 鉴权: security.api_key (X-API-Key), CORS 白名单 localhost:5173

| 当前项目状态 (更新于 2026-06-19)

### Phase 1 已完成 ✅
- [x] 项目骨架 + CLI (story 命令)
- [x] 角色卡系统 (兼容 V2 规范)
- [x] Lorebook + 关键词触发引擎
- [x] 写作引擎 (大纲/写作/草稿三种模式)
- [x] 精修系统 (去AI味/节奏/风格/连贯性)
- [x] LLM 模型层 (DeepSeek 远程 + Ollama 本地 + 路由)
- [x] DeepSeek API Key 配置，端到端测试通过
- [x] 本地模型升级：qwen2.5-14b → Qwen3.5-9B-Q6_K

### Phase 2.1 已完成 ✅
- [x] FastAPI 后端 11 个路由 (novel/generate/models/research/export)
- [x] SSE 流式输出支持 (EventSource 格式，逐 token 推送)
- [x] MD 导出 (指定目录/单章/全书)
- [x] 资料检索接口 + 保存
- [x] 63 个单元测试全部通过

### Phase 2.2 进度 (基本完成) ✅
- [x] Vue 3 + TypeScript + Vite + Element Plus + Pinia 项目搭建
- [x] 路由: /writing /characters /outline /world /settings
- [x] API 服务层 (SSE 流式 + REST, 生成器模式)
- [x] 写作界面: 类起点专业编辑器（小说列表↔章节列表双层切换）
- [x] 右击菜单: 重命名/导出/删除小说/灵魂记忆
- [x] 章节管理: 添加/删除/拖拽排序/单章保存
- [x] 字数/段落/对话实时统计
- [x] SSE 流式打字机效果 + 中断支持
- [x] 角色卡界面: 卡片网格 + 编辑弹窗 (V2 字段)
- [x] 大纲界面: 章节树 + 详情编辑
- [x] 世界观管理: 分类目录 + 条目列表
- [x] 设置界面: 模型列表 + 写作参数
- [x] AI 面板: 模式切换（闲聊/写作/联网搜索）
- [x] 每小说独立存储目录（灵魂记忆/角色/设定/文风档案）
- [x] 灵魂记忆编辑器（用户备注/自定义prompt/偏好模型）
- [x] 文风分析（上传外部资料提取风格指纹）
- [x] 用户画像持久化
- [x] 人物关系图谱 (ECharts/D3-force)
- [x] 写作进度面板 (字数统计/阶段标记)
- [x] 润色/扩写/缩写右键菜单

## Phase 4 — P7 写作工作站（AI 出草稿 · 作者审核）🚧 架构与评估完成, 待实施
> 目标: 让作者本人能长期稳定写完超长篇(架构上限 2000 万字), 全书在 设定一致 / 文风统一 / 素材可溯源 三线不崩。
> **主文档: `docs/design/P7-ARCHITECTURE.md`**（架构+流程+闸门+已定决策 D1-D4）
> 子文档: `docs/design/P7-LONG-MEMORY.md`（记忆层机制）｜依据: `docs/research/R1-R6`
> 调研依据: `docs/research/R1-long-context-memory.md`（长上下文与记忆系统）
>           `docs/research/R2-style-consistency.md`（文风统一）
>           `docs/research/R3-prior-art-wiki.md`（先例与"每本小说一个知识库"评估）

### 已定架构要点（v3, 与旧版 M1-M5 的差异）
- **AI 出草稿, 作者审核**(作者主写为备选模式): 闸门 5 道（G0 设定与技法 / G1 总纲 / G2 场景节拍 / G3 正文草稿 / G4 canon 回写）
- **P5 作者时间有限**是决定取向的硬约束: 审核成本最小化(草稿自带依据/校验分级只推争议项/定点改动/diff/前置约束/候选筛选/批量审核)
- **文风 → 技法线**: 参考书目产出 技法条目 + 分割方式 + 风格特征, 按场景取用、可多本组合
- **素材 → 持续流**: 初始搜索 + 边写边补 + 实时导入 + 未建档提醒(不拦写作) + 变更隔离(改旧不改前)
- **已锁决策**: D1 AI 默认产出整场/整章草稿供审核(光标续写为次模式); D2 书目注明"提供什么"; D3 建档提醒异步不阻塞; D4 AI 走远程、本地只做离线活(且离线批处理与写作**串行排队**, 显存实测约束)

### 阶段 Ⅰ — 地基（模型调用契约 + 最小闭环）
- [ ] 模型调用契约统一: 交互式写作/抽取走 `thinking: disabled` + 显式 temperature; 规划类保留思考并单独预留 token 预算
- [ ] 空产出保护: `content` 为空即失败重试, 不依赖 HTTP 状态码（实测 v4-pro 思考模式可返回 200+空正文）
- [ ] 最小闭环: 装配 → 辅助生成 → 校验 跑通一次
- [ ] 注入可见性: 每次生成能回答"这次带了哪些片段进来"（R6 铁律 3）
- 验收: 不再出现静默空正文; 每次生成可列出注入清单

### 阶段 Ⅱ — 记忆线（写下去不靠人脑）
- [ ] 章摘要 schema（事件/出场/状态变化/钩子）+ 抽取（本地模型, 离线批处理）
- [ ] 摘要树: 章 → 10 章组 → 100 章卷 → 全书主线（增量, 每卷末从原文重建 arc）
- [ ] 结构化状态层: 人物/关系/地点/时间线/伏笔状态机
- [ ] 装配器: 硬预算上限; 常驻骨架 + 按需检索; **同时作为作者手边的参考面板**
- 验收: 20M 字级装配输入受限在预算内; 第 N 章正确接续第 N−100 章主线与伏笔

### 阶段 Ⅱ.5 — 伏笔账本与注入（最小版, N9）⬅ 先做这个
> 动机: 阅文时代的产品需求原话——「一本书写个三五年，伏笔就记不起来了」；同类产品（起点作家助手、
>   马良）都把**伏笔当一等公民模块**而非设定附属（见 `~/wiki/comparisons/product-novel-tools-setting-modules.md`）。
> 设计要点、扩展点与**非目标**见 `docs/design/P7-MVP-PLAN.md` §9.1.1。
> 约束: **最小化改动** —— 不新建存储体系、不改装配器签名、不改 SSE 契约、不引入检索/向量。

- [ ] 伏笔账本最小模型: `<小说目录>/novel.json` 增 `threads`（真源）+ `threads/` 只读镜像，沿用既有
  「model 为真源 / 目录文件为 human-readable 镜像」约定；字段 `id/title/status/planted_chapter/payoff_chapter/strength/note`
- [ ] 装配器挂 `threads` provider + 一条槽位（走既有 `extra_providers` 口子，**不改 `build_novel_builder` 签名**）
- [ ] 注入规则（最小版，非检索）: 只注入 `status ∈ {planted, developed}` 且 `planted_chapter ≤ 本章` 的伏笔；
  超预算按「本章 − **埋设**章」降序截断并标 `truncated`
- [ ] A 类校验 2 条（确定性、不调模型）: `dangling_threads`（悬空伏笔）/ `unknown_payoff`（回收章不存在）；
  **无账本时返回 skipped 而不是猜**（遵守 N5 铁律）
- [ ] 最小 API: `GET/POST/PUT/DELETE /api/novel/{id}/threads`（复用 `APIModel` camelCase 兼容）
- [ ] 前端: 写作页右侧面板只读展示「未回收伏笔」清单（本期不做编辑 UI）
- **非目标（明确推迟到阶段 Ⅲ 完整版）**: 向量/按需检索、从正文自动抽伏笔、变更隔离、图谱关系、编辑 UI
- 验收: 账本增删改查通过；生成时未回收伏笔进入注入清单（`manifest` 可见）；悬空伏笔能被校验报出；
  无账本时校验返回 skipped 而非告警

### 阶段 Ⅲ — 设定库（novel-kb）
- [ ] 每本小说一个 markdown 知识库（SCHEMA/index/log + entities/timeline/plot/style）
- [ ] frontmatter schema: `id/type/aliases/status/established_in/valid_from/supersedes`
- [ ] 伏笔一等公民: planted → developed → payed_off/abandoned + payoff_plan（**最小版已前移到阶段 Ⅱ.5 / N9**）
- [ ] 增量维护 + lint（孤儿页/断链/悬空伏笔/设定冲突, 区分 plot hole 与刻意反转）
- [ ] 变更隔离: 改设定只在生效点之后生效, 不污染已定稿正文
- 验收: 悬空伏笔与设定冲突可报出; 改设定不影响已定稿章节

### 阶段 Ⅳ — 技法线与理念库
- [ ] 书目录入含"提供什么"标注（D2）
- [ ] 抽取: 技法条目（含适用条件）+ 分割方式 + 风格特征/样段
- [ ] 按场景检索技法提示, 支持多本书目组合指派
- [ ] **理念/规则库**: 作者导入方法论 → 编译为条款（规则名+触发场景+判定方式+违反动作+阈值）
- [ ] 条款分三类落点: A 可自动检验→校验器硬告警; B 半可检验→本地判官结构化输出; C 只能提示→风格块注入
- [ ] 规则库 schema + 条款启停 + 来源标注（材料原文不入库, 只存作者编译的原创条款）
- [ ] 复用已存在的漂移检测（`style/metrics.py` + `style/drift.py`, 现处于**搁置**状态, 归入本阶段启用）
- 验收: 给定场景类型能取回对应技法条目; 导入一份方法论能产出带分类与阈值的条款并在校验时命中

### 阶段 Ⅴ — 素材线（持续流入）
- [ ] 三种采集路径: 初始搜索 / 写作中实时导入 / 未建档反向提醒
- [ ] 素材卡片 schema（服饰/制度/地理/宗教/命名/事件/议题）+ 来源标签
- [ ] 场景召回: 写到服饰场景就带服饰卡片
- [ ] 卡片修订与版本隔离
- 验收: 产出中非虚构细节可回溯到卡片; 未建档提醒生效且不阻塞输入

### 阶段 Ⅵ — 质量上限（按需）
- [ ] best-of-n 按文风分 rerank + 正则防奖励攻击
- [ ] 一致性 lint 接入 ConStory 式 5 类 19 子类检测（技法与文风维度为重点）
- [ ] 图谱关系层（只对设定库实体建图 + PPR 多跳, 不做全文建图）
- [ ] 书目风格 LoRA（单作品语料 ≥3 万字后）
- [ ] 暂缓: DPO/GRPO、n-gram logit 注入、激活向量（证据不足或脆弱）

| 参考项目地址
| 项目 | 地址 |
|------|------|
| 91Writing | https://github.com/ponysb/91Writing |
| SillyTavern | https://github.com/SillyTavern/SillyTavern |
| inkos | https://github.com/Narcooo/inkos |
| vela | https://github.com/heider-x/vela |
| StoryForge | https://github.com/yuanbw2025/storyforge |
