import axios from 'axios'

// 后端 API 基础路径
const BASE_URL = import.meta.env.VITE_API_BASE || '/api'

/** API Key 来源：localStorage（运行时可改，无需重新构建）> 构建期 VITE_API_KEY */
export function getApiKey(): string {
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem('story_api_key')
    if (stored) return stored
  }
  return (import.meta.env.VITE_API_KEY as string) || ''
}

/** 运行时设置 API Key（设置页可调用；空串表示清除） */
export function setApiKey(key: string): void {
  if (typeof localStorage === 'undefined') return
  if (key) localStorage.setItem('story_api_key', key)
  else localStorage.removeItem('story_api_key')
}

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
})

// 鉴权头：后端在 security.api_key 已配置时，对 /api/* 强制校验 X-API-Key
api.interceptors.request.use((config) => {
  const key = getApiKey()
  if (key && config.headers) config.headers.set('X-API-Key', key)
  return config
})

/** SSE(原生 fetch) 用统一请求头 —— axios 拦截器管不到 fetch */
export function sseHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const key = getApiKey()
  if (key) headers['X-API-Key'] = key
  return headers
}

/** 拼 SSE 的绝对/相对 URL —— 与 axios 的 BASE_URL 保持同一来源（避免 REST/SSE 不一致） */
export function apiUrl(path: string): string {
  return `${BASE_URL}${path}`
}

/**
 * 通用 SSE 流解析器 — 解析 event/data 格式，逐 token 回传
 * 后端格式: event: token / event: done / event: error
 */
async function* readSSE<T = string>(
  res: Response,
  onToken: (data: any) => T | null,
  onDone?: () => T | null,
  onError?: (msg: string) => T | null,
): AsyncGenerator<T> {
  if (!res.ok) throw new Error(`SSE error: ${res.status}`)
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        const raw = line.slice(6).trim()
        if (currentEvent === 'token') {
          const parsed = JSON.parse(raw)
          const result = onToken(parsed)
          if (result !== null) yield result
        } else if (currentEvent === 'done') {
          if (onDone) {
            const result = onDone()
            if (result !== null) yield result
          }
          return
        } else if (currentEvent === 'error') {
          const parsed = JSON.parse(raw)
          if (onError) {
            const result = onError(parsed.error || '未知错误')
            if (result !== null) yield result
          } else {
            yield `\n[Error: ${parsed.error || '未知错误'}]` as unknown as T
          }
          return
        }
      }
    }
  }
}

// ── 模型 ─────────────────────────────────────

export interface ModelInfo {
  name: string
  provider: string
  model_id: string
  base_url: string
  api_key: string
  enabled: boolean
  temperature: number
  max_tokens: number
}

export async function fetchModels(): Promise<ModelInfo[]> {
  const res = await api.get('/models/')
  return res.data?.data || res.data
}

export async function updateModel(
  name: string,
  config: Partial<Pick<ModelInfo, 'enabled' | 'api_key' | 'base_url' | 'temperature' | 'max_tokens'>>
): Promise<ModelInfo> {
  const res = await api.patch(`/models/${encodeURIComponent(name)}`, config)
  return res.data?.data || res.data
}

export async function testModel(
  name: string
): Promise<{ status: string; message: string }> {
  const res = await api.post(`/models/${encodeURIComponent(name)}/test`)
  return res.data?.data || res.data
}

// ── 小说 ─────────────────────────────────────

export interface NovelBrief {
  id: string
  title: string
  author: string
  genre: string
  word_count: number
  chapter_count: number
  created: string
  updated: string
}

export interface NovelDetail extends NovelBrief {
  synopsis: string
  characters: string[]
  lorebooks: string[]
  chapters: any[]
}

export interface NovelCreateRequest {
  title: string
  author?: string
  genre?: string
  synopsis?: string
  save_path?: string
}

export async function fetchNovels(): Promise<NovelBrief[]> {
  const res = await api.get('/novel/')
  return res.data?.data || res.data
}

export async function fetchNovel(id: string): Promise<NovelDetail> {
  const res = await api.get(`/novel/${id}`)
  return res.data?.data || res.data
}

export async function createNovel(data: NovelCreateRequest): Promise<NovelDetail> {
  const res = await api.post('/novel/', data)
  return res.data?.data || res.data
}

// ── 生成 ─────────────────────────────────────

export async function* generateOutlineStream(params: {
  novel_id?: string
  chapter_number?: number
  chapter_title?: string
  model?: string
}): AsyncGenerator<string> {
  const res = await fetch(apiUrl('/generate/outline'), {
    method: 'POST',
    headers: sseHeaders(),
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`SSE error: ${res.status}`)
  yield* readSSE(
    res,
    (d) => d.token ?? null,
    () => null,
  )
}

export async function* generateChapterStream(params: {
  novel_id?: string
  chapter_number: number
  chapter_title?: string
  model?: string
}): AsyncGenerator<string> {
  const res = await fetch(apiUrl('/generate/chapter'), {
    method: 'POST',
    headers: sseHeaders(),
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`SSE error: ${res.status}`)
  yield* readSSE(
    res,
    (d) => d.token ?? null,
    () => null,
  )
}

export async function* chatStream(params: {
  messages: { role: string; content: string }[]
  system_prompt?: string
  model?: string
  temperature?: number
  mode?: string
  search?: boolean
  stylePrompt?: string
  profileId?: string
}): AsyncGenerator<string> {
  const res = await fetch(apiUrl('/generate/chat'), {
    method: 'POST',
    headers: sseHeaders(),
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`SSE error: ${res.status}`)
  yield* readSSE(
    res,
    (d) => d.token ?? null,
    () => null,
  )
}

// ── 导出 ─────────────────────────────────────

export async function exportMd(params: {
  novel_id?: string
  output_dir?: string
  export_all?: boolean
  chapter_numbers?: number[]
}): Promise<{ path: string; chapters_exported: number; word_count: number }> {
  const res = await api.post('/export/md', params)
  return res.data?.data || res.data
}

export async function exportJson(params: {
  novel_id?: string
  output_dir?: string
}): Promise<{ path: string; chapters_exported: number; word_count: number; format: string }> {
  const res = await api.post('/export/json', params)
  return res.data?.data || res.data
}

export async function importJson(params: {
  json_data: string
  restore_path?: string
  force?: boolean
}): Promise<{ id: string; title: string; chapter_count: number; word_count: number }> {
  const res = await api.post('/import/json', params)
  return res.data?.data || res.data
}

// ── 设置 ─────────────────────────────────────

export interface WritingSettings {
  default_model: string
  temperature: number
  max_tokens: number
}

export async function fetchSettings(): Promise<WritingSettings> {
  const res = await api.get('/settings')
  return res.data?.data || res.data
}

export async function saveSettings(
  params: Partial<WritingSettings>
): Promise<WritingSettings> {
  const res = await api.post('/settings', params)
  return res.data?.data || res.data
}

// ── 资料检索 ────────────────────────────────

export async function research(params: {
  query: string
  save_to_lore?: boolean
  lore_category?: string
}): Promise<{ query: string; summary: string; sources: any[]; saved_to: string }> {
  const res = await api.post('/research/', params)
  return res.data?.data || res.data
}

export default api

// ── 文风 ─────────────────────────────────────

export interface StyleProfileInfo {
  id: string
  name: string
  author: string
  source_work: string
  genre: string
  features: Record<string, any>
  style_prompt: string
  sample_text: string
  tags: string[]
  created_at: string
  updated_at: string
}

export interface StyleListResponse {
  profiles: StyleProfileInfo[]
  total: number
}

export interface StyleAnalyzeResponse {
  features: Record<string, any>
  style_prompt: string
  profile_id: string
}

export interface StyleConsistencyResult {
  consistency_score: number
  consistent_aspects: string[]
  inconsistent_aspects: string[]
  suggestions: string[]
  conclusion: string
}

export async function fetchStyleProfiles(genre = ''): Promise<StyleProfileInfo[]> {
  const params = genre ? `?genre=${encodeURIComponent(genre)}` : ''
  const res = await api.get(`/style/profiles${params}`)
  return (res.data as StyleListResponse).profiles
}

export async function getStyleProfile(id: string): Promise<StyleProfileInfo> {
  const res = await api.get(`/style/profiles/${id}`)
  return res.data as StyleProfileInfo
}

export async function saveStyleProfile(data: {
  name: string
  author?: string
  source_work?: string
  genre?: string
  features?: Record<string, any>
  style_prompt?: string
  sample_text?: string
  tags?: string[]
}): Promise<StyleProfileInfo> {
  const res = await api.post('/style/profiles', data)
  return res.data as StyleProfileInfo
}

export async function deleteStyleProfile(id: string): Promise<void> {
  await api.delete(`/style/profiles/${id}`)
}

export async function analyzeStyle(data: {
  text: string
  name?: string
  author?: string
  source_work?: string
  genre?: string
}): Promise<StyleAnalyzeResponse> {
  const res = await api.post('/style/analyze', data)
  return res.data as StyleAnalyzeResponse
}

export async function checkStyleConsistency(data: {
  text: string
  profile_id?: string
  style_prompt?: string
}): Promise<StyleConsistencyResult> {
  const res = await api.post('/style/check', data)
  return res.data as StyleConsistencyResult
}

export async function searchStyleProfiles(q: string): Promise<StyleProfileInfo[]> {
  const params = q ? `?q=${encodeURIComponent(q)}` : ''
  const res = await api.get(`/style/search${params}`)
  return (res.data as StyleListResponse).profiles
}
