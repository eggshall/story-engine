# N0 评审报告 — 前端鉴权打通（X-API-Key）

> 评审对象：commit `c38bd04`「N0: 前端鉴权打通 — X-API-Key 注入 + 单测 + 真实浏览器 E2E」
> 参照基准：`docs/design/P7-MVP-PLAN.md`（§9 节点划分/流程/E2E 要求）、`docs/design/P7-MVP-REVIEW.md`（P0-1）、`AGENTS.md`（鉴权约定）
> 核验范围：`src/frontend/src/utils/api.ts`、`src/frontend/src/utils/__tests__/api.spec.ts`、`src/frontend/e2e/`、`scripts/e2e_dev_stack.sh`、`scripts/_read_api_key.py`、`src/story_engine/api/main.py`、`tests/test_auth.py`，并做全仓搜索与实测
> 评审角色：评审（只读；本轮未修改任何代码或既有文档，仅新增本文件）
> 日期：2026-10-11

---

## 0. 结论摘要（先给判断）

| 维度 | 结论 | 一句话依据 |
|---|---|---|
| 总体 | **通过（核心验收成立）** | 现网 401 已被实测消除；无绕过 `utils/api.ts` 的调用；无阻塞性缺陷 |
| A 现象消除 | ✅ 成立 | 无 Key→401 / 带 Key→200（经 vite 代理实测），真实浏览器 E2E 1 passed |
| B 测试有效性 | ⚠️ 部分偏软 | REST 用例**确实**经过请求拦截器（非假测）；SSE 用例仅测 3 个中的 1 个且未覆盖 `readSSE` |
| C key 存储/注入 | ⚠️ 可用但不完整 | `setApiKey()` **全仓无调用**，设置页未接入；生产若未构建期注入仍会 401 |
| D 回归风险 | ✅ 低 | 命名导出为增量、拦截器只加头、SSE 保留了 `Content-Type`；全量 pytest 637 / vitest 72 全绿 |
| E E2E 缺口 | ⚠️ 需补 | 未断言任一 200、未断言浏览器请求头、未覆盖 SSE 路径、无负向对照 |
| F 修复项 | **P0=0，P1=3，P2=4** | 均非阻塞，建议在 N0.5/N1 前处理 |

**实测命令与结果（本机复跑，证据）**

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q` | `637 passed`，覆盖率 `92.80%`（门禁 75%） |
| `npx vitest run`（`src/frontend`） | `12 passed`，`72 passed` |
| `npx vue-tsc --noEmit` | exit 0 |
| `npx vite build` | `✓ built in 6.13s` |
| `npx playwright test --config e2e/playwright.config.ts` | `1 passed (1.5s)`（复用 `~/.cache/ms-playwright/chromium-1223`） |
| HTTP 直连后端 | `/api/health` 无 Key→`200`；`/api/models` 无 Key→`401`；带 Key→`307`；跟随→`200`；错 Key→`401` |
| HTTP 经 vite 代理 5173 | `/api/models/` 无 Key→`401`，带 Key→`200`；`/api/health`→`200` |

---

## A. 修复是否真的消除现网 401？是否存在绕过 `utils/api.ts` 的直连？

**结论：✅ 消除；全仓无绕过。**

后端中间件（`src/story_engine/api/main.py:65-75`）在 `security.api_key` 已配置时对 `/api*`（`/api/health` 除外）强制校验 `X-API-Key`；`config/config.yaml` 已配置该 key，故此前浏览器必然全 401。前端注入点：

| 注入点 | 位置 | 覆盖 |
|---|---|---|
| axios 请求拦截器 | `src/frontend/src/utils/api.ts:28-32` | 所有 `api.get/post/delete...` |
| SSE 请求头 | `src/frontend/src/utils/api.ts:35-40`（`sseHeaders()`） | 3 处原生 `fetch`：`:177` outline、`:196` chapter、`:219` chat |

**全仓搜索（`rg` 排除 `node_modules/.venv/dist`）结论**：除上述 3 处 `fetch('/api/...')` 外，没有任何其它 `fetch`、`axios` 直连、`EventSource`、`WebSocket`、`XMLHttpRequest`。所有业务调用均经导出的 `api` 实例（`export default api` 见 `api.ts:292`），例如：

| 文件:行 | 调用 |
|---|---|
| `src/components/NovelTree.vue:198` | `api.get('/system/paths')` |
| `src/stores/novel.ts:59,74,92` | `api.post/delete('/novel/...')` |
| `src/views/WorldView.vue:296,311` | `api.get/post('/novel/current/map')` |
| `src/views/SettingsView.vue:397` | `api.post('/novel/.../update')` |
| `src/views/ResearchView.vue:203` | `api.get('/research/')` |
| `src/components/ChapterPanel.vue:108` | `api.post('/novel/.../reorders')` |

**实测证据**：`curl` 无 Key→`401`、错 Key→`401`、带 Key 经代理→`200`；浏览器 E2E 通过。**A 通过。**

---

## B. 测试是否"看起来测了其实没测"？

**结论：REST 用例是真的走了拦截器（非假测）；SSE 用例偏软。**

**B-1 REST 用例确实经过请求拦截器 —— 是有效测试。** 证据链：
- 依赖 axios `1.18.0`；`node_modules/axios/lib/core/dispatchRequest.js:46` 为 `const adapter = adapters.getAdapter(config.adapter || defaults.adapter, config)`，而 `dispatchRequest` 排在请求拦截器链**之后**执行，因此 `api.defaults.adapter` 被替换不影响拦截器先行。
- 用例只设置了 `X-API-Key` 的唯一来源是拦截器（`api.ts:28-32`）；`spec.ts:40-47` 断言带 Key 时头存在、`:49-55` 断言无 Key 时头不存在。有/无对照成立，排除"全局默认头"的可能。

**B-2 但存在弱化点：**

| 问题 | 位置 | 影响 |
|---|---|---|
| 3 个 SSE 只测了 `generateChapterStream` | `api.spec.ts:57-83` | `generateOutlineStream`(`api.ts:177`)、`chatStream`(`api.ts:219`) 无断言 |
| `body: null` 导致 `readSSE` 直接抛错被 `.catch` 吞掉 | `api.spec.ts:59,67` | 只验"发了 fetch + 头"，未验流解析/单一 done |
| 未在 `afterEach` 复位 `api.defaults.adapter` | `api.spec.ts:27` | 泄漏到后续用例；当前每例重设故未爆，属隐患 |
| 断言取 `init.headers` 普通对象下标 | `api.spec.ts:69,82` | 应统一用 `new Headers(init.headers).get(...)` 归一化大小写 |

**更硬的断言写法（建议）**

1. **SSE 用真实本地 HTTP server（node `http`，vitest `environment: node` 的独立文件），断言服务端收到的头 + 流解析：**
```ts
// 服务端记录 req.headers['x-api-key'] / req.headers['content-type']，并回一段真实 SSE:
server.write('event: token\ndata: {"token":"你好"}\n\n')
server.write('event: done\ndata: {}\n\n')
// 客户端：await collect(generateChapterStream({chapter_number:1}))
expect(serverSeen['x-api-key']).toBe(KEY)
expect(serverSeen['content-type']).toContain('application/json')
expect(tokens).toEqual(['你好'])       // 逐 token
expect(doneCount).toBe(1)              // 单一 done
```
2. **三函数参数化**：`it.each([generateOutlineStream, generateChapterStream, chatStream])` 各断言一次头。
3. **REST 增硬**：在 adapter 内断言 `config.headers instanceof AxiosHeaders`；或对 3 个真实端点走一次本地 server 断言服务端收到头（而非只查 adapter 收到的 config）；并在 `afterEach` 恢复真实 adapter。

**B 结论：不算"假测"，但未达到 P7-MVP-PLAN §9.3 对 SSE 的"逐 token + 单一 done"要求。**

---

## C. key 的存储与注入方式是否合理？切换是否需刷新？多环境是否冲突？

**结论：方向正确（localStorage 优先 > 构建期），但有 1 处功能空转 + 1 处潜在不一致。**

| 项 | 现状 | 评价 |
|---|---|---|
| 存储 | `localStorage['story_api_key']` 明文（`api.ts:9`） | 本地单用户工具可接受；XSS 可读、且**构建期密钥会打进 dist bundle**（`api.ts:12`），需在部署说明中标注 |
| 运行时切换 | `setApiKey()`（`api.ts:16-20`）**全仓无任何调用**（`rg` 仅命中定义） | 与 P7-MVP-REVIEW P0-1 建议的"从 VITE_API_KEY/设置读取"只完成一半；**设置页未接入** |
| 是否需刷新 | 无需：`getApiKey()` 在**每次请求/每次 SSE 调用**时读取，改 localStorage 后新请求即生效 | ✅ 但已加载数据不会自动重取，需重新导航/触发 |
| 生产可用性 | 若部署时未设 `VITE_API_KEY` 且用户未手写 localStorage，则 key 为空 → 拦截器不带头 → **仍 401** | ⚠️ P1：现网修复"必要条件"满足，但缺运行时录入入口 |
| 多环境 | `BASE_URL` 支持 `VITE_API_BASE`（`api.ts:4,23`），但 3 处 SSE **硬编码 `/api`**（`api.ts:177,196,219`） | ⚠️ 一旦 `VITE_API_BASE` 指向跨域/base path，REST 与 SSE 目标不一致 |
| 类型 | `src/frontend/src/env.d.ts:10` 仅声明 `VITE_API_BASE`，未声明 `VITE_API_KEY` | 借 `vite/client` 的字符串索引签名能过 `vue-tsc`，但不显式、易误改 |

---

## D. 回归风险

**结论：✅ 低，未发现回归。**

| 检查项 | 结论 | 证据 |
|---|---|---|
| 导出 `api` 实例 | 增量：原 `export default api`（`api.ts:292`）保留，新增命名导出 | 全仓 default 导入（`NovelTree.vue:175` 等）不破坏 |
| 拦截器影响所有请求 | 仅**追加**头，不删除/覆盖其它头；`if (key && config.headers)` 守卫 | `api.ts:28-32` |
| SSE 头替换是否丢原有头 | 未丢：改动前 3 处 headers 仅有 `Content-Type: application/json`，`sseHeaders()` 同样返回它（diff 可证） | 且单测 `spec.ts:70` 显式断言 `Content-Type` |
| 空 key 行为 | 无 key 时不设置头（`spec.ts:49-55` 覆盖） | 不会发送空 header |
| 全量回归 | `pytest 637 passed`、`vitest 72 passed`、`vue-tsc 0`、`vite build 0` | 见 §0 |
| 潜在（非阻断） | 拦截器对 `/api/health` 也加头（无害）；跨域时预检由外层 CORS 中间件短路，不受鉴权中间件影响 | `main.py:92` CORS 后注册=最外层 |

---

## E. 当前 E2E 的缺口（具体到页面/请求）

| # | 缺口 | 现状位置 | 建议补的断言 |
|---|---|---|---|
| 1 | 只断言"无 401"，未断言**任一 `/api` 响应为 200** | `e2e/n0-auth.e2e.ts:21-24` | `expect(apiResponses.some(r => r.status === 200)).toBe(true)`，并点名 `.../api/novel/`、`.../api/models/` |
| 2 | 未直接断言**浏览器请求确实带 `X-API-Key`** | 全文无 `page.on('request')` | `page.on('request', r => { if (r.url().includes('/api/')) expect(r.headers()['x-api-key']).toBeTruthy() })`（不打印值） |
| 3 | 未覆盖 **SSE 路径**（与 axios 拦截器是不同代码路径） | WritingView/OutlineView 未触发 | `await page.route('**/api/generate/chapter', route => { expect(route.request().headers()['x-api-key']).toBeTruthy(); route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: token\ndata: {"token":"测"}\n\nevent: done\ndata: {}\n\n' }) })`，再点生成并断言页面出现 token |
| 4 | 无**负向对照**（证明测试能抓回归） | 仅正向 | 加一例：`addInitScript` 清 localStorage 且不带 env → 断言出现 401（或跳过 env 服务另起无 key 场景） |
| 5 | 渲染断言偏软：`/test-novel|novel_ae0fa8d5|写作/` | `e2e/n0-auth.e2e.ts:28` | "写作"出现在导航，列表为空也能过；应断言小说条目 locator 可见，如 `await expect(page.getByText('test-novel')).toBeVisible()` |
| 6 | 仅冒烟 `/writing` 一页 | `e2e/n0-auth.e2e.ts:17` | 补 `/settings`、`/outline` 加载无 401（这些都是异步 `/api` 页） |
| 7 | 计划要求"产物截图/日志留痕"，但 `screenshot: 'only-on-failure'` | `e2e/playwright.config.ts:26` | 通过时也输出 run 日志/`trace` 留存，或在评审报告中附运行输出 |

---

## F. 最终结论与修复优先级

**结论：通过（核心验收成立）。** 现网 401 已被实测消除；无绕过路径；单测非假测；全量回归全绿；真实浏览器 E2E 通过。下列为**非阻塞**改进项，建议在 N0.5/N1 前处理。

| 优先级 | 问题 | 文件与改法 |
|---|---|---|
| **P0** | 无阻塞项 | — |
| **P1-1** | 生产无运行时录入 key 入口，未构建期注入则仍 401 | `src/frontend/src/views/SettingsView.vue` 增 API Key 输入并调用 `setApiKey()`（`api.ts:16`）；或加全局 401 拦截器提示配置（axios 响应拦截器） |
| **P1-2** | E2E 未覆盖 SSE 与 200/负向断言 | `src/frontend/e2e/n0-auth.e2e.ts`：按 §E-1/2/3/4/5 补断言（`page.route` stub SSE + 断言请求头 + 断言 200 + 负向 401） |
| **P1-3** | SSE 单测只覆盖 1/3 且未覆盖 `readSSE` | `src/frontend/src/utils/__tests__/api.spec.ts`：`it.each` 三函数；用本地 http server 喂真实 SSE 流，断言逐 token + 单一 done（§B） |
| **P2-1** | SSE 硬编码 `/api`，与 `VITE_API_BASE` 不一致 | `src/frontend/src/utils/api.ts:177,196,219` 改用 `BASE_URL` 拼接 |
| **P2-2** | `VITE_API_KEY` 未在类型声明 | `src/frontend/src/env.d.ts:10` 增 `readonly VITE_API_KEY: string` |
| **P2-3** | 构建期 key 打入 dist / localStorage 明文的安全性未说明 | 在 `AGENTS.md` 或部署文档注明：生产优先用运行时录入，避免把密钥烘进 bundle |
| **P2-4** | 单测 adapter 泄漏、SSE 头断言未归一化 | `api.spec.ts`：`afterEach` 复位 `api.defaults.adapter`；用 `new Headers(init.headers).get('X-API-Key')` |

> 备注：`e2e/` 仍在 `src/frontend/e2e/`，符合 N0.5「上移到项目根」的既定待办，非 N0 缺陷。
