import { expect, test } from '@playwright/test'

/**
 * N6 节点 · 真实浏览器 E2E（真实 vite + 真实后端 + 真实 SSE + 本地假上游）
 *
 * 前置：`bash scripts/e2e_dev_stack.sh --fake`
 *
 * 为什么必须用浏览器跑：N6 是"把校验结果变成作者能操作的东西"——校验清单要按规则分组、
 * 点条目要能在正文里精确定位、带指令重写要能流式预览、保存要真落盘。这些全是跨层行为
 * （DOM ↔ 偏移 ↔ SSE ↔ 磁盘），单测只能证明各层各自"看起来对"。
 *
 * 闭环链路（一条不落）：
 *   写脏正文 → 审稿页校验 → 点条目高亮到那段 → 给指令重写 → 候选稿只预览不落盘
 *   → 点保存 → 磁盘上的章节真的变成候选稿
 */

const NOVEL_TITLE = `E2E-N6-${Date.now()}`
const LONG_PARA = '他继续向前走，'.repeat(60)          // > 300 字，必被段落规则标出来
const DIRTY_TEXT = `他推开门。\n\n${LONG_PARA}\n\n值得注意的是，一切都结束了。`
const FAKE_OUTPUT = '擂台之上'

// 1280x720 下三栏会互相遮挡（右侧面板压住顶栏按钮），用真实写作时的窗口尺寸量级
test.use({ viewport: { width: 1680, height: 1050 } })

test.describe('N6 · 审稿页（真实浏览器）', () => {
  test('校验 → 定位 → 带指令重写 → 保存，全链路闭环', async ({ page }) => {
    test.setTimeout(180_000)

    // 网络层嗅探：只观察不改变请求，把 v2 的原始 SSE 响应体留档（校验 done 载荷内容）
    await page.addInitScript(() => {
      const origFetch = window.fetch.bind(window)
      const store: string[] = []
      ;(window as unknown as { __v2Bodies: string[] }).__v2Bodies = store
      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const res = await origFetch(input as RequestInfo, init)
        const url = typeof input === 'string' ? input : (input as Request).url || ''
        if (url.includes('/api/generate/chapter/v2')) {
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

    let apiKey = ''
    let novelId = ''
    page.on('request', (req) => {
      const key = req.headers()['x-api-key']
      if (!apiKey && key && req.url().includes('/api/')) apiKey = key
    })
    /** 按标题从小说列表里找回 id —— response 监听是异步的，建完书不能立刻断言 id */
    const findNovelId = async (key: string) => {
      const res = await page.request.get('/api/novel/', { headers: { 'X-API-Key': key } })
      const body = await res.json()
      const list = (body?.data ?? body ?? []) as Array<{ id: string; title: string }>
      return (Array.isArray(list) ? list : []).find((n) => n?.title === NOVEL_TITLE)?.id ?? ''
    }

    // ── 1. 建书（真实 UI + 真实后端）──
    await page.goto('/writing')
    await page.waitForLoadState('networkidle')
    await page.locator('.tree-header button').first().click()
    await page.locator('input[placeholder="输入小说标题"]').fill(NOVEL_TITLE)
    await page.getByRole('button', { name: '创建' }).click()
    await expect(page.locator('.chapter-panel')).toBeVisible()
    expect(apiKey, '应从页面请求里取到鉴权头').not.toBe('')
    await expect
      .poll(async () => {
        novelId = await findNovelId(apiKey)
        return novelId
      }, { message: '应能从小说列表里按标题找回刚建的书', timeout: 20_000 })
      .not.toBe('')

    // ── 2. 造一章"脏正文"（长段 + 无钩子 + AI 味），走真实接口 ──
    // 新书是**空书**（没有章节），必须先建章再写正文；只断言 HTTP 200 会漏掉
    // `success:false`（比如"章节不存在"）这种"200 但没做事"的情况。
    const created = await page.request.post(`/api/novel/${novelId}/chapters`, {
      headers: { 'X-API-Key': apiKey },
      data: { chapter_number: 1, title: '第一章', content: DIRTY_TEXT },
    })
    expect(created.status()).toBe(200)
    const createdBody = await created.json()
    expect(createdBody?.success, `建章必须成功：${JSON.stringify(createdBody)}`).toBe(true)

    // ── 3. 侧栏有"审稿"入口，深链直接打开这一章 ──
    await page.goto('/review')
    await expect(page.locator('.sidebar-menu')).toContainText('审稿')

    await page.goto(`/review?novel=${novelId}&chapter=1`)
    await expect(page.locator('[data-testid="draft-text"]')).toContainText('他推开门。')

    // ── 4. 校验：清单按规则分组、能定位、跳过项明说"还没法判"──
    await page.locator('[data-testid="check-btn"]').click()

    const findings = page.locator('[data-testid="finding"]')
    await expect(findings.first()).toBeVisible({ timeout: 30_000 })
    const rules = await findings.evaluateAll((els) =>
      els.map((el) => (el as HTMLElement).dataset.rule),
    )
    expect(rules, `应有段落长度与 AI 味告警，实际=${rules.join(',')}`).toContain(
      'paragraph_length',
    )
    expect(rules).toContain('ai_flavor')
    // 第一章没有前序章节 → 对话占比无基线：必须显示"没判定"，不能让作者读成"没问题"
    await expect(page.locator('[data-testid="incomplete-banner"]')).toContainText('对话占比')

    // ── 5. 点条目 → 左侧正文精确高亮到那一段（300+ 字的长段）──
    await page.locator('[data-testid="finding"][data-rule="paragraph_length"]').first().click()
    const mark = page.locator('[data-testid="highlight"]')
    await expect(mark).toBeVisible()
    const marked = (await mark.textContent()) || ''
    expect(marked.length, '高亮的应是被点的那一整段').toBeGreaterThan(300)
    expect(marked).toBe(LONG_PARA)

    // ── 6. 给指令 + 带指令重写：候选稿只预览 ──
    await page.locator('[data-testid="quick-instruction"]').first().click()
    await expect(page.locator('[data-testid="instruction-input"]')).not.toHaveValue('')

    await page.locator('[data-testid="rewrite-btn"]').click()
    await expect(page.locator('[data-testid="candidate-hint"]')).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('[data-testid="draft-text"]')).toContainText(FAKE_OUTPUT)

    // 协议层：done 载荷必须自报 rewrite=true / saved=false（后端没替作者落盘）
    await expect
      .poll(
        async () =>
          await page.evaluate(
            () => (window as unknown as { __v2Bodies?: string[] }).__v2Bodies?.length ?? 0,
          ),
        { message: '应嗅探到 /api/generate/chapter/v2 的响应体', timeout: 30_000 },
      )
      .toBeGreaterThan(0)
    const rawBodies: string[] = await page.evaluate(
      () => (window as unknown as { __v2Bodies?: string[] }).__v2Bodies ?? [],
    )
    const rawBody = rawBodies[rawBodies.length - 1]
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
    expect(donePayloads, 'v2 也必须只有一个 done').toHaveLength(1)
    expect(donePayloads[0].rewrite).toBe(true)
    expect(donePayloads[0].saved).toBe(false)
    expect(donePayloads[0].context_manifest, 'done 载荷要带注入清单').toBeTruthy()
    // 注入可见性：第一章没有手写件 → 清单必须点名缺了什么（而不是静默为空）
    await expect(page.locator('[data-testid="manifest-skipped"]')).toBeVisible()

    // 还没点保存 → 磁盘上仍是脏正文
    const before = await page.request.get(`/api/novel/${novelId}`, {
      headers: { 'X-API-Key': apiKey },
    })
    const beforeBody = await before.json()
    expect(beforeBody?.data?.chapters?.[0]?.content).toBe(DIRTY_TEXT)

    // ── 7. 点保存 → 候选稿真的落到章节里 ──
    await page.locator('[data-testid="save-btn"]').click()

    await expect
      .poll(
        async () => {
          const res = await page.request.get(`/api/novel/${novelId}`, {
            headers: { 'X-API-Key': apiKey },
          })
          const body = await res.json()
          return body?.data?.chapters?.[0]?.content ?? ''
        },
        { message: '保存后磁盘上的第一章应变成候选稿', timeout: 30_000 },
      )
      .toBe(FAKE_OUTPUT)

    expect(pageErrors, `页面不应有未捕获异常: ${pageErrors.join(' | ')}`).toHaveLength(0)

    // ── 8. 自清理 ──
    const del = await page.request.delete(`/api/novel/${novelId}`, {
      headers: { 'X-API-Key': apiKey },
    })
    expect(del.status(), `自清理删除应成功(200)，实际 ${del.status()}`).toBe(200)
  })
})
