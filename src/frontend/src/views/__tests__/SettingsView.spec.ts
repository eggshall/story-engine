import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

// Mock API module
const mockFetchModels = vi.fn()
const mockUpdateModel = vi.fn()
const mockTestModel = vi.fn()

vi.mock('../../utils/api', () => {
  const api = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    defaults: { baseURL: '/api' },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  }
  return {
    default: api,
    fetchModels: (...args: any[]) => mockFetchModels(...args),
    updateModel: (...args: any[]) => mockUpdateModel(...args),
    testModel: (...args: any[]) => mockTestModel(...args),
  }
})

// Stub for el-card that renders header slot content
const ElCardStub = {
  name: 'ElCard',
  template: '<div class="el-card"><div v-if="$slots.header" class="el-card__header"><slot name="header" /></div><div class="el-card__body"><slot /></div></div>',
}

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
  ElLoading: vi.fn(),
  default: {},
}))

describe('SettingsView - Model Management', () => {
  const sampleModels = [
    {
      name: 'pro-model',
      provider: 'deepseek',
      model_id: 'deepseek-chat',
      base_url: 'https://api.deepseek.com/v1',
      api_key: '****key',
      enabled: true,
      temperature: 0.7,
      max_tokens: 8192,
    },
    {
      name: 'local-model',
      provider: 'local',
      model_id: 'qwen3.5:9b-q6-fixed',
      base_url: 'http://localhost:11434',
      api_key: '****lama',
      enabled: false,
      temperature: 0.8,
      max_tokens: 8192,
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchModels.mockResolvedValue(sampleModels)
    mockUpdateModel.mockResolvedValue({
      name: 'pro-model', enabled: true, temperature: 0.7,
      max_tokens: 8192, base_url: 'https://api.deepseek.com/v1', api_key: '****key',
    })
    mockTestModel.mockResolvedValue({ status: 'ok', message: '连接成功' })
    setActivePinia(createPinia())
  })

  async function mountView() {
    const SettingsView = (await import('../../views/SettingsView.vue')).default
    return mount(SettingsView, {
      global: {
        stubs: {
          ElCard: ElCardStub,
          ElSwitch: true,
          ElButton: true,
          ElInput: true,
          ElForm: true,
          ElFormItem: true,
          ElSelect: true,
          ElOption: true,
          ElSlider: true,
          ElInputNumber: true,
          ElIcon: true,
        },
      },
    })
  }

  it('renders model list from API', async () => {
    const wrapper = await mountView()
    await flushPromises()

    expect(mockFetchModels).toHaveBeenCalled()
    expect(wrapper.text()).toContain('pro-model')
    expect(wrapper.text()).toContain('local-model')
  })

  it('shows provider and model_id', async () => {
    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('deepseek')
    expect(wrapper.text()).toContain('deepseek-chat')
  })

  it('shows base_url, temperature and max_tokens', async () => {
    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('api.deepseek.com')
    expect(wrapper.text()).toContain('0.7')
    expect(wrapper.text()).toContain('8192')
  })

  it('shows model cards with header content', async () => {
    const wrapper = await mountView()
    await flushPromises()

    const headers = wrapper.findAll('.el-card__header')
    expect(headers.length).toBeGreaterThanOrEqual(2)
    expect(headers[0].text()).toContain('pro-model')
  })

  it('store updateModel method works', async () => {
    const { useSettingsStore } = await import('../../stores/settings')
    const store = useSettingsStore()
    await store.loadModels()

    const ok = await store.updateModel('pro-model', { enabled: false })
    expect(ok).toBe(true)
    expect(mockUpdateModel).toHaveBeenCalledWith('pro-model', { enabled: false })
  })

  it('store testConnection method works', async () => {
    const { useSettingsStore } = await import('../../stores/settings')
    const store = useSettingsStore()

    const result = await store.testConnection('pro-model')
    expect(result.status).toBe('ok')
    expect(mockTestModel).toHaveBeenCalledWith('pro-model')
  })

  it('has writing parameters and about sections', async () => {
    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('写作参数')
    expect(wrapper.text()).toContain('关于')
    expect(wrapper.text()).toContain('v0.5.0')
  })
})
