# N4b 代码评审（只读）— 装配器真实数据源 + `POST /api/generate/chapter/v2` + 注入清单上 done 载荷

## 1. 结论

**需补充后通过** —— 无 P0 级功能缺陷（全量 747 passed/3 skipped、覆盖率 94.88%，真实 HTTP E2E 4/4 绿），但存在若干需要在 N5/N6/N7 前收敛的契约与可见性 P1（全局角色卡污染 E2E、`context_manifest`/`injection_manifest` 命名分叉、上一章结尾截断无标记、`OSError` 与 `empty` 混同）。

## 2. P0（必须修）

无。已逐条核对 A–E 的怀疑路径，未发现"manifest 说有、实际没进 prompt"或"v2 可绕鉴权/写坏空章节"的实现缺陷（证据见 §5）。

## 3. P1（应该修）

**P1-1 E2E 受仓库全局 `data/characters` 污染，断言并非确定值**
`tests/e2e/test_n4b_chapter_v2_manifest_real_http.py:84-122` 断言 `manifest["dropped"] == []`、`over_budget is False`，但路由会无条件加载全局角色卡（`generate.py:250-254` → `characters/manager.py:12` `CHARACTERS_DIR = data_dir()/"characters"`）。测试只 patch 了 `NOVELS_ROOT`（`:48-53`），没隔离角色目录。当前本机卡块 428 字符（实测），离 40000 预算很远所以绿；一旦有人往 `data/characters/` 加大卡，E2E 会因与本特性无关的原因变红。
建议：在 fixture 里同时 `monkeypatch.setattr("story_engine.characters.manager.CHARACTERS_DIR", root/"characters")`，使"有卡/无卡"两种情形都受控。

**P1-2 传输字段名分叉：实现用 `context_manifest`，多处文档/前端注释用 `injection_manifest`**
实现与 `AGENTS.md`、`docs/design/P7-MVP-PLAN.md:96` 一致（`context_manifest`，`generate.py:340`），但以下位置仍写 `injection_manifest`：`src/story_engine/api/sse.py:18`、`src/frontend/src/utils/api.ts:52`、`docs/design/P7-MVP-PLAN.md:65`、`docs/design/reviews/P7-MVP-REVIEW.md:79/106/135`、`tests/test_writer/test_sse_contract.py:16`。N6 审稿页/前端按注释键 `injection_manifest` 取值会拿到 `undefined`，且不会有任何报错——典型的静默错配。
建议：本次一并把陈旧引用改到 `context_manifest`（或反向统一），并把该键写进 `docs/design/P7-ARCHITECTURE.md` 的 done 载荷契约。

**P1-3 上一章结尾的截断在 manifest 里不可见**
`chapter_tail` 在 **provider 内部**就截到 2000 字（`context_sources.py:112`），而槽位级截断标记来自 `_apply_slot_budget`（`context_builder.py:234-264`）→ `ManifestEntry.truncated`（`:320-329`）。因此真实 5 万字的前一章结尾被砍到 2000 字时，manifest 只显示 `chars=2000 / truncated=False`，作者无法知道"这是截过的"。这与架构对"注入可见性"的要求（`context_sources.py` 模块 docstring、`context_builder.py:30-39`）不符。
建议：provider 截断时显式留痕，例如 `source="chapter_tail:ch_0001(截2000)"`，或让 `ContextPiece` 带一个 `note/truncated` 字段透传到 `ManifestEntry`。

**P1-4 `_read_text` 吞掉 `OSError`，"读取失败"被伪装成"作者还没写"**
`context_sources.py:41-46` 把不存在与读失败统一返回 `""`，装配器随后记 `SkippedSlot(reason="empty")`（`context_builder.py:224`）。权限/IO 故障会被显示成"该槽位没内容"，与"没注成必须可见且原因准确（`error:<type>`）"的承诺冲突。覆盖率输出确认 `context_sources.py:44-45` 正是未测分支。
建议：只对 `FileNotFoundError` 返回空；其余 `OSError` 让它抛出，由 `_collect` 记成 `error:<类型>`（`context_builder.py:207-209` 已能承接），并补一条单测。

## 4. P2（可选优化）

- **`recap:N` 语义歧义**：`recap` 逐行成片段，`source=recap:1..N`（`context_sources.py:80-81`）是**行号**不是章号；作者看到 `recap:5` 会误以为是第 5 章。N7 要换成 `summary:ch_XXXX`（`docs/design/P7-MVP-PLAN.md:96`），两套 source 约定需要一份说明/迁移注记。
- **manifest 是易失的**：只挂在 `done` 载荷（`generate.py:339-340`），未随章节落盘。刷新/重开页面后看不到"当时注入了什么"，长期可见性打折。可在 N5/N6 把 `manifest` 存进章节旁文件。
- **`max_tokens=8192` 硬编码**（`generate.py:315`）与 `/chapter` 的 `word_estimate*2`（`:198`）口径不同，二者差异缺注释；建议注释说明或配置化。
- **长文本走 query string**：`beat/mainline/recap`（`generate.py:231-234`）可能很长，URL 走 h11 请求行有大小上限（`/depolish` 的 `text` query 是既有先例，`generate.py:452`）。建议改为 POST JSON body。
- **`task="generate"` 字面量**（`generate.py:314`）而 `/chat`、`/depolish` 用 `TASK_GENERATE` 常量（`:421/:485`）；建议统一。
- **空白覆盖文本**：`override or _read_text(...)`（`context_sources.py:67/92-95`）对纯空白串为真值 → 既不回退文件、又注入一段空白。建议 `override.strip() or ...`。
- **未知小说在 SSE 端点上返回 JSON**（`generate.py:243-248`，与 `/chapter:146-147` 同款）：前端 `readSSE` 拿不到 `event:` 行，会走解析异常分支。E2E 对此放得很松（`tests/e2e/...:193-197`：允许 200/400，且 payload 为空时**不做任何断言**，`_raw`/HTML 也能蒙混过去）。建议收紧为只接受 200 + JSON + `success is False`。
- **槽位预算把"字符常量"当 token 用**：`Slot.max_tokens=CHAPTER_TAIL_CHARS`（`context_sources.py:56-57`）与 `estimate_tokens=len()`（`context_builder.py:150-156`）目前恰好等价；一旦按语言加权（已知债）就会语义漂移，建议直接写 2000 并把常量语义注明为"字符"。
- **分隔符不计入任何 entry**：槽位块之间的 `"\n\n"`（`context_builder.py:332`）与 bullets 的 `"- "`（`:164`）不归属任何 `ManifestEntry`，故按 `slot_id` 汇总的 token 会略小于 `manifest.total_tokens`。作者用 entries 反推"某槽位占比"时会低估。可在 entry 上加 rendered 长度或明说这是下界。

## 5. 已核实为正确的地方（实际验证过）

- **全量绿**：`.venv/bin/python -m pytest -q` → `747 passed, 3 skipped`，覆盖率 94.88%（`context_sources.py` 95%）。`ruff` / `mypy`（新文件）均通过。
- **manifest → prompt 闭环成立**：路由把 `assembled.text` 原样嵌入 user message（`generate.py:294-302`），而 `build()` 的 `text = "\n\n".join(blocks)` 与 `entries` 同源（`context_builder.py:311-332`）；因此不存在"manifest 说有、prompt 没有"的路径。E2E 用假上游实收 body 断言四段手写件内容均在 prompt（`test_n4b...py:124-137`）确为真。
- **单一 done / 错误路径**：v2 生成器崩/空产出守卫抛 `LLMStreamError`（`llm/router.py:196-218`）时，异常在 `async for` 处抛出、`finally` 关闭生成器（`generate.py:321-327`），章节构造在循环之后，**不会写出空章节**；`event_stream` 转 `error` 且不再补 done（`sse.py:114-124`）。
- **E2E 真实链路**：`real_http_stack` 起真实 uvicorn + 真实 `X-API-Key`；无 key → 401（`test_n4b...py:168-179`）实测通过；未知小说返回明确 message（`:182-197`）。
- **`over_budget`/`total_tokens` 在裁剪后重算**：`context_builder.py:314-319` 只累加未 drop 的块，语义正确。
- **请求文本覆盖文件生效**：`test_explicit_text_overrides_file` 绿；`override or file` 优先级实现无误。
- **`extra_providers` 能覆盖标准 provider**：`providers.update(extra_providers)`（`context_sources.py:195-196`）可替换 `recap`，N7 换 SQLite provider 无需改装配器签名——E 问的"N7 是否够用"：**够**。
- **线程池使用合理**：`builder.build` 内有 `path.read_text`（`context_sources.py:42-43`）等阻塞 IO，`run_sync` 有必要，非纯 CPU。
- **角色卡链路**：`load_card` 返回 `CharacterCard`（`characters/manager.py:29-36`），`to_prompt_block` 可用（`models.py:47-67`），`Novel.characters: Dict[str, CharacterCard]`（`models.py:129`）经 pydantic 强制转换，未见 dict 穿透。
- **`word_count` 口径与 `/chapter` 一致**：均用 `strip_fallback_prefix`（`generate.py:334` vs `:220`）。
- **`_safe_novel_id` 防穿越**（`novel_storage.py:60-72`）；`mainline/recap/beats` 文件名固定或用整型格式化章号，无注入路径穿越。

对 D 中"改测试掩盖问题"的判断：**属于改成更正确的断言，不是掩盖**。全局角色卡确实存在并**确实被注入**（实测 block 428 字符），因此"characters 出现在 skipped"本身就是错误断言；改成"标准槽位必须要么注入/要么被裁/要么 skipped"的不变量更贴合事实。唯一代价是该 E2E 不再固定角色槽位置，但 `test_characters_use_existing_renderer`（`test_context_sources.py:116-128`）已单测覆盖——可接受。

## 6. 未覆盖的风险 / 我的判断可能有误之处

- **"作者能看到"只到后端为止**：N4b 只交付 done 载荷，前端 `api.ts` 尚无 `context_manifest` 消费方（grep 确认无 UI 引用）。若 N6 之前没有渲染，架构宣称的"作者必须能看到"在用户层面尚未成立——这可能是节点划分的有意留白，请确认。
- **P1-1 的严重度取决于 CI 环境**：若 CI 每次从干净 checkout（无 `data/characters` 或仅此小卡）跑，则当前不红；但它是"隐式全局状态依赖"，我按可维护性提到 P1。
- **`context_manifest` 命名**：我以 `AGENTS.md` 与 `P7-MVP-PLAN.md:96` 为准判定实现正确、其余为陈旧文档；若项目实际以 `injection_manifest` 为对外契约，则结论应反转（实现需改名）。请以团队契约为准。
- 我未运行浏览器 E2E（本次无前端改动），也未做真实模型 `live` 调用（默认跳过），这两项不构成本 diff 的验收阻塞。
