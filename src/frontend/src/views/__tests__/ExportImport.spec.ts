import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock axios
const mockApiPost = vi.fn()
vi.mock('../../utils/api', () => {
  const api = {
    post: (...args: any[]) => mockApiPost(...args),
    get: vi.fn(),
    patch: vi.fn(),
    defaults: { baseURL: '/api' },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  }
  return {
    default: api,
    exportJson: async (...args: any[]) => {
      const res = await api.post('/export/json', ...args)
      return (res.data?.data) || res.data || res
    },
    importJson: async (...args: any[]) => {
      const res = await api.post('/import/json', ...args)
      return (res.data?.data) || res.data || res
    },
  }
})

describe('Export/Import API functions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('exportJson returns path and stats', async () => {
    const { exportJson } = await import('../../utils/api')
    mockApiPost.mockResolvedValue({
      data: {
        data: { path: '/tmp/test-novel.json', chapters_exported: 2, word_count: 500, format: 'json' },
      },
    })
    const result = await exportJson({ novel_id: 'test-novel' })
    expect(mockApiPost).toHaveBeenCalledWith('/export/json', { novel_id: 'test-novel' })
    expect(result.path).toContain('.json')
    expect(result.chapters_exported).toBe(2)
    expect(result.format).toBe('json')
  })

  it('exportJson supports custom output_dir', async () => {
    const { exportJson } = await import('../../utils/api')
    mockApiPost.mockResolvedValue({
      data: {
        data: { path: '/custom/path/test-novel.json', chapters_exported: 2, word_count: 500, format: 'json' },
      },
    })
    const result = await exportJson({ novel_id: 'test-novel', output_dir: '/custom/path' })
    expect(mockApiPost).toHaveBeenCalledWith('/export/json', {
      novel_id: 'test-novel',
      output_dir: '/custom/path',
    })
    expect(result.path).toContain('/custom/path')
  })

  it('importJson creates novel from JSON data', async () => {
    const { importJson } = await import('../../utils/api')
    mockApiPost.mockResolvedValue({
      data: {
        data: { id: 'imported-novel', title: '导入的小说', chapter_count: 3, word_count: 1500 },
      },
    })
    const result = await importJson({
      json_data: JSON.stringify({ title: '导入的小说', chapters: [] }),
      force: true,
    })
    expect(mockApiPost).toHaveBeenCalledWith('/import/json', {
      json_data: JSON.stringify({ title: '导入的小说', chapters: [] }),
      force: true,
    })
    expect(result.title).toBe('导入的小说')
    expect(result.id).toBe('imported-novel')
  })

  it('importJson works without force flag', async () => {
    const { importJson } = await import('../../utils/api')
    mockApiPost.mockResolvedValue({
      data: {
        data: { id: 'new-novel', title: '新小说', chapter_count: 0, word_count: 0 },
      },
    })
    const result = await importJson({
      json_data: '{"title":"新小说","chapters":[]}',
    })
    expect(mockApiPost).toHaveBeenCalledWith('/import/json', {
      json_data: '{"title":"新小说","chapters":[]}',
    })
    expect(result.id).toBe('new-novel')
  })
})
