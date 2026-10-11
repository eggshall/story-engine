# N3 评审报告（只读）

## 1. 结论

**需补充后通过** —— N3 的字面目标（config 放行 `thinking`/`task`、不被静默剥离、有真实断言）已达成且测试真实有效；但新增的"模型级默认 task"会波及多个未显式传 task 的正文/对话端点，且 `_validate_task` 的"不连坐整条配置"承诺对非字符串值并不成立，建议修掉这两条再提交。

---

## 2. P0（必须修）

无。实测当前 `config/config.yaml` 未设置任何 `task`/`thinking`（见 `scripts/check_config_models.py` 输出），因此默认值 `"generate"→""` 对现有 7 个调用点**无行为回归**（见 §5），不存在已激活的 bug。

---

## 3. P1（应该修）

### P1-1 模型级 `task` 会静默改变未显式传 task 的正文/对话端点
`api_client.py:94` 的解析是 `request.task or self.default_task or TASK_GENERATE`，而请求级默认已改为 `""`（`base.py:29`）。于是**任何没显式传 `task=` 的调用点都会继承 config 的 `task`**。当前未传 task 的调用点：

- `src/story_engine/api/routes/generate.py:302`（`/api/generate/chat` 自由对话）
- `src/story_engine/api/routes/generate.py:364`（`/api/generate/depolish` 去 AI 味）
- `src/story_engine/api/routes/style.py:240`（文风写作）
- `src/story_engine/writer/engine.py:198` / `:241`（`write_chapter`/`draft_chapter`）

只有 `generate.py:197`（章节正文）和 `engine.py:130`（大纲）显式传了 task。若某模型配置 `task: plan`，上列端点会**开启思考且不再发 temperature**（`api_client.py:95-109`），正是 N1 要消灭的"静默退回思考模式"（可能 reasoning 吃满 max_tokens → 空产出）。`draft_chapter` 的 `max_tokens=1000` 尤其脆弱。

证据：`api_client.py:96-97,108-109`；`generate.py:302-307` 与 `:364-369` 的 `LLMRequest(...)` 均无 `task=`。

建议（二选一）：
1. 在所有正文/对话调用点显式传 `task="generate"`（`chat`/`depolish`/`style`/`write_chapter`/`draft_chapter`），并补一条断言"这些端点请求体内 `thinking==disabled`"；或
2. 把优先级反过来：请求级默认保持 `"generate"`，config 的 `task` 需要请求显式"继承"才生效（更符合现有 N1 契约）。

### P1-2 `_validate_task` 的"不连坐整条配置"对非字符串值不成立
`config.py:103-107` 明确承诺"task 写错 → 降级为未设置……不连坐整条模型配置"，但 `task: Optional[str]`（`config.py:96`）在 Pydantic 类型校验阶段就失败，`field_validator`（默认 `mode="after"`）根本没机会跑。实测：

```
task=5      -> []   （整条模型被过滤）
task=True   -> []
task=["plan"] -> []
task={"a":1} -> []
task="genrate" -> [{'task'? 无, 保留模型}]   # 只有字符串拼错才走降级
```

证据：`tests/test_config_llm_schema.py:133-141` 只测了字符串拼错；非字符串路径无测试（属"看起来测了其实没测"，见 §4）。
建议：`task: Any`，或在 `field_validator(mode="before")` 里把非字符串/非法值统一降级为 None 并告警。

---

## 4. P2（可选优化）

1. **`thinking` 无值域校验，非法 dict 原样发给上游**：`config.py:98` 是 `Optional[Dict[str, Any]]`，`api_client.py:105` 直接 `payload["thinking"] = self.thinking_override`。配置 `thinking: {"type": "xxx"}` 会原样发给 deepseek，可能 400（恰是 N1 评审 P2-1 反对的"乱发"）。建议加 `Literal["enabled","disabled"]` 校验或白名单。
2. **provider 间语义不一致**：`thinking_override`/`default_task` 只在 `OpenAIClient` 消费，`AnthropicClient`（`api_client.py:205+`）与 `LocalLLMClient`（`local_client.py`）完全忽略 `task`/`thinking`。真实配置的 `default_model` 恰是本地 `qwen3.5-9b-q6`——给它写 `task`/`thinking` 是静默空操作，与 N3"config 驱动"的本意部分背离。至少应在文档/注释里写明"仅 deepseek/openai provider 生效"，或让本地客户端也把思考关掉。
3. **`weight` 是死字段**：`config.py:90` 放行，但 `rg weight src/story_engine` 无任何读取方（`router.py::_pick_target` 只按名字/default/首个）。放行它确实避免了"静默剥离"，但当前=养了一个不生效的字段。建议在 `_pick_target` 里真正实现按 weight 选目标，或加注释说明"预留给 N4/离线调度"。
4. **`exclude_none=True` 的两处副作用**（实测）：
   - 显式写 `read_timeout: null`/`task: null` 会被抹掉 → 再看 `_build_router_locked`（`generate.py:67-70`）注入全局值，等价于"用户显式 null 被改成全局值"；
   - **未知字段若值为 None**：仍会告警，但被 `exclude_none` 从输出丢弃（`typo_null` 不进 `model_dump`），与 config.py:74 "原样保留" 文档略有出入。
5. **`save()` 会把未知/拼错字段写回 config.yaml**：`config.py:144` 的 extras 进入 `_data`，`config.py:198-202` 的 `save()` 原样落盘，调用点见 `routes/models.py:85`、`routes/system.py:105`、`cli.py:295`。即一次 typo 键会被持久化（可见性提升，但也会把垃圾写进正式配置）。若担心，可在 `save()` 前剔除 `model_extra` 或至少再告警。
6. **新脚本 lint 不过**：`scripts/check_config_models.py:15` ruff `I001`（import 未排序）。CI 只跑 `ruff check src tests`（`.github/workflows/ci.yml:25`）所以不挡红，但 AGENTS.md §5 要求"ruff 全绿"，建议 `ruff --fix`。
7. **E2E 时间断言余量偏薄**：`tests/e2e/test_n3_per_model_timeout_real_http.py:75` 只断言 `elapsed < 3.0`（模型级 1s vs 上游 3s）。逻辑上已能证伪"用全局 60s"（那样会 3s 后成功、`event: error` 不出现），但改成 `elapsed < 2` 更能锁定"用的是 1s"。
8. **仓库内残留评审脚手架**：未跟踪的 `docs/design/reviews/N3-REVIEW.md` 目前只有 4 行工具叙述（往次中断产物），提交前请用正式评审内容覆盖，别把这 4 行带进历史。

---

## 5. 已核实为正确的地方（实测）

- **extras 确实保留**：`extra="allow"`（`config.py:79`）+ `model_dump` 会带上未知字段；`test_unknown_key_is_kept_and_warned` 实测通过。
- **可选字段缺省不再以 None 出现**：`test_config_p1.py:73-80` 断言 `read_timeout`/`task` 不在输出里，这正是 `api_client.py:43` 的 `config.get("read_timeout") or ...` 与 `generate.py:67-70` 的 `"read_timeout" not in m` 能正确回退的前提。
- **模型级 read_timeout 真正落到 HTTP 层**：跑 `tests/e2e/test_n3_per_model_timeout_real_http.py` → `2 passed in 5.06s`。我核对了 `write_config` 未设 `llm.read_timeout`（`fake_upstream.py:211-225`），若字段被剥离，`api_client.py:43` 会回退 60s，测试一会在 3s 后成功、`event: error` 不出现→必然失败；单模型故无 fallback、非空错误不重试（`router.py:117-122`），断言不可被绕过。
- **默认 `task=""` 对生产链路无回归**：`rg 'LLMRequest\('` 的 7 个调用点中，`generate.py:197`/`engine.py:130` 显式传值，其余 5 个当前 config 无 `task`（`check_config_models.py` 输出 `task=(未设置)`）→ 解析回 `generate`，与改前一致；`tests/test_writer/test_api_empty_output_e2e.py:90-91` 仍断言 `stream_task=="generate"`/`tasks==["extract"]` 通过。
- **既有测试改动是正常契约同步，非弱化**：`test_thinking_contract.py:89` 由 `== "generate"` 改为 `== ""`，但随后仍断言 `payload["thinking"]=={"type":"disabled"}` 与 `temperature`（`:93-94`），测的是解析后行为；`test_config_p1.py:73-80` 是新增字段 `weight` 的同步 + 强化断言。
- **静态检查**：`.venv/bin/ruff check src tests` → All checks passed；`.venv/bin/mypy src/story_engine` → Success；`pytest tests/test_llm tests/test_config_p1.py tests/test_config_llm_schema.py tests/test_writer tests/e2e` → `234 passed, 3 skipped`。
- **未越界**：`rg reasoning_effort src` 确认全仓只发注释/断言、无发送路径；前端 `src/frontend` 无 `task/thinking` 引用，N3 未触碰 SSE 契约。

---

## 6. 未覆盖的风险 / 我的判断可能有误之处

- **N3 未跑浏览器 E2E**：N3 纯后端改动，我判断无需 Playwright；若流程强制每节点真浏览器冒烟，请以实际执行为准。
- **P1-1 的严重度取决于产品意图**：若约定"`task: plan` 只标给规划用途的专用模型、且不用于正文端点"，则当前实现在真实配置下无触发路径，可算 P2。但 `chat`/`depolish`/`style` 与规划共用同一默认模型时就会中招。
- **`weight` 的"死字段"判断依赖路线图**：若 N4/N7 计划用它做离线调度，放行即合理；我未在 `docs/design/P7-MVP-PLAN.md` 找到其消费者，故按当下代码判定。
- **E2E 时间断言在 CI 高负载下可能抖动**：本机 5.06s 通过，未在多并发环境验证。
- **我未深入核对 `Config.save()` 的全部调用链**（只静态确认 3 处 `save()`），未知字段回盘的实际持久化效果建议补一条单测。
