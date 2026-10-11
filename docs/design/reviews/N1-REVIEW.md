I'll perform the N1 review. Let me start by examining the commit and relevant files.
# N1 评审报告 — 远程模型调用契约

## 1. 结论

**需补充后通过**：核心契约（thinking 开关 / 温度 / 空产出守卫）实现正确且对远程 OpenAI 兼容客户端有效，649 passed/3 skipped、ruff/mypy/vitest 全绿；但与 `docs/design/P7-MVP-PLAN.md` 的 N1/1.2 验收相比，**路由层"重试 1 次并记录"缺失**、**本地默认模型路径仍无空产出守卫**、**E2E 未达 9.3 的"真实 HTTP + X-API-Key"标准**，另有若干鲁棒性/兼容性缺口，需补充后再归档。

---

## 2. P0（必须修）

在本次提交定义的功能范围内，未发现会直接打断现有链路的确定性缺陷。唯一"可能致命但未验证"的点见 P1-1（建议按 P0 对待，先验证再合并）。

---

## 3. P1（应该修）

**P1-1 `thinking` 参数只在"非配置模型"上被真实验证过（高危兼容性）**
- 证据：`tests/test_llm/test_thinking_live.py:41` 固定 `model_id: "deepseek-flash"`，而实际运行配置 `config/config.yaml:8,17` 的 `model_id` 是 `deepseek-chat`。live 测试（默认 skip）没有覆盖真正会跑的模型；commit message 里"实测 generate 成功"与测试文件用的 model_id 不一致。
- 风险：若 `deepseek-chat` 对未知字段 `thinking` 做严格校验（commit 自己已观察到 `reasoning_effort` 与 `disabled` 共存会被 API 拒绝，说明该 API 会校验参数），则**所有正文/大纲生成会 400 全挂**，属于比"静默空正文"更严重的回归。
- 建议：live 测试改用配置里的 `deepseek-chat`（或参数化 v4-pro/flash），并把"send thinking disabled 后 HTTP 200"作为 live 断言；确认后再合并。

**P1-2 未知/拼错的 `task` 会静默退回"开启思考且丢温度"——正是 N1 要消灭的 bug**
- 证据：`src/story_engine/llm/api_client.py:76-80` 是 `if task in _NO_THINKING_TASKS: disabled else: enabled`。除 `"plan"` 外的任何值（含 typo `"geneate"`）都落到 `else`，于是 `thinking=enabled` 且不发送 temperature。
- 建议：显式白名单校验，非法值直接抛 `ValueError`（或至少默认 `disabled`）；补一条"未知 task 报警/不静默开启思考"的单测。这是防止本 bug 复发的关键防线。

**P1-3 本地客户端完全不受契约保护，而它正是默认模型**
- 证据：`config/config.yaml:2` `default_model: qwen3.5-9b-q6`（provider=local）。`src/story_engine/llm/local_client.py` 既不读 `request.task`，也不做空产出判定：`chat()`（:141）仍回退 `reasoning_content` 且无空内容失败分支；`chat_stream()`（:158-194）零 token 时**不抛异常**，正常结束 → `sse.py` 会补 `event: done` + 空正文。
- 结论：远程路径修好了，但默认路径的"静默空正文"依旧存在。保留 reasoning 回退本身合理（Qwen 兼容、已注释），但"空产出即失败"的守卫应下沉到 `BaseLLM`/router 或至少在 local 客户端复用。建议至少在 N1 收尾时补一条 local 的空产出守卫（或明确记录为已接受风险并开 follow-up 节点）。

**P1-4 计划书 1.2 的"路由层重试 1 次并记录"未实现**
- 证据：全仓 `rg "retry|重试|LLMEmptyResponse"` 仅命中 `sse.py:64` 的文案；`router.chat/chat_stream` 无重试逻辑，空产出直接落到 fallback 或失败。`docs/design/P7-MVP-PLAN.md:64` 明确要求"路由层重试 1 次并记录"，:`78` 要求断言 `mock.chat.call_count == 2`。
- 建议：补 router 层一次性重试 + 日志，并加对应单测；或将此条显式移出 N1 并在节点表登记。

**P1-5 N1 的 E2E 未达 9.3 标准（改了 SSE 跨层行为却没按标准取证）**
- 证据：`tests/test_writer/test_api_empty_output_e2e.py` 用 `fastapi.testclient.TestClient`（ASGI 进程内，不是真实 HTTP socket），且 `test_config` 关掉鉴权、**未带 `X-API-Key`**；模型调用是被 mock 的 router，不是"本地假 OpenAI 兼容 server"，也不是 `@live`。而 `docs/design/P7-MVP-PLAN.md:206` 要求"真实 app + 真实 HTTP（含 X-API-Key）"，`AGENTS.md §5` 同。
- 建议：至少补一条走真实 HTTP（起 uvicorn 或用 `httpx` 打本地 ASGI）并带鉴权头的 SSE 用例；或把"error 无 done"断言并入既有真实 HTTP E2E 套件。

**P1-6 前端把 error 文本当正文落盘**
- 证据：`src/frontend/src/utils/api.ts:83-92`（`event: error` 无 `onError` 时 yield `` `\n[Error: ...]` ``）+ `src/frontend/src/views/WritingView.vue:324-333`（把每个 token 累加进 `currentChapter.content` 后 `saveCurrentChapter()`）。后端现在返回的"模型返回空产出…"会作为**章节正文被保存**。
- 说明：前端确实"认识"error 事件、没有吞掉（这一点是对的），但调用方把它当普通 token 持久化。MVP-1 声明"不改前端"，但 N1 改变了错误时序，应至少在下一节点（N2）修掉，或在本条登记；当前未提交的 `api.sse.spec.ts:151-163` 只断言 `[Error:` 可见，未断言"不落盘"。

---

## 4. P2（可选优化）

- **P2-1 provider="openai" 会被强塞 `thinking`**：`router.py:36-37` 把 `openai` 也交给 `OpenAIClient`，而 `_build_payload`（:76-84）对所有 OpenAI 兼容 provider 无条件发 `thinking`。docstring 声称兼容 Qwen/Kimi（:21），但不同厂商字段名不同（如 DashScope `enable_thinking`），发错字段可能 400。建议按 provider 决定，或至少在配置注释中收窄适用范围。
- **P2-2 AnthropicClient 完全忽略 `task`**：`api_client.py:216-247` 未读 `request.task`，`LLMRequest.task` 的语义在 Anthropic 上静默失效（该 provider 默认 disabled，非当前现网）。契约若声称"任务类型决定思考模式"，应补齐或明确注释为"仅 OpenAI 兼容远端"。
- **P2-3 流式空白未按"纯空白"判失败**：非流式用 `.strip()` 判定（:98），流式用 `yielded_chars += len(content)`（:151）计的是原始字符，纯空白 token 会通过。建议流式同样累计 `len(content.strip())`。
- **P2-4 陈旧注释**：`tests/test_llm/test_api_client.py:1` 模块 docstring 仍写"reasoning 回退"，与已改写的 `TestReasoningNoLongerFallsBack` 不符。
- **P2-5 契约位置建议**：把"task→思考模式"策略放在 `OpenAIClient._build_payload` 尚可，但更稳妥的是在 `BaseLLM` 暴露 provider-agnostic 的 `build_payload`，各子类覆写 provider 细节；这样 `AnthropicClient`/`LocalLLMClient` 不会各自漂移。当前迁移成本低，越晚改越痛。

---

## 5. 已核实为正确的地方（实测）

- **全量测试真绿**：`.venv/bin/python -m pytest -q` → `649 passed, 3 skipped`，覆盖率 `93.71%`（≥75 门禁）；`ruff check` 全过；`mypy src/story_engine` 无错。
- **payload 契约实现无误**：`api_client.py:64-85`；`test_thinking_contract.py:84-123` 断言的是**生产方法** `_build_payload` 经 `http.post.call_args` 的真实输出（不是工具函数），非"假绿"：generate/extract → `thinking=disabled` + `temperature` 下发 + `reasoning_effort` 不出现；plan → `thinking=enabled` + 不带 `temperature`。
- **非流式空产出语义正确**：`:98-114` 对 `content=None`/`""`/纯空白一律 `success=False` 且 error 含"空产出"，不再回退 reasoning；`test_api_client.py:91-129` 与 `test_thinking_contract.py:128-141` 双重覆盖。
- **流式零 token 守卫正确**：`:160-166` 在流结束后按累计字符判失败并抛 `LLMStreamError`；`router.chat_stream` 能捕获并 fallback（`test_thinking_contract.py:168-199` 验证"空产出 → 切到 backup 并带 `[Fallback → backup]`"）。
- **SSE 层语义正确**：`sse.py:40-64` 捕获 `LLMStreamError` → `event: error`，且异常路径**不会**走到 `:57` 的补发 `done`；E2E `test_api_empty_output_e2e.py` 确实穿过 `EventSourceResponse(event_stream(...))`（断言 `event: error` 存在、`event: done` 不存在），这一层没有被绕过。
- **调用点核对**：全仓 `LLMRequest(` 构造点已逐一核对——`generate.py:296/358`、`style.py:240`、`engine.py:198/241` 均为创作/改写类，默认 `task="generate"` **语义相符**；`engine.py:130`（大纲 JSON）标 `extract`、`generate.py:193`（正文，`max_tokens=word_estimate*2` 高危点）标 `generate`，与契约一致。`plan` 分支目前在生产代码中**无调用点**（仅测试使用），属计划中的预留，无回归。
- **前端确实识别 error 事件**：`api.ts:83-92` 有独立分支，不会把 `event: error` 当普通 data 或吞掉；未提交的 `api.sse.spec.ts:151-163` 用真实 node:http 流验证了"error → 可见文本、只请求一次"。
- **live 测试门控正确**：`test_thinking_live.py` 通过 `pytestmark`+`skipif(STORY_LIVE!=1)` 且缺 `DEEPSEEK_API_KEY` 时 skip，默认不计费不污染 CI。

---

## 6. 未覆盖的风险 / 我的判断可能有误之处

1. **无法验证 `deepseek-chat` 是否接受 `thinking` 字段**（P1-1）。我依据的是"test model_id 与 config 不一致"这一客观事实；若确实用配置模型手动验证过，则 P1-1 可降为 P2。
2. **本地路径是否算 N1 范围**（P1-3）。commit 与测试注释都明确把 local 排除在契约外，所以严格按节点定义它不算漏项；但鉴于它是默认模型，我倾向按 P1 提出。
3. **重试算不算 N1 范围**（P1-4）。节点表 N1 摘要只说"空产出守卫 + 既有冲突测试改写"，是 MVP-1 的 1.2 细则要求重试；若团队把重试留给后续节点，则这是"登记而非缺陷"。
4. **工作区状态**：`src/frontend/src/utils/__tests__/api.sse.spec.ts` 的 N1 错误用例是**未提交**改动，`docs/design/reviews/N1-REVIEW.md` 是一个未跟踪的残留占位。也就是说"N1 提交"本身不含任何前端文件（已用 `git show --name-only 3693fa6` 确认）。请确认前端对该契约的测试是否应随 N1 一起提交。
5. 我未读任何密钥值，也未调用真实 API；所有关于 DeepSeek 参数行为的结论均来自 commit message 与测试自述。
