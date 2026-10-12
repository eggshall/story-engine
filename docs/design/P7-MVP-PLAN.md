# P7 最小化实现计划书（MVP Plan）

> 目的：**先让闭环跑起来、看到真实效果与真实问题**，再决定下一步投入。本轮只做"能跑通的最小切片"。
> 依据：`P7-ARCHITECTURE.md`（架构与流程，已定稿）｜子文档 `P7-LONG-MEMORY.md`｜调研 `docs/research/R1–R7`
> 状态：待评审（提交 opencode 审核评估）｜日期：2026-10-11

---

## 0. 本计划要回答的问题

架构已经定好，现在要回答的是：**"能不能在短时间内跑出一个能真实使用的闭环，让我看到效果并暴露真实问题"**。

因此本计划：

1. **范围极小**：只做"生成一章草稿 → 自动校验 → 我审"这一条垂直路径；
2. **不动现有可用功能**：加模块、加接口、加一个前端页面，不改写作主流程的行为；
3. **每步都能独立验收**：每段结束都有可运行的命令与可观察的结果；
4. **把大件留到后面**：素材库、技法库、条款库完整版、知识库、向量检索、五道闸门 UI 全都不在 MVP 内，用"最小替身"顶替。

---

## 1. 现状（可复用的资产，避免重造）

| 已有 | 位置 | MVP 怎么用 |
|---|---|---|
| 章节生成 | `POST /api/generate/chapter`、`POST /api/style/generate` | MVP-2 在此之上加"装配 + 注入清单" |
| 对话式生成 | `POST /api/generate/chat`（含 `style_prompt`/`profile_id` 注入） | 保持不动，作为备选模式 |
| 文风库 + 画像 | `style/db.py`、`style/analyzer.py`、`render_style_block()` | MVP-2 直接复用三段式风格块 |
| 文风量化指标 + 漂移检测 | `style/metrics.py`、`style/drift.py`（现搁置） | MVP-2 直接启用为校验器内核 |
| 精修/AI 味/节奏 | `polish/__init__.py`（AI_PATTERNS 等） | 复用为禁词表与 AI 味检测 |
| 每本小说独立存储 | `tools/novel_storage.py`（novel.json / chapters / soul_memory） | MVP-3 摘要落此处旁路（新增 SQLite） |
| 模型路由 | `llm/router.py`、`llm/api_client.py` | MVP-1 在此加固调用契约 |
| 前端写作页 | `views/WritingView.vue` + `components/*` | MVP-2 只**新增**一个审稿页，不改写作页 |

**已知技术债（必须在 MVP-1 处理，否则后面全白干）**：
远程模型思考模式默认开启、且思考模式下 `temperature` 被静默忽略；实测 `deepseek-v4-pro` 在 `max_tokens=8000` 时
全部预算被思考吃掉、`content` 为空字符串 —— 而 HTTP 状态码仍是 200，SSE 会把空正文当成功推给前端。

---

## 2. MVP 三期（每期独立可验收）

### 2.0 P0 前置（评审补充 —— 开工前必须闭环，均已在代码中核实）

来源：`P7-MVP-REVIEW.md` §3（文件级清单）。以下 8 项必须随 M1 一并处理，否则后续阶段强制返工：

| # | 前置项 | 落点 | 为什么必须现在做 |
|---|---|---|---|
| P0-1 | **前端补 `X-API-Key`** | `frontend/src/utils/api.ts`（axios 实例 + 3 处 SSE `fetch`） | 【现网 bug】后端 `main.py` 中间件在 `security.api_key` 已配置时强制校验，前端一个头都没带 → 浏览器全部 `/api` 请求 401，新审稿页同样跑不起来 |
| P0-2 | **config schema 放行新字段** | `core/config.py`(`_LLMModelConfig` / `_validate_models`) | 白名单 + `model_dump()` 会**静默剥离** `thinking`/`reasoning_effort` → M1 的"config 驱动"是空操作，看似通过实则无效 |
| P0-3 | **SSE 单一 `done` + 载荷契约** | `api/sse.py`、`api/routes/generate.py`、`frontend/src/utils/api.ts`(`readSSE.onDone(payload)`) | 现状：`sse.py` 会补发第二个 `done`，前端读到首个 `done` 即 return 且 `onDone` 无参 → 注入清单无处承载、前端读不到 |
| P0-4 | **既有冲突测试的处置** | `tests/test_llm/test_api_client.py`（断言"空 content 回退 reasoning"的两条） | 与 M1 的"空产出报错"直接冲突；不改则"pytest 全绿"无法达成，且语义未定义（reasoning 是否算正文） |
| P0-5 | **token 计数策略** | 计划内用中文启发式（`len(text)` 或 `/1.2`），manifest 标注 `token_estimate: true` | manifest 的 tokens 字段与预算裁剪都依赖它；不引依赖就不装 tiktoken |
| P0-6 | **校验路由归属** | 新建 `api/routes/check.py` 并在 `main.py` 注册 | `generate.py` 的 router 前缀是 `/api/generate`，与计划中的 `/api/check/chapter` 不匹配 |
| P0-7 | **SQLite 路径约定** | `memory/store.py` 必须用 `novel_storage._novel_dir(novel_id)` 取真实目录 | 已索引的"自定义路径小说"真实目录在别处，天真拼 `NOVELS_ROOT/{id}` 会写错位置或丢数据 |
| P0-8 | **离线队列与全局 router 共享单锁** | `memory/queue.py` ↔ `api/routes/generate.py` 的全局 `_router` | 不共享则交互写作与离线摘要仍并发抢显存；且离线任务必须 `fallback=False`，否则会被静默路由到远程（违反 D4） |


### MVP-1 · 地基加固（先能信）——目标：不再出现静默空正文

| # | 任务 | 涉及文件 | 验收（可测） |
|---|---|---|---|
| 1.1 | 调用契约：按任务类型传 `thinking`（生成/抽取 = disabled，规划 = enabled）与显式 `temperature`；config 驱动 | `llm/api_client.py`、`core/config.py`、`config/config.yaml` | 单测：请求体含 `{"thinking":{"type":"disabled"}}` 且不含 `reasoning_effort` |
| 1.2 | 空产出保护：`content` 为空/纯空白 → 抛 `LLMEmptyResponse`，路由层重试 1 次并记录 | `llm/base.py`、`llm/router.py` | 单测：mock 返回 reasoning-only → 抛错 + 重试；mock 两次空 → 明确失败（不静默） |
| 1.3 | 注入清单（最小版）：生成时记录"用了哪些片段、各占多少 token"，随响应返回并在日志留痕 | `llm/router.py` / `api/routes/generate.py` | 调用生成接口，响应里能看到 `context_manifest` 列表（含来源与字符数） |
| 1.4 | 真实回归：用 v4-pro 与 flash 各生成一段 300 字，断言非空且 `reasoning_tokens=0` | `tests/test_llm/`（新增） | `pytest tests/test_llm -q` 全绿 |

**不做**：不改前端、不改生成提示词、不动现有接口字段（只**新增**返回字段）。

---

### MVP-2 · 垂直闭环（能审一章）——目标：真实跑一次"生成→校验→我审"

| # | 任务 | 涉及文件 | 验收（可测） |
|---|---|---|---|
| 2.1 | 装配器 v0：按固定槽位组装上下文并返回结构化的"注入了什么"（全书写法/主线 手写 + 最近 N 章摘要 + 上一章结尾 2000 字 + 本章节拍 + 风格块） | 新增 `writer/context_builder.py` | 单测：给定槽位输入 → 输出含全部槽位的文本 + manifest；预算超限时按优先级裁剪 |
| 2.2 | A 类校验器（最小集 5 条）：章末钩子、对话占比、段落长度、视角一致性、禁词/AI 味 | 新增 `check/rules.py`（复用 `style/metrics.py` + `polish`） | 单测：构造"无钩子/对话失衡/超长段/视角突跳/命中禁词"的样例文本，逐条命中并给出定位 |
| 2.3 | 新接口：`POST /api/generate/chapter/v2`（走装配器）与 `POST /api/check/chapter`（返回校验报告：级别 + 定位 + 建议） | `api/routes/generate.py`、`api/schemas.py` | 契约测试：接口返回结构与 schema 一致；校验报告含 `level/location/suggestion` |
| 2.4 | 前端审稿页：三栏（左=草稿正文、中=校验清单、右=待决项/我给的修改意见），支持"带指令重写"按钮 | 新增 `views/ReviewView.vue`、`utils/api.ts` | 组件测试：注入 mock 报告 → 渲染出清单条目；点重写调用接口 |
| 2.5 | 真实体验：导入一本真实小说（或用手上的 4 万字试写），完整跑"节拍 → 草稿 → 校验 → 审" | — | 人工：能读、能改、能保存；把遇到的问题记录到 `docs/design/P7-MVP-FEEDBACK.md` |

**不做**：不做素材卡片、不做技法库、不做条款库、不做知识库、不做检索；节拍与主线在 MVP-2 里**手写**。

---

### MVP-3 · 记忆最小版（能连续写 5 章）——目标：不再靠人脑记前文

| # | 任务 | 涉及文件 | 验收（可测） |
|---|---|---|---|
| 3.1 | 章摘要生成：定稿后本地模型（离线批处理）产出结构化摘要（事件/出场/状态变化/钩子） | 新增 `memory/summarizer.py` | 单测：固定样例章 → 输出 JSON 字段齐全；幂等（同章重复跑不重复入库） |
| 3.2 | 摘要存储与查询：SQLite（`summaries`: level/chapter_from/chapter_to/summary/tokens） | 新增 `memory/store.py` | 单测：写入/读取/按范围查询；删章后一致 |
| 3.3 | 装配器接入真实摘要（替换手写的"最近 N 章"），main story 仍手写一份 | `writer/context_builder.py` | 单测：写入 5 章摘要后，第 6 章装配里含第 1 章摘要；manifest 反映来源 |
| 3.4 | 离线队列：本地批处理与交互式写作**串行排队**（显存约束：本地大模型占 ~14.4GB） | 新增 `memory/queue.py`（简单串行锁即可） | 单测：并发触发生成与摘要时，摘要任务排队等待而非并发 |

**验收（阶段级 —— 按评审要求下沉为确定性断言，不靠 LLM 输出自证）**：
1. 写入 ch_0001..ch_0005 的摘要后，装配第 6 章时 `context_manifest` 中必含 `source == "summary:ch_0001"` 且 `chars > 0`；
2. 删除 ch_0001 摘要后重跑同一装配：该条目从 manifest 消失、对应槽位 `chars` 下降，且**不抛异常**；
3. 断言装配文本内的摘要条数 == store 中命中范围内的条数（纯数据层断言，与模型输出无关）。

---

## 3. 明确的边界

- 不在 MVP 内：素材卡片与导入、参考书目技法抽取、方法论条款库、novel-kb 知识库、向量检索、五道闸门完整 UI、批量审核、候选 rerank、图谱、LoRA。
- 不改：现有 `/api/generate/*` 的行为与字段（只新增 v2 与 check 接口）；不改写作页；不动 `data/novels` 目录结构（摘要另存 SQLite）。
- 每次提交前必须：`pytest -q` 全绿、`ruff` / `mypy` 通过、前端 `vitest` 通过、`vite build` 通过。

---

## 4. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 思考模式静默空正文 | 全链路白干 | MVP-1 先做（这是唯一"必须先做"的项） |
| 前端新增页面引入测试噪音 | 拖慢迭代 | 新页面独立目录，mock 所有 API；不碰现有页面的测试 |
| 装配器预算失控 | 成本/质量双输 | manifest 里显示 token 占比；超限按优先级裁剪（先砍检索，永不砍风格块与节拍） |
| 本地模型与写作抢显存 | 生成失败/极慢 | 3.4 串行队列；MVP-2 阶段暂不用本地模型 |
| 摘要在小样本上看不出价值 | 结论误判 | 3.4 的"删摘要对比"验收，用可观察的差异证明 |

---

## 5. 提交评审的问题清单（请 opencode 重点挑战）

1. **任务粒度**：每项能否在半天内完成？有没有需要再拆的项（尤其 2.1 装配器、2.4 前端页）？
2. **依赖顺序**：MVP-2 是否真的不依赖 MVP-3？若必须依赖，最小依赖是什么？
3. **验收可测性**：有没有"看起来测了其实没测"的验收（如 1.3 注入清单、2.2 校验规则）？请指出并给出更硬的断言。
4. **遗漏的前置**：是否漏了必要前置（如前端 `utils/api.ts` 的 SSE/超时改造、鉴权 header `X-API-Key`、config schema 迁移、`data/novels` 与 SQLite 的路径约定）？
5. **返工风险排序**：MVP 里哪些决定会显著影响后续阶段（素材/技法/条款/知识库）的实现，是否需要现在就把接口形状留好？
6. **是否有更小的第一步**：如果只能做一件事就先看到效果，应该是哪一件？

---

## 6. 交付物与里程碑

| 里程碑 | 交付 | 判断标准 |
|---|---|---|
| M1 | 调用契约 + 空产出保护 + 注入清单 | 连续多次生成不再出现空正文；每次生成可查注入清单 |
| M2 | 装配器 v0 + 校验器 5 条 + 审稿页 | 能用真实文本跑"生成→校验→审"一次 |
| M3 | 章摘要 + SQLite + 装配接入 | manifest 断言：第 6 章装配含 ch_0001 摘要且 chars>0；删除后该条目消失而流程不报错 |
| 之后 | 依 M1–M3 暴露的问题决定（素材/技法/条款/知识库的优先级） | — |

---

## 7. 与整体架构的对应关系

本 MVP = 架构 `P7-ARCHITECTURE.md` 的"阶段 Ⅰ 地基"+"阶段 Ⅱ 记忆"的最小垂直切片；
阶段 Ⅲ（设定库）/Ⅳ（技法与理念）/Ⅴ（素材）/Ⅵ（质量上限）**刻意后置**，等 MVP 暴露真实问题后再排优先级。
架构中的五道闸门在 MVP 里只落地 G3（正文审核）这一个真实界面，G0/G1/G2 先用"手写节拍 + 手写主线"顶替。

---

## 8. 评审修订记录（opencode 评审 → 本计划的对应修改）

评审报告：`P7-MVP-REVIEW.md`（215 行，含文件级前置清单与证据索引）。**结论：需补充后开工**（分期与顺序成立，
但硬前置未补、部分验收偏软、两处接口形状会导致后续阶段强制返工）。

| 编号 | 评审建议 | 本计划的对应修改 |
|---|---|---|
| R1 | 1.3 拆为"记账"与"传输"，传输契约在 M1 定死（单一 `done` + manifest + usage） | 已拆入 §2.0 的 P0-3；M1 的 1.3 只做记账，传输契约随 P0-3 在 M1 内定 |
| R2 | 2.1 拆为"槽位装配（含 provider 接缝）"与"预算/裁剪/manifest"；先定义 `Slot`/`ContextManifest` | 待开工前按此拆分（装配器定义为**槽位注册表**，避免后续阶段反复重构） |
| R3 | 2.4 拆为"骨架"与"交互+测试"；补路由/导航/鉴权头/api.ts 封装 | 待拆分；路由与导航注册、鉴权头见 P0-1 |
| R4 | 所有验收按评审 §2 表改写为字段级断言；阶段级 3 下沉到装配器确定性层 | **已改**：MVP-3 阶段级验收与 M3 里程碑判据均已改为 manifest 确定性断言 |
| R5 | 新增前置任务块"P0 前置"，含评审 §3 的 #1–#11 | **已加**：§2.0（取其中 8 项硬前置，其余 3 项随期间处理） |
| R6 | 明确 SQLite 用 `_novel_dir()`，并覆盖自定义路径小说用例 | **已加**：P0-7（并列入 3.2 的测试要求） |
| R7 | 离线队列与全局 `_router` 共享单锁，离线任务 `fallback=False` | **已加**：P0-8；3.4 的验收改为"断言 `max_concurrent == 1`" |
| R8 | 1.4 改为 mock 单测 + `@pytest.mark.live` 分离，避免 CI 依赖网络 | 待改（1.4 的真实验证标 `live`，默认不跑） |
| R9 | 显式列出需改写的既有测试 `test_api_client.py:88-120` | **已加**：P0-4 |
| R10 | 校验路由新建 `api/routes/check.py` 并在 `main.py` 注册 | **已加**：P0-6 |

其余随期间处理的评审项：token 计数（P0-5）、覆盖率门禁（每模块随码交付测试）、漂移基线来源
（2.2 明确基线来自风格画像或前序章节，无基线时返回 `ok`/`skipped` 而非误报 alert）。

**命名统一（N4b 定）**：注入清单在 done 载荷里的字段名一律为 **`context_manifest`**
（N2/N4b 实现的键名）。历史评审报告 `P7-MVP-REVIEW.md` 里出现的 `injection_manifest` 是当时的
提案名，已废弃；代码注释、AGENTS.md、本计划书均已改齐，避免前端按旧名取值拿到 `undefined`。

**后续待办（N4b 评审 P2）**：`context_manifest` 目前只随 done 载荷下发（刷新页面即丢）。
**由 N6 承接**：把它随章节落盘（旁路文件或 SQLite），让"当时注入了什么"可长期回看。

## 9. 开发流程与评审约定（本项目强制，每个节点都必须走完）

### 9.1 节点划分（每个节点 = 一次可独立评审的交付）

| 节点 | 内容 | 依赖 |
|---|---|---|
| **N0** | 前端鉴权打通（`X-API-Key` 注入 + 断言测试 + 真实浏览器 E2E）—— 修掉现网 401 | — |
| **N0.5** ✅ | 工程结构整理：`e2e/` 上移到项目根（依赖改由根 `package.json` 管理，`npm run e2e`）、清理被跟踪的产物（`coverage.xml`）、更新 `.gitignore` | N0 |
| **N1** | 调用契约（`thinking`/显式温度/空产出守卫）+ 既有冲突测试改写 | N0 |
| **N2** ✅ | SSE 单一 `done` + 载荷契约（后端 `sse.py`/`generate.py` + 前端 `readSSE.onDone(payload)`） | N1 |
| **N3** ✅ | config schema 放行 `thinking`/`task` 字段（含"不被静默剥离"的断言） | N1 |
| **N4** ✅ | 装配器 v0（拆为 N4a 槽位注册表 `Slot(...)` + `ContextManifest` + 两级预算 / N4b 真实数据源 + `POST /api/generate/chapter/v2` + 注入清单上 done 载荷） | N2/N3 |
| **N5** ✅ | A 类校验器 5 条 + `api/routes/check.py`（含漂移无基线时返回 ok/skipped 的行为） | N4 |
| **N6** ✅ | 审稿页（路由 + 导航注册 + 三栏 + 带指令重写）+ 注入清单落盘 `GET /api/check/manifest` | N4/N5 |
| **N7** | 章摘要 + SQLite（走 `_novel_dir`）+ 装配接入 + 离线串行队列 | N4 |
| **N8** 🚧 | 项目空间：角色卡/世界观**按小说绑定**（全局目录退役）+ 素材库（仅作复制来源） | N6 |
| **N9** ⬅ 下一个 | **伏笔账本 + 注入 + 校验（最小版）**：`novel.json` 增 `threads`；装配器挂 `threads` provider/槽位；A 类校验 2 条；`/api/novel/{id}/threads` CRUD。**不改装配器签名、不改 SSE 契约、不引入检索** —— 要点见 §9.1.1 | N8（世界观按书绑定） |

**N8 进度（2026-10-11 收工时）**

已完成（全门禁绿：pytest 855 passed / 94.33%，ruff+mypy 清，vitest 104，vue-tsc 0）：
- 后端：`characters/manager.py` 改 novel-scoped（list/load/save/delete/search 全部带 novel_id）；
  新增 `characters/library.py`（素材库，纯复制语义）；`generate.py` 三处"把全部全局卡并进当前小说"
  的合并代码删除 → 生成只用本书的卡；`cli.py` 的 character 命令迁移为 `--novel` 版
- 接口：`api/routes/characters.py`（GET/POST/PUT/DELETE `/api/novel/{id}/characters`、
  `/api/library/characters`、`.../to-library`、`.../import`）已注册进 `main.py`
- 前端：`CharactersView.vue` 接接口（替换原**纯内存** store）+ 顶部"选择小说"（优先写作页当前那本
  → 记住上次选的 → 最近更新）+ 另存为素材/从素材库导入/删除；`api.ts` 新增 8 个函数
- 数据：全局示例（`data/characters/林晓月`、`data/lore/天玄大陆`）删除；
  `data/novels/未命名作品`（测试残留空壳书）与 `data/novels/novel_ae0fa8d5`（真书的旧本地副本）已清
- 测试：`tests/test_characters/`（57 例：novel-scoped CRUD、隔离性、素材库复制语义、接口契约）

明天从这里开始（N8 剩余）：
1. **世界观/设定集同步做一遍**：`lore/lorebook.py` 改 novel-scoped、`engine._build_world_context()`
   改用本书 `lorebooks`、新增 `/api/novel/{id}/lorebooks` 系列 + 素材库 lore 端点
2. 前端世界观页（WorldView）加"设定集"区块（现在那页只有世界地图，lorebook 完全没有 UI）
3. 浏览器 E2E：建卡 → 刷新仍在（持久化回归）→ 换书看不到；素材库导入 → 两本书互不影响
4. opencode 只读评审 → 逐条处置 → 一个节点一次提交
5. 待办：`AGENTS.md` 补 N8 约定（需用户在弹窗批准）；`data/novels/{custom-exports,test-novel,导出测试}`
   是空壳残留目录（无 novel.json，界面不显示），可与用户确认后一并清掉


### N8 决策（用户已定，2026-10-11）

- **方案 A：纯每本独立**。角色卡存 `<小说目录>/characters/<角色>.json`、世界观存
  `<小说目录>/lore/<设定集>.json`（`novel.json` 里的 `characters`/`lorebooks` 字典是真源，
  目录文件是 human-readable 镜像，沿用 `_write_files` 既有约定）。
- **全局 `data/characters/`、`data/lore/` 退役**：生成不再注入全局卡（现在是
  `generate.py` 无条件 `list_cards()` 全部并入当前小说 —— 所有书共用一副卡组）。
- **素材库 `data/library/{characters,lore}/`**：只用于「另存为素材 / 从素材导入」的**纯复制**，
  不是共享引用（改素材不影响已导入的书）。
- 现有全局示例数据（`林晓月`、`天玄大陆`）删除。
- 背景：前端"角色卡"页当前是**纯内存态**（`stores/characters.ts` 无持久化、无 API），
  刷新即丢且与生成用的数据不是同一份 —— N8 一并修掉。
- **陷阱（写代码时必须遵守）**：角色卡/设定集只能经
  `load_novel → 改模型 → save_novel` 保存。`novel_storage._write_files` 每次保存都会
  **先清空再重建** `characters/`、`lore/` 目录，绕过模型直接往镜像目录写文件，
  会在下一次保存章节时被整目录清空（作者眼里是"卡莫名其妙没了"）。
  回归用例：`tests/test_characters/test_novel_scoped_cards.py::test_card_survives_chapter_save`。

### 9.1.1 N9 设计要点 —— 伏笔账本 + 注入 + 校验（最小版）

> 动机来源：同类产品的对照结论（`~/wiki/comparisons/product-novel-tools-setting-modules.md`）——
> 起点作家助手把**伏笔做成一等公民模块**（且可「从正文选段落建立」），马良用
> **埋设/强化/回收三段式 + 埋设章/回收章双向指针**。本项目此前的伏笔只隐含在 `lore` 的
> 关键词触发里，装不下「埋设章 → 回收章」的状态机。

#### 为什么这是「最小化改动」——四个已就绪的扩展点

| 扩展点 | 现状 | 本节点怎么用 |
|---|---|---|
| `context_sources.build_novel_builder(..., extra_providers=...)` | 已存在，注释明确写着「用于后续阶段挂新数据源 —— **不改本函数签名**」 | 直接把 `threads` provider 从 `extra_providers` 传入 |
| `default_slots()` | 槽位是「注册表名字」的列表，provider/renderer 解耦（N4a 特意做成这样） | 新增一条 `Slot(...)`，不动既有槽位 |
| `ContextPiece(text, source, truncated)` + `manifest.skipped`/`error:<类型>` | 「没注成必须可见」已是既有契约 | 账本为空 → 返回空列表 → 自动进 `skipped`，无需新机制 |
| `check/rules.py` A 类校验器 | 确定性、不调模型、发现带 `level + location + suggestion`；无基线返回 `skipped` | 新增 2 条规则，不改框架 |

**明确不碰**：`build_novel_builder` 签名、SSE 契约（`token`/`done`/`error` 与单一 `done`）、
`generate.py` 的既有装配调用链、`printer`/渲染框架、`router.py` 的模型层。

#### 数据模型（沿用既有存储约定）

`<小说目录>/novel.json` 增 `threads`（**真源**），并镜像 `<小说目录>/threads/*.json`（human-readable），
与 `characters`/`lorebooks` 的「model 为真源 / 目录文件为镜像」约定一致。

| 字段 | 说明 |
|---|---|
| `id` | 稳定标识（生成后不再改） |
| `title` | 一眼能看懂的短句（不要只写"神秘老者"） |
| `status` | `planted` → `developed` → `paid_off` / `abandoned` |
| `planted_chapter` | 埋设章号 |
| `payoff_chapter` | 回收章号，未回收为 `null`（**改章节顺序时最易失效的位置信息**） |
| `strength` | 1–5，越大表示此刻越该让读者感觉到 |
| `note` | 计划怎么回收 / 回收什么 |

> **本期仅展示 / 待用（评审 P2-7，别假装已生效）**：
> `strength` 目前**不参与**注入排序与校验，纯粹是给前端面板展示"强度"用的字段；
> `ThreadContext.dangle_threshold` 虽然可传，但**没有 API / config 入口**
> （`api/routes/check.py` 从不赋值），实际只能用默认 30。两者都标记为待用，
> 而不是写成"可配"。

**⚠️ 陷阱（必须遵守，与 N8 的同源）**：`novel_storage._write_files` 每次保存会按模型里的字典
**先清空再重建**镜像目录。实现后核对过真实行为（原文写得不准确，此处按代码更正）：

| 镜像目录 | 实际行为 |
|---|---|
| `chapters/` | 先 unlink 所有 `*.json` 再写 |
| `characters/` | 先 unlink 所有 `*.json` 再写 |
| `lore/` | **只写，不清空**（历史实现差异，未做统一） |
| `threads/`（N9 新增） | 采用与 `characters/` **一致**的「先清空再重建」—— 这样删掉的伏笔不会在目录里留残影 |

因此伏笔**必须经 `threads.manager`（load → 改模型 → save）写入**，不能直接写这个目录，
否则下一次保存章节时会被整目录清空。回归用例：
`tests/test_threads/test_threads_survive_save.py::test_thread_mirror_survives_chapter_save`
（端到端那半条在 `tests/e2e/test_n9_threads_real_http.py::test_thread_survives_real_generation`）。
（另：PLAN 原文拼写为 `payed_off`，**实现时统一为 `paid_off`**；阶段 Ⅲ 那一行待同步改。）

#### 注入（本期是**规则过滤**，不是检索）

```
Slot("threads", priority=SUMMARIES, provider="threads", renderer="bullets", max_tokens=1200)
```

- 排位放在 `beat` 之后、`recap` 之前：伏笔回答的是「本章该推进什么」，与节拍同级紧邻
- 优先级取 `SUMMARIES` 同级（**可被裁**）而非 `PINNED`：账本属"记忆"类，不是硬约束
- 过滤规则：`status ∈ {planted, developed}` 且 `planted_chapter ≤ 本章章号`
- 超 `max_tokens`：按「本章 − **埋设**章」降序截断（模型里没有"上次推进章"字段，
  原设计写"按距上次推进的章数"是笔误，**评审 P2-6** 已更正），**并在 `ContextPiece.truncated` 自报**
- provider 契约照旧：读不到 → 返回 `[]` → 进 `manifest.skipped`
- `source` 命名沿用既有风格：`thread:<id>`

#### A 类校验（2 条，确定性、不调模型）

| 规则 | 判定 | level |
|---|---|---|
| `dangling_threads` | `status ∈ {planted, developed}` 且 `本章 − planted_chapter > 阈值`（默认 30，可配） | `alert` / `warn` 分级 |
| `unknown_payoff` | `payoff_chapter` 指向不存在的章节 | `alert` |

**无账本 / 无基线时返回 `skipped` 而不是猜**（遵守 N5 铁律）；`location` 偏移相对请求原文。

#### 接口与前端

- `GET/POST/PUT/DELETE /api/novel/{id}/threads`，请求/响应复用 `APIModel`（camelCase 兼容）
- 前端：写作页右侧面板**只读**展示「未回收伏笔」清单（本期不做编辑 UI，作者先用文件/接口维护）

#### 非目标（明确推迟，避免范围蔓延）

向量或按需检索注入、从正文自动抽取伏笔、变更隔离（改设定不污染已定稿）、
图谱关系层、伏笔编辑 UI、素材卡片化。**这些都在阶段 Ⅲ–Ⅵ，不在 N9。**

#### 验收

1. 账本 CRUD 通过；`novel.json` 与 `threads/` 镜像一致，且**保存章节后镜像不被清空**
2. 生成时未回收伏笔进入注入清单（`GET /api/check/manifest` 可见 `source="thread:<id>"`）
3. 无账本时：注入侧槽位进 `skipped`（`empty`）；**校验侧伏笔规则不参与**，
   报告形状与 N5 完全一致（不告警、也不新增规则条目）—— **评审 P1-2** 把验收文字与实现对齐，
   不再写"校验返回 skipped"（实现取的是"没账本就不跑"，见上文两处修正的说明）
4. 悬空伏笔 / 回收章不存在能被校验报出
5. E2E 判定：改了文件落盘与 HTTP 接口 → **必须有真实 HTTP E2E**；校验规则本身用单测即可

#### N9 实施记录（2026-10-12）

已完成 ①②③④（RED → GREEN → REFACTOR → E2E），门禁全绿：

| 门禁 | 结果 |
|---|---|
| `pytest -q` | **912 passed / 3 skipped**，覆盖率 94.34%（门禁 75%） |
| `ruff check src/story_engine tests` | All checks passed |
| `mypy src/story_engine` | Success（65 源文件） |
| `vitest run` / `vue-tsc --noEmit` | 104 passed / 0 |

落地文件：`core/models.py`（`PlotThread` + `Novel.threads`）、
`threads/manager.py`（新增包，CRUD + `advance_thread` + `select_open_threads`）、
`tools/novel_storage.py`（子目录 + 镜像）、`writer/context_sources.py`（槽位 + provider）、
`check/rules.py`（`ThreadContext` + 2 条规则 + `THREAD_RULES`）、
`api/routes/threads.py`（新增，5 个端点 + 注册进 `main.py`）、
`api/routes/check.py`（有账本才追加伏笔规则）。

**实现中相对设计的两处修正（都已写回本文档）**：
1. 镜像目录行为按代码更正（`lore/` 只写不清空；`threads/` 与 `characters/` 一致先清空）；
2. **校验接口只在「有账本」时追加伏笔规则**（而非总是跑、无账本记 `skipped`）。
   理由：后者会让每本还没用过账本的旧书报告里凭空多出两条 `skipped` 规则，
   改变 N5 既定响应形状 —— 取最小影响。已用 E2E 钉死该不变量
   （`test_book_without_ledger_keeps_legacy_report_shape`）。

**本节点未做（按"最小化改动"显式延后，不是遗漏）**：
- **前端只读面板**（写作页展示「未回收伏笔」清单）—— 后端契约已就绪，作者当前可用
  文件/接口维护；面板作为独立增量，避免本节点把前后端一起改动而难以评审

#### N9 评审结论（⑤⑥，2026-10-12）

评审报告归档：`docs/design/reviews/N9-REVIEW.md`（`opencode run --agent requirements`，只读）。

- **无 P0**；结论原文为「需修复后提交」
- **2 个 P1 + 9 个 P2 已全部处置**（逐条处置表见归档报告末节）：
  - P1-1 `PUT` 改 id 会静默覆盖另一条伏笔（真实数据丢失路径）→ 目标 id 已存在即失败 + 2 条回归
  - P1-2 验收 3 文字与实现对齐（校验侧「不参与」而非"返回 skipped"）
  - P2-1 camelCase 文档承诺未落地（驼峰字段被静默丢成 0）→ `APIModel` + `extra="forbid"` + 4 条测试
  - 其余：误报修正、老书兼容回归、manifest 端点 E2E、抽公共筛选函数、文档更正、弱断言改行为断言
- 修复后门禁：**921 passed / 3 skipped**（覆盖率 94.36%）· ruff / mypy / vitest / vue-tsc 全绿

### 9.2 每个节点的固定流程（测试先行，缺一步不算完成）

```
① RED    先写会失败的测试（后端 pytest / 前端 vitest），确认它真的红
② GREEN  最小实现让它变绿；不顺手重构无关代码
③ REFACTOR 清理，保持 pytest + vitest + ruff + mypy + vite build 全绿
④ E2E    跑该节点的端到端验证（见 9.3），把实际输出留痕
⑤ 评审   交 opencode 评审（opencode run --agent requirements "<评审提示>"），
         要求它指出：任务/实现是否漏项、测试是否"看起来测了其实没测"、是否引入回归
⑥ 修复   按评审结论修复（治本，不改测试掩盖），再跑全量回归
⑦ 提交   一次节点一次提交（commit message 写明节点号 + 验收结果 + 评审结论）
```

### 9.3 E2E 要求（"必要"的判定）

| 层级 | 现状 | 本项目的 E2E 要求 |
|---|---|---|
| 后端 API E2E | 已有 `TestClient` 用法与 `tests/test_writer/test_sse.py` | **必须**：真实 app + 真实 HTTP（含 `X-API-Key`）走完整链路；SSE 要断言"逐 token + 单一 done + done 载荷字段"；模型调用用本地假 OpenAI 兼容 server 或标 `@pytest.mark.live` |
| 前端交互 E2E | vitest + happy-dom（无 Playwright） | 关键路径**必须有真实浏览器冒烟**：起后端 + 起 vite，用浏览器驱动打开页面、点按钮、断言页面出现预期内容（产物截图/日志留痕）。纯组件测试不算 E2E |
| 模型真实调用 | 无 | 涉及调用契约的节点（N1）必须有一次真实远程调用验证（非空正文 + `reasoning_tokens=0`），标 `live` |

判定原则：**改了跨进程/跨层的行为（HTTP、SSE、鉴权、文件落盘）就必须有 E2E**；纯内部函数（如校验规则）用单测即可。

### 9.4 评审记录归档

每次 opencode 评审的报告归档为 `docs/design/reviews/N<节点号>-REVIEW.md`，结论（可开工/需修复）+ 修复情况
写在对应的 commit message 里，便于回溯。
