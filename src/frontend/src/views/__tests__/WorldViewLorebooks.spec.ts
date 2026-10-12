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
import { ElMessage, ElMessageBox } from 'element-plus'

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
        ElOption: {
          name: 'ElOption',
          props: ['label', 'value'],
          template: '<div class="el-option" :data-value="value">{{ label }}</div>',
        },
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

  it('迟到的设定集响应不许串书（A 的慢响应落地时不许覆盖 B 的内容）', async () => {
    // 同一类竞态（地图侧已修过一次）：`loadBooks()` 在飞时换书 → 旧响应后到 →
    // 把 B 的书目替换成 A 的。界面看起来"正常"，内容却是别人的。
    let releaseA: (v: unknown) => void = () => {}
    mockFetchNovelLorebooks.mockImplementation((id: string) => {
      if (id === 'novel_b') {
        return Promise.resolve([
          { name: '乙书设定', entries: { b1: { keys: ['乙'], content: '乙书内容', priority: 50, enabled: true } } },
        ])
      }
      return new Promise((r) => (releaseA = r)) // A 的响应挂住，稍后手动放行
    })

    const { wrapper, flushPromises } = await mountWorldView()
    await flushPromises()

    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'novel_b')
    await flushPromises()
    expect(wrapper.text()).toContain('乙书内容')

    releaseA([
      { name: '甲书设定', entries: { a1: { keys: ['甲'], content: '甲书内容', priority: 50, enabled: true } } },
    ])
    await flushPromises()

    expect(wrapper.text()).toContain('乙书内容')
    expect(wrapper.text(), '迟到的 A 响应不该出现在 B 这本书里').not.toContain('甲书内容')
  })
})

/**
 * 第五切片：条目「类型」（`LorebookEntry.category`）。
 *
 * 这一维**不是新字段** —— `core/models.py` 里早有 `category`（默认 `general`），
 * 接口层也早就放行它。缺的只是 UI：新建条目的 category 恒为 general，
 * 于是「地名一致性校验」对所有新条目形同关闭（`novel.py` 只认 地理/地点 这类值）。
 *
 * 取值表见 `src/story_engine/lore/categories.py`（后端唯一定义处）。
 */
describe('WorldView 条目「类型」', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchNovels.mockResolvedValue(NOVELS)
    mockFetchNovelLorebooks.mockResolvedValue(BOOKS)
  })

  /** 弹窗里的「类型」下拉（按 `data-testid` 找，不靠 DOM 顺序猜第几个 ElSelect） */
  function categorySelect(wrapper: any) {
    const found = wrapper
      .findAllComponents({ name: 'ElSelect' })
      .find((c: any) => c.attributes('data-testid') === 'form-category')
    expect(found, '弹窗里应有 data-testid="form-category" 的「类型」下拉').toBeTruthy()
    return found
  }

  it('新建条目时选的「类型」必须写进 payload 的 category', async () => {
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('[data-testid="new-entry"]').trigger('click')
    await wrapper.find('[data-testid="form-book"]').setValue('新区')
    await wrapper.find('[data-testid="form-entry-id"]').setValue('e9')
    await wrapper.find('[data-testid="form-content"]').setValue('天阙城是东域都城')
    categorySelect(wrapper).vm.$emit('update:modelValue', '地点')
    await wrapper.find('[data-testid="save-entry"]').trigger('click')
    await flushPromises()

    const payload = mockCreateNovelLorebook.mock.calls[0][1]
    expect(payload.entries.e9.category).toBe('地点')
  })

  it('「其他」选项的存储值必须是历史默认值 general（改成就地取「其他」会让老数据分叉）', async () => {
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('[data-testid="new-entry"]').trigger('click')
    await flushPromises()

    // 断言**标签 → 存储值**的映射本身（弹窗里渲染出的选项带 data-value），
    // 而不是直接 $emit('general') 把映射跳过去（评审 P2-3）
    const options = wrapper.findAll('.el-option')
    const other = options.find((o) => o.text() === '其他')
    expect(other, '下拉里应有「其他」选项').toBeTruthy()
    expect(other!.attributes('data-value')).toBe('general')
    const place = options.find((o) => o.text() === '地点')
    expect(place!.attributes('data-value')).toBe('地点')
  })

  it('条目卡片显示类型；老条目（没有 category）显示为「其他」而不是空白', async () => {
    mockFetchNovelLorebooks.mockResolvedValue([
      {
        name: '天玄大陆',
        entries: {
          capital: { keys: ['天阙城'], content: '东域都城', priority: 50, enabled: true, category: '地点' },
          legacy: { keys: ['古法'], content: '第四切片之前建的条目', priority: 50, enabled: true },
        },
      },
    ])
    const { wrapper } = await mountWorldView()

    const cards = wrapper.findAll('.entry-card')
    const labels = cards.map((c) => c.find('[data-testid="entry-category"]').text())
    expect(labels).toContain('地点')
    expect(labels).toContain('其他')
  })

  it('未知类型（老数据「地理」）原样显示，并能被同名的过滤按钮筛出来', async () => {
    // 评审 P1-2：兜底成「其他」会让同一条目"卡片显示其他、点其他找不到、编辑器里又写着地理"
    mockFetchNovelLorebooks.mockResolvedValue([
      {
        name: '天玄大陆',
        entries: {
          old: { keys: ['东域'], content: '老数据用的是「地理」', priority: 50, enabled: true, category: '地理' },
          capital: { keys: ['天阙城'], content: '东域都城', priority: 50, enabled: true, category: '地点' },
        },
      },
    ])
    const { wrapper, flushPromises } = await mountWorldView()

    const card = wrapper.findAll('.entry-card').find((c) => c.text().includes('老数据用的是「地理」'))
    expect(card!.find('[data-testid="entry-category"]').text()).toBe('地理')

    // 过滤行要给出「地理」这一项（否则这条只能靠"全部类型"看，等于筛不出来）
    const chip = wrapper.find('[data-testid="type-filter-地理"]')
    expect(chip.exists(), '过滤行应包含数据里出现的未知类型').toBe(true)
    await chip.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('老数据用的是「地理」')
    expect(wrapper.text()).not.toContain('东域都城')
  })

  it('按类型过滤：只剩该类型的条目，「全部」能还原', async () => {
    mockFetchNovelLorebooks.mockResolvedValue([
      {
        name: '天玄大陆',
        entries: {
          capital: { keys: ['天阙城'], content: '东域都城', priority: 50, enabled: true, category: '地点' },
          sword: { keys: ['青锋'], content: '上古神兵', priority: 50, enabled: true, category: '物品' },
        },
      },
    ])
    const { wrapper, flushPromises } = await mountWorldView()
    expect(wrapper.text()).toContain('上古神兵')

    await wrapper.find('[data-testid="type-filter-地点"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('东域都城')
    expect(wrapper.text()).not.toContain('上古神兵')

    await wrapper.find('[data-testid="type-filter-all"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('上古神兵')
  })

  it('编辑老条目时下拉**真的列出**它的原值（不是只把值塞进表单）', async () => {
    mockFetchNovelLorebooks.mockResolvedValue([
      {
        name: '天玄大陆',
        entries: {
          culti: { keys: ['筑基'], content: '旧', priority: 80, enabled: true, category: '地理' },
        },
      },
    ])
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('.entry-card').trigger('click')
    await flushPromises()

    // 断言渲染出来的选项里真有它 —— 删掉 `categoryOptions` 追加原值那段逻辑这条必须红（评审 P2-3）
    const options = wrapper.findAll('.el-option').map((o) => o.text())
    expect(options).toContain('地理（原有取值）')
    expect(categorySelect(wrapper).props('modelValue')).toBe('地理')
  })

  it('保存后被当前筛选挡住 → 自动切回「全部」并说明（不然"已保存"却找不到）', async () => {
    const { wrapper, flushPromises } = await mountWorldView()

    // 先把类型过滤设成「地点」，再新建一条默认类型（其他）的条目
    await wrapper.find('[data-testid="type-filter-地点"]').trigger('click')
    await wrapper.find('[data-testid="new-entry"]').trigger('click')
    await wrapper.find('[data-testid="form-book"]').setValue('天玄大陆')
    await wrapper.find('[data-testid="form-entry-id"]').setValue('e9')
    await wrapper.find('[data-testid="form-content"]').setValue('新设定')
    await wrapper.find('[data-testid="save-entry"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="type-filter-地点"]').exists()).toBe(true)
    // 关键行为：列表里真的能看到它（不是嘴上说已保存）
    expect(wrapper.text()).toContain('境界：筑基→金丹')
    const msg = (ElMessage.success as any).mock.calls.map((c: any[]) => String(c[0])).join(' | ')
    expect(msg).toContain('已切回')
  })

  it('换书时两个过滤一起复位（老书选了「地点」，新书只有「其他」条目也要看得见）', async () => {
    mockFetchNovelLorebooks.mockImplementation(async (id: string) =>
      id === 'novel_b'
        ? [{ name: '乙书设定', entries: { b1: { keys: ['乙'], content: '乙书内容', priority: 50, enabled: true } } }]
        : BOOKS,
    )
    const { wrapper, flushPromises } = await mountWorldView()

    await wrapper.find('[data-testid="type-filter-地点"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('都市背景：二环以内限行') // 被「地点」筛掉了

    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'novel_b')
    await flushPromises()

    // 类型过滤若跨书保留，这条 general 的条目就会被挡住 —— 那就是"只清了一个过滤"
    expect(wrapper.text()).toContain('乙书内容')
  })

  it('编辑已有条目时「删除条目」按钮必须在（曾因 v-if 引用未定义变量而永远不显示）', async () => {
    const { wrapper, flushPromises } = await mountWorldView()

    // 新建态不该有删除按钮
    await wrapper.find('[data-testid="new-entry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="delete-entry"]').exists()).toBe(false)

    // 切到编辑态（弹窗桩始终渲染，所以直接点卡片即可）
    await wrapper.find('.entry-card').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="delete-entry"]').exists()).toBe(true)
  })
})
