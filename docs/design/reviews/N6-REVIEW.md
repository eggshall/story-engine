# N6 评审报告 — 审稿页（三栏 + 带指令重写 + 注入清单落盘）

> 只读评审。评审对象：`ReviewView.vue`、`manifest_store.py`、`check.py` 的 manifest 端点、
> `generate.py` 的 v2 rewrite 分支、`schemas.py`、以及 4 组测试。
> 我没有改任何文件、没有 commit。

## 1. 结论

**需补充后通过。** P0 = 1，P1 = 5，P2 = 7。

后端最核心的承诺 **"重写只出候选稿、绝不落盘" 是成立的**（真 HTTP E2E 用磁盘断言证明，
见 §5）。但前端在"重写进行中切换章节/小说"时会把候选稿拼成 `"null…"` 并且**保存按钮仍可点**，
且保存是**不可逆的全量覆盖**——这是唯一一个会造成正文数据损坏、且用户非本意的缺陷，故列 P0。
其余问题集中在：审稿页的校验拿不到基线（对话占比永远 skipped，测试恰好把 bug 断言成期望）、
注入清单落盘在真实 UI 里**没有任何触发入口**、"读取历史清单"按钮在真实使用中永远失败。

### 我实际跑过的

- `.venv/bin/python -m pytest tests/test_writer/test_manifest_store.py tests/e2e/test_n6_review_real_http.py -q` → **16 passed**（9 + 7），与描述数量一致（子集跑覆盖门禁不适用）。
- `npx vitest run src/views/__tests__/ReviewView.spec.ts` → **9 passed**。
- `ruff check` 对 N6 涉及的 6 个文件 → **All checks passed**。
- 未跑全量 `pytest`（会触发覆盖率门禁且耗时）；819/94.91% 这一数字我未复核，但子集与静态检查无异议。

---

## 2. P0（必须修）

### P0-1 重写流进行中切换章节/小说 → 候选稿变成 `"null…"`，且保存按钮可点、会串章覆盖
- 证据：
  - `ReviewView.vue:367` 流式累加：`candidate.value += token`。
  - `ReviewView.vue:314-321` `onChapterChange()` 把 `candidate.value = null`（切小说同理，`:305`），
    但**不会中断正在进行的 `for await` 循环**（没有 `AbortController`，也没有"本次重写代号"校验）。
  - JS 里 `null + "擂台"` === `"null擂台"`。于是切章后每个到达的 token 都往 `null` 上拼。
  - `ReviewView.vue:377-388` `saveCandidate()` 在点击时读取**当前**的 `novelId/chapterNumber`，
    保存的却是上一章那条流拼出来的脏串 → 覆盖到**新选中的章节**。
- 后果：作者"重写到一半切去看另一章"，回来后候选框里是 `null…` 内容，`candidate-hint` 仍提示
  "满意再点保存"，点下去就把脏串写进另一章（且无回退，见 P1-1）。
- 怎么验证（缺的具体断言）：
  - 单测：mock 的异步生成器 `yield '候选'` → `await` 一拍 → 抛错/继续；在流未结束时调用
    `onChapterChange()`，断言 `candidate` 不被设为字符串、且 `save-btn` 处于 disabled。
    （现有 `ReviewView.spec.ts` 没有"流进行中切章"的用例。）
  - 浏览器 E2E：重写点击后立刻切章，断言候选提示消失、保存按钮禁用、磁盘两章内容都未变。
- 最小改法：`rewrite()` 里给每次重写分配一个 `runId`（或 `AbortController`），循环内 `if (runId !== currentRunId) return`；
  `onChapterChange`/`onNovelChange` 里 `currentRunId++` 并 `abort()`。保存前加 `if (!candidate.value || candidate.value.startsWith('null'))` 已不是根治，根治是中断+代号。

---

## 3. P1（应该修）

### P1-1 保存是不可逆全量覆盖，且没有任何兜底（半截候选稿也能保存）
- 证据：`ReviewView.vue:377-388` → `POST /api/novel/{id}/chapters/{n}/save`；
  `novel.py:209-227` 直接 `c.content = req.content` 后 `save_novel`；
  `novel_storage.py:282-287` 原子写 `os.replace`，旧内容**当场消失**，无副本。
- 叠加两个触发点：
  - `ReviewView.vue:369-374` 重写中途出错（SSE `error`）时 `if (!candidate.value) candidate.value = null`——
    **只在候选稿为空时才清空**；已经流出的半截候选稿会保留，`save-btn` 变可用，可一键把半截稿覆盖整章。
  - P0-1 的串章脏串同样落到这条保存路径。
- 回答任务里的问题：**「作者点保存就没回退路径」单独看不构成 P0**（是作者显式触发、且候选稿在保存前确实只在内存/预览），
  但与"半截稿可保存 + 串章脏串可保存"叠加后就是**数据损坏**，因此我把这一簇的最脏点（P0-1）定 P0，本项定 P1。
- 怎么验证（缺的具体断言）：`ReviewView.spec.ts` 加两例：①生成器先 `yield` 再 `throw`，断言
  `save-btn` disabled / `mockSaveChapterContent` 不被调用；②重写成功后断言 `mockSaveChapterContent` **未**被调用
  （现有保存用例只测"点了保存会调用"，没测"不点不会调用"）。
- 最小改法：在后端 `api_save_chapter` 覆盖前把旧正文旁路写一份 `<novel_dir>/backups/ch_XXXX.<时间戳>.md`
  （完全复用 `novel_storage._atomic_write`，不引入版本库）；前端错误路径**无条件**丢弃候选稿，不提供"保存半截稿"。

### P1-2 审稿页的"对话占比"永远 skipped：校验从不传 `novel_id/chapter_number`，后端 text 模式也不加载前序
- 证据：
  - `ReviewView.vue:331` `report.value = await checkChapter({ text })` —— 只传 `text`。
  - `ReviewView.spec.ts:149` 把这个行为**写死成断言**：`toHaveBeenCalledWith({ text: DRAFT })`。
  - 后端 `check.py:103-122`：`text` 非空时**根本不进入** `_load_chapter_text`，`previous_texts` 恒为 `[]`；
    `build_baseline(features, [])` → `source="none"` → `check_dialogue_ratio` 恒 `skipped`（`rules.py:341-348`）。
  - 即便作者在审稿页，也无法把"候选稿文本"和"第 N 章的前序章节"一起送进去：`CheckChapterRequest`
    同时有 `text` 与 `novel_id/chapter_number`，但路由逻辑是**二选一**，不是"用 text 判正文、用 chapter 取基线"。
- 后果：中栏永远提示"对话占比没判定"，作者永远拿不到这条规则的价值；台账里 `baseline_source` 恒为 `none`。
- 怎么验证：构造一本有 ≥3 章、前两章对话占比稳定的书，在审稿页校验第 3 章，
  期望 `baseline_source == "previous_chapters"` 且 `dialogue_ratio` 的 level ∈ {ok,warn}；当前必为 skipped。
- 最小改法：ReviewView 传 `{ text, novel_id, chapter_number }`；后端改为"给了 `novel_id+chapter_number` 就
  无论 text 是否为空都 `_load_chapter_text` 取 `previous_texts`，但正文用请求里的 `text`"。

### P1-3 注入清单落盘在真实 UI 里**没有任何触发入口**，"读取本章历史清单"按钮永远失败
- 证据：
  - `generate.py:378-381`：`save_manifest` **只在非 rewrite 分支**调用（`rewrite` 分支 `:369-374` 提前 return）。
  - 前端唯一调用 v2 的地方是 `ReviewView.vue:355-360`，而重写按钮 `:disabled="... || !instruction.trim()"`
    （`:145`）——**永远带非空 instruction**，永远走 rewrite 分支。
  - `WritingView.vue:192,326` 用的是 `generateChapterStream`（`/generate/chapter`），不是 v2；
    全仓 `rg 'chapter/v2'` 在 `src/` 下除 `utils/api.ts` 外无第二调用方。
  - 于是 `ReviewView.vue:390-400` 的"读取本章历史清单"在真实使用中**必然**返回 `success=false`。
  - 浏览器 E2E 只断言了 done 载荷里的 `manifest-skipped`（`n6-review.e2e.ts:159`），**从没点过
    `load-manifest-btn`**；唯一验证落盘的是后端 E2E 里直接 httpx 调 v2 生成模式（`test_n6_review_real_http.py:98-115`）。
- 后果：N6 承诺的"注入清单落盘"在后端成立、在**产品层不可达**——作者看不到任何一条历史清单。
- 怎么验证（缺的具体断言）：浏览器 E2E 加一步：先用 v2 生成模式产生一章（或让写作页改走 v2），
  再进审稿页点"读取本章历史清单"，断言出现 `manifest-slot`。
- 最小改法：二选一——(a) 写作页/审稿页提供"按装配器生成本章"入口走 v2（空 instruction）；
  或 (b) rewrite 命中已有章节时，作者点保存后把该次 rewrite 的 `context_manifest` 一并落盘（补 `save_manifest` 调用）。
  并在 E2E 里点一次该按钮。

### P1-4 清单写盘失败被静默：done 仍报 `saved=true`，GET 文案还把"写失败"说成"不是装配器生成"
- 证据：
  - `manifest_store.py:29-43` 写失败返回 `None` 且只 `logger.warning`。
  - `generate.py:379-385` **忽略返回值**，done 载荷照发 `saved=True, context_manifest=...`，前端无法区分。
  - `check.py:50-56` 读不到时统一回 `"该章可能不是用装配器生成的"`——把 IO 失败和"从未生成"混为一谈。
- 后果：作者事后读不到清单，会以为"这章本来就没注入"，而真相是写盘失败；"注入可见性"落空且无人知道。
- 怎么验证（缺的具体断言）：`test_manifest_store.py` 已测"写失败返回 None"（9 例之一），但
  **没有一条**断言"写失败会以某种方式出现在 done 载荷/日志/GET 文案里"。加一例：patch `_atomic_write` 抛错，
  跑 v2 生成，断言 done 载荷带 `manifest_persisted=false`（或 GET 文案包含"写盘失败"）。
- 最小改法：`save_manifest` 的结果回填 done：`manifest_persisted=bool(path)`；`GET` 的 message 改成
  "清单缺失（可能写盘失败，或该章不是 v2 生成）"，并在前端把该 flag 显示出来。

### P1-5 重写流进行中"校验"按钮仍可点 → 对半截候选稿出报告，且报告会长驻中栏
- 证据：`ReviewView.vue:28-36` 校验按钮 `:disabled="!viewedText"`，不含 `rewriting`/`checking`；
  `rewrite()` 从 `:349` 起就把 `viewMode='candidate'`，第一片 token 到达后 `viewedText` 即非空。
- 后果：作者在流未结束时点"校验"，拿到的是**半截文本**的报告；流结束后左栏已是全文、中栏却还是半截稿的报告
  （`checkedText` 与最终 `viewedText` 不等，`canHighlight` 只是不画高亮，但清单条目照样显示）。作者会误读。
- 怎么验证（缺的具体断言）：单测里让生成器"先 yield 再挂起"，期间 `trigger('click')` 校验按钮，
  断言 `check-btn` 是 disabled / `mockCheckChapter` 未被调用。
- 最小改法：`:disabled="!viewedText || rewriting || checking"`，并在 `rewriting` 变 true 时清空旧 `report`。

---

## 4. P2（可选优化）

- **P2-1 空内容章节不算"没有正文"**：`generate.py:301-304` 只判 `current is None`。若章节存在但
  `content == ""`（`api_add_chapter` 允许空 content），rewrite 会拿去重写并让模型"重写空文"。
  任务描述是"第一章没有正文时要报 error"。改：`if current is None or not (current.content or '').strip()`。
  现有 E2E（`test_rewrite_without_existing_chapter_is_error_not_empty_stream`）只覆盖"章不存在"。
- **P2-2 `checkedText` 在 `await` 之前赋值，失败时旧报告/旧高亮残留**：`ReviewView.vue:330-332`
  `checkedText.value = text` 在 `checkChapter` 之前，`highlight.value = null` 在其之后。若 `checkChapter` 抛错，
  `checkedText` 已是新文本、`report`/`highlight` 还是旧的；配合 `canHighlight`（`:250-252`）恰好在
  "切 tab 后校验一次但失败"时能把旧报告的高亮画到新文本上。改：`checkedText` 改到成功后赋值，catch 里一并清 `report/highlight`。
- **P2-3 深链与切书无异常处理**：`ReviewView.vue:277` `Number(route.query.chapter || 0)` 对数组型 query 得 `NaN`；
  `onNovelChange`（`:299-312`）无 try/catch，`@change` 触发的失败会变成未捕获 promise，界面停在旧小说且 `errorMsg` 为空。
- **P2-4 `loadManifest` 无 try/catch**：`ReviewView.vue:390-400` 只在 `res.ok=false` 时提示；网络异常时
  未捕获且无任何用户提示。
- **P2-5 `GET /api/check/manifest` 输入未校验、语义不精确**：`check.py:42` 未用 `_safe_novel_id`，
  非法 `novel_id` 会经 `manifest_path` 抛 `ValueError` → 500；负章号会生成 `ch_-001.json` 之类怪名。
  另外 rewrite 保存后不会刷新清单，落盘清单描述的是"上次生成时"的注入，和当前正文不再一一对应，
  建议在 UI/文档明示"清单 = 生成时注入记录"。
- **P2-6 单测缺的关键断言**（与 §6 呼应）：未断言"重写后不自动 save"；未断言"抛错后保存按钮禁用"；
  未断言 `checkChapter` 收到 `novel_id/chapter_number`（若加了这条，P1-2 会被立刻抓到）。
- **P2-7 `App.vue:1` 行首有字面 `\n`**（字节 `5c 6e`，即反斜杠+n 两字符，`xxd` 可验），
  在 `<template>` 之前。非本次引入（`git show HEAD:...` 同样如此），构建能过，但属脏字节，建议清理。

---

## 5. 已核实为正确的地方（我读过/跑过）

- **"候选稿不落盘"后端成立**：`generate.py:286` 判 `rewrite = bool(instruction.strip())`；
  rewrite 分支 `:369-374` 只 `yield done_payload(..., rewrite=True, saved=False)` 后 `return`，
  **不 append、不 `_save_novel`**；`save_manifest` 也只在非 rewrite 分支。E2E `test_rewrite_returns_candidate_without_saving`
  用真实磁盘断言 `chapter2.content == OLD_TEXT`、`len(chapters)==2`，是硬证据。
- **无 provider 会写盘**：rewrite 路径只有 `build_novel_builder`→`builder.build`（`context_builder.py:275`，
  纯函数，provider 只读文件）与模型流；`context_sources.py` 的 provider 均为只读。
- **并发两次重写不互相污染**：每次请求 `_load_novel` 各自实例化 `Novel`（`novel_storage.py:196-231`，无全局缓存），
  共享的只有全局 `_router`，不涉及章节写。两次 rewrite 都只读，无写。
- **SSE 单一 done 契约**：v2 两条分支都自带 done，`event_stream`（`sse.py:76-113`）在 `done_sent` 后不再补发；
  rewrite 无正文时 `yield error_payload` 后 return，`error` 流无 done。E2E `_done()` 断言恰好一个 done。
- **字段名一致**：done 载荷用 `context_manifest`（`generate.py:372,384`），前端 `ReviewView.vue:363` 按同名读取，
  `App.vue`/路由/鉴权沿用既有约定。
- **落盘走 `_novel_dir`**：`manifest_store.py:26` 经索引解析，自定义路径小说的一例单测（`test_manifest_store.py:88-101`）覆盖。
- **写失败不炸主流程**：`manifest_store.py:41-43` 兜住所有异常；单测 `TestWriteFailureNeverBreaksGeneration` 覆盖
  `_atomic_write` 抛错与 `mkdir` 抛错两条路径。
- **偏移相对请求原文**：`check.py:103-104` 不 `strip()`；`ReviewView.vue:250-252` 用
  `viewedText === checkedText` 守卫，常规"校验→点条目→高亮"链路正确，E2E 高亮了整段 300+ 字长段。

---

## 6. 测试质量（"看起来测了其实没测"自查）

| 测试 | 问题 |
|---|---|
| `ReviewView.spec.ts:149` | `toHaveBeenCalledWith({ text: DRAFT })` 把 P1-2 的缺陷**固化成期望**——它"证明"了页面只传 text，却没人觉得这是 bug。 |
| `n6-review.e2e.ts:111` | 断言 `incomplete-banner` 含"对话占比"。因为页面永远不传基线，这条**必然为真**，无论书里有多少前序章节——是假绿，掩盖 P1-2。 |
| `n6-review.e2e.ts`（整条） | 从不点 `load-manifest-btn`。清单落盘产品层不可达（P1-3）因此逃过 E2E。 |
| `ReviewView.spec.ts:281-293` | "重写失败不留半截候选稿"只 mock 了**未 yield 就 throw**；没有"先 yield 再 throw"的用例，正好漏掉 P1-1 的可保存半截稿。 |
| `ReviewView.spec.ts:268-279` | 只测"点保存会调用 save"，没有反例断言"重写完/出错时不自动 save"。 |
| `test_manifest_store.py` | 只测"写失败 → 返回 None"；没有断言写失败会被**上抛到 done 载荷/GET 文案**（P1-4）。 |
| `test_n6_review_real_http.py:117-130` | `test_generate_mode_reports_saved` 是好用例（断言 `saved=True` 且磁盘内容变化），但它走的是 httpx 直连，不代表 UI 会走这条路。 |

建议补的最小断言（逐条对应上面的 P0/P1）：流中断后 `save-btn` disabled；流中 `check-btn` disabled；
`checkChapter` 收到 `novel_id/chapter_number` 且第 3 章 `baseline_source == "previous_chapters"`；
点一次 `load-manifest-btn` 能看到 `manifest-slot`；写盘失败时 done 带 `manifest_persisted=false`。

---

## 7. 未覆盖的风险 / 我的判断可能有误之处

1. **P0/P1-1 的定级可辩**：若维护者认为"作者不会在重写进行中切章"，P0-1 可降为 P1；但 `"null"+token` 是
   明确的代码缺陷（非设计取舍），且保存不可逆，我倾向保守定 P0。
2. **P1-3 可能是有意分期**：N4b 的 v2 生成模式本就没有前端入口，N6 只做"承接落盘"。若如此，请在
   commit message / `P7-MVP-PLAN.md` 写明"清单落盘的 UI 触发在 N7/下一节点"，并暂时隐藏或标灰
   "读取本章历史清单"按钮，避免给作者一个必然失败的入口。
3. 我没有跑全量 pytest/vitest/build（耗时且本机限制），819 passed / 94.91% / vue-tsc 0 错误
   这些数字来自提交说明，我只复核了 N6 相关子集（16 + 9）与 ruff。
4. P2-7（`App.vue` 首行 `\n`）是历史遗留、非本次引入，列出仅供顺手清理。
