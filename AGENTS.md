# AGENTS.md — story-engine 项目导览与协作约定

> 给 AI 编码 agent（opencode / Claude Code / Codex 等）和人类协作者的项目入口文档。
> 规则：**动手前先读本文件 → 再读 `PLAN.md` 与相关 `docs/`**。不要凭猜测改代码。

## 1. 项目是什么

AI 辅助中文长篇小说写作系统。当前形态：**作者主写 / AI 出草稿、作者审核**（架构见 `docs/design/P7-ARCHITECTURE.md`）。
后端 FastAPI（async + SSE 流式），前端 Vue 3 + TypeScript + Element Plus + Pinia，模型层支持远程（DeepSeek）与本地（Ollama）。

## 2. 目录结构

```
story-engine/
├── src/story_engine/          # 后端 Python 包 (pyproject: story-engine, CLI 入口 story)
│   ├── api/                   # FastAPI 应用
│   │   ├── main.py            # 应用入口 + 鉴权中间件 + CORS
│   │   ├── schemas.py         # 请求/响应模型 (APIModel: camelCase 兼容)
│   │   ├── sse.py             # SSE 事件封装 (token/done/error)
│   │   └── routes/            # novel / generate / style / export / research / models / system
│   ├── core/                  # config.py (YAML 加载 + 白名单校验), models.py (Pydantic 数据模型)
│   ├── llm/                   # base.py(抽象) / api_client.py(OpenAI 兼容) / local_client.py(Ollama) / router.py(路由+fallback)
│   ├── writer/                # engine.py 写作引擎（大纲/写作/草稿 + 前情提要）
│   ├── characters/            # 角色卡 CRUD（SillyTavern V2 兼容）
│   ├── lore/                  # Lorebook + 关键词触发注入
│   ├── style/                 # 文风库: db.py(SQLite) / analyzer.py(画像) / recommend.py(题材匹配) / metrics.py+drift.py(量化与漂移检测)
│   ├── polish/                # 精修: 去 AI 味(AI_PATTERNS/SOFT_PATTERNS) / 节奏 / 连贯性
│   ├── tools/                 # novel_storage.py(每本小说独立目录) / memory_models.py(SoulMemory) / web_search.py / prompts.py
│   ├── data_pipeline/         # 语料采集与清洗（Gutenberg 公版库、本地导入、繁转简）
│   └── utils/                 # file_utils / url_utils
├── src/frontend/              # 前端 Vue 3 + Vite（含 vitest 单测）
│   └── src/{views,components,stores,router,utils}/
├── e2e/                       # ★ 项目级浏览器 E2E（Playwright；依赖在根 package.json）
├── tests/                     # 后端 pytest（按域分子目录：test_llm/ test_writer/ test_lore/ ...）
│   └── e2e/                   # 真实 HTTP + 鉴权的后端 E2E（uvicorn + 假上游，不花钱）
├── config/config.yaml         # 运行配置（模型、search.vpn_enabled、security.api_key 等）
├── data/                      # 运行期数据：novels/（每本一个目录）、style_profiles/、research/、exports/
├── docs/
│   ├── design/                # 设计文档（P7-ARCHITECTURE / P7-MVP-PLAN / P7-LONG-MEMORY）
│   │   └── reviews/           # 每节点的评审报告（N<节点>-REVIEW.md）
│   ├── research/              # R1–R7 调研报告（长上下文/文风/先例/资料源/热点/流程/方法论）
│   ├── plan.md, test-report.md
├── scripts/                   # 数据管线与开发脚本（p6_*、eval_style_drift、e2e_dev_stack.sh）
├── PLAN.md                    # 任务清单（Phase 划分，勾选式）
└── CHANGELOG.md               # 版本变更
```

## 3. 环境与常用命令

```bash
# 后端（Python 3.11+，项目自带 .venv；不要用系统 python）
.venv/bin/python -m pytest -q                       # 全量测试（含覆盖率门禁 75%）
.venv/bin/ruff check src/story_engine tests         # 静态检查
.venv/bin/mypy src/story_engine                     # 类型检查
.venv/bin/python -m uvicorn story_engine.api.main:app --host 127.0.0.1 --port 8000   # 起后端

# 前端（在 src/frontend 下）
npm run dev            # vite dev server (5173)
npm run build          # vite build
npx vitest run         # 单测
npx vue-tsc --noEmit   # 类型检查

# 浏览器 E2E（项目根；先起开发栈，再跑 Playwright）
bash scripts/e2e_dev_stack.sh           # 起后端(8000)+前端(5173) 并做 HTTP 鉴权校验（真实模型）
bash scripts/e2e_dev_stack.sh --fake    # 假上游模式：模型指向本地假上游(8899)，不花钱、正文可断言
npm run e2e                             # = playwright test --config e2e/playwright.config.ts
# 开发栈退出（含 Ctrl-C）会自动清理自己起的进程；--fake 的临时配置在 /tmp/e2e_fake_config.yaml
```

注意（本机环境特有）：
- `node`/`npx` 在 `~/.nvm/versions/node/v22.23.2/bin`，**非交互 shell 不在 PATH**，需先 `export PATH=...`。
- npm 官方源不通，安装依赖加 `--registry=https://registry.npmmirror.com`；`github.com` 直连不通（用 codeload 或镜像）。
- 内联 `python -c "..."` / `curl | python` 会触发安全扫描被拦 → 把脚本写到文件再跑（见 `scripts/_read_api_key.py`）。

## 4. 必须遵守的既有约定（违反会造成隐性 bug）

| 约定 | 说明 |
|---|---|
| **鉴权头** | 后端在 `security.api_key` 已配置时对 `/api/*` 强制校验 `X-API-Key`（`/api/health` 除外）。前端所有请求必须带头：REST 走 `utils/api.ts` 的 axios 实例（拦截器注入），SSE 用 `sseHeaders()`。**新增任何请求路径都要带**。 |
| **密钥来源与安全** | 前端密钥优先级：`localStorage['story_api_key']`（设置页运行时录入，`setApiKey()`）> 构建期 `import.meta.env.VITE_API_KEY`。生产部署**优先用设置页录入**——构建期注入会把密钥打进 `dist` bundle；localStorage 明文仅适用于本机单用户场景。切换密钥无需刷新，但已加载的数据需重新触发请求。 |
| **SSE 契约（N2）** | 事件为 `token` / `done` / `error`；`EventSourceResponse` 只接受 dict（不要自己拼 `data:` 字符串）。**单一 done**：一条流最多一个 `done` —— 生成器自己 yield 了 done（用 `sse.done_payload(**fields)` 构造）包装层就不再补发；`done` 之后产出的事件一律丢弃并告警；`error` 流不再有 `done`。**载荷**：结果字段（`chapter`、`outline`、后续的 `injection_manifest`）放 done 的 data 里，前端用 `readSSE.onDone(payload)`（即三个流式接口的第二参 `hooks.onDone`）接收。前端 `readSSE` 逐 token 解析，**`error` 事件默认抛 `Error`（不能当正文 yield，否则会被存进章节）**，调用方负责 catch 后提示用户。 |
| **空产出守卫** | 远程与本地客户端都必须受保护：守卫在 `router.py::_guard_nonempty_stream` / `_chat_with_retry`（provider 无关），本地客户端没有自己的守卫，新增客户端不要重复实现。 |
| **每本小说目录** | 通过 `tools/novel_storage.py::_novel_dir(novel_id)` 取真实目录（支持自定义路径 + 索引），不要自己拼路径。 |
| **配置** | `core/config.py::_LLMModelConfig` 是白名单：新增配置字段必须同时加进模型，否则会被 `model_dump()` **静默剥离**。 |
| **配置路径覆盖** | `STORY_CONFIG_PATH=<file>` 覆盖 `core/config.py::DEFAULT_CONFIG_PATH`（浏览器 E2E / 多环境用）。生产环境别设，否则配置静默漂移。 |
| **前端字段命名** | 后端 `APIModel` 兼容 camelCase/snake_case（`alias_generator=to_camel`）。 |
| **本地模型显存** | 本地大模型（如 gm4 ≈14.4GB）与交互式写作不能并发（16GB 卡）；离线批处理必须串行排队。 |

## 5. 测试与 E2E 要求

- **测试先行**：先写会失败的测试，再实现。
- 提交前必须全绿：`pytest -q`、`vitest run`、`ruff`、`mypy`、`vue-tsc --noEmit`、`vite build`。
- **E2E 判定**：改了跨进程/跨层行为（HTTP、SSE、鉴权、文件落盘）就必须有 E2E；纯内部函数用单测。
  - 后端：真实 app + 真实 HTTP（含鉴权头）→ 放 `tests/e2e/`，用 uvicorn 起真实 socket + 本地"假上游"
    （OpenAI 兼容 HTTP server）；工具在 `tests/e2e/fake_upstream.py`
    （`FakeUpstream` / `write_config` / `real_http_stack` / `parse_sse_events`，N1/N2 起共用）打真实请求，
    SSE 要断言"逐 token + 单一 done + done 载荷字段"。`TestClient`（进程内 ASGI）算单测，不算 E2E。
  - 前端：关键路径必须有**真实浏览器**冒烟（Playwright，见 `e2e/`），复用已缓存 chromium
    （`~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome`），不要重新下载浏览器。
  - 真实模型调用标 `@pytest.mark.live`，默认不跑（`STORY_LIVE=1` 才执行）。

## 6. 开发流程（每个节点都要走完，用户强制）

```
① RED 写失败测试 → ② GREEN 最小实现 → ③ REFACTOR 全绿
→ ④ E2E 留痕 → ⑤ 交 opencode 评审（报告归档 docs/design/reviews/N<节点>-REVIEW.md）
→ ⑥ 按评审修复（治本，不改测试掩盖）→ ⑦ 一次节点一次提交（message 写节点号+验收结果+评审结论）
```

opencode 用法（本机二进制在 `~/.nvm/versions/node/v22.23.2/bin/opencode`）：
```bash
export PATH=$PATH:/home/syzc/.nvm/versions/node/v22.23.2/bin && source ~/.bashrc
opencode run --agent <角色> "<提示词>"      # 角色: requirements / decomposer / coder / tester / fixer
```

## 7. 文档地图（先读哪个）

| 问题 | 看这里 |
|---|---|
| 现在要做什么 | `PLAN.md`；节点级流程见 `docs/design/P7-MVP-PLAN.md` §9 |
| 架构与流程为什么这样 | `docs/design/P7-ARCHITECTURE.md`（前提 P1–P5、闸门 G0–G4、已定决策 D1–D4） |
| 记忆层机制细节 | `docs/design/P7-LONG-MEMORY.md` |
| 结论的依据（带来源） | `docs/research/R1–R7` |
| 历史变更 | `CHANGELOG.md` |

## 8. 待整理项（用户已提出，先行记录）

1. ~~**`e2e/` 目录上移到项目根**~~：**已完成（N0.5）** —— 浏览器 E2E 在根级 `e2e/`（依赖由根 `package.json` 管理，
   运行 `npm run e2e`，开发栈 `npm run e2e:stack`）；后端真实 HTTP E2E 在 `tests/e2e/`（pytest）。
2. **代码结构梳理**：目录职责与文件命名统一、清理无用产物（如 `.ipynb`/缓存）、按域拆分 `tests/` 与 `scripts/`。
3. **本文件持续维护**：结构或约定变化时同步更新 `AGENTS.md`（它是 agent 的唯一入口）。
