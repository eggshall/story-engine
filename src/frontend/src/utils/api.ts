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
 *
 * N2 契约：`done` 事件是**唯一的结果收尾信号**，其 data 载荷（如章节生成的
 * `chapter`、后续的 `context_manifest`）通过 `onDone(payload)` 交给调用方；
 * 读到第一个 `done` 即结束（后端保证只发一个，客户端再兜一层防御）。
 */
async function* readSSE<T = string>(
  res: Response,
  onToken: (data: any) => T | null,
  onDone?: (payload: StreamDonePayload) => T | null,
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
            const result = onDone(parseDonePayload(raw))
            if (result !== null) yield result
          }
          return
        } else if (currentEvent === 'error') {
          const parsed = JSON.parse(raw)
          const msg = parsed.error || '未知错误'
          if (onError) {
            const result = onError(msg)
            if (result !== null) yield result
          } else {
            // N1 评审 P1-6：错误文案**绝不能**当正文 yield 出去 ——
            // 调用方（如 WritingView.generateChapter）会把 token 直接累加并落盘成章节正文，
            // 于是"模型返回空产出…"会被存进小说里。默认抛错，由调用方 catch 后提示用户。
            throw new Error(msg)
          }
          return
        }
      }
    }
  }
}

/** done 事件载荷：至少含 `done: true`，其余字段由各流自己定义 */
export interface StreamDonePayload {
  done?: boolean
  [key: string]: any
}

/** 流式接口的可选钩子（N2 起：done 载荷从 done 事件里回传） */
export interface StreamHooks {
  onDone?: (payload: StreamDonePayload) => void
}

/** 解析 done 载荷：空/非法 JSON 不炸（按"已完成"处理并告警），避免收尾阶段反而把流打断 */
function parseDonePayload(raw: string): StreamDonePayload {
  if (!raw) return { done: true }
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') return parsed as StreamDonePayload
    return { done: true }
  } catch {
    console.warn('SSE done 载荷解析失败，按空载荷处理')
    return { done: true }
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

/** 保存单章正文（作者在审稿页点"保存"时用；也是候选稿落盘的唯一入口） */
export async function saveChapterContent(
  novelId: string,
  chapterNumber: number,
  content: string,
  title?: string,
): Promise<void> {
  const res = await api.post(`/novel/${novelId}/chapters/${chapterNumber}/save`, {
    content,
    ...(title ? { title } : {}),
  })
  const body = res.data
  if (body?.success === false) throw new Error(body.message || '保存失败')
}

// ── 校验 / 注入清单（N5 + N6）────────────────────

export type CheckLevel = 'alert' | 'warn' | 'ok' | 'skipped'

export interface CheckLocation {
  start: number
  end: number
  paragraph_index?: number | null
  excerpt?: string
}

export interface CheckFinding {
  rule_id: string
  rule_name: string
  level: CheckLevel
  suggestion: string
  /** 相对**请求原文**的字符区间；相对指标（如对话占比）没有单点可定位 → null */
  location: CheckLocation | null
  details: Record<string, any>
}

export interface CheckReport {
  /** 只表达可执行结论（alert/warn/ok）—— 规则被跳过不算"这章有问题" */
  level: 'alert' | 'warn' | 'ok'
  findings: CheckFinding[]
  summary: Record<CheckLevel, number>
  by_rule: Record<string, Record<string, number>>
  rules_run: string[]
  /** 有规则因缺基线被跳过（内容没判定过），配合 skipped_rules 提示作者 */
  incomplete: boolean
  skipped_rules: string[]
  baseline_source: string
  text_length: number
}

/** 校验一章/一段正文（确定性、不花 token） */
export async function checkChapter(params: {
  text?: string
  novel_id?: string
  chapter_number?: number
  profile_id?: string
  baseline_chapters?: number
}): Promise<CheckReport> {
  const res = await api.post('/check/chapter', params, { timeout: 60000 })
  const body = res.data
  if (body?.success === false) throw new Error(body.message || '校验失败')
  return body?.data as CheckReport
}

/** 读回某章生成时落盘的注入清单（没有记录时 ok=false，不是错误） */
export async function fetchChapterManifest(
  novelId: string,
  chapterNumber: number,
): Promise<{ ok: boolean; manifest?: any; message?: string }> {
  const res = await api.get('/check/manifest', {
    params: { novel_id: novelId, chapter_number: chapterNumber },
  })
  const body = res.data
  if (body?.success === false) return { ok: false, message: body.message }
  return { ok: true, manifest: body?.data }
}

/** 装配器版章节生成（N4b）：done 载荷带 `chapter` + `context_manifest`
 *
 * `instruction` 非空 = **带指令重写**：后端只回候选稿（`saved=false`），不落盘 ——
 * 作者看着预览满意了再点保存（覆盖正文不可逆，不能替作者决定）。 */
export async function* generateChapterV2Stream(
  params: {
    novel_id: string
    chapter_number: number
    chapter_title?: string
    model?: string
    profile_id?: string
    beat?: string
    mainline?: string
    recap?: string
    instruction?: string
  },
  hooks?: StreamHooks,
): AsyncGenerator<string> {
  const res = await fetch(apiUrl('/generate/chapter/v2'), {
    method: 'POST',
    headers: sseHeaders(),
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`SSE error: ${res.status}`)
  yield* readSSE(
    res,
    (d) => d.token ?? null,
    (payload) => {
      hooks?.onDone?.(payload)
      return null
    },
  )
}

// ── 生成 ─────────────────────────────────────

export async function* generateOutlineStream(
  params: {
    novel_id?: string
    chapter_number?: number
    chapter_title?: string
    model?: string
  },
  hooks?: StreamHooks,
): AsyncGenerator<string> {
  // 注意（N2 评审 P2-8）：本接口的**结果不在 token 流里**，而是 done 载荷的 `outline`
  // 字段（经 hooks.onDone 传出）；返回值只保留签名兼容，不要把它当结构体用。
  const res = await fetch(apiUrl('/generate/outline'), {
    method: 'POST',
    headers: sseHeaders(),
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`SSE error: ${res.status}`)
  yield* readSSE(
    res,
    (d) => d.token ?? null,
    (payload) => {
      hooks?.onDone?.(payload)
      return null
    },
  )
}

export async function* generateChapterStream(
  params: {
    novel_id?: string
    chapter_number: number
    chapter_title?: string
    model?: string
  },
  hooks?: StreamHooks,
): AsyncGenerator<string> {
  const res = await fetch(apiUrl('/generate/chapter'), {
    method: 'POST',
    headers: sseHeaders(),
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`SSE error: ${res.status}`)
  yield* readSSE(
    res,
    (d) => d.token ?? null,
    (payload) => {
      hooks?.onDone?.(payload)
      return null
    },
  )
}

export async function* chatStream(
  params: {
    messages: { role: string; content: string }[]
    system_prompt?: string
    model?: string
    temperature?: number
    mode?: string
    search?: boolean
    stylePrompt?: string
    profileId?: string
  },
  hooks?: StreamHooks,
): AsyncGenerator<string> {
  const res = await fetch(apiUrl('/generate/chat'), {
    method: 'POST',
    headers: sseHeaders(),
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`SSE error: ${res.status}`)
  yield* readSSE(
    res,
    (d) => d.token ?? null,
    (payload) => {
      hooks?.onDone?.(payload)
      return null
    },
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

// ── 角色卡（N8：按小说绑定；素材库只作复制来源）────

export interface ApiCharacterCard {
  name: string
  description?: string
  personality?: string
  background?: string
  appearance?: string
  first_mes?: string
  scenario?: string
  style_examples?: string[]
  tags?: string[]
  relationships?: { target: string; relation: string; description: string }[]
}

function _unwrap(body: any, fallback: string) {
  if (body?.success === false) throw new Error(body.message || fallback)
  return body?.data
}

/** 列出**这本书**的角色卡 */
export async function fetchNovelCharacters(novelId: string, q = ''): Promise<ApiCharacterCard[]> {
  const res = await api.get(`/novel/${novelId}/characters`, { params: q ? { q } : {} })
  return _unwrap(res.data, '读取角色卡失败')?.cards || []
}

export async function createNovelCharacter(
  novelId: string,
  card: ApiCharacterCard,
): Promise<ApiCharacterCard> {
  const res = await api.post(`/novel/${novelId}/characters`, card)
  return _unwrap(res.data, '新建角色卡失败')
}

export async function updateNovelCharacter(
  novelId: string,
  name: string,
  card: ApiCharacterCard,
): Promise<ApiCharacterCard> {
  const res = await api.put(`/novel/${novelId}/characters/${encodeURIComponent(name)}`, card)
  return _unwrap(res.data, '更新角色卡失败')
}

export async function deleteNovelCharacter(novelId: string, name: string): Promise<void> {
  const res = await api.delete(`/novel/${novelId}/characters/${encodeURIComponent(name)}`)
  _unwrap(res.data, '删除角色卡失败')
}

/** 素材库（所有书共用的一份"复制来源"，不是共享引用） */
export async function fetchLibraryCharacters(): Promise<ApiCharacterCard[]> {
  const res = await api.get('/library/characters')
  return _unwrap(res.data, '读取素材库失败')?.cards || []
}

export async function exportCharacterToLibrary(
  novelId: string,
  name: string,
  newName = '',
): Promise<void> {
  const res = await api.post(
    `/novel/${novelId}/characters/${encodeURIComponent(name)}/to-library`,
    null,
    { params: newName ? { new_name: newName } : {} },
  )
  _unwrap(res.data, '另存为素材失败')
}

export async function importCharacter(
  novelId: string,
  payload: { source: string; name: string; new_name?: string; overwrite?: boolean },
): Promise<{ name: string; from: string }> {
  const res = await api.post(`/novel/${novelId}/characters/import`, payload)
  return _unwrap(res.data, '导入角色卡失败')
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
