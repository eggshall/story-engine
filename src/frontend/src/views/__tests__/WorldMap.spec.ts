/**
 * WorldView「地图」tab —— 地图接口按书绑定 + 失败不再静默（RED 先行）。
 *
 * 背景（本次实测的缺陷）：组件调的是 `/novel/current/map`，而后端只有
 * `/api/novel/{novel_id}/map`，**服务端没有 current 这个概念** → 后端拿 `novel_id="current"`
 * 找书 → 404 → 前端把异常**静默吞掉**（`catch` 里什么都不做）。结果：地图的**读写都是坏的**，
 * 而界面看上去一切正常。
 *
 * 本文件钉住的行为：
 *   1. 地图读写都带**选中那本书**的 id（不再出现 `current`）；
 *   2. 地图接口失败时要**报出来**（不能静默吞）；地图图片只在本机预览、未上传，界面要说清。
 *
 * 备注：本文件原来的「map API endpoint works」/「save map markers API works」两条是**假测试**
 * —— 它们自己调 mock、再断言 mock 自己返回的东西，从未挂载组件。已一并替换为真行为断言。
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ElMessage } from 'element-plus'

const mockFetchNovelMap = vi.fn()
const mockSaveNovelMap = vi.fn()

vi.mock('../../utils/api', () => {
  const api = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    defaults: { baseURL: '/api' },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  }
  return {
    default: api,
    fetchNovels: vi.fn().mockResolvedValue([{ id: 'novel_a', title: '甲书' }]),
    fetchNovelLorebooks: vi.fn().mockResolvedValue([]),
    createNovelLorebook: vi.fn(),
    updateNovelLorebook: vi.fn(),
    deleteNovelLorebook: vi.fn(),
    fetchLibraryLorebooks: vi.fn(),
    exportLorebookToLibrary: vi.fn(),
    importLorebook: vi.fn(),
    fetchNovelMap: (...a: any[]) => mockFetchNovelMap(...a),
    saveNovelMap: (...a: any[]) => mockSaveNovelMap(...a),
    errorDetail: (e: any, fb: string) => e?.message || fb,
  }
})

vi.mock('../../stores/novel', () => ({
  useNovelStore: () => ({ currentNovel: { id: 'novel_a', title: '甲书' } }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
  ElLoading: vi.fn(),
  default: {},
}))

async function mountWorldView() {
  const { mount, flushPromises } = await import('@vue/test-utils')
  const WorldView = (await import('../../views/WorldView.vue')).default
  const wrapper = mount(WorldView, {
    global: {
      stubs: {
        ElButton: { name: 'ElButton', template: '<button><slot /></button>' },
        ElMenu: { name: 'ElMenu', template: '<div class="el-menu"><slot /></div>' },
        ElMenuItem: { name: 'ElMenuItem', template: '<div class="el-menu-item"><slot /></div>' },
        ElIcon: true,
        ElTag: { name: 'ElTag', template: '<span class="el-tag"><slot /></span>' },
        ElEmpty: true,
        ElDialog: { name: 'ElDialog', template: '<div class="el-dialog"><slot /></div>' },
        ElForm: true,
        ElFormItem: { name: 'ElFormItem', template: '<div><slot /></div>' },
        ElInput: { name: 'ElInput', template: '<input />' },
        ElSelect: { name: 'ElSelect', template: '<select data-testid="novel-select"><slot /></select>' },
        ElOption: true,
        // 真实 el-tabs 通过 `update:modelValue` 报切页，stub 照这个契约来
        ElTabs: {
          name: 'ElTabs',
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template:
            '<div class="el-tabs">' +
            '<button data-testid="tab-map" @click="$emit(\'update:modelValue\', \'map\')">map</button>' +
            '<button data-testid="tab-entries" @click="$emit(\'update:modelValue\', \'entries\')">entries</button>' +
            '<slot /></div>',
        },
        ElTabPane: { name: 'ElTabPane', template: '<div class="el-tab-pane"><slot /></div>' },
        ElCheckbox: true,
      },
    },
  })
  await flushPromises()
  return { wrapper, flushPromises }
}

describe('WorldView 地图 tab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchNovelMap.mockResolvedValue({ image_path: '', markers: [] })
    mockSaveNovelMap.mockResolvedValue({ image_path: '', markers: [] })
  })

  it('mounts and shows the page title', async () => {
    const { wrapper } = await mountWorldView()

    expect(wrapper.text()).toContain('世界观设定')
  })

  it('切到地图 tab 用选中那本书的 id 调地图接口，不再出现 current', async () => {
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('[data-testid="tab-map"]').trigger('click')
    await flushPromises()

    expect(mockFetchNovelMap).toHaveBeenCalledWith('novel_a')
    expect(mockFetchNovelMap).not.toHaveBeenCalledWith('current')
  })

  it('保存标记也用同一本书的 id', async () => {
    const { wrapper, flushPromises } = await mountWorldView()
    await wrapper.find('[data-testid="tab-map"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="save-map"]').trigger('click')
    await flushPromises()

    expect(mockSaveNovelMap).toHaveBeenCalledWith('novel_a', expect.any(Object))
  })

  it('地图接口失败要报出来，不能静默吞掉', async () => {
    mockFetchNovelMap.mockRejectedValue(new Error('小说不存在'))
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('[data-testid="tab-map"]').trigger('click')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalled()
    expect(wrapper.text()).toContain('地图')
  })

  it('地图图片只在本机预览，界面必须说清它没上传', async () => {
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('[data-testid="tab-map"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('未上传')
  })
})
