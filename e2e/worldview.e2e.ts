import { expect, test } from '@playwright/test'
import zlib from 'node:zlib'

/**
 * 造一张纯色 PNG。
 *
 * 为什么不用 1×1 的占位图：`.map-image-wrapper` 由图片撑开，1 像素的图会让它只有 1 像素见方，
 * `click({ position })` 会落在元素外（第一次就死在这）。这里按 PNG 规范现造一张确定尺寸的图，
 * 自包含、不需要往仓库里塞二进制夹具。
 */
const CRC_TABLE = (() => {
  const t = new Int32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c
  }
  return t
})()

function crc32(buf: Buffer): number {
  let c = -1
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8)
  return (c ^ -1) >>> 0
}

function pngChunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length, 0)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body), 0)
  return Buffer.concat([len, body, crc])
}

function makeSolidPng(w: number, h: number): Buffer {
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(w, 0)
  ihdr.writeUInt32BE(h, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 2 // truecolor RGB
  const raw = Buffer.alloc((w * 3 + 1) * h) // 每行前置一个 filter=0 字节，像素全 0
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', zlib.deflateSync(raw)),
    pngChunk('IEND', Buffer.alloc(0)),
  ])
}

/**
 * N8 第四切片 · 世界观页（真实浏览器 + 真实后端）
 *
 * 前置：`bash scripts/e2e_dev_stack.sh --fake`
 *
 * 为什么必须用浏览器跑：这一页原来是**两处虚构** ——
 *   1. 「条目」是页面内写死的数组（刷新即丢）；
 *   2. 「地图」打的是 `/novel/current/map`，服务端没有 current 这个概念 → 404 且被空 catch 吞掉。
 * 修好之后要证明的行为全是跨层闭环（DOM ↔ HTTP ↔ 磁盘），单测只能证明各层各自"看起来对"：
 *
 *   API 建设定集 → 页面按**选中那本书**渲染 → **刷新仍在**（真落盘）
 *   → **换书看不到**（按书隔离）→ **删除后刷新不复活**（真删了）
 *   → 地图读写打的是**这本书**的 id（不再出现 current），且图片未被上传这件事界面说清了
 *
 * 注：用 UI 弹窗"新建条目"的路径由组件单测覆盖（`WorldViewLorebooks.spec.ts`），
 * 这里专注"落盘/隔离/不复活"这类只有真实浏览器 + 真实磁盘才能证明的事。
 */

const TITLE_A = `E2E-WORLD-A-${Date.now()}`
const TITLE_B = `E2E-WORLD-B-${Date.now()}`
const BOOK = '天玄大陆'
const ENTRY_CONTENT = '境界：筑基→金丹'

test.use({ viewport: { width: 1440, height: 900 } })

test('世界观页 · 设定集按书绑定：落盘 → 刷新仍在 → 换书看不到 → 删除后不复活', async ({
  page,
}) => {
  test.setTimeout(180_000)

  const pageErrors: string[] = []
  page.on('pageerror', (e) => pageErrors.push(String(e)))

  const apiUrls: string[] = []
  let apiKey = ''
  page.on('request', (req) => {
    const url = req.url()
    if (url.includes('/api/')) {
      apiUrls.push(url)
      const key = req.headers()['x-api-key']
      if (!apiKey && key) apiKey = key
    }
  })

  // ── 1. 建两本书（真接口）──
  // 注：这里不用 UI 建书 —— 有书之后写作页顶栏第一个按钮会变成「新建章节」，
  // 与 n6 里「空态点第一个按钮建书」的路径不再一致（第一次踩过）。UI 建书已由 n6 覆盖，
  // 本文件专注世界观页自己的跨层行为。
  await page.goto('/writing')
  await page.waitForLoadState('networkidle')
  await expect.poll(() => apiKey, { message: '应从页面请求里取到鉴权头', timeout: 20_000 }).not.toBe('')
  const H = { 'X-API-Key': apiKey }

  const createNovel = async (title: string): Promise<string> => {
    const res = await page.request.post('/api/novel/', { headers: H, data: { title } })
    const body = await res.json()
    expect(body?.success, `建书应成功 ${title}: ${JSON.stringify(body)}`).toBe(true)
    return body?.data?.id ?? ''
  }
  const idA = await createNovel(TITLE_A)
  const idB = await createNovel(TITLE_B)
  expect(idA, 'A 书应拿到 id').not.toBe('')
  expect(idB, 'B 书应拿到 id').not.toBe('')

  // ── 2. 给 A 书加一个设定集（真接口、真落盘）──
  const created = await page.request.post(`/api/novel/${idA}/lorebooks`, {
    headers: H,
    data: {
      name: BOOK,
      description: '',
      entries: {
        culti: { keys: ['筑基'], content: ENTRY_CONTENT, priority: 80, enabled: true },
      },
    },
  })
  expect((await created.json())?.success, '建设定集应成功').toBe(true)

  // ── 3. 打开世界观页，选 A 书 → 左栏与条目区都要渲染出来 ──
  const pickNovel = async (title: string) => {
    await page.locator('[data-testid="novel-select"]').click()
    await page.locator('.el-select-dropdown__item').filter({ hasText: title }).first().click()
  }

  await page.goto('/world')
  await pickNovel(TITLE_A)
  await expect(page.locator('.world-categories')).toContainText(BOOK, { timeout: 20_000 })
  await expect(page.locator('.world-entries')).toContainText(ENTRY_CONTENT)
  // 写死的那条假数据不该再出现（它是"条目是假数据"的证据）
  await expect(page.locator('.world-view')).not.toContainText('盖亚大陆')

  // ── 4. 刷新仍在（真的落盘了，不是内存态）──
  await page.reload()
  await expect(page.locator('.world-categories')).toContainText(BOOK, { timeout: 20_000 })
  await expect(page.locator('.world-entries')).toContainText(ENTRY_CONTENT)

  // ── 5. 换书看不到（按书隔离）──
  await pickNovel(TITLE_B)
  await expect(page.locator('.world-categories')).not.toContainText(BOOK, { timeout: 20_000 })
  await expect(page.locator('.world-entries')).not.toContainText(ENTRY_CONTENT)

  // ── 6. 地图 tab：打的是这本书的 id，且不再出现 current ──
  apiUrls.length = 0
  await page.getByRole('tab', { name: '地图' }).click()
  await expect(page.locator('.world-view')).toContainText('未上传')
  const mapUrls = apiUrls.filter((u) => u.includes('/map'))
  expect(
    mapUrls.some((u) => u.includes(`/api/novel/${idB}/map`)),
    `应打 B 书的地图：${mapUrls.join(',')}`,
  ).toBe(true)
  expect(
    mapUrls.some((u) => u.includes('/current/')),
    `不该再出现 current：${mapUrls.join(',')}`,
  ).toBe(false)

  // ── 6b. 地图**写**路径：上传图 → 加标记 → 保存 → 直查接口确认真的落盘 ──
  // 缺陷自述"读写都是坏的"，只验 GET 不够；单测里 `saveNovelMap` 只是被 mock 掉，测不到 HTTP 路径。
  const png = makeSolidPng(160, 120)
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name: 'map.png', mimeType: 'image/png', buffer: png })
  await page.locator('.map-image-wrapper').click({ position: { x: 40, y: 30 } })
  await page.locator('.new-marker-form input').first().fill('王城')
  await page.getByRole('button', { name: '添加' }).click()
  await page.locator('[data-testid="save-map"]').click()

  await expect
    .poll(
      async () => {
        const r = await page.request.get(`/api/novel/${idB}/map`, { headers: H })
        const b = await r.json()
        return (b?.data?.markers || []).map((m: { name: string }) => m.name).join(',')
      },
      { message: '标记应真的落盘到这本书', timeout: 20_000 },
    )
    .toBe('王城')

  // 本机预览的 blob 地址不能写进服务端（换个会话就失效）
  const mapSaved = await page.request.get(`/api/novel/${idB}/map`, { headers: H })
  expect((await mapSaved.json())?.data?.image_path ?? '').not.toContain('blob:')

  // ── 7. 回 A 书 → 删除设定集 → 刷新不复活 ──
  await page.getByRole('tab', { name: '条目' }).click()
  await pickNovel(TITLE_A)
  await page.locator('[data-testid="lorebook-天玄大陆"]').click()
  await page.locator('[data-testid="delete-lorebook"]').click()
  // 按 class 点主按钮，不依赖文案：本应用没注册 Element Plus 的 zh-CN locale，
  // ElMessageBox 的按钮实际是 "OK"/"Cancel"（已在评审里记为待办的 UI 一致性问题）
  await page.locator('.el-message-box__btns .el-button--primary').click()

  await expect(page.locator('.world-categories')).not.toContainText(BOOK, { timeout: 20_000 })
  await expect(page.locator('.world-entries')).not.toContainText(ENTRY_CONTENT)

  await page.reload()
  await expect(page.locator('.world-categories')).not.toContainText(BOOK, { timeout: 20_000 })

  // 服务端也真的没了（不是只在界面上藏起来）
  const listed = await page.request.get(`/api/novel/${idA}/lorebooks`, { headers: H })
  const listedBody = await listed.json()
  expect(listedBody?.data?.names ?? [], 'A 书的设定集应为空').toHaveLength(0)

  expect(pageErrors, `页面不应有未捕获异常: ${pageErrors.join(' | ')}`).toHaveLength(0)

  // ── 8. 自清理 ──
  expect((await page.request.delete(`/api/novel/${idA}`, { headers: H })).status()).toBe(200)
  expect((await page.request.delete(`/api/novel/${idB}`, { headers: H })).status()).toBe(200)
})
