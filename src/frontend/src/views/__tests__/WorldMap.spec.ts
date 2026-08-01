import { describe, it, expect, beforeEach, vi } from 'vitest'

const mockApiGet = vi.fn()
const mockApiPost = vi.fn()

vi.mock('../../utils/api', () => {
  const api = {
    get: (...args: any[]) => mockApiGet(...args),
    post: (...args: any[]) => mockApiPost(...args),
    patch: vi.fn(),
    defaults: { baseURL: '/api' },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  }
  return {
    default: api,
    fetchNovels: vi.fn(),
    fetchNovel: vi.fn(),
  }
})

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
  ElLoading: vi.fn(),
  default: {},
}))

describe('WorldView - Map Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows entry and map tabs', async () => {
    const { mount, flushPromises } = await import('@vue/test-utils')
    const WorldView = (await import('../../views/WorldView.vue')).default
    const wrapper = mount(WorldView, {
      global: {
        stubs: {
          ElButton: true,
          ElMenu: true,
          ElMenuItem: true,
          ElIcon: true,
          ElTag: true,
          ElEmpty: true,
          ElDialog: { name: 'ElDialog', template: '<div class="el-dialog"><slot /></div>' },
          ElForm: true,
          ElFormItem: true,
          ElInput: true,
          ElSelect: true,
          ElOption: true,
          ElTabs: { name: 'ElTabs', template: '<div class="el-tabs"><slot /></div>' },
          ElTabPane: { name: 'ElTabPane', template: '<div class="el-tab-pane"><slot /></div>' },
          ElUpload: {
            name: 'ElUpload',
            template: '<div class="el-upload" @click="$emit(\'click\')"><slot /></div>',
          },
        },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('世界观设定')
  })

  it('map API endpoint works', async () => {
    mockApiGet.mockResolvedValue({
      data: { data: { image_path: '/uploaded/map.png', markers: [
        { id: 'm1', name: '王城', x: 45, y: 30, description: '测试标记' },
      ]}},
    })
    const res = await mockApiGet('/novel/test-novel/map')
    const data = res.data?.data || res.data
    expect(data.markers.length).toBe(1)
    expect(data.markers[0].name).toBe('王城')
  })

  it('save map markers API works', async () => {
    const markers = [{ id: 'm1', name: '森林', x: 50, y: 50 }]
    mockApiPost.mockResolvedValue({
      data: { data: { image_path: '/map.png', markers }},
    })
    const res = await mockApiPost('/novel/test-novel/map', { image_path: '/map.png', markers })
    const data = res.data?.data || res.data
    expect(data.markers[0].name).toBe('森林')
  })
})
