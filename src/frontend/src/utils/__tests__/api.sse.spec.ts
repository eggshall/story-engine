/**
 * N0 评审 P1-3：SSE 路径的**硬断言**测试
 *
 * 与 api.spec.ts 的差别：这里起一个真实本地 HTTP server（node:http），
 * - 在**服务端**断言收到的 `x-api-key` / `content-type`（而不是只看客户端传了什么）
 * - 让 `readSSE` 真的解析一段 SSE 流，断言"逐 token + 单一 done"
 *
 * 两个垫片，均不改变被测行为：
 *   1) URL 垫片：api.ts 用 `/api/...` 相对路径 → 解析到本地 server
 *   2) fetch 垫片：用 node:http 发真实请求（服务端能记录头），再把响应体包成
 *      Web ReadableStream 给 readSSE 解析（happy-dom 的 fetch 不做流式 body）
 */
import { request as httpRequest } from 'node:http'
import { createServer, type Server } from 'node:http'
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest'

import {
  chatStream,
  generateChapterStream,
  generateOutlineStream,
  setApiKey,
} from '../api'

const KEY = 'sse-test-key'
const SSE_BODY =
  'event: token\ndata: {"token":"你好"}\n\n' +
  'event: token\ndata: {"token":"世界"}\n\n' +
  'event: done\ndata: {}\n\n'

let server: Server
let base = ''
let originalFetch: typeof fetch
let seen: { headers: Record<string, string | string[] | undefined>; path: string }[] = []

// N1：空产出时后端发的是 event: error（无 done），前端必须让作者看见原因。
// 用 NL 拼接避免在测试源码里写转义换行。
const NL = String.fromCharCode(10)
const ERROR_BODY = [
  'event: error',
  'data: {"error":"模型返回空产出（流式零 token）"}',
  '',
  '',
].join(NL)

let sseBody = SSE_BODY

type StreamResponse = { ok: boolean; status: number; body: ReadableStream<Uint8Array> }

/** 真实 HTTP 请求 + 把响应体包成 Web 流（供 readSSE 解析） */
function realFetch(url: string, init: RequestInit = {}): Promise<StreamResponse> {
  return new Promise((resolve, reject) => {
    const u = new URL(url)
    const req = httpRequest(
      {
        hostname: u.hostname,
        port: u.port,
        path: `${u.pathname}${u.search}`,
        method: (init.method as string) || 'GET',
        headers: (init.headers as Record<string, string>) || {},
      },
      (res) => {
        const chunks: Buffer[] = []
        res.on('data', (c: Buffer) => chunks.push(c))
        res.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf8')
          const body = new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(new TextEncoder().encode(text))
              controller.close()
            },
          })
          resolve({ ok: (res.statusCode || 0) < 400, status: res.statusCode || 0, body })
        })
      },
    )
    req.on('error', reject)
    if (init.body) req.write(init.body as string)
    req.end()
  })
}

async function collect(gen: AsyncGenerator<string>): Promise<string[]> {
  const out: string[] = []
  for await (const token of gen) out.push(token)
  return out
}

beforeAll(async () => {
  server = createServer((req, res) => {
    seen.push({ headers: req.headers, path: req.url || '' })
    res.writeHead(200, { 'Content-Type': 'text/event-stream' })
    res.end(sseBody)
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const addr = server.address()
  const port = typeof addr === 'object' && addr ? addr.port : 0
  base = `http://127.0.0.1:${port}`

  originalFetch = globalThis.fetch
  globalThis.fetch = ((input: string | URL | Request, init?: RequestInit) => {
    const url =
      typeof input === 'string' && input.startsWith('/') ? base + input : String(input)
    return realFetch(url, init) as unknown as Promise<Response>
  }) as typeof fetch
})

afterAll(async () => {
  globalThis.fetch = originalFetch
  await new Promise<void>((resolve) => server.close(() => resolve()))
})

beforeEach(() => {
  seen = []
  sseBody = SSE_BODY
  setApiKey(KEY)
})

describe('N0 · SSE 真实 HTTP 硬断言（服务端视角）', () => {
  it.each([
    ['generateOutlineStream', generateOutlineStream, '/api/generate/outline'],
    ['generateChapterStream', generateChapterStream, '/api/generate/chapter'],
    ['chatStream', chatStream, '/api/generate/chat'],
  ])('%s：服务端收到 X-API-Key，客户端逐 token 解析且只出现一次 done', async (_n, fn, path) => {
    const tokens = await collect(
      (fn as (p: Record<string, unknown>) => AsyncGenerator<string>)({
        chapter_number: 1,
        messages: [{ role: 'user', content: 'hi' }],
      }),
    )

    // 逐 token（readSSE 真的跑通了，而不是被 catch 吞掉）
    expect(tokens).toEqual(['你好', '世界'])

    // 服务端视角：只发一次请求、路径与头都正确
    expect(seen).toHaveLength(1)
    expect(seen[0].path).toBe(path)
    expect(seen[0].headers['x-api-key']).toBe(KEY)
    expect(String(seen[0].headers['content-type'])).toContain('application/json')
  })

  it('负向对照：未配置 key 时服务端收不到 X-API-Key', async () => {
    setApiKey('')

    await collect(generateChapterStream({ chapter_number: 1 }))

    expect(seen).toHaveLength(1)
    expect(seen[0].headers['x-api-key']).toBeUndefined()
  })
})

describe('N1 · 空产出的 error 事件在前端表现为异常（不落盘）', () => {
  it('后端 event: error → 流以 Error 结束，绝不把错误文案当正文 yield 出去', async () => {
    sseBody = ERROR_BODY

    const err = await collect(generateChapterStream({ chapter_number: 1 })).then(
      () => null,
      (e: Error) => e,
    )

    expect(err).toBeInstanceOf(Error)
    expect(err!.message).toContain('空产出')
    // 关键：没有任何 token 被当成正文（否则 WritingView 会把它存进章节）
    expect(seen).toHaveLength(1)
    expect(seen[0].path).toBe('/api/generate/chapter')
  })

  it('对照：正常 token 流不会被误判为错误', async () => {
    const tokens = await collect(generateChapterStream({ chapter_number: 1 }))
    expect(tokens).toEqual(['你好', '世界'])
  })
})

// N2：done 载荷契约（后端单一 done + 载荷寄在 done 上；前端必须把它送达调用方）
const DONE_WITH_PAYLOAD = [
  'event: token',
  'data: {"token":"擂台"}',
  '',
  '',
  'event: token',
  'data: {"token":"之上"}',
  '',
  '',
  'event: done',
  'data: {"done":true,"chapter":{"chapter_number":1,"title":"试炼","word_count":4}}',
  '',
  '',
].join(NL)

const DOUBLE_DONE = [
  'event: token',
  'data: {"token":"甲"}',
  '',
  '',
  'event: done',
  'data: {"done":true,"chapter":{"chapter_number":1,"title":"第一份"}}',
  '',
  '',
  'event: token',
  'data: {"token":"不该出现"}',
  '',
  '',
  'event: done',
  'data: {"done":true,"chapter":{"chapter_number":1,"title":"第二份"}}',
  '',
  '',
].join(NL)

describe('N2 · done 载荷契约（readSSE.onDone(payload)）', () => {
  it('章节流：done 的 chapter 载荷原样交给 onDone，且只调用一次', async () => {
    sseBody = DONE_WITH_PAYLOAD
    const payloads: Record<string, any>[] = []

    const tokens = await collect(
      generateChapterStream({ chapter_number: 1 }, { onDone: (p) => payloads.push(p) }),
    )

    expect(tokens).toEqual(['擂台', '之上'])
    expect(payloads).toHaveLength(1)
    expect(payloads[0].done).toBe(true)
    expect(payloads[0].chapter.title).toBe('试炼')
    expect(payloads[0].chapter.word_count).toBe(4)
  })

  it('大纲流：done 载荷同样送到 onDone（不再只能靠 token 承载结构体）', async () => {
    sseBody = [
      'event: done',
      'data: {"done":true,"outline":{"chapter_number":1,"title":"试炼","beats":["入场"]}}',
      '',
      '',
    ].join(NL)
    const payloads: Record<string, any>[] = []

    const tokens = await collect(
      generateOutlineStream({ novel_id: 'n1' }, { onDone: (p) => payloads.push(p) }),
    )

    expect(tokens).toEqual([])
    expect(payloads).toHaveLength(1)
    expect(payloads[0].outline.title).toBe('试炼')
  })

  it('防御性：后端若违规发两次 done，客户端只认第一次', async () => {
    sseBody = DOUBLE_DONE
    const payloads: Record<string, any>[] = []

    const tokens = await collect(
      generateChapterStream({ chapter_number: 1 }, { onDone: (p) => payloads.push(p) }),
    )

    expect(tokens).toEqual(['甲'])
    expect(payloads).toHaveLength(1)
    expect(payloads[0].chapter.title).toBe('第一份')
  })

  it('兼容：done 事件体为空/非法 JSON 时不炸，仍按完成处理', async () => {
    sseBody = ['event: done', 'data: ', '', ''].join(NL)
    const payloads: Record<string, any>[] = []

    const tokens = await collect(
      generateChapterStream({ chapter_number: 1 }, { onDone: (p) => payloads.push(p) }),
    )

    expect(tokens).toEqual([])
    expect(payloads).toHaveLength(1)
  })
})

