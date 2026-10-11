# N4a 评审报告：装配器 v0 切片一（槽位注册表 + ContextManifest + 预算裁剪）

## 1. 结论

**需补充后通过。** 槽位注册表 / manifest 的形状基本立住了，10 条单测全绿、ruff+mypy 干净；但预算判定与 manifest 记账用了两套 token 口径（渲染后 vs 各片段之和），已复现出 `over_budget=False` 却实际超预算的错误，且 `dropped` 只记 slot_id、缺 provider 异常/缺失的可见性——这些都会在 N4b 挂上 SSE 后直接暴露给作者。

> 流程判定：N4a 全部是纯内部函数，按 §9.3「纯内部函数用单测即可」，本轮**不强制真 E2E 是正确的**；但 N4b 一旦把 manifest 挂到 `done` 载荷就跨层，必须补真实 HTTP E2E。

---

## 2. P0（必须修）

### P0-1 预算判定用「渲染后长度」，manifest 记账用「片段之和」→ `over_budget` 会假阴性

证据（`src/story_engine/writer/context_builder.py`）：
- 裁剪总量 `total = sum(t ...)` 的 `t` 是 `estimate_tokens(rendered)`（:179 计算、:184 汇总）；
- 但最终 `total_tokens = sum(e.tokens ...)`，而每条 `e.tokens = estimate_tokens(piece.text)`（:208、:220）；
- `over_budget` 用这个偏小的 `total_tokens` 判定（:226-228）。

`_render_bullets`（:119-120）给每段加 `"- "` 前缀、plain 也加 `\n` 分隔，这些都进 `rendered` 却不进 `entries`，所以 `sum(entries) <= sum(rendered)`，**单向低估**。

复现（已实跑）：
```
slot notes(priority=0, renderer="bullets") 返回 3 段 "aaa"/"bbb"/"ccc"，budget_tokens=10
→ result.text = "- aaa\n- bbb\n- ccc"（17 token）
→ manifest.total_tokens = 9
→ manifest.over_budget = False   # 实际注入了 17 > 10
```
后果：作者看到的 token 占比与预算结论都是错的；「预算硬上限」在 manifest 上无法自证（P7-LONG-MEMORY §4:95、MVP 风险表 P116 都要求硬预算 + token 占比）。

建议改法：`total_tokens` 改为「**实际注入槽位的 rendered token 之和**」，与裁剪口径统一；per-piece `entries` 仅作溯源。并在裁剪后断言 `total_tokens == sum(estimate_tokens(rendered) for kept slots)`，补一条 `bullets` + 超预算的用例（现测试全是 `plain`，永远看不到这 bug）。

---

## 3. P1（应该修）

### P1-1 `dropped` 只记 `slot_id`，多片段槽位（摘要）丢信息
`ContextManifest.dropped: List[str]`（:80）、裁剪时 `dropped.append(slot.slot_id)`（:195）。摘要槽位是多片段（:88-105 已支持每片一条 entry），被裁时作者**无法知道裁掉了几条、哪些 source**。而 MVP-3 验收（PLAN:98）要「装配文本内摘要条数 == store 命中条数」，`dropped` 表达不了部分裁掉。建议 `DroppedSlot(slot_id, pieces, tokens, sources)` 或记录被裁片段的 source。

### P1-2 未注册 provider / 空产出 在 manifest 中「静默消失」，违背 S4/「注入可见性」
`_collect` 对未注册 provider 只 `logger.warning` 后返回 `[]`（:156-159），且 `not rendered` 的槽位在 :204 被跳过。于是「provider 没注册」「provider 正常但内容为空」与「这个槽位本来就没配」在 manifest 里**长得一模一样**（都既不在 `entries` 也不在 `dropped`）。契约 S4 写「不静默消失」，此处没兑现。建议 manifest 增 `skipped: [{slot_id, reason}]`（`provider_missing` / `empty`）。

### P1-3 provider 异常没有兜住，且与「纯函数」承诺冲突
`build` 调 `provider(inputs)`（:160）无 try/except。N4b 的 provider 要读 DB/文件（`memory/store.py`、`_novel_dir`），单个 provider 抛异常会让整次装配崩溃（挂到路由后即 500）。建议装配器层 per-slot try/except → 记入 manifest `errors` 并跳过该槽位，其余槽位照常装配。

### P1-4 缺「每槽位独立预算」接缝（架构明确要求）
P7-LONG-MEMORY §4:95「每个槽位有独立预算与填充策略」，:97-107 给了 S0–S8 逐槽预算（1.5K/3K/…/18K）。但 `Slot`（:39-52）只有 `priority`，`ContextBuilder` 只有全局 budget，无法表达「S6 检索最多 18K」。这正是 R2 想避免的返工点。建议现在给 `Slot` 加可选 `max_tokens`（以及为 N4b 预留位置锚定：架构要求 S0/S1 在头、S7/S8 在尾）。

### P1-5 文档与实现矛盾：docstring 说「不超发」，pinned 实际就会超发
模块 docstring :18「预算仍不够则 `over_budget=True`（明示，**不超发**）」，但 `test_pinned_slots_are_never_trimmed`(:146-165) 与我的复现都表明：pinned 槽位会照样注入并只把 `over_budget` 置真——**确实是超发的**。同时 `truncated` 字段（:72）没有任何写入路径，恒为 False（无截断策略）。建议：修正文案为「pinned 允许超预算但显式标记」，并明确「单个 pinned 槽位自身超预算」时的策略（截断 or 拒绝装配），否则 N4b 无从处理。

### P1-6 同优先级 tie-break 未测，且注释与代码不一致
代码裁剪键 `key=lambda i: (-priority, -i)`（:186-189），即**同优先级时后声明的先裁**（:185 注释如此）；但测试 :178 注释写「同优先级按 slot 声明顺序」，且 `test_dropped_order_is_deterministic` 的 a/b/c 是 10/90/50，**没有任何同优先级用例**——这是个「看起来测了其实没测」的点。建议补两个同为 `priority=50` 的槽位，钉死后声明先裁。

---

## 4. P2（可选优化）

- **`estimate_tokens=len(text)` 的方向**（:106-112）：对纯 ASCII/英文/JSON 是**高估**（约 4 字 ≈ 1 token），不是低估。后果是 ASCII 密集槽位（大纲是 JSON，engine.py:193 用 `model_dump_json`）被高估、相对中文槽位更早被裁。作为相对比较勉强够用，但请在 docstring 写明「按字符数会高估 ASCII 内容」。
- **`priority` 语义反直觉**（:16、:44）：`0=永不裁、越大越先裁` 与「priority 高=更重要」的通行认知相反；后续有素材/技法/条款/检索等多类数据源时极易配反。建议提供具名常量（如 `PINNED`/`RETRIEVAL`）或改语义为「保留优先级（越大越保）」。
- **重复 `slot_id` 校验无测试**：:145-147 有 `ValueError`，但 10 条用例里没有覆盖它。
- **`truncated` 死字段**：:72 恒 False，要么实现截断、要么先删以免误导 N6。
- **`_collect` 未做类型防御**：:160-161 `provider(inputs) or []`，若 provider 误返回 `str`，`p.text` 会 AttributeError 崩装配。
- **`build(inputs)` 未拷贝入参**：:172 直接把调用方 mapping 透传给 provider，provider 若写脏则第二次 build 结果变，破坏「同输入同输出」承诺。
- **N6 三栏字段**：`entries` 有 `priority` 可算占比，尚可；但缺「这次没注入什么」（见 P1-2）与每槽位聚合值，展平时作者要自己 reduce。

---

## 5. 已核实为正确的地方（实际验证）

- 实跑 `.venv/bin/python -m pytest -q --no-cov tests/test_writer/test_context_builder.py` → **10 passed**；`ruff check` 与 `mypy` 对新模块均通过。
- **pinned 永不裁**逻辑正确：复现 `budget=5`、两个 priority=0 槽位 50 字 → 均保留、`over_budget=True`、`dropped=["retrieval"]`，`over_budget` 确由 pinned 保护导致，非「顺带为真」。
- **`test_trims_lowest_priority_first` 确实触发裁剪**：30 token > budget 25，裁掉 priority=90 的 `low` 后 20 ≤ 25，断言有效（不是预算刚好够的空转）。
- **`test_all_slots_land_in_text_and_manifest` 没有被蒙混**：四段文本互异，且同时断言 `set(entries)=={...}` 与 `chars`，`in` 之外有结构断言。
- 预算裁剪的**顺序确定性**（`test_dropped_order_is_deterministic`）与 `budget=None` 不裁（`test_budget_none_means_no_trim`）行为正确。
- `manifest.to_dict()` 可 JSON 序列化（`asdict` + 基础类型），`test_manifest_is_json_serialisable` 通过。
- 多片段 provider **每片一条 entry**（`source=summary:ch_0001` 可溯源），符合 S2 一一对应。

---

## 6. 未覆盖的风险 / 我的判断可能有误之处

- **「相对比较够用」这个前提值得商榷**：`len()` 对中英混排的一致性差，一旦 N4b 把 45K 预算交给配置，中文槽位（1 字≈1 token）与英文/JSON 槽位（4 字≈1 token）的裁剪会系统性偏袒/歧视，且随语言比例漂移。若接受，请把「按语言加权」列入 N4b/N7 的已知债。
- **per-slot 预算是 N4a 该留还是 N4b 再补**：我按架构 §4:95 判为应在 N4a 留接缝（否则违反 R2 初衷），但也可能项目故意把「填充策略」全推给 N4b；若如此，P1-4 降为 P2。
- **pinned 超预算该截断还是放行**：我倾向「显式放行 + 告警」，但架构只说「绝不砍风格块与节拍」没说截断，最终策略应由你定；当前实现「放行但不处理」至少要在文档里说清，否则 N4b 会误以为已有兜底。
- **未执行的验证**：没有跑全量 `pytest`（仅跑本模块），无法排除新模块引入的间接回归（该文件目前无人 import，风险低）；也未检查前端 `StreamDonePayload` 是否接受 `entries` 嵌套对象（N4b 才需要）。
