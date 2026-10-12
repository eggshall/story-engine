I'll start by inspecting the working tree state and the diff.
Let me read the full diff and the changed files.
Now the untracked files and remaining diffs.
Now let me run the tests to verify they're actually green and test the claimed behavior.
Let me empirically verify a suspected R4 gap (error then done ordering).
Let me run the full backend suite to check for regressions.
# N2 评审报告：SSE 单一 `done` + done 载荷契约

## 1. 结论
**需补充后通过** —— 主干契约（单一 done + 载荷转发 + 前端 `onDone(payload)`）实现正确、单测/E2E 真实且全绿；但存在 3 个应修问题（R4 在 error→done 顺序下未真正生效、开发栈前端进程清理会漏杀、临时配置把真实 `api_key` 以 0644 落盘且不清理）。

验证基线（我实际跑的）：
- `pytest -q --no-cov` → **683 passed, 3 skipped**
- `npx vitest run` → **85 passed**
- `ruff` / `mypy` / `vue-tsc --noEmit` → 全清
- 新增 E2E：`tests/e2e/test_n2_sse_done_real_http.py` + `test_n1...` → **7 passed**
- `e2e/test-results/.last-run.json` = `{"status":"passed"}`（20:22，与新增 spec 时间吻合）

---

## 2. P0（必须修）
无。核心跨端链路工作正常，未发现会破坏验收的缺陷。

---

## 3. P1（应该修）

### P1-1　R4「error 流不得有 done」在 error→done 顺序下不成立
- 位置：`src/story_engine/api/sse.py:80-85`（done 分支）与 `:97-98`（补 done 的守卫）。
- 证据：补 done 的守卫检查了 `error_sent`，但**循环内**遇到生成器显式 yield 的 done 时只判断 `done_sent`，不判断 `error_sent`。我实跑了一个探针生成器 `yield {"error": ...}; yield {"done": True, ...}`：

  ```
  EVENTS: ['error', 'done']
  [{"error": "先出错"}, {"done": true, "chapter": {...}}]
  ```
- 影响：与模块 docstring 第 23 行与 `tests/test_writer/test_sse_contract.py:18` 宣称的 R4 矛盾；契约测试也没有覆盖这个顺序（只测了单独 error、done→error）。当前路由都在 error 后 `return`（`generate.py:171/135`），所以是**潜在**缺陷，但契约被测试锁死为「保证」，应当在包装层真正保证。
- 建议改法：在 `if "done" in item:` 分支加 `if error_sent: continue`（或直接 `break`/`return`），并补一条 `test_error_then_done_is_suppressed` 用例锁死。

### P1-2　`scripts/e2e_dev_stack.sh` 清理会漏杀 vite/node（前端 PID 是子 shell）
- 位置：`scripts/e2e_dev_stack.sh:54-56`（`( cd src/frontend && ... npx vite ... ) & FRONT=$!`）配合 `:23-28` 的 `cleanup`（`kill "$pid"`）。
- 证据：`FRONT` 是**子 shell** 的 PID，而 vite/node 是它的子进程。我用等价的 `( sleep 314 ) & P=$!; kill $P` 实测：

  ```
  subshell_pid=151718
  LEAKED: sleep still alive after killing subshell
  ```
  子 shell 被杀后其子进程被 reparent，`wait` 也无法回收 → 端口 5173 可能被残留占用，与脚本第 13 行「避免残留占用 8000/5173/8899」的承诺不符。后端（`:50-53`）与假上游（`:37-39`）是直接 exec 的 python 进程，`kill` 有效，问题只在前端。
- 建议改法：子 shell 内用 `exec npx vite ...`（让 `$!` 即 vite 本身），或启动时 `setsid`、清理时 `kill -- -"$FRONT"` 杀进程组，或在 cleanup 里补 `pkill -P "$FRONT"`。

### P1-3　临时配置把真实 `security.api_key` 以 0644 写入 `/tmp` 且退出不清理
- 位置：`scripts/e2e_fake_config.py:56-61`（原样 dump 真实配置，含 key）+ `scripts/e2e_dev_stack.sh:45-46`（固定 `--out /tmp/e2e_fake_config.yaml`）+ `:23-28`（cleanup 只杀进程，不删文件）。
- 证据：`ls -l /tmp/e2e_fake_config.yaml` → `-rw-r--r-- 1 <user> <user> 511 ...`（本机 umask 0022）。该文件明文保存真实 `api_key`（脚本注释只说「不打印」，但落盘仍是对密钥的复制），任何本地用户/进程可读，且退出后长期留存。
- 影响：与项目 AGENTS.md「密钥来源与安全」约定相悖；虽为单用户本机场景影响有限，但属应修的泄漏面。
- 建议改法：用 `mktemp`（默认 0600）或写后 `chmod 600`；并在 `cleanup` 中 `rm -f "$CFG_ENV"`。注意 prompt 本身也强调不得暴露该 key，评审仅列路径/权限，未读取内容。

---

## 4. P2（可选优化）

- **P2-1 `error` 之后仍可能继续下发 token / 再次 error**：`sse.py:74-95` 在 `error_sent=True` 后不终止循环；若生成器 yield error 后继续 yield，会继续产生事件（前端 `readSSE` 在 error 处即 return/throw，实际不可达，但契约上不干净）。建议 error 后 `break`。
- **P2-2 断言偏弱**：`tests/e2e/test_n2_sse_done_real_http.py:148-149` 用 `names.count("done") <= 1`，"跨流兜底"用例允许 0 个 done 也算过；建议 `== 1`。
- **P2-3 `readSSE` 提前 return 不释放 reader**：`api.ts:86` return 时未 `reader.cancel()`（`:62` 取到 reader）。N2 之前就存在，非本节点引入；done 是最后事件影响小。
- **P2-4 遗留构造器**：`sse.py:112-117` 的 `format_sse_done()/format_sse_error()` 仍产出旧形状 `{"done": true}`（无载荷），当前无路由使用（仅单测引用）。建议与 `done_payload/error_payload` 统一或标注 deprecated，避免后人误用回旧行为。
- **P2-5 `parseDonePayload` 对空载荷的容忍**：`api.ts:118-128` 把空/非法 data 当 `{done:true}`，会让"后端漏发载荷"在 UI 上不可见。当前由 E2E 对 chapter/outline 载荷做硬断言兜住，可接受；可考虑在 `console.warn` 之外加灰度统计。
- **P2-6 `STORY_CONFIG_PATH` 无路径校验**：`config.py:49-55` 若指向不存在文件，`Config._load`（`:98-99`）静默回退空配置 → `security.api_key` 为空 → 中间件退化为「仅回环」（`main.py:75-81`）。不是远程绕过，但生产误设会造成服务不可达级别的配置漂移，建议启动时对显式覆盖做 `exists()` 校验/告警。
- **P2-7 `R3` 告警可能把正文写进日志**：`sse.py:77` `%r` 打印被丢弃的 item，若 done 后混入长 token，会以 WARNING 落盘整段内容。影响低。
- **P2-8 `generateOutlineStream` 返回类型语义过时**：`api.ts:208-213` 仍声明 `AsyncGenerator<string>`，实际该接口不再产出有意义的 token（`OutlineView.vue:123` 用 `_token` 丢弃）。建议更新注释/类型以免后续调用方误把返回值当结构体。

---

## 5. 已核实为正确的地方（我实际验证过的）
- **所有流式出口都已覆盖**：全仓 `EventSourceResponse` 只有 `generate.py:120/158/310/371`（outline/chapter/chat/depolish）与 `style.py:254`，全部经 `event_stream`；无遗漏的流式路由。
- **无消费者依赖旧行为**：`rg` + 全量 `pytest` 全绿证明没有测试/脚本依赖「双 done」或「done 无载荷」；`test_analyze.py:306`（depolish 断言 `event: done`）在改动后仍通过（补 done 路径）。
- **跨端字段对齐**：后端 `done_payload(chapter=chapter.model_dump(...))`（`generate.py:227`）→ 前端 `WritingView.vue:341 donePayload?.chapter` 及 `:343-345 title/word_count`，与 `Chapter` 模型 snake_case（`core/models.py:112-120`）一致；`done_payload(outline=...)`（`:133`）→ `OutlineView.vue:125 p?.outline`，`applyOutline` 读取的 `chapter_number/title/summary/beats/key_scenes`（`:140-146`）与 `ChapterOutline`（`core/models.py:102-109`）一致。
- **R1/R2/R3 单测真的在测被测行为**：`test_sse_contract.py` 覆盖生成器自带 done 不重复、载荷保留、重复 done 去重、done 后 token/error 丢弃、done 后异常不补 done、未知异常脱敏；我实跑 35 例全过。
- **E2E 真的跨了鉴权与真实 socket**：`tests/e2e/test_n2_sse_done_real_http.py` 用 httpx 打真实 uvicorn 端口；由于临时配置的 key（`e2e-n2-key`）与真实配置不同，若中间件没读到临时配置就会 401、`status_code==200` 断言必失败——用例通过本身即证明鉴权中间件真实生效。
- **Playwright 的 fetch tee 不会「静默永远通过」**：`e2e/n2-chapter-stream.e2e.ts:112-121` 先 `expect.poll(...__sseBodies.length).toBeGreaterThan(0)`，clone 失败/无体时会明确失败；随后 `:127-143` 断言 `event: done` 恰好 1 行且载荷 `chapter.content/title` 正确，并在 `:109` 用「本地占位标题为空 → 只能是后端载荷」的界面断言交叉验证。
- **前端 done 解析边界**：`api.sse.spec.ts` 覆盖载荷送达、只认第一个 done、空/非法 JSON 不炸，实跑 10 例全过。
- **设计取舍合理**：把单一 done 放在 `event_stream` 包装层（provider 无关、一处保证）比各路由各自保证更稳；`hooks?: StreamHooks` 为可选第二参，对 `AiChatPanel.vue:203`、`WritingView.vue:419/504` 等现有调用零侵入，且 `StreamDonePayload` 的 `[key:string]:any` 足以承载 N4 的 `injection_manifest`。

---

## 6. 未覆盖的风险 / 我的判断可能有误之处
- **Playwright 浏览器 E2E 我未亲自重跑**（只依据 `e2e/test-results/.last-run.json` 的 `status: passed` 与文件时间戳）。若需绝对证据，应再跑一次 `bash scripts/e2e_dev_stack.sh --fake` + `npm run e2e`。
- **P1-2 的漏杀结论来自等价子 shell 实验**，未直接对真实 dev stack 做进程树核验；理论上若 bash 对子 shell 末命令做了 exec 优化则不一定复现——但真实脚本子 shell 内是 `cd && npx`（两条命令），不会 exec 优化，判断成立。
- **P1-3 的严重度依赖部署形态**：单用户本机可视为低危，多用户/共享机器则是真实泄漏；我按项目的密钥安全约定给了 P1。
- **P1-1 当前无路由触发**（latent），若评审者认为「契约只需覆盖现实路由」可降为 P2；但既然单测 docstring 把 R4 写成保证，我倾向按契约缺陷处理。
- 我**没有**阅读/输出 `config/config.yaml` 或 `/tmp/e2e_fake_config.yaml` 中的任何密钥值；P1-3 只依据文件权限与脚本代码。
