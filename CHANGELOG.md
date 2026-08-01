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
