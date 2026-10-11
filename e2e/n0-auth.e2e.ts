import { expect, test } from '@playwright/test'

/**
 * N0 节点 · 真实浏览器 E2E
 *
 * 前置：后端 127.0.0.1:8000 + vite 5173（`bash scripts/e2e_dev_stack.sh`，前端带 VITE_API_KEY）。
 * 覆盖（含评审 P1-2 补强）：
 *  1) 写作页加载：无 401 + 至少一个 /api 响应 200 + 浏览器请求确实带 X-API-Key
 *  2) 负向对照：localStorage 放错 key 时必须出现 401（证明测试能抓回归）
 *  3) 设置页运行时录入密钥：填写 → 保存 → localStorage 生效
 *  4) 多页冒烟：/settings、/outline 加载无 401
 */
test.describe('N0 · 前端鉴权打通（真实浏览器 + 真实后端）', () => {
  test('写作页加载后无 401、有 200，且浏览器请求带 X-API-Key', async ({ page }) => {
    const apiResponses: { url: string; status: number }[] = []
    const missingKey: string[] = []

    page.on('response', (res) => {
      if (res.url().includes('/api/')) {
        apiResponses.push({ url: res.url(), status: res.status() })
      }
    })
    page.on('request', (req) => {
      if (req.url().includes('/api/')) {
        // 只断言"存在"，不打印密钥值
        if (!req.headers()['x-api-key']) missingKey.push(req.url())
      }
    })

    await page.goto('/writing')
    await page.waitForLoadState('networkidle')

    expect(apiResponses.length, '应至少发出一次 /api 请求').toBeGreaterThan(0)

    const unauthorized = apiResponses.filter((r) => r.status === 401)
    expect(unauthorized, `不应出现 401，实际: ${JSON.stringify(unauthorized)}`).toHaveLength(0)

    const ok = apiResponses.filter((r) => r.status === 200)
    expect(ok.length, `应至少有一个 200，实际: ${JSON.stringify(apiResponses)}`).toBeGreaterThan(0)
    expect(ok.some((r) => r.url.includes('/api/novel')), '应有小说列表请求返回 200').toBe(true)

    expect(missingKey, `这些 /api 请求缺少 X-API-Key: ${JSON.stringify(missingKey)}`).toHaveLength(0)

    const body = await page.locator('body').innerText()
    expect(body).not.toContain('无效的 API Key')
  })

  test('负向对照：密钥错误时必须被 401 拒绝', async ({ page }) => {
    const statuses: number[] = []
    page.on('response', (res) => {
      if (res.url().includes('/api/') && !res.url().includes('/api/health')) {
        statuses.push(res.status())
      }
    })
    // localStorage 优先级高于构建期 VITE_API_KEY → 覆盖为错值
    await page.addInitScript(() => localStorage.setItem('story_api_key', 'definitely-wrong-key'))

    await page.goto('/writing')
    await page.waitForLoadState('networkidle')

    expect(statuses.some((s) => s === 401), `应出现 401，实际: ${JSON.stringify(statuses)}`).toBe(true)
  })

  test('设置页可运行时录入密钥（保存后 localStorage 生效）', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')

    const keyInput = page.locator('.settings-view input[type="password"]').first()
    await expect(keyInput).toBeVisible()
    await keyInput.fill('runtime-key-from-e2e')
    await page.getByRole('button', { name: '保存' }).first().click()

    const stored = await page.evaluate(() => localStorage.getItem('story_api_key'))
    expect(stored).toBe('runtime-key-from-e2e')
  })

  test('冒烟：/settings 与 /outline 加载均无 401', async ({ page }) => {
    for (const path of ['/settings', '/outline']) {
      const bad: string[] = []
      const handler = (res: { url: () => string; status: () => number }) => {
        if (res.url().includes('/api/') && res.status() === 401) bad.push(res.url())
      }
      page.on('response', handler)
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      expect(bad, `${path} 出现 401: ${JSON.stringify(bad)}`).toHaveLength(0)
      page.off('response', handler)
    }
  })
})
