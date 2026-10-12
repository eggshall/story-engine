# N9 评审报告（伏笔账本 + 注入 + 校验）

> 评审方式：`opencode run --agent requirements`（**只读**评审，未改代码）
> 评审日期：2026-10-12
> 输入：`docs/design/P7-MVP-PLAN.md` §9.1.1 + 本节点全部改动（见 commit message）
> 说明：以下为报告正文（原会话含工具调用噪声，此处只留结论）

---

# N9 评审报告（伏笔账本 + 注入 + 校验）

## 先说结论性的核对结果

- `threads/manager.py` 行覆盖 **100%**；用户点名的三个易漏分支——`advance_thread` 非法状态（`test_invalid_status_rejected`）、`model_copy` 更新路径（`test_advance_to_paid_off...`）、镜像删除路径（`test_deleted_thread_mirror_is_removed`）——**均被真实触达**，不是空跑。
- 老 `novel.json` 无 `threads` 字段：实测 `load_novel` 正常、`save_novel` 后补出 `threads` 键（兼容 OK，但见 P2-3）。
- 无账本旧书：`_load_thread_context` 返回 `None`，既有 5 条规则与响应形状**未变**，并有 E2E 钉死。
- SSE 契约、`build_novel_builder` 签名、既有槽位优先级未动。

---

## P0（阻断）

无。

---

## P1（应修）

**P1-1 · `api/routes/threads.py:86-88` — PUT 改 id 时静默覆盖另一条伏笔（数据丢失）**
```python
if thread.id != thread_id:
    delete_thread(novel_id, thread_id)
save_thread(novel_id, thread, overwrite=True)   # ← overwrite=True 绕过了"同名不覆盖"守卫
```
实测：PUT `/threads/t1` 且 body `{"id":"t2"}` 时，`t2` 被 `hijack` 静默改写，返回 `success=true`。这直接违反本节点的核心原则「不静默覆盖作者的账本」，且无任何测试覆盖改 id 场景。
**改法**：改 id 时先 `if load_thread(novel_id, thread.id) is not None: return success=false`，删除旧条目后用 `overwrite=False` 保存；或明确"id 不可改，改 id 请先删"。

**P1-2 · 验收 3 与实现不一致（任务漏项 or 文档需改）**
§9.1.1 验收 3：「无账本时……**校验返回 skipped**（不告警）」。实现（`api/routes/check.py:192-195`）在无账本时**根本不把 `THREAD_RULES` 加入**，因此接口层永远不会返回那两条 `skipped`；`skipped` 只在直接调用 `run_rules(..., rules=THREAD_RULES)` 时出现（仅单测覆盖）。计划书 §9.1.1「实施记录」把它记为有意修正，但验收文字未同步。
**处置**：要么实现"跑规则并返回 skipped"，要么把验收 3 改成"无账本时伏笔规则不参与、报告形状不变"，二者取一，别让验收与实现长期互斥。

---

## P2（建议）

**P2-1 · `api/routes/threads.py:67/81/106` + `core/models.py:123` — 设计承诺的 camelCase 未落地，字段被静默丢弃**
设计写「请求/响应复用 `APIModel`（camelCase 兼容）」，但请求体是 core `PlotThread(BaseModel)`、`AdvanceThreadRequest(BaseModel)`，**非 APIModel**。实测 POST `{"plantedChapter":50}` 存成 `planted_chapter=0`，`success=true`；`chapterNumber` 同理。这正是 AGENTS 里点名的"camelCase 不匹配"沉淀。虽与 N8 `characters.py` 一致（前端当前用 snake_case），但契约文本与实现不符，将来前端按文档发 camelCase 会静默失效。
**改法**：在 `api/schemas.py` 定义 `APIModel` 的 `ThreadPayload`/`AdvanceThreadPayload` 并转换；或修正设计文字为 snake_case + 加一条 `extra="forbid"` 防止静默丢字段。

**P2-2 · `check/rules.py:557-561` — `unknown_payoff` 对"计划中未写到"的回收章误报**
实测 `payoff_chapter=30`、`known_chapters=[1,2,3]` → `alert`。模型语义是"未回收为 None"，但 API 允许 `status=planted + payoff_chapter=30`（计划回收）。作者按"计划"填了回收章就会被误报。建议：只对 `status == "paid_off"` 的条目判定，或容忍 `payoff_chapter > max(known_chapters)`（未写到的未来章）。

**P2-3 · 缺"老 `novel.json` 无 `threads`"的显式回归测试**
用户点名问这条。行为实测正确，但没有测试锁定兼容性。建议在 `test_threads_survive_save.py` 加一条：手写不含 `threads` 的 `novel.json` → `load_novel` 不炸、`save_novel` 后键补齐。

**P2-4 · 验收 2 点名的 `GET /api/check/manifest` 未被测试**
§9.1.1 验收 2 原文写「（`GET /api/check/manifest` 可见 `source="thread:<id>"`）」，但 `tests/e2e/test_n9_threads_real_http.py:142-151` 只断言 SSE `done` 载荷里的 `context_manifest`，没验证落盘清单端点。建议补一条：生成后 GET manifest，断言 entries 含 `thread:t1`。

**P2-5 · `writer/context_sources.py:187-206` 与 `threads/manager.py:107-120` 两套等价过滤**
provider 重抄了一遍"OPEN_STATUSES + planted≤本章 + 排序"逻辑，只共享常量。N5 评审 P1-8 的教训（两套等价规则必然漂移）在这里重演，且没有"二者结果一致"的测试。建议抽公共函数，provider 复用之。

**P2-6 · 排序语义与设计/文档不符**
设计说"距上次推进的章数"降序，代码（`manager.py:112`、`context_sources.py:196`）用的是「本章 − **埋设**章」。模型里没有 "last_advanced_chapter" 字段，所以"上次推进"根本无法表达。要么补字段，要么把 design/docstring 改成"距埋设"。

**P2-7 · `strength` 是死字段；`dangle_threshold` 未真正"可配"**
`core/models.py:145` 的 `strength(1–5)` 完全不参与注入与校验；设计说悬空阈值"默认 30，可配"，但 `ThreadContext.dangle_threshold` 没有任何 API/config 入口（`api/routes/check.py:148-152` 从不赋值）。要么用上，要么标注为"仅展示/待用"。

**P2-8 · `api/routes/check.py:193` — 有 novel_id 但 chapter_number 缺省为 0 时仍跑 dangling**
实测：账本 planted@1、不传 `chapter_number` → `dangling_threads` 返回 `ok`（因 `planted>0` 被全部"还没埋到"排除），而不是"缺章号 → skipped"。与 `check_dangling_threads` 的 `chapter_number is None → skipped` 意图不符。建议把缺省/0 规范成 `None` 传入。

**P2-9 · 弱/自证式断言**
`tests/test_threads/test_rules.py:114-119` 的 `assert THREAD_RULES == ("dangling_threads","unknown_payoff")` 属于"断言实现里的常量本身"（改实现测试跟着改），有效信息只有与 `DEFAULT_RULES` 不相交那半句。E2E `tests/e2e/test_n9_threads_real_http.py:28` 的 `CLEAN_TEXT` 里 `\\n` 是**字面反斜杠+n**而非换行，弱化了文本。建议：断言"两条规则各自能给 alert/warn"的行为，而非常量；`CLEAN_TEXT` 用真换行。

---

## 最终结论

**需修复后提交。**
必须处理：**P1-1**（PUT 改 id 静默覆盖，是真实数据丢失路径，且违背"不静默覆盖"原则）；**P1-2** 需二选一（补实现"返回 skipped"或改验收文字）。其余 P2 建议在本节点或紧随的收尾提交里一并处理，尤其是 P2-1/P2-3/P2-4（分别对应你点名的 camelCase 静默失效、老书兼容回归、验收未真正覆盖）。

## 处置记录（⑥ 按评审修复）

| 编号 | 结论 | 处置 |
|---|---|---|
| **P0** | 无 | — |
| **P1-1** | 采纳，已修 | `PUT` 改 id 时若目标 id 已存在 → `success=false`（不再 `overwrite=True` 静默改写）。补两条回归：`test_change_id_cannot_hijack_another_thread`（劫持被拒 + 两条都未被改）、`test_change_id_to_free_slot_still_works`（改到空闲 id 仍可用，别为修 bug 关掉功能） |
| **P1-2** | 采纳，已修 | 验收 3 文字与实现对齐：**校验侧伏笔规则不参与**（不是"返回 skipped"），报告形状与 N5 完全一致 |
| **P2-1** | 采纳，已修 | 新增 `PlotThreadRequest` / `AdvanceThreadRequest`（`APIModel` + `extra="forbid"`）：驼峰可用、拼错字段 422 而非静默丢弃。补 `test_camel_case_body_is_accepted`、`test_advance_camel_case_is_accepted`、`test_unknown_field_is_rejected_not_dropped`、`test_request_model_stays_in_sync_with_core`（防字段分叉） |
| **P2-2** | 采纳，已修 | `unknown_payoff` 只判 `status == "paid_off"`：作者按计划填的未来回收章不再误报。补 `test_planned_future_payoff_is_not_an_error` |
| **P2-3** | 采纳，已修 | 补 `test_legacy_novel_without_threads_key_still_loads`：手写不含 `threads` 的 `novel.json` → 能加载、保存后补键 |
| **P2-4** | 采纳，已修 | E2E 补 `test_manifest_endpoint_exposes_thread_source`：生成后 `GET /api/check/manifest` 必须能看到 `thread:t1` |
| **P2-5** | 采纳，已修 | 抽出 `threads.manager.open_threads_of(novel, chapter_number)`，provider 直接复用之；`select_open_threads` 变成薄封装。两套等价过滤 → 一套 |
| **P2-6** | 采纳，已修 | 文档/注释统一为「本章 − **埋设**章」；原"距上次推进"是实现笔误（模型里没有该字段） |
| **P2-7** | 采纳，已记录 | `strength` 与 `dangle_threshold` 在计划书里明确标注为**仅展示 / 待用**（`strength` 不参与排序与校验；`dangle_threshold` 无 API/config 入口），不再写成"可配" |
| **P2-8** | 采纳，已修 | `api/routes/check.py` 把缺省/0 章号规范成 `None`，悬空规则据此返回 `skipped`（原为误给 `ok`） |
| **P2-9** | 采纳，已修 | 常量断言（`THREAD_RULES == (...)`）改为**行为断言**（默认组跑出来的报告里不含伏笔规则）；`CLEAN_TEXT` 改为显式 `"\n\n".join([...])`，不再依赖源码里的转义写法 |

### 一处评审误读（说明，非争议）

P2-9 说 `CLEAN_TEXT` 里是"字面反斜杠+n 而非换行"—— 源码里写的是 `\n` **转义序列**，
Python 解析后运行时确实是真换行（与既有 `test_n5_check_real_http.py` 同一写法）。
仍按建议改成显式拼接，理由是**消除歧义**，不是原写法有错。

### 复核结果（修复后）

| 门禁 | 结果 |
|---|---|
| `pytest -q` | **921 passed / 3 skipped**，覆盖率 94.36% |
| `ruff check src/story_engine tests` | All checks passed |
| `mypy src/story_engine` | Success（65 源文件） |
| `vitest run` / `vue-tsc --noEmit` | 104 passed / 0 |
