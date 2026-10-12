/**
 * WorldView「条目」tab 接后端（方案 A）—— RED 先行。
 *
 * 背景（本次实测）：`WorldView.vue` 的 `entries` 是**页面内写死的数组**（一条「盖亚大陆」），
 * 全项目没有任何 lorebook 接口调用 —— 刷新即丢，而后端 `/api/novel/{id}/lorebooks` 早已就绪。
 *
 * 本文件钉住的行为：
 *   1. 进页就用**选中那本书**的 id 拉设定集（不是写死数据、也不是 `/novel/current/...`）；
 *   2. 左侧分类 = 本书的**设定集名**（动态；原写死的 地理/历史/魔法/势力/人物 退役）；
 *   3. 点某个设定集只显示它的条目；
 *   4. 换书后重新拉取（不会串书）。
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ElMessageBox } from 'element-plus'

const mockFetchNovels = vi.fn()
const mockFetchNovelLorebooks = vi.fn()
const mockCreateNovelLorebook = vi.fn()
const mockUpdateNovelLorebook = vi.fn()
const mockDeleteNovelLorebook = vi.fn()

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
    fetchNovels: (...a: any[]) => mockFetchNovels(...a),
    fetchNovelLorebooks: (...a: any[]) => mockFetchNovelLorebooks(...a),
    createNovelLorebook: (...a: any[]) => mockCreateNovelLorebook(...a),
    updateNovelLorebook: (...a: any[]) => mockUpdateNovelLorebook(...a),
    deleteNovelLorebook: (...a: any[]) => mockDeleteNovelLorebook(...a),
    fetchLibraryLorebooks: vi.fn(),
    exportLorebookToLibrary: vi.fn(),
    importLorebook: vi.fn(),
    fetchNovelMap: vi.fn(),
    saveNovelMap: vi.fn(),
    errorDetail: (e: any, fb: string) => e?.message || fb,
  }
})

/** 写作页当前那本书 = 'novel_a'（三级优先里的第一级） */
vi.mock('../../stores/novel', () => ({
  useNovelStore: () => ({ currentNovel: { id: 'novel_a', title: '甲书' } }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
  ElLoading: vi.fn(),
  default: {},
}))

const NOVELS = [
  { id: 'novel_a', title: '甲书', updated: '2026-10-12' },
  { id: 'novel_b', title: '乙书', updated: '2026-10-11' },
]

const BOOKS = [
  {
    name: '天玄大陆',
    description: '东域修仙体系',
    entries: {
      culti: { keys: ['筑基', '金丹'], content: '境界：筑基→金丹', priority: 80, enabled: true },
    },
  },
  {
    name: '现代都市',
    description: '',
    entries: {
      city: { keys: ['汽车'], content: '都市背景：二环以内限行', priority: 60, enabled: true },
    },
  },
]

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
        ElDialog: {
          name: 'ElDialog',
          template: '<div class="el-dialog"><slot /><slot name="footer" /></div>',
        },
        ElForm: { name: 'ElForm', template: '<form><slot /></form>' },
        ElFormItem: { name: 'ElFormItem', template: '<div><slot /></div>' },
        ElInput: {
          name: 'ElInput',
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template:
            '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
        },
        ElSelect: {
          name: 'ElSelect',
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<select :value="modelValue"><slot /></select>',
        },
        ElOption: true,
        ElTabs: { name: 'ElTabs', template: '<div class="el-tabs"><slot /></div>' },
        ElTabPane: { name: 'ElTabPane', template: '<div class="el-tab-pane"><slot /></div>' },
        ElCheckbox: true,
      },
    },
  })
  await flushPromises()
  return { wrapper, flushPromises }
}

describe('WorldView 条目 tab → 后端设定集', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchNovels.mockResolvedValue(NOVELS)
    mockFetchNovelLorebooks.mockResolvedValue(BOOKS)
  })

  it('进页就用选中那本书的 id 拉设定集', async () => {
    const { wrapper } = await mountWorldView()

    expect(mockFetchNovelLorebooks).toHaveBeenCalledWith('novel_a')
    // 渲染的是接口数据，不是页面里写死的那条
    expect(wrapper.text()).toContain('境界：筑基→金丹')
    expect(wrapper.text()).not.toContain('盖亚大陆')
  })

  it('左侧分类是本书的设定集（动态），不再是写死的五个分类', async () => {
    const { wrapper } = await mountWorldView()

    const menu = wrapper.find('.world-categories')
    expect(menu.text()).toContain('天玄大陆')
    expect(menu.text()).toContain('现代都市')
    expect(menu.text()).not.toContain('魔法/能力')
  })

  it('点某个设定集只显示它的条目', async () => {
    const { wrapper, flushPromises } = await mountWorldView()
    expect(wrapper.text()).toContain('都市背景：二环以内限行')

    await wrapper.find('[data-testid="lorebook-现代都市"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('都市背景：二环以内限行')
    expect(wrapper.text()).not.toContain('境界：筑基→金丹')
  })

  it('换书后重新拉取（不串书）', async () => {
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'novel_b')
    await flushPromises()

    expect(mockFetchNovelLorebooks).toHaveBeenCalledWith('novel_b')
  })

  it('弹窗保存新条目 → 调 createNovelLorebook，payload 里带上这个条目', async () => {
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('[data-testid="new-entry"]').trigger('click')
    await wrapper.find('[data-testid="form-book"]').setValue('新区')
    await wrapper.find('[data-testid="form-entry-id"]').setValue('e9')
    await wrapper.find('[data-testid="form-content"]').setValue('新设定内容')
    await wrapper.find('[data-testid="save-entry"]').trigger('click')
    await flushPromises()

    expect(mockCreateNovelLorebook).toHaveBeenCalledWith(
      'novel_a',
      expect.objectContaining({
        name: '新区',
        entries: expect.objectContaining({
          e9: expect.objectContaining({ content: '新设定内容' }),
        }),
      }),
    )
  })

  it('删除设定集 → 先确认再调 deleteNovelLorebook', async () => {
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('[data-testid="lorebook-天玄大陆"]').trigger('click')
    await wrapper.find('[data-testid="delete-lorebook"]').trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(String((ElMessageBox.confirm as any).mock.calls[0][0])).toContain('天玄大陆')
    expect(mockDeleteNovelLorebook).toHaveBeenCalledWith('novel_a', '天玄大陆')
  })

  it('确认框里点取消 → 什么都不删（不是"确认后才删"的空话）', async () => {
    ;(ElMessageBox.confirm as any).mockRejectedValueOnce(new Error('cancel'))
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('[data-testid="lorebook-天玄大陆"]').trigger('click')
    await wrapper.find('[data-testid="delete-lorebook"]').trigger('click')
    await flushPromises()

    expect(mockDeleteNovelLorebook).not.toHaveBeenCalled()
  })

  it('编辑已有条目必须原样保留后端字段（category/position），不能被打回默认值', async () => {
    // 评审 P0-1：后端 LorebookEntry 还有 category(默认 general)/position，且 category 被
    // 地名一致性校验依赖。前端表单不暴露它们 → 必须"以原条目为底合并"写回。
    mockFetchNovelLorebooks.mockResolvedValue([
      {
        name: '天玄大陆',
        entries: {
          culti: {
            keys: ['筑基'],
            content: '旧内容',
            priority: 80,
            enabled: true,
            category: '地理',
            position: 'before_char',
          },
        },
      },
    ])
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('.entry-card').trigger('click')
    await wrapper.find('[data-testid="form-content"]').setValue('新内容')
    await wrapper.find('[data-testid="save-entry"]').trigger('click')
    await flushPromises()

    const payload = mockUpdateNovelLorebook.mock.calls[0][2]
    expect(payload.entries.culti.category).toBe('地理')
    expect(payload.entries.culti.position).toBe('before_char')
    expect(payload.entries.culti.content).toBe('新内容')
  })

  it('换书后旧书内容必须从 DOM 消失（不只是"调了新接口"）', async () => {
    mockFetchNovelLorebooks.mockImplementation(async (id: string) =>
      id === 'novel_b'
        ? [{ name: '乙书设定', entries: { b1: { keys: ['乙'], content: '乙书内容', priority: 50, enabled: true } } }]
        : BOOKS,
    )
    const { wrapper, flushPromises } = await mountWorldView()
    expect(wrapper.text()).toContain('境界：筑基→金丹')

    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'novel_b')
    await flushPromises()

    expect(wrapper.text()).toContain('乙书内容')
    expect(wrapper.text()).not.toContain('境界：筑基→金丹')
    expect(wrapper.find('.world-categories').text()).not.toContain('天玄大陆')
  })
})
