/**
 * N0 节点测试：前端鉴权头（REST + fetch 调用点）
 *
 * 评审修复项（N0-REVIEW §B-2 / P2-4）：
 * - `afterEach` 复位 adapter，避免泄漏到其它用例
 * - 断言统一用大小写归一化的取值函数
 * - SSE 的三个函数都覆盖（原实现只测了 generateChapterStream）
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  api,
  chatStream,
  fetchModels,
  generateChapterStream,
  generateOutlineStream,
} from '../api'

const KEY = 'test-key-123'

/** axios 的 headers 可能是普通对象 / AxiosHeaders / Headers，统一大小写归一取值 */
function headerOf(headers: unknown, name: string): string | null {
  if (!headers) return null
  const anyH = headers as Record<string, unknown> & { get?: (n: string) => unknown }
  if (typeof anyH.get === 'function') {
    const v = anyH.get(name)
    if (v !== undefined && v !== null) return String(v)
  }
  const direct = anyH[name] ?? anyH[name.toLowerCase()]
  return direct === undefined || direct === null ? null : String(direct)
}

function mockAdapter() {
  const captured: { headers: unknown } = { headers: undefined }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(api.defaults as any).adapter = async (config: any) => {
    captured.headers = config.headers
    return { data: { data: [] }, status: 200, statusText: 'OK', headers: {}, config }
  }
  return captured
}

describe('N0 · 前端鉴权头（REST 路径，经请求拦截器）', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    // 复位 adapter，避免影响其它用例（评审 P2-4）
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (api.defaults as any).adapter
    vi.unstubAllGlobals()
  })

  it('配置了 Key 时必须带 X-API-Key', async () => {
    localStorage.setItem('story_api_key', KEY)
    const captured = mockAdapter()

    await fetchModels()

    expect(headerOf(captured.headers, 'X-API-Key')).toBe(KEY)
  })

  it('未配置 Key 时不带该头（不发送空 header）', async () => {
    const captured = mockAdapter()

    await fetchModels()

    expect(headerOf(captured.headers, 'X-API-Key')).toBeNull()
  })
})

describe('N0 · 访问密钥存取（设置页运行时录入的地基）', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('setApiKey 写入 localStorage，getApiKey 读回；空串表示清除', async () => {
    const { getApiKey, setApiKey } = await import('../api')

    setApiKey('abc-123')
    expect(localStorage.getItem('story_api_key')).toBe('abc-123')
    expect(getApiKey()).toBe('abc-123')

    setApiKey('')
    expect(localStorage.getItem('story_api_key')).toBeNull()
  })
})

describe('N0 · 前端鉴权头（SSE 调用点，含请求头与 URL 来源）', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it.each([
    ['generateOutlineStream', generateOutlineStream, '/api/generate/outline'],
    ['generateChapterStream', generateChapterStream, '/api/generate/chapter'],
    ['chatStream', chatStream, '/api/generate/chat'],
  ])('%s：配置了 Key 时 fetch 带 X-API-Key，且 URL 来自统一的 BASE_URL', async (_n, fn, path) => {
    localStorage.setItem('story_api_key', KEY)
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, body: null })
    vi.stubGlobal('fetch', fetchMock)

    // body 为 null 会在 readSSE 抛错，属预期（这里只验请求侧）
    await fn({ chapter_number: 1, messages: [] })
      .next()
      .catch(() => undefined)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(path)
    expect(headerOf(init.headers, 'X-API-Key')).toBe(KEY)
    expect(headerOf(init.headers, 'Content-Type')).toBe('application/json')
  })

  it('未配置 Key 时不带该头', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, body: null })
    vi.stubGlobal('fetch', fetchMock)

    await generateChapterStream({ chapter_number: 1 })
      .next()
      .catch(() => undefined)

    const [, init] = fetchMock.mock.calls[0]
    expect(headerOf(init.headers, 'X-API-Key')).toBeNull()
  })
})
