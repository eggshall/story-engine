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
  [x] 公版中文小说数据采集与清洗 Pipeline (P6) — v0.7.0 数据源: Gutenberg 中文公版库 (444本) 直连采集; D:/文章数据 存储; 35本首批入库 (1316万字, 覆盖严肃/幽默讽刺/悲伤/流行四大题材); 本地导入通道 (txt/epub 自动清洗)
  [ ] 文风画像自动批量生成
  [ ] 文风 vs 题材匹配推荐
```

---

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

| 参考项目地址
| 项目 | 地址 |
|------|------|
| 91Writing | https://github.com/ponysb/91Writing |
| SillyTavern | https://github.com/SillyTavern/SillyTavern |
| inkos | https://github.com/Narcooo/inkos |
| vela | https://github.com/heider-x/vela |
| StoryForge | https://github.com/yuanbw2025/storyforge |
