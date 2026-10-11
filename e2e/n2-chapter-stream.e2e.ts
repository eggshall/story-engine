import { expect, test } from '@playwright/test'

/**
 * N2 节点 · 真实浏览器 E2E（真实 vite + 真实后端 + 真实 SSE + 本地假上游）
 *
 * 前置：`bash scripts/e2e_dev_stack.sh --fake`
 *   - 后端 127.0.0.1:8000 用 STORY_CONFIG_PATH 指向"模型=本地假上游"的临时配置
 *   - 前端 127.0.0.1:5173（VITE_API_KEY 注入，鉴权链路真实）
 *   - 假上游流式固定产出「擂台之上」，非流式返回固定大纲（标题「试炼」）
 *
 * 为什么必须用浏览器跑：N2 改的是 SSE 帧与"载荷送达"这条跨层行为。单测只能证明
 * 后端补了什么、前端解析了什么；这里证明**整条链路**上真的有且只有一个 done，
 * 且 done 载荷确实被页面消费（章节标题被采用）。
 *
 * 三层证据（同一份数据）：
 *   1) 网络层：浏览器侧嗅探到的 SSE 原始响应体里 `event: done` 恰好 1 次
 *      —— 用 initScript 给 window.fetch 挂一个 tee（不影响被测行为），
 *      因为 Chromium 对已被应用读掉的流式响应不保留 body（response.text() 会报
 *      "No data found for resource"）。
 *   2) 协议层：该 done 的 data 是 JSON 且含 chapter 载荷
 *   3) 界面层：正文渲染进编辑器、章节标题来自 done 载荷（本地占位章节标题为空，
 *      只有采用载荷才可能是「试炼」）
 */

const NOVEL_TITLE = `E2E-N2-${Date.now()}`
const EXPECTED_TEXT = '擂台之上'
const EXPECTED_TITLE = '试炼'

// 1280x720 下右侧 AI 面板会压住写作页顶栏（生成按钮被遮挡 → 点击被拦截），
// 用足够大的视口让三栏布局各就各位（这也是真实写作时的窗口尺寸量级）。
test.use({ viewport: { width: 1680, height: 1050 } })

test.describe('N2 · SSE 单一 done + 载荷（真实浏览器）', () => {
  test('生成章节：全链路只有一个 done，且 done 载荷进了界面', async ({ page }) => {
    test.setTimeout(120_000)

    // 网络层嗅探：给 fetch 挂 tee（只观察，不改变请求/响应），把章节流的原始 SSE 文本留档
    await page.addInitScript(() => {
      const origFetch = window.fetch.bind(window)
      const store: string[] = []
      ;(window as unknown as { __sseBodies: string[] }).__sseBodies = store
      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const res = await origFetch(input as RequestInfo, init)
        const url = typeof input === 'string' ? input : (input as Request).url || ''
        if (url.includes('/api/generate/chapter')) {
          res
            .clone()
            .text()
            .then((t) => store.push(t))
            .catch(() => undefined)
        }
        return res
      }
    })

    const pageErrors: string[] = []
    page.on('pageerror', (e) => pageErrors.push(String(e)))

    // 自清理用：从页面实际发出的请求里取到鉴权头与新建的小说 id（只在本进程内使用，不打印）
    let observedApiKey = ''
    let createdNovelId = ''
    page.on('request', (req) => {
      const key = req.headers()['x-api-key']
      if (!observedApiKey && key && req.url().includes('/api/')) observedApiKey = key
    })
    page.on('response', async (res) => {
      if (createdNovelId) return
      if (res.request().method() === 'POST' && /\/api\/novel\/?$/.test(new URL(res.url()).pathname)) {
        try {
          const body = await res.json()
          createdNovelId = body?.data?.id || body?.id || ''
        } catch {
          // 解析不到就退化成"手动清理"，不阻断断言
        }
      }
    })

    // ── 建一部小说（走真实 UI + 真实后端）──
    await page.goto('/writing')
    await page.waitForLoadState('networkidle')
    await page.locator('.tree-header button').first().click()
    await page.locator('input[placeholder="输入小说标题"]').fill(NOVEL_TITLE)
    await page.getByRole('button', { name: '创建' }).click()

    await expect(page.locator('.chapter-panel'), '创建后应进入章节面板').toBeVisible()

    // ── 生成章节 ──
    // 先登记"生成请求已发出"的期望，让"按钮没点到"这类问题以明确信息失败，
    // 而不是最后卡在 60s 的正文断言上。
    const genRequest = page.waitForRequest(
      (req) => req.url().includes('/api/generate/chapter'),
      { timeout: 20_000 },
    )
    await page.locator('.topbar-right button').filter({ hasText: '生成' }).first().click()
    await genRequest

    // 界面层：正文逐 token 渲染进编辑器
    const editor = page.locator('.chapter-editor textarea')
    await expect(editor, '假上游正文应逐 token 渲染进编辑器').toHaveValue(
      new RegExp(EXPECTED_TEXT),
      { timeout: 60_000 },
    )

    // 界面层：空产出/报错必须没有出现
    const body = await page.locator('body').innerText()
    expect(body).not.toContain('生成失败')

    // 界面层：标题来自 done 载荷（本地占位章节标题为空 → 只能来自后端载荷）
    await expect(page.locator('.chapter-title-input input')).toHaveValue(EXPECTED_TITLE)

    // 网络层 + 协议层：浏览器侧看到的原始 SSE 体
    await expect
      .poll(
        async () =>
          await page.evaluate(
            () =>
              (window as unknown as { __sseBodies?: string[] }).__sseBodies?.length ?? 0,
          ),
        { message: '应嗅探到 /api/generate/chapter 的响应体', timeout: 30_000 },
      )
      .toBeGreaterThan(0)

    const rawBodies: string[] = await page.evaluate(
      () => (window as unknown as { __sseBodies?: string[] }).__sseBodies ?? [],
    )
    const rawBody = rawBodies[rawBodies.length - 1]
    const doneLines = rawBody.split('\n').filter((l) => l.trim() === 'event: done')
    expect(doneLines, `done 事件数应为 1，实际响应体:\n${rawBody}`).toHaveLength(1)

    const donePayloads = rawBody
      .split('\n')
      .filter((l) => l.startsWith('data: '))
      .map((l) => {
        try {
          return JSON.parse(l.slice(6))
        } catch {
          return null
        }
      })
      .filter((p) => p && p.done === true)
    expect(donePayloads, 'done 载荷必须是合法 JSON 且 done=true').toHaveLength(1)
    expect(donePayloads[0].chapter?.content?.trim()).toBe(EXPECTED_TEXT)
    expect(donePayloads[0].chapter?.title).toBe(EXPECTED_TITLE)

    expect(pageErrors, `页面不应有未捕获异常: ${pageErrors.join(' | ')}`).toHaveLength(0)

    // ── 收尾：删掉本次 E2E 建的小说，避免 data/novels 越跑越脏 ──
    expect(createdNovelId, '应能记录到本次新建的小说 id（用于自清理）').not.toBe('')
    expect(observedApiKey, '应能从页面请求里取到鉴权头（用于自清理）').not.toBe('')
    const del = await page.request.delete(`/api/novel/${createdNovelId}`, {
      headers: { 'X-API-Key': observedApiKey },
    })
    expect(del.status(), `自清理删除应成功(200)，实际 ${del.status()}`).toBe(200)
  })
})
