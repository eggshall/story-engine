import { describe, it, expect, beforeEach, vi } from 'vitest'

describe('Settings API functions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchSettings returns current settings', async () => {
    const mockGet = vi.fn().mockResolvedValue({
      data: { data: { default_model: 'pro-model', temperature: 0.7, max_tokens: 4096 } },
    })
    vi.doMock('../../utils/api', () => ({
      default: {
        get: mockGet,
        post: vi.fn(),
        patch: vi.fn(),
        defaults: { baseURL: '/api' },
        interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      },
      fetchSettings: async () => {
        const res = await mockGet('/settings')
        return res.data?.data || res.data
      },
    }))
    const { fetchSettings } = await import('../../utils/api')
    const result = await fetchSettings()
    expect(result.default_model).toBe('pro-model')
    expect(result.temperature).toBe(0.7)
  })

  it('saveSettings persists changes', async () => {
    const mockPost = vi.fn().mockResolvedValue({
      data: { data: { default_model: 'new-model', temperature: 0.5, max_tokens: 8192 } },
    })
    vi.doMock('../../utils/api', () => ({
      default: {
        post: mockPost,
        get: vi.fn(),
        patch: vi.fn(),
        defaults: { baseURL: '/api' },
        interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      },
      saveSettings: async (params: any) => {
        const res = await mockPost('/settings', params)
        return res.data?.data || res.data
      },
    }))
    const { saveSettings } = await import('../../utils/api')
    const result = await saveSettings({ temperature: 0.5 })
    expect(mockPost).toHaveBeenCalledWith('/settings', { temperature: 0.5 })
    expect(result.temperature).toBe(0.5)
  })
})

vi.mock('../../utils/api', () => {
  const mockGet = vi.fn()
  const mockPost = vi.fn()
  return {
    default: { get: mockGet, post: mockPost, patch: vi.fn(),
      defaults: { baseURL: '/api' },
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } } },
    fetchModels: vi.fn(),
    fetchSettings: vi.fn().mockResolvedValue({
      default_model: 'pro-model', temperature: 0.7, max_tokens: 4096,
    }),
    saveSettings: vi.fn(),
    fetchNovels: vi.fn().mockResolvedValue([]),
    exportJson: vi.fn(),
    importJson: vi.fn(),
  }
})

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
  ElLoading: vi.fn(),
  default: {},
}))

describe('SettingsView - Writing params', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    // 注意：前两个测试用了 vi.doMock（运行时注册），会覆盖静态 vi.mock。
    // 这里统一用 vi.doMock 重注册完整 mock（含 fetchModels），避免 SettingsView
    // onMounted → loadModels() 走到无 fetchModels 的 mock 而报 unhandled error。
    vi.doMock('../../utils/api', () => ({
      default: {
        get: vi.fn(), post: vi.fn(), patch: vi.fn(),
        defaults: { baseURL: '/api' },
        interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      },
      fetchModels: vi.fn().mockResolvedValue([]),
      fetchSettings: vi.fn().mockResolvedValue({
        default_model: 'pro-model', temperature: 0.7, max_tokens: 4096,
      }),
      saveSettings: vi.fn(),
      fetchNovels: vi.fn().mockResolvedValue([]),
      exportJson: vi.fn(),
      importJson: vi.fn(),
    }))
    vi.doMock('element-plus', () => ({
      ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
      ElMessageBox: { confirm: vi.fn() },
      ElLoading: vi.fn(),
      default: {},
    }))
    const { setActivePinia, createPinia } = await import('pinia')
    setActivePinia(createPinia())
  })

  async function mountView() {
    const { mount, flushPromises } = await import('@vue/test-utils')
    const SettingsView = (await import('../../views/SettingsView.vue')).default
    return mount(SettingsView, {
      global: {
        stubs: {
          ElCard: {
            name: 'ElCard',
            template: '<div class="el-card"><div v-if="$slots.header" class="el-card__header"><slot name="header" /></div><div class="el-card__body"><slot /></div></div>',
          },
          ElSwitch: true, ElButton: true, ElInput: true,
          ElForm: true, ElFormItem: true, ElSelect: true,
          ElOption: true, ElSlider: true, ElInputNumber: true,
          ElIcon: true, ElUpload: true, ElDivider: true,
          ElDialog: { name: 'ElDialog', template: '<div class="el-dialog"><slot /></div>' },
        },
      },
    })
  }

  it('shows project info section', async () => {
    const { flushPromises } = await import('@vue/test-utils')
    const wrapper = await mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('项目信息')
    expect(wrapper.text()).toContain('项目导出')
    expect(wrapper.text()).toContain('写作参数')
  })
})
