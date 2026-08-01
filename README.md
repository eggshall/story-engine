# 故事引擎 (Story Engine)

AI 小说生成系统 — 远程 API (DeepSeek / Claude) + 本地模型 (Ollama) 混合架构。

## 快速开始

```bash
# 安装
cd story-engine
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 查看帮助
story --help

# 创建示例数据
story character example
story lore example

# 查看系统信息
story info
```

## 启动 API 服务

```bash
source .venv/bin/activate
```

访问 http://localhost:8000/docs 查看自动生成的 API 文档。
## 项目结构

```
story-engine/
├── src/story_engine/
│   ├── cli.py                  # CLI 入口
│   ├── core/                   # 配置 + 数据模型
│   ├── characters/             # 角色卡系统 (V2 规范)
│   ├── lore/                   # 设定管理 (Lorebook)
│   ├── writer/                 # 写作引擎 (三种模式)
│   ├── polish/                 # 精修系统 (去AI味/风格/节奏)
│   ├── llm/                    # 模型层 (远程/本地路由)
│   └── api/                    # FastAPI 后端 (REST + SSE 流式)
│       ├── main.py             # 应用入口
│       ├── schemas.py          # 请求/响应模型
│       ├── sse.py              # SSE 流式工具
│       └── routes/
│           ├── models.py       # 模型管理
│           ├── novel.py        # 小说 CRUD
│           ├── generate.py     # 生成 (大纲/章节/对话)
│           ├── export.py       # MD 导出
│           └── research.py     # 资料检索
├── config/config.yaml
├── data/
│   ├── characters/             # 角色卡
│   ├── lore/                   # 设定集
│   ├── novels/                 # 小说
│   ├── research/               # 资料检索
│   └── novels/exports/         # MD 导出
├── tests/                      # 63 个单元测试
└── PLAN.md                     # 开发计划
```

## API 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/models/` | 列出模型 |
| GET | `/api/models/default` | 默认模型 |
| GET | `/api/novel/` | 小说列表 |
| POST | `/api/novel/` | 创建小说 |
| GET | `/api/novel/{id}` | 小说详情 |
| DELETE | `/api/novel/{id}` | 删除小说 |
| POST | `/api/generate/outline` | 生成大纲 (SSE) |
| POST | `/api/generate/chapter` | 生成章节 (SSE) |
| POST | `/api/generate/chat` | AI 对话 (SSE) |
| POST | `/api/export/md` | 导出 MD |
| POST | `/api/research/` | 资料检索 |

## 运行测试

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## 模型配置

编辑 `config/config.yaml` 或使用 CLI：

```bash
story config set-key llm.models.0.api_key sk-xxx
story config show
```

当前可用模型：
- **Qwen3.5-9B-Q6_K** — 本地 (Ollama, 7.4GB, 默认)
- **DeepSeek v4 Pro** — 远程 (主力写作)
- **DeepSeek v4 Flash** — 远程 (低成本备选)
- **Claude Sonnet 4** — 远程 (润色, 需配 Key)

详见 [PLAN.md](PLAN.md)。
