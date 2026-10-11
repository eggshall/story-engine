# P7-MVP-PLAN 批判性评审报告

> 评审对象：`docs/design/P7-MVP-PLAN.md`
> 参照基准：`docs/design/P7-ARCHITECTURE.md`（已定稿，D1–D4 / P1–P5 锁定不质疑）、`docs/design/P7-LONG-MEMORY.md`、`docs/research/R1–R7`
> 代码核验范围：`src/story_engine/`、`src/frontend/src/`、`tests/`、`config/config.yaml`、`pyproject.toml`
> 评审角色：评审（只读；本轮未修改任何代码或既有文档，仅新增本文件）
> 日期：2026-10-11

---

## 0. 结论摘要（先给判断）

| 维度 | 结论 | 一句话依据 |
|---|---|---|
| 总体 | **需补充后开工** | 方向与分期正确，但有 5 项硬前置缺失、2 处接口形状会在后续阶段强制返工、若干验收"测了等于没测" |
| 任务粒度 | 基本合理，**3 项需再拆** | 1.3 / 2.1 / 2.4 各含"两个独立交付物"，半天装不下 |
| 依赖顺序 | MVP-2 **不依赖** MVP-3（成立） | 但 2.1 必须预留 provider 接缝，否则 3.3 必返工 |
| 可测性 | **约 40% 的验收偏软** | 1.3、2.1、2.2、3.1、3.3、阶段级 3 需要更硬断言 |
| 前置依赖 | **漏 5 项**（鉴权头最致命） | 现网 `config.yaml` 已启用 `security.api_key`，前端**完全没有** `X-API-Key` |
| 返工风险 | 最高两处：装配器接口、注入清单的 SSE 传输 | 直接影响阶段 Ⅲ–Ⅴ 与审稿页 |

**最小第一步（若只做一件事）**：在 `src/story_engine/llm/api_client.py` 的 `OpenAIClient.chat_stream` / `chat` 注入 `thinking`/`temperature` 并加空产出守卫，配合 `src/story_engine/llm/router.py` 的 `ModelRouter.chat_stream` 把"零 token 流"转为 `LLMStreamError` —— 只此一处即可消除"静默空正文"，且效果可被真实生成接口直接观察。

---

## 1. 第 5 节 6 个问题逐条回答

### Q1 任务粒度：每项能否半天完成？哪些要拆？

| 任务 | 半天可行性 | 判断 | 拆分建议 |
|---|---|---|---|
| 1.1 调用契约 + config 驱动 | ⚠️ 紧 | 实际要动 3 个客户端类 + config schema + config.yaml；且 `_LLMModelConfig` 会**静默丢弃** `thinking` 字段（见 §3-2） | 拆 (a) schema/config 透传；(b) payload 注入与 task→thinking 映射 |
| 1.2 空产出保护 | ✅ 可 | 逻辑小 | 无需拆；但须同步改冲突测试（§3-8） |
| 1.3 注入清单 | ❌ 否 | 含"记账"与"随响应返回"两件事，且流式通道无承载位（§4-②） | 拆 (a) manifest 数据结构与记账；(b) 传输（SSE done 载荷 + 前端） |
| 1.4 真实回归 | ✅ 可 | 但属 live 集成测试，不应进默认 pytest | 拆 unit（mock）+ `@pytest.mark.live`（无 key 跳过） |
| 2.1 装配器 v0 | ❌ 否 | 槽位组装、token 预算、优先级裁剪、manifest 四件事；且无 tokenizer 依赖 | 拆 (a) 槽位装配 + 接缝；(b) 预算/裁剪/manifest |
| 2.2 A 类 5 条规则 | ✅ 可 | 复用 `metrics`/`polish` 已有函数 | 阈值需外置为 config，否则返工 |
| 2.3 新接口 | ✅ 可 | 契约清晰 | 需先定 `CheckReport` schema 与路由前缀归属（§3-9） |
| 2.4 前端审稿页 | ❌ 否 | 三栏 UI + 重写按钮 + route/nav + api.ts 封装 + 鉴权头 + 组件测试 | 拆 (a) 骨架三栏；(b) 交互与测试 |
| 2.5 真实体验 | — | 非编码任务，依赖 2.1–2.4 | 保留 |
| 3.1–3.4 | ⚠️ 3.4 紧 | 3.4 需与全局 `_router` 打通（§3-4），非"简单串行锁" | 3.4 拆：锁对象归属 + router 集成 |

**结论**：2.1 与 2.4 是本 MVP 最重的两块，各需再拆；1.3 必须拆，否则会被 SSE 传输问题反噬。

### Q2 依赖顺序：MVP-2 是否真的不依赖 MVP-3？

| 判断 | 说明 |
|---|---|
| **是，MVP-2 不依赖 MVP-3** | 2.1 的"最近 N 章摘要"在 MVP-2 用手写替身；2.2 是纯 Python（不调本地模型）；2.3/2.4 只消费装配与校验结果。MVP-2 全程走远程（符合 D4），不需要本地队列。 |
| **但有唯一最小依赖：装配器接缝** | 3.3 明确要"替换手写的最近 N 章"。若 2.1 把摘要来源硬编码为"读 `novel.json` 上一章结尾"，3.3 就必须重构。**最小依赖 = 现在就把"摘要来源"抽成 provider 协议**（如 `SummaryProvider.recent(n, up_to_ch)`），MVP-2 用 `HandwrittenSummaryProvider`，MVP-3 换 `SqliteSummaryProvider`。 |
| 隐性依赖 | 2.1 的 manifest 字段形状被 2.4 与 3.3 同时消费；1.3 的 manifest 传输被 2.4 消费 → 这两处接口必须在 MVP-1/2 一次定死。 |

### Q3 验收可测性：哪些"看起来测了其实没测"？

见 **§2 专项审计表**（含逐条更硬断言）。最典型的 6 条：1.3、2.1 裁剪、2.2 定位、3.1、3.3、阶段级 3。

### Q4 遗漏的前置：是否漏了必要前置？

**是，漏了 5 项**，其中鉴权头会导致新页面在浏览器里直接 401。详见 **§3 文件级清单**。计划书自己列的候选（`utils/api.ts` SSE/超时、`X-API-Key`、config schema 迁移、SQLite 路径）**全部属实**，此外还漏了：token 计数依赖、路由/导航注册、既有冲突测试、SSE done 双发与 onDone 无载荷。

### Q5 返工风险排序：哪些决定影响后续阶段？

见 **§4**。最高两处：(1) `writer/context_builder.py` 的槽位/接缝设计；(2) 注入清单经 SSE `done` 的传输与前端 `readSSE` 契约。

### Q6 是否有更小的第一步？

**有。** 见 **§5 结论**。一句话：先让"生成不再静默产空"这一条闭环真实可见，其余全部押后。

---

## 2. 验收可测性专项审计（问题清单 + 更硬断言）

> 判定口径：**可测** = 有确定性输入 → 可断言到具体字段/数值；**伪测** = 只断言"存在/非空/能跑"，无法区分"功能没生效"与"碰巧通过"。

| # | 计划书原文验收 | 判定 | 问题 | 更硬的断言写法（具体到字段/数值） |
|---|---|---|---|---|
| 1.1 | 单测：请求体含 `{"thinking":{"type":"disabled"}}` 且不含 `reasoning_effort` | ⚠️ 偏软 | 只测 payload，未测 config→task 映射；config 字段会被 `_validate_models` 丢弃 | 断言 `mock.post.call_args.kwargs["json"] == {...}` 中 `json["thinking"]=={"type":"disabled"}` 且 `"reasoning_effort" not in json`；再断言 **生成任务** disabled、**规划任务** enabled：`build_payload(task="generate")["thinking"]["type"]=="disabled"`、`build_payload(task="plan")["thinking"]["type"]=="enabled"` |
| 1.2 | mock 返回 reasoning-only → 抛错 + 重试；两次空 → 明确失败 | ❌ 与现状冲突 | 现有 `api_client.py:75` 会**回退** `reasoning_content`，reasoning-only **不会**为空（见 §3-8） | 先定义语义：`content` 空且 `reasoning_content` 空 → `LLMResponse.success is False` 或抛 `LLMEmptyResponse`。断言：`with pytest.raises(LLMEmptyResponse)`；router 层断言 `mock.chat.call_count == 2` 且第二次后返回 `success is False`；**并删除/改写** `tests/test_llm/test_api_client.py:88-120` |
| 1.3 | 响应里能看到 `injection_manifest` 列表（含来源与字符数） | ❌ 伪测 | "能看到"未指字段名/承载事件；流式 `done` 双发且前端 `onDone` 无参（§3-6） | 断言 `done` 事件 `json.loads(data)["injection_manifest"]` 是 `list`，每项含键 `slot_id, source, chars, tokens, truncated`（类型断言），且 `sum(i["chars"] for i in m) > 0`；对检索类 slot 断言 `source` 以 `summary:`/`retrieval:` 前缀 |
| 1.4 | 断言非空且 `reasoning_tokens=0` | ⚠️ 环境依赖 | 需真实 key（`config.yaml` 里 `api_key:''`）与网络，会污染 CI | 拆两层：unit 层 `assert resp.usage["completion_tokens_details"]["reasoning_tokens"] == 0 and len(content.strip())>0`（mock usage）；live 层 `@pytest.mark.live`，无 `DEEPSEEK_API_KEY` 时 `pytest.skip` |
| 2.1 | 输出含全部槽位 + manifest；超限按优先级裁剪 | ⚠️ 偏软 | "按优先级裁剪"无断言；"永不砍风格块与节拍"未测 | 断言 `assembled` 文本含每个 slot 的唯一哨兵串（如 `<SLOT:style_block>`）；给 `budget=总token*0.5` 时：`manifest.total_tokens <= budget`，`{i["slot_id"] for i in dropped} ⊆ {检索类}`，且 `"style_block" not in dropped and "beats" not in dropped`，且 `"<STYLE_SENTINEL>" in assembled` |
| 2.2 | 逐条命中并给出定位 | ⚠️ 偏软 | "定位"未定义（offset？段号？span？） | 断言报告 `items` 中每条含 `rule_id ∈ {chapter_hook, dialogue_ratio, paragraph_length, pov_consistency, forbidden_ai}`、`level ∈ {ok,warn,alert}`、`location` 含 `start:int,end:int`（或 `paragraph_index:int`）、`suggestion:str`。具体：无钩子样例 → `chapter_hook.level=="warn"`；超长段 → `paragraph_length.location.paragraph_index==k and metrics.paragraph_length>300`；视角突跳 → `pov_consistency.metrics.pov_first_ratio>0.5`；禁词 → `forbidden_ai.hits==[{"word":"然而","count":N}]` |
| 2.3 | 返回结构与 schema 一致；报告含 `level/location/suggestion` | ⚠️ 偏软 | 未定响应是裸报告还是 `ApiResponse` 包裹 | 断言 `resp.status_code==200`；若走 `ApiResponse` 则 `body["success"] is True and set(body["data"])=={"report"}`；`report["level"] in {"ok","warn","alert"}`；`all(set(it)>= {"rule_id","level","location","suggestion"} for it in report["items"])` |
| 2.4 | 注入 mock 报告 → 渲染清单；点重写调用接口 | ⚠️ 偏软 | 未断言渲染条数、重写请求体、保存回写 | 断言 `wrapper.findAll('[data-testid=check-item]').length == mock.items.length`；点击后 `fetchMock` 最后一次 URL 为 `/api/generate/chapter/v2` 且 body 含 `rewrite_instruction`；**新增保存断言**：编辑后 `PUT`/`POST` 到章节保存接口，`GET /api/novel/{id}` 返回 `chapters[n].content == 编辑后文本` |
| 2.5 | 人工：能读、能改、能保存 | ✅ 合理（人工） | "能保存"需落到具体接口 | 人工步骤明确：`POST /api/novel/{id}/chapter/{n}`（现有 `ChapterSaveRequest`）→ `GET` 校验 `content` 一致 |
| 3.1 | 输出 JSON 字段齐全；幂等 | ⚠️ 偏软 | "字段齐全"未列字段；幂等未断行数 | 断言 `set(summary) == {"events","characters","state_changes","hook"}`，`isinstance(summary["events"], list) and len(summary["events"])>0`；幂等：连跑两次后 `store.count(chapter=1) == 1` |
| 3.2 | 写入/读取/按范围查询；删章后一致 | ⚠️ 偏软 | "一致"无断言 | 断言 `query(1,5) == [1,2,3,4,5]`；删 ch3 后 `query(1,5)==[1,2,4,5]` 且 `store.get(3) is None`，`total_rows==4`（无孤儿） |
| 3.3 | 第 6 章装配里含第 1 章摘要 | ❌ 伪测 | 手写"main story"可能已含第 1 章内容，混淆来源 | 在第 1 章摘要里埋唯一 nonce（如 `ZQ-NONCE-1`），断言 `nonce in assembled` 且 `manifest` 有 `source=="summary:L1:ch1"`；再断言 main-story 常量**不含**该 nonce，排除巧合 |
| 3.4 | 并发触发生成与摘要时摘要排队 | ⚠️ 偏软 | "排队"未断时序 | 断言并发记录的时间线：`summarize_start_ts >= generate_end_ts`（或两者不重叠区间），并断言**同一时刻**在跑的任务数 `==1`（用计数器 `max_concurrent==1`） |
| 阶段级 3 | 删第 1 章摘要 → 第 6 章"可观察失忆" | ❌ 伪测（不可靠） | 依赖 LLM 随机性，temperature>0 时同一输入两次结果不同，无法稳定证明因果 | **改在确定性层测量**：断言 `context_builder` 输出在"有/无 ch1 摘要"两次装配的 `assembled` 差异，且 `manifest` 中 `summary:L1:ch1` 从存在变不存在。LLM 输出层只做**定性人工复核**，不作自动化门禁 |
| M1 里程碑 | 连续多次生成不再空正文 | ⚠️ 偏软 | "多次"无次数 | 断言 `N=5` 次真实生成 `all(len(strip_fallback_prefix(c))>0)`；并断言空产出时 SSE 发 `event: error` 而非 `done` |
| M3 里程碑 | 连续 6 章不失控 | ⚠️ 偏软 | "不失控"无阈值 | 断言第 6 章装配 `manifest.total_tokens <= budget`，且 `summary:L1:ch1` 在 manifest 中 |

**总评**：1.3、2.1（裁剪）、2.2（定位）、3.3、阶段级 3、M1/M3 共 7 条需要按上表改写后才算可测。其中 **阶段级 3 与 3.3 是"用 LLM 输出证明记忆生效"的典型伪测**，必须下沉到装配器/manifest 的确定性断言。

---

## 3. 遗漏的前置依赖（文件级）

| # | 缺失前置 | 涉及文件（具体位置） | 为什么是前置 / 不做的后果 | 建议 |
|---|---|---|---|---|
| 1 | **前端鉴权头完全缺失** | `src/frontend/src/utils/api.ts:6-9`（axios 实例无 `X-API-Key`）；`:146-150`、`:165-169`、`:188-192`（3 个 SSE `fetch` 无头）；`config/config.yaml:45-49` 已设 `security.api_key`；中间件 `src/story_engine/api/main.py:65-82` | 现网配置下，浏览器所有 `/api` 请求都会 401；新审稿页与 `/api/check/chapter` 同样 401 → MVP-2 前端**直接跑不起来** | 在 axios 加请求拦截器注入 `X-API-Key`（从 `VITE_API_KEY`/设置读取），并给 3 个 SSE `fetch` 加同一头；补一条前端测试断言请求头存在 |
| 2 | **config schema 会吞掉新字段** | `src/story_engine/core/config.py:49-59`（`_LLMModelConfig` 白名单）、`:62-77`（`_validate_models` 用 `model_dump()`） | 往 `config.yaml` 写 `thinking`/`reasoning_effort`/`task_type` 会被 `model_dump()` 静默剥离 → "config 驱动"变成空操作，1.1 看似通过实则无效 | 扩展 `_LLMModelConfig` 字段，或改 `model_dump(exclude_none=False)` 前 `extra="allow"`；补单测：含 `thinking` 的配置经 `_validate_models` 后仍在 |
| 3 | **SQLite 与 `data/novels` 路径约定未定** | 现有全局库 `src/story_engine/style/db.py:22-23`（`data/style_profiles/style_profiles.db`）；per-novel 目录解析 `src/story_engine/tools/novel_storage.py:134-142`（自定义路径走 `.index.json`）；样本 `data/novels/novel_ae0fa8d5`（自定义路径） | 若 MVP-3 把 `summaries.db` 天真放到 `NOVELS_ROOT/{id}/`，**自定义路径小说**（已索引、真实目录在别处）会写错位置或丢失 | 明确：`memory/store.py` 必须用 `novel_storage._novel_dir(novel_id)` 取真实目录，DB 放 `{real_dir}/summaries.db`；补一条"自定义路径小说也能存取摘要"的测试 |
| 4 | **离线队列与现有 router 未打通** | `src/story_engine/llm/router.py`（无 GPU 串行/互斥）；`src/story_engine/llm/local_client.py:34,110`（`asyncio.Lock` 仅护 warmup）；`src/story_engine/api/routes/generate.py:37-52`（全局 `_router` 懒加载） | MVP-3 3.4 的"简单串行锁"若不与全局 `_router` 共享，交互式写作与离线摘要仍会并发抢显存；且 `router.chat` 默认 `fallback=True` 会把离线任务**静默路由到远程**，违反 D4 | 定义全局 `TaskQueue`（单锁）供 `generate.py` 与 `memory/queue.py` 共用；离线任务调用时 `model_name=本地模型, fallback=False`；补 `max_concurrent==1` 断言 |
| 5 | **流式通道无 manifest/usage 承载位 + SSE done 双发** | `src/story_engine/llm/router.py:99-150`（`chat_stream` 仅 yield `str`）；`src/story_engine/api/sse.py:40-64`（生成器结束后**再补一个** done）；`src/story_engine/api/routes/generate.py:218`（先 yield `{"done":True,"chapter":...}`）；`src/frontend/src/utils/api.ts:15-60`（`readSSE` 首个 done 即 return，`onDone` 无参） | 1.3 的 manifest 无处可放；即便放 `done`，前端读不到（首个 done 提前 return、onDone 无载荷）→ 1.3"不改前端"与"能看到"自相矛盾 | 定契约：SSE 只发**一个** `done`，载荷 `{"done":true,"chapter":...,"injection_manifest":...,"usage":...}`；`sse.py` 不再补发；`readSSE.onDone(payload)` 接收载荷 |
| 6 | **token 计数无依赖/无策略** | `pyproject.toml` 依赖清单（无 tiktoken/transformers）；2.1 manifest 要"各占多少 token" | 无计数口径则预算/裁剪无法实现，manifest 的 `tokens` 字段无从谈起 | 明确用启发式（中文 `len(text)` 或 `len/1.2`）并在 manifest 标注 `token_estimate: true`；或显式加依赖并记录 ADR |
| 7 | **前端路由/导航注册未列入任务** | `src/frontend/src/router/index.ts:5-46`（仅 6 条路由）；`src/frontend/src/App.vue:13-36`（硬编码菜单项） | "只新增审稿页、不改写作页"不等于"不改路由/导航"；不注册则页面不可达 | 任务 2.4 显式包含：新增 `/review` 路由 + App.vue 菜单项 |
| 8 | **既有测试与新行为冲突** | `tests/test_llm/test_api_client.py:88-120`（`test_chat_content_falls_back_to_reasoning`、`test_chat_content_empty_string`）明确断言"空 content 回退 reasoning" | MVP-1.2 要求空产出抛错，会**直接打红**这两个既有测试；计划书要求"pytest 全绿"却未列入改动 | 在 MVP-1 明确列出需改写/删除的这两条测试，并说明新语义（reasoning 是否算有效正文） |
| 9 | **校验路由归属与前缀冲突** | 计划把 check 放 `api/routes/generate.py` + `api/schemas.py`，但该 router 前缀是 `/api/generate`（`generate.py:26`），而路径是 `/api/check/chapter` | 前缀不匹配 → 路由注册到错误命名空间或需新模块却漏 `include_router`（`main.py:101-108`） | 新建 `api/routes/check.py` 并 `main.py` 注册；或在计划中明确改为 `POST /api/generate/check` |
| 10 | **漂移检测缺基线来源** | `src/story_engine/style/drift.py:127-252`（`detect_drift` 需 `baseline`）；2.2 拟复用它 | 第 1 章无历史，`baseline` 全 0 → 偏差被放大为 alert（`_deviation` 除 floor），产生大量误报，规则形同虚设 | 2.2 明确基线来源：来自风格画像（`style/db.py`）或前序章节 `build_baseline`；无基线时对应规则返回 `ok` 或 `skipped`，并断言该行为 |
| 11 | **覆盖率门禁** | `pyproject.toml`：`addopts` 含 `--cov-fail-under=75` | 新增 `context_builder/check/memory` 大量代码若测试不同步，整体覆盖率跌破 75 → CI 红 | 每模块随代码交付测试；里程碑验收显式包含覆盖率不降 |

---

## 4. 任务粒度与依赖顺序 → 返工风险

### 4.1 最可能返工的两处（按代价排序）

**返工点 ①：装配器接口形状（2.1）—— 影响阶段 Ⅲ/Ⅳ/Ⅴ**

- 现状：`writer/engine.py:83-103` 已有 `_build_character_context` / `_build_previous_summary`（滑动窗口 5 章、纯字符串拼接），`_build_world_context` 调 lorebook。
- 风险：若 2.1 把槽位写死为"固定拼接 + 字符串"，则：
  - 3.3 换真实摘要 → 改 `context_builder.py`；
  - 阶段 Ⅲ 设定库、Ⅳ 技法、Ⅴ 素材都要各自往装配器加"按需检索"槽位 → 再改；
  - manifest 结构随槽位扩展反复变 → 连带 2.4 审稿页显示、2.3 契约测试、1.3 传输全部返工。
- 代价：一次装配器重构 ≈ 重写装配逻辑 + manifest + 下游 3 处测试 + 审稿页 manifest 面板；且跨 3 个阶段反复发生。
- **建议**：现在就把装配器定义为**槽位注册表**：`Slot(slot_id, priority, provider, renderer)` + 统一 `ContextManifest{slot_id, source, chars, tokens, truncated}`。MVP-2 只注册 5 个槽位，后续阶段"加注册项"而非"改装配器"。

**返工点 ②：注入清单的传输契约（1.3 ↔ 2.4）—— 影响所有"生成可解释"需求**

- 现状：`router.chat_stream` 只 yield `str`；`sse.py` 补发第二个 done；前端 `readSSE` 首个 done 即返回且 `onDone` 无参。
- 风险：若 1.3 按"不改前端、后端能看到"实现（例如塞进日志或裸 dict），则 2.4 一旦要在 UI 显示"本次注入了什么"，就必须重定事件协议、改 `sse.py`、`generate.py`、`api.ts`、审稿页测试。架构 §4.1 明确"草稿自带依据"是省作者时间的核心手段 → 该传输是**产品级刚需**，不是可选。
- 代价：触及 4 个文件 + SSE 端到端测试；若 M1 已发版，还要兼容旧前端。
- **建议**：M1 就定死：单一 `done` 事件携带 `chapter + injection_manifest + usage`；`readSSE.onDone(payload)`。1.3 的"能看到"改为"在 done 载荷中断言"。

### 4.2 依赖顺序结论

| 顺序 | 判断 |
|---|---|
| M1 → M2 → M3 | 正确，无需重排 |
| M2 内部 | 2.1 必须在 2.3/2.4 之前定 manifest/slot 契约；2.2 可与 2.1 并行，但阈值须外置 config |
| M2 ↔ M3 | M2 不依赖 M3；唯一接缝是"摘要 provider"，须在 M2 预留 |
| 隐患 | 1.3 若延到 M2 才定传输，会与 2.4 耦合爆炸 → **1.3 的传输契约应在 M1 与 1.2 一并定** |

---

## 5. 结论与最小第一步

### 5.1 结论

**需补充后开工**（不是"需重排"：分期与顺序成立；不是"可开工"：5 项硬前置未补，其中鉴权头会让前端直接不可用）。

开工前必须闭环的补充项（对应 §3 编号）：

1. 前端 `X-API-Key` 注入（#1）
2. config schema 放行 `thinking`/task 字段（#2）
3. SQLite 路径约定（#3）
4. SSE 单一 `done` + manifest 载荷契约（#5）
5. token 计数策略（#6）
6. 既有冲突测试的处置（#8）
7. 校验路由归属（#9）
8. 漂移基线来源（#10）

### 5.2 如果只做一件事先看到效果

**目标**：消除"静默空正文"（架构 §7 阶段 Ⅰ 的第一条可验证结果），且能被真实接口直接观察。

**最小改动（具体到文件与函数）**：

| 文件 | 函数 | 改动 |
|---|---|---|
| `src/story_engine/llm/base.py` | `LLMRequest` | 增 `task: str = "generate"`（或 `thinking: bool`）字段 |
| `src/story_engine/llm/api_client.py` | `OpenAIClient.chat_stream`（`:93-122`）与 `chat`（`:58-91`） | 按 `task` 注入 `payload["thinking"]={"type":"disabled"}` 与显式 `temperature`；流式累计 token，结束时若为空则抛 `LLMStreamError`/`LLMEmptyResponse` |
| `src/story_engine/llm/router.py` | `ModelRouter.chat_stream`（`:99-150`） | 将"零 token 正常结束"识别为空产出并转 `LLMStreamError`，避免 fallback 把空流当成功 |
| `src/story_engine/api/routes/generate.py` | `_stream_chapter`（`:159-218`） | 空产出时走 `error` 事件而非 `done`（`sse.py` 已支持） |

**验收（硬断言）**：`pytest tests/test_llm -q` 中新增 mock 用例：`content=""` 且 `reasoning_content=""` → `success is False`；对真实 `POST /api/generate/chapter` 连跑 5 次，`all(len(content.strip())>0)`，空产出时 SSE 收到 `event: error`。

> 说明：`api_client.py:75` 当前会把 `reasoning_content` 当正文回退，因此"空正文"实际只发生在 **流式路径**（`:116-118` 不读 reasoning）与"reasoning 也为空"时。这一步同时收口非流式语义，是整条链最便宜、收益最高的一刀。

---

## 6. 修改建议清单（可直接落到计划书）

| 编号 | 建议 | 落点 |
|---|---|---|
| R1 | 1.3 拆为"记账"与"传输"；传输契约在 M1 定死（单一 done + manifest + usage） | 计划 §2 MVP-1 |
| R2 | 2.1 拆为"槽位装配（含 provider 接缝）"与"预算/裁剪/manifest"；先定义 `Slot`/`ContextManifest` | 计划 §2 MVP-2 |
| R3 | 2.4 拆为"骨架"与"交互+测试"；补路由/导航/鉴权头/api.ts 封装 | 计划 §2 MVP-2 |
| R4 | 所有验收按 §2 表改写为字段级断言；阶段级 3 下沉到装配器确定性层 | 计划 §2/§6 |
| R5 | 新增前置任务块"P0 前置"，含 §3 的 #1–#11 | 计划 §2 之前 |
| R6 | 明确 SQLite 用 `_novel_dir()`，并覆盖自定义路径小说用例 | 计划 §2 MVP-3 |
| R7 | 离线队列与全局 `_router` 共享单锁，离线任务 `fallback=False` | 计划 §2 MVP-3.4 |
| R8 | 1.4 改为 mock 单测 + `@pytest.mark.live` 分离，避免 CI 依赖网络 | 计划 §2 MVP-1.4 |
| R9 | 显式列出需改写的既有测试 `test_api_client.py:88-120` | 计划 §2 MVP-1.2 |
| R10 | 校验路由新建 `api/routes/check.py` 并在 `main.py` 注册（或统一改前缀） | 计划 §2 MVP-2.3 |

---

## 附录 A：核验证据索引

| 结论 | 证据位置 |
|---|---|
| 前端无鉴权头 | `src/frontend/src/utils/api.ts:6-9,146-150,165-169,188-192`；`config/config.yaml:45-49`；`src/story_engine/api/main.py:65-82` |
| config 吞字段 | `src/story_engine/core/config.py:49-59,62-77` |
| 既有测试冲突 | `tests/test_llm/test_api_client.py:88-120` |
| 空正文根因 | `src/story_engine/llm/api_client.py:75,116-118`；`src/story_engine/llm/local_client.py:141,188` |
| SSE 双 done / 前端无载荷 | `src/story_engine/api/sse.py:40-64`；`src/story_engine/api/routes/generate.py:218`；`src/frontend/src/utils/api.ts:15-60` |
| 自定义路径小说 | `src/story_engine/tools/novel_storage.py:75-77,116-142,244-268`；`data/novels/novel_ae0fa8d5` |
| 全局 SQLite 先例 | `src/story_engine/style/db.py:22-23` |
| 漂移需基线 | `src/story_engine/style/drift.py:96-106,127-177` |
| 路由注册点 | `src/story_engine/api/main.py:101-108`；`src/story_engine/api/routes/generate.py:26` |
| 覆盖率门禁 | `pyproject.toml`（`--cov-fail-under=75`） |
| 无 check/injection 实现 | `rg "check/chapter\|/api/check\|injection_manifest\|LLMEmptyResponse"` 无命中 |
