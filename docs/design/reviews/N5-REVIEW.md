# N5 评审报告 — A 类校验器 5 条 + `POST /api/check/chapter`

## 1. 结论

**需补充后通过**。5 条规则、路由、schema、单测与真 HTTP E2E 基本达标（38 例全绿，ruff/mypy 干净，鉴权/确定性/读盘都真实覆盖）；但有 2 处必须在提交前治本：**风格画像基线分支是死代码**（与文档/验收矛盾且无真实数据测试），以及 **`AI_PATTERNS` 里的 `在[\w]+的[\w]+下` 会把正常中文硬告警**（违反"宁跳过不误报"的项目铁律）。

---

## 2. P0（必须修）

### P0-1 风格画像基线分支是死代码：`profile_id` 实际不起任何作用
- 证据链：
  - 校验读画像：`api/routes/check.py:64-66` 取 `profile.features` 原样返回 → `check/rules.py:117` 用 `(profile_features or {}).get("dialogue_ratio")` 找英文键。
  - 但真实画像 features 全是**中文键**：`style/analyzer.py:97-103`（"词汇水平"/"对话比例"…），`style/db.py:85` `DIALOGUE_RATIO = "对话比例"`，`style/recommend.py:18-32` 也按中文键取。
  - 我实测现有唯一写画像的流程 `POST /api/style/analyze`（`style.py:120,138`）产出的就是中文键结构 `{"对话比例": {"value": "...", "score": n}}`；全仓 `rg '"dialogue_ratio"'` 在 `style/` 下只命中 metrics/drift，**没有任何一处把 `dialogue_ratio` 写进 `profile.features`**。
- 后果：`Baseline(source="profile")` 永不触发 → 文本模式带 `profile_id` 永远落到 `previous_chapters`（无前序则 `none`/`skipped`）。`check.py:15` 的 `"风格画像 > 前序章节中位数 > 无"` 与 `P7-MVP-PLAN.md:170-171` 的验收（"基线来自风格画像或前序章节"）**均未真正实现**。
- 测试是"看起来测了其实没测"：`tests/test_check/test_rules.py:196-201` 用**手搓的** `{"dialogue_ratio": 0.42}` 断言 profile 胜出，没有任何用例用真实 `StyleProfile`/`StyleDb` 走一遍。这正是计划书 §9.2 要防的那类假绿。
- 建议改法：在 `_profile_features` 内做键映射（读 "对话比例" 的 `value`/`score`，或改用 `metrics`），并新增一个用真实 `StyleDb().save_profile(StyleProfile(...))` 的契约测试证明 `baseline_source == "profile"`；若决定不做画像基线，就删掉该分支与文档承诺。

### P0-2 `check_ai_flavor` 把 `在[\w]+的[\w]+下` 当硬套话逐条 warn（正常中文被误报）
- 证据：`check/rules.py:301-312` 无条件遍历全部 `AI_PATTERNS`；其中 `polish/__init__.py:33` 的 `(r"在[\w]+的[\w]+下", "")` 对 Unicode `\w` 会匹配任意中文。实测：
  - 输入 `"在夜色的笼罩下，他慢慢往前走。"` → 产出 `warn`，`location.excerpt = "在夜色的笼罩下"`。
- 这是确定性的高误报源，直接违背本节点文件头 `check/rules.py:10-12` 与项目"宁跳过也不误报"的教训。
- 建议改法：把该结构正则从"硬告警"里剔除（`AI_PATTERNS` 是给 `DeAIFilter.clean` 的替换表，不适合原样当硬告警表）；若要保留，降级为软性聚合，或限定明确套话（"在一定程度上""从某种角度来说"）。

---

## 3. P1（应该修）

### P1-1 视角规则不剥离引号 → 对话里的第三人称被判"视角突跳"
`check/rules.py:210-217` 只对段落做人称计数、不剥引号（`metrics._QUOTE_SPAN` 已存在但没用）。实测第一人称正文里一句人物对白：

```
我推开门，我看见他站在窗边。
「他昨天就走了，他说他不会再回来。」我说。
我叹了口气，我轻轻关上门。
```
第 2 段计数 `{first:1, third:3}` → 被判 `third`，规则报 `warn`、`jump_paragraphs:[2]`。这是高频误报。建议先 `_QUOTE_SPAN.sub("", para)` 再计数，或对引号内人称加权为 0。

### P1-2 `metrics._THIRD_PERSON` 含 `"它"`，第一人称场景描述物体被误判
`style/metrics.py:39` `("他","她","它","祂")`。实测第一人称文本 `"我拿起它，我看了它一眼。\n\n…\n\n它静静地躺在桌上，它泛着冷光。"` → 第 3 段 `{first:0, third:2}`，主视角被判 `third` 并告警。建议视角只看"他/她"，`它` 归为物件不计入（或单独处理）。

### P1-3 视角告警文案是错的，且 `pov` 变量未用
`check/rules.py:241,249`：`idx, pov = jumps[0]` 取了 `pov` 却从不使用；suggestion 里 `{'第一/第三人称'}` 是**单元素集合字面量**，永远渲染成字面串 `"第一/第三人称"`。实测输出 `"…但第 2 段只有第一/第三人称混用…"`，对作者是误导。应改为按 `pov` 输出 `第一人称`/`第三人称`，或删掉 `pov`。

### P1-4 文本模式 `strip()` 后返回的字符偏移相对客户端看不到的串
`api/routes/check.py:73` `text = (req.text or "").strip()`，随后所有 `location.start/end` 都是相对**去空白后**的文本。E2E 甚至把这点写死了（`tests/e2e/test_n5_check_real_http.py:71`）。N6 审稿页若拿原始粘贴文本按 `start:end` 跳转将**整体错位**。建议：只判空不 `strip()`（或 `lstrip` 记录偏移），保证 offset 相对请求原文。

### P1-5 整章级别 `level` 把 `skipped` 排在 `ok` 之前，干净文本显示 `skipped`
`check/rules.py:64` `order={"alert":0,"warn":1,"skipped":2,"ok":3}`。文本无基线但其余全通过时 `level=="skipped"`（`test_check_api.py:82` 用 `in ("ok","skipped")` 默认接受了）。作者会读成"没校验"。建议 `level` 只反映可执行结论（alert/warn/ok），把"有规则跳过"用独立的 `incomplete: bool` / `skipped_rules[]` 表达。

### P1-6 "硬套话"把正常连接词逐条告警
`polish/__init__.py:16-17` 的 `然而[，,]`/`但是[，,]` 被 `rules.py:301` 当硬告警。实测 `"但是，他还是答应了。"` → `warn "AI 套话「但是，」…"`。这两词是正常中文，且与 `SOFT_PATTERNS`（`:38-39`）重复计数（同一处既硬 warn 又计入软聚合，双重噪音）。建议硬表只留"值得注意的是""毋庸置疑"等真正套话，把"然而/但是"交给软性聚合。

### P1-7 E2E 确定性断言可能被"两次都失败"骗过
`tests/e2e/test_n5_check_real_http.py:113-128` 只断言 `first == second`。`ApiResponse.data: Any = None`（`schemas.py:272`），若两次都返回 `success=False`，则 `first == second == None` 仍通过。该用例没有像 `test_text_mode_returns_full_report` 那样先断言 `success is True`/`findings` 非空。建议加 `assert 两次 success is True 且 findings 非空`。

### P1-8 与 `style/drift.py` 重复且阈值不一致
`check/rules.py:29` 对话容差 `0.15`，`style/drift.py:40` 同一指标用 `0.18` 且是聚合判级模型；`P7-MVP-PLAN.md:29` 本意是"MVP-2 直接启用 drift 为校验器内核"。现在两套"对话占比容差"并存，日后必然漂移。建议二选一：把 `check/rules.py` 的对话判定改为调用 `drift.detect_drift`（或至少共享阈值常量），并在文档里明确 drift 的接入点。

---

## 4. P2（可选优化）

- **段长多条 warn 会刷屏**：`check/rules.py:174-196` 每个超长段产一条独立 Finding（同 `rule_id`），N6 需按 `rule_id` 分组展示，否则长文多段直接淹没审稿列表。
- **`summary()` 信息量不足**：`rules.py:69-73` 只有级别计数，没有"通过规则数/跳过原因"；三栏中栏做规则清单时需要后端补 `rules_run` 之外的按规则归并。
- **`dialogue_ratio` 的 warn 没有 location**：`rules.py:286-295` 未传 `location`，与"每条 warn 都能定位"的契约不符；前端必须处理 `location == null`。相对指标可接受无定位，但应在 schema/文档里明说哪些规则可能为 null。
- **`details` 形状未定义**：后端 `Dict[str, object]`（`rules.py:51`）、schema `Dict[str, Any]`（`schemas.py`），不同规则键各不相同，前端若依赖它渲染需先定形状；否则请前端只用 `level/suggestion/location`。
- **`min_previous=2` 使第 2 章永远拿不到对话判定**（`rules.py:111,121-122`），叠加 P0-1 后早期章节完全无对话基线。可考虑单章时用更宽容差而非直接跳过，保持"不误报"前提下增加覆盖率。
- **`anyio.to_thread.run_sync(run_rules, …)` 多余**：`check.py:95` 是短 CPU 纯函数；把端点声明为同步 `def`（FastAPI 自动丢线程池）更简单。`_profile_features` 走线程还牵出 `StyleDb` 的线程局部连接（`db.py:20,109-118`），非必须。
- **`context_manifest` 落盘待办未处理**：`P7-MVP-PLAN.md:177-178` 明确"N5/N6 把它随章节落盘"。本节点没做（也没在路由 docstring 里承认把它推给 N6）。请显式决定由 N6 承接，避免计划项静默丢失。
- **`似乎[似乎]`/`仿佛[仿佛]` 是坏正则**（`polish/__init__.py:30-31`）：只匹配"似乎似/似乎乎"，`"他似乎明白了什么。"` 实测不命中 → 硬表里这两条永远死。顺带修。
- **章末钩子价值偏低**：`HOOK_KEYWORDS` 含"得到/获得/突破"这类普通词（`polish/__init__.py:169-175`）。实测 `"他最终得到了那件东西。"` → `ok`；而安静文学收尾 `"…天边露出灰白。"` → `warn`。既不敏感又会给文学性收尾添噪音，建议把建议语气降到"可忽略"，或改判 `skipped`。
- **`test_consistent_pov_passes` 的"不命中"侧是人造的**：`test_rules.py:99-105` 每段补到 2 个"我"才过。真实常见的"1 个我/段"会走 `skipped`（被 `POV_MIN_MARKERS` 静默丢弃），该路径没有"不误报"用例覆盖。
- **自定义路径小说未覆盖**：`_load_chapter_text` 走 `load_novel` → `_novel_dir`（`check.py:38-40`）本应支持自定义路径，但无 E2E/单测（计划 P0-7 要求覆盖）。

---

## 5. 已核实为正确的地方（我实际跑过/读过）

- **测试全绿**：`.venv/bin/python -m pytest tests/test_check tests/e2e/test_n5_check_real_http.py` → 38 passed（24 rules + 9 api + 5 e2e），与描述数量一致；`ruff check` 与 `mypy` 对新文件均无问题。
- **E2E 是真跨层**：`tests/e2e/fake_upstream.py:228-266` 起真实 uvicorn（`port=0` 随机端口）＋真实中间件；`test_requires_api_key` 无头得 401、其余带 `X-API-Key` 得 200，鉴权确实覆盖新端点。
- **`pov_counts` 重构一致**：`metrics.py:120-143` 的 `pov_ratios` 改为基于 `pov_counts` 实现后语义不变（`_FIRST_PERSON`/`_THIRD_PERSON` 计数），`measure()` 仍输出 `pov_first_ratio/pov_third_ratio`。
- **确定性**：单测 `test_deterministic` 与真 HTTP 的两次请求字节一致均通过；`run_rules` 无随机/时间/模型调用。
- **无基线不误报**：`test_without_baseline_*` 与 E2E `by_rule["dialogue_ratio"]["level"] == "skipped"` 均证实。
- **基线取中位数**：`rules.py:123-124` 用 `statistics.median`，抗单章异常，符合 prompt 与漂移教训。
- **容差边界包含**：`rules.py:277` `abs(delta) <= DIALOGUE_TOLERANCE_PP` 为闭区间，`test_within_tolerance_band_passes`（+10pp）验证。
- **错误路径显式**：缺参数（`check.py:76-81`）、未知小说/空章（`check.py:85-89`）都返回 `success=False`＋可读 message，无异常泄漏。
- **schema 兜底**：`check.py:97` `CheckReportPayload.model_validate(report.to_dict())` 能在字段漂移时炸掉；端点用 `model_dump()`（snake_case）与其它路由（`novel.py:73` 等）一致，无 camelCase 不一致问题。
- **章号筛选**：`check.py:43-48` 排序后取 `< chapter_number`，空书/缺章处理正确。
- **空文本不崩**：`test_empty_text_does_not_crash` 通过。

---

## 6. 未覆盖的风险 / 我的判断可能有误之处

1. **P0-1 的严重度**可辩：它不产生错误告警（安全降级为 skipped），所以也可能是"P1 功能缺失"。但既然验收/注释/测试都声称画像优先，我按"文档与实现不符＋假绿测试"定为 P0；若维护者接受降级为 P1，请在 commit message 里说明画像基线改为 N6 交付。
2. **P0-2 是否算 N5 引入**：`AI_PATTERNS` 是既有 `polish` 表，但"把整张表逐条当硬告警"是 N5 的新决策，所以我把误报责任归到 `check_ai_flavor`。
3. **POV 误报（P1-1/1-2）实际频率**依赖文本；我给的样例是构造的，但都是小说常见写法（对话引用第三人称、第一人称写物件），不是我硬凑的边界。
4. 我没有跑**全量** pytest（会触发 75% 覆盖率门禁且耗时长）；结论基于 N5 相关子集。全量回归请在修复后自行跑一次。
5. `docs/design/reviews/N5-REVIEW.md` 当前只有一行占位内容；按 §9.4 它应是归档的评审报告本体——请确认这是否由你的评审流水线自动写入，还是需要人工补齐。
