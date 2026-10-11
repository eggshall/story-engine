import { expect, test } from '@playwright/test'

/**
 * N0 节点 · 真实浏览器 E2E
 *
 * 验证：前端带上 X-API-Key 后，写作页加载时的所有 /api 请求不再被后端 401 拒绝。
 * 前置：后端在 127.0.0.1:8000、vite 在 5173（`bash scripts/e2e_dev_stack.sh`）。
 */
test.describe('N0 · 前端鉴权打通', () => {
  test('写作页加载后无 401，且界面渲染出已有小说', async ({ page }) => {
    const apiResponses: { url: string; status: number }[] = []
    page.on('response', (res) => {
      if (res.url().includes('/api/')) {
        apiResponses.push({ url: res.url(), status: res.status() })
      }
    })

    await page.goto('/writing')
    await page.waitForLoadState('networkidle')

    expect(apiResponses.length, '应至少发出一次 /api 请求').toBeGreaterThan(0)

    const unauthorized = apiResponses.filter((r) => r.status === 401)
    expect(unauthorized, `不应出现 401，实际出现: ${JSON.stringify(unauthorized)}`).toHaveLength(0)

    const body = await page.locator('body').innerText()
    expect(body).not.toContain('无效的 API Key')
    expect(body).toMatch(/test-novel|novel_ae0fa8d5|写作/)
  })
})
