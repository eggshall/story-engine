/**
 * N0 节点测试：前端鉴权头打通
 *
 * 背景：后端 `main.py` 中间件在 `security.api_key` 已配置时，对 `/api/*` 强制校验 `X-API-Key`；
 * 而前端此前一个请求头都没带 → 浏览器全部请求 401。本测试先写（RED），再实现（GREEN）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api, fetchModels, generateChapterStream } from '../api'

const KEY = 'test-key-123'

/** axios 的 headers 可能是普通对象或 AxiosHeaders（大小写归一），统一取值 */
function headerValue(headers: unknown, name: string): unknown {
  if (!headers) return undefined
  const h = headers as Record<string, unknown> & { get?: (n: string) => unknown }
  if (typeof h.get === 'function') {
    const v = h.get(name)
    if (v !== undefined && v !== null) return v
  }
  return h[name] ?? h[name.toLowerCase()]
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

describe('N0 · 前端鉴权头', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('REST 请求：配置了 Key 时必须带 X-API-Key', async () => {
    localStorage.setItem('story_api_key', KEY)
    const captured = mockAdapter()

    await fetchModels()

    expect(headerValue(captured.headers, 'X-API-Key')).toBe(KEY)
  })

  it('REST 请求：未配置 Key 时不带该头（不发送空 header）', async () => {
    const captured = mockAdapter()

    await fetchModels()

    expect(headerValue(captured.headers, 'X-API-Key')).toBeUndefined()
  })

  it('SSE(fetch) 请求：配置了 Key 时必须带 X-API-Key', async () => {
    localStorage.setItem('story_api_key', KEY)
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, body: null })
    vi.stubGlobal('fetch', fetchMock)

    // 读取一次触发 fetch；body 为 null 会抛错，属预期，忽略即可
    await generateChapterStream({ chapter_number: 1 })
      .next()
      .catch(() => undefined)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0]
    expect((init.headers as Record<string, string>)['X-API-Key']).toBe(KEY)
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('SSE(fetch) 请求：未配置 Key 时不带该头', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, body: null })
    vi.stubGlobal('fetch', fetchMock)

    await generateChapterStream({ chapter_number: 1 })
      .next()
      .catch(() => undefined)

    const [, init] = fetchMock.mock.calls[0]
    expect((init.headers as Record<string, string>)['X-API-Key']).toBeUndefined()
  })
})
