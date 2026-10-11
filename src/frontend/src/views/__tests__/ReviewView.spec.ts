import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ── mock API 层（审稿页所有外部依赖都在这一个模块里）──
const mockFetchNovels = vi.fn()
const mockFetchNovel = vi.fn()
const mockCheckChapter = vi.fn()
const mockGenerateV2 = vi.fn()
const mockSaveChapterContent = vi.fn()
const mockFetchManifest = vi.fn()

vi.mock('../../utils/api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  fetchNovels: (...a: any[]) => mockFetchNovels(...a),
  fetchNovel: (...a: any[]) => mockFetchNovel(...a),
  checkChapter: (...a: any[]) => mockCheckChapter(...a),
  generateChapterV2Stream: (...a: any[]) => mockGenerateV2(...a),
  saveChapterContent: (...a: any[]) => mockSaveChapterContent(...a),
  fetchChapterManifest: (...a: any[]) => mockFetchManifest(...a),
}))

import ReviewView from '../ReviewView.vue'

// 审稿页支持深链（/review?novel=&chapter=），单测里给个可控的空 query
const { routeQuery } = vi.hoisted(() => ({ routeQuery: {} as Record<string, string> }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: routeQuery }) }))

const stubs = {
  'el-select': {
    name: 'ElSelectStub',
    template: '<div class="el-select-stub"><slot /></div>',
    props: ['modelValue', 'placeholder'],
  },
  'el-option': { template: '<div class="el-option-stub" />', props: ['label', 'value'] },
  // 注意：**不要**在 stub 里再 $emit('click') —— 组件根元素的原生 click 会经属性透传
  // 触发一次父组件的 @click，再加一次 emit 就是"点一下跑两遍"（异步流里表现为候选稿翻倍）
  'el-button': {
    template: '<button class="el-button-stub" :disabled="disabled"><slot /></button>',
    props: ['disabled', 'loading', 'size', 'type'],
  },
}

// 正文里的三段：第 3 段超长（会被 paragraph_length 标出来）
const PARA_LONG = '他继续向前走，'.repeat(60)
const DRAFT = `他推开门。\n\n${PARA_LONG}\n\n一切都结束了。`
const LONG_START = DRAFT.indexOf(PARA_LONG)          // 别手算偏移，免得差一个字符

const REPORT = {
  level: 'warn',
  findings: [
    {
      rule_id: 'paragraph_length',
      rule_name: '段落长度',
      level: 'warn',
      suggestion: '第 2 段 421 字，超过 300 字：拆成两三段',
      location: { start: LONG_START, end: LONG_START + PARA_LONG.length, paragraph_index: 1, excerpt: PARA_LONG.slice(0, 30) },
      details: { chars: PARA_LONG.length },
    },
    {
      rule_id: 'chapter_hook',
      rule_name: '章末钩子',
      level: 'warn',
      suggestion: '章末没找到钩子/悬念词：如果这是有意的文学性收尾，可忽略',
      location: { start: DRAFT.length - 8, end: DRAFT.length, paragraph_index: 2, excerpt: '一切都结束了。' },
      details: { window: 200 },
    },
    {
      rule_id: 'dialogue_ratio',
      rule_name: '对话占比',
      level: 'skipped',
      suggestion: '没有基线（前序章节不足），这次不判定',
      location: null,
      details: { baseline_source: 'none' },
    },
    {
      rule_id: 'pov_consistency',
      rule_name: '视角一致性',
      level: 'ok',
      suggestion: '全章人称标记一致',
      location: null,
      details: {},
    },
  ],
  summary: { alert: 0, warn: 2, ok: 1, skipped: 1 },
  by_rule: {
    paragraph_length: { warn: 1 },
    chapter_hook: { warn: 1 },
    dialogue_ratio: { skipped: 1 },
    pov_consistency: { ok: 1 },
  },
  rules_run: ['chapter_hook', 'dialogue_ratio', 'paragraph_length', 'pov_consistency'],
  incomplete: true,
  skipped_rules: ['dialogue_ratio'],
  baseline_source: 'none',
  text_length: DRAFT.length,
}

function mountView() {
  return mount(ReviewView, { global: { stubs } })
}

describe('ReviewView（审稿页）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const k of Object.keys(routeQuery)) delete routeQuery[k]     // 深链 query 每例重置
    mockFetchNovels.mockResolvedValue([{ id: 'novel_a', title: '人类大进步' }])
    mockFetchNovel.mockResolvedValue({
      id: 'novel_a',
      title: '人类大进步',
      chapters: [
        { chapter_number: 1, title: '第一次发射', content: '第一章正文。' },
        { chapter_number: 2, title: '试炼', content: DRAFT },
      ],
    })
    mockCheckChapter.mockResolvedValue(REPORT)
    mockSaveChapterContent.mockResolvedValue(undefined)
    mockFetchManifest.mockResolvedValue({ ok: true, manifest: { entries: [], skipped: [] } })
    mockGenerateV2.mockImplementation(async function* () {
      yield '候选'
      yield '稿正文'
    })
  })

  it('首次进入自动选中最新的有正文的章节并展示草稿', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(mockFetchNovels).toHaveBeenCalled()
    expect(wrapper.find('[data-testid="draft-text"]').text()).toContain('他推开门。')
    expect(wrapper.find('[data-testid="draft-text"]').text()).toContain('一切都结束了。')
  })

  it('深链 /review?novel=&chapter= 直接定位到指定章节', async () => {
    // 回归：`route` 没绑定时这里会抛 ReferenceError（浏览器 E2E 抓到过一次，单测也要能抓）
    routeQuery.novel = 'novel_a'
    routeQuery.chapter = '1'
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-testid="draft-text"]').text()).toContain('第一章正文。')
  })

  it('校验后按规则分组渲染清单，并显示整章级别与"没判定"提示', async () => {
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-testid="check-btn"]').trigger('click')
    await flushPromises()

    // 必须把书/章一起送过去：否则后端拿不到前序章节，"对话占比"永远 skipped（评审 P1-2）
    expect(mockCheckChapter).toHaveBeenCalledWith({
      text: DRAFT,
      novel_id: 'novel_a',
      chapter_number: 2,
    })
    expect(wrapper.find('[data-testid="report-level"]').attributes('data-level')).toBe('warn')
    // 缺基线 → 明确说"还没法判"，而不是让作者读成"没问题"
    expect(wrapper.find('[data-testid="incomplete-banner"]').text()).toContain('对话占比')

    const findings = wrapper.findAll('[data-testid="finding"]')
    expect(findings.length).toBe(3)                                  // ok 项默认不显示
    expect(findings.map((f) => f.attributes('data-rule'))).toEqual([
      'chapter_hook', 'dialogue_ratio', 'paragraph_length',
    ])
    expect(wrapper.findAll('[data-testid="finding"]')[2].text()).toContain('超过 300 字')
  })

  it('勾选"显示已通过项"后 ok 项才出现', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="check-btn"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="show-ok"]').setValue(true)

    expect(wrapper.findAll('[data-testid="finding"]').length).toBe(4)
    expect(wrapper.text()).toContain('全章人称标记一致')
  })

  it('点清单条目 → 左侧正文精确高亮该字符区间', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="check-btn"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="highlight"]').exists()).toBe(false)

    await wrapper.findAll('[data-testid="finding"]')[2].trigger('click')

    const mark = wrapper.find('[data-testid="highlight"]')
    expect(mark.exists()).toBe(true)
    expect(mark.text()).toBe(PARA_LONG)                  // 高亮的正是被点的那一段
  })

  it('换了正在看的文本就不再画旧高亮（偏移只对被校验过的那段有效）', async () => {
    // 让报告里的定位在"候选稿"文本内有效
    mockCheckChapter.mockResolvedValue({
      ...REPORT,
      text_length: '候选稿正文'.length,
      findings: [
        {
          rule_id: 'chapter_hook',
          rule_name: '章末钩子',
          level: 'warn',
          suggestion: '章末没找到钩子',
          location: { start: 0, end: 4, paragraph_index: 0, excerpt: '候选稿正' },
          details: {},
        },
      ],
      rules_run: ['chapter_hook'],
      incomplete: false,
      skipped_rules: [],
    })
    const wrapper = mountView()
    await flushPromises()
    // 先重写出候选稿，再校验候选稿，这样 left 面板存在"两份文本"可切换
    await wrapper.find('[data-testid="instruction-input"]').setValue('加强悬念')
    await wrapper.find('[data-testid="rewrite-btn"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="check-btn"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="finding"]').trigger('click')
    expect(wrapper.find('[data-testid="highlight"]').text()).toBe('候选稿正')

    // 切回草稿：文本变了，旧偏移不能拿来标草稿
    await wrapper.find('[data-testid="tab-draft"]').trigger('click')
    expect(wrapper.find('[data-testid="highlight"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="draft-text"]').text()).toContain('他推开门。')

    // 切回候选稿：偏移依然有效，高亮回来
    await wrapper.find('[data-testid="tab-candidate"]').trigger('click')
    expect(wrapper.find('[data-testid="highlight"]').text()).toBe('候选稿正')
  })

  it('带指令重写：把指令发给后端、把候选稿流式预览出来，并带上注入清单', async () => {
    mockGenerateV2.mockImplementation(async function* (
      params: any,
      hooks?: { onDone?: (p: any) => void },
    ) {
      expect(params.instruction).toBe('章末加一个未解的问题')
      yield '候选'
      yield '稿正文'
      hooks?.onDone?.({
        chapter: { content: '候选稿正文' },
        context_manifest: {
          entries: [{ slot_id: 'beat', tokens: 30 }, { slot_id: 'chapter_tail', tokens: 12 }],
          skipped: [{ slot_id: 'style', reason: 'empty' }],
          dropped: [],
        },
        rewrite: true,
        saved: false,
      })
    })
    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('[data-testid="instruction-input"]').setValue('章末加一个未解的问题')
    await wrapper.find('[data-testid="rewrite-btn"]').trigger('click')
    await flushPromises()

    const params = mockGenerateV2.mock.calls[0][0]
    expect(params.novel_id).toBe('novel_a')
    expect(params.chapter_number).toBe(2)
    // 候选稿进预览（左栏切到候选稿），原文还在，没有被覆盖
    expect(wrapper.find('[data-testid="draft-text"]').text()).toContain('候选稿正文')
    expect(wrapper.find('[data-testid="candidate-hint"]').text()).toContain('还没有覆盖磁盘')
    // 注入清单可见（作者能核这次注入了什么、缺了什么）
    const slots = wrapper.findAll('[data-testid="manifest-slot"]').map((s) => s.attributes('data-slot'))
    expect(slots).toEqual(['beat', 'chapter_tail'])
    expect(wrapper.find('[data-testid="manifest-skipped"]').text()).toContain('style')
  })

  it('点保存才把候选稿写回章节（覆盖动作由作者触发）', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="instruction-input"]').setValue('删掉套话')
    await wrapper.find('[data-testid="rewrite-btn"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="save-btn"]').trigger('click')
    await flushPromises()

    expect(mockSaveChapterContent).toHaveBeenCalledWith('novel_a', 2, '候选稿正文')
  })

  it('重写失败（未 yield 就报错）时报错且不留候选稿', async () => {
    mockGenerateV2.mockImplementation(async function* () {
      throw new Error('第5章还没有正文，无法按指令重写（先按节拍生成）')
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="instruction-input"]').setValue('加强悬念')
    await wrapper.find('[data-testid="rewrite-btn"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="error"]').text()).toContain('还没有正文')
    expect(wrapper.find('[data-testid="candidate-hint"]').exists()).toBe(false)
    expect(mockSaveChapterContent).not.toHaveBeenCalled()
  })

  // ─── N6 评审 P0-1 / P1-1 / P1-5：流未结束时的保护 ───

  /** 可控生成器：先吐一片，然后挂在闸门上等测试放行 */
  function gatedGenerator(yieldFirst = '候选') {
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    mockGenerateV2.mockImplementation(async function* () {
      yield yieldFirst
      await gate
      yield '后半截'
    })
    return () => release()
  }

  it('P0-1：重写进行中切章节 → 丢弃在途 token，候选稿清空、保存按钮不可点', async () => {
    const release = gatedGenerator()
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="instruction-input"]').setValue('删掉套话')
    await wrapper.find('[data-testid="rewrite-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="draft-text"]').text()).toContain('候选')   // 第一片已到

    // 切章（v-model + change，跟真实 el-select 行为一致）
    const selects = wrapper.findAllComponents({ name: 'ElSelectStub' })
    expect(selects.length, `期望两个 select 桩（小说/章节），实际 HTML: ${wrapper.html().slice(0, 300)}`).toBe(2)
    const chapterSelect = selects[1]
    chapterSelect.vm.$emit('update:modelValue', 1)
    chapterSelect.vm.$emit('change', 1)
    await flushPromises()

    release()                                     // 放行旧流剩下的 token
    await flushPromises()

    // 旧流的 token 不能拼进新章节的候选稿（否则会得到 "null…" / 串章内容）
    expect(wrapper.find('[data-testid="draft-text"]').text()).toContain('第一章正文。')
    expect(wrapper.find('[data-testid="candidate-hint"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="save-btn"]').attributes('disabled')).toBeDefined()
    expect(mockSaveChapterContent).not.toHaveBeenCalled()
  })

  it('P1-1：先流出半截再报错 → 半截稿可见但禁止保存', async () => {
    let fail!: (e: Error) => void
    mockGenerateV2.mockImplementation(async function* () {
      yield '半截候选'
      await new Promise<never>((_r, reject) => { fail = reject })
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="instruction-input"]').setValue('加钩子')
    await wrapper.find('[data-testid="rewrite-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="draft-text"]').text()).toContain('半截候选')

    fail(new Error('上游断了'))
    await flushPromises()

    expect(wrapper.find('[data-testid="rewrite-failed"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="save-btn"]').attributes('disabled')).toBeDefined()
    // 点了也不能保存（覆盖正文不可逆，半截稿不许落盘）
    await wrapper.find('[data-testid="save-btn"]').trigger('click')
    await flushPromises()
    expect(mockSaveChapterContent).not.toHaveBeenCalled()
  })

  it('P1-1：重写成功但作者没点保存 → 绝不自作主张落盘', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="instruction-input"]').setValue('加钩子')
    await wrapper.find('[data-testid="rewrite-btn"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="candidate-hint"]').exists()).toBe(true)
    expect(mockSaveChapterContent).not.toHaveBeenCalled()
  })

  it('P1-5：重写进行中"校验"按钮不可点，也真的不会打接口', async () => {
    const release = gatedGenerator()
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="instruction-input"]').setValue('删掉套话')
    await wrapper.find('[data-testid="rewrite-btn"]').trigger('click')
    await flushPromises()

    const checkBtn = wrapper.find('[data-testid="check-btn"]')
    expect(checkBtn.attributes('disabled')).toBeDefined()
    await checkBtn.trigger('click')
    await flushPromises()
    expect(mockCheckChapter).not.toHaveBeenCalled()

    release()
    await flushPromises()
  })

  // ─── N6 评审 P1-3 / P1-4：清单落盘在界面上真的可达 ───

  it('P1-3：按节拍写下一章走 v2 生成模式（不带指令），清单立即可见', async () => {
    mockGenerateV2.mockImplementation(async function* (
      _params: any,
      hooks?: { onDone?: (p: any) => void },
    ) {
      hooks?.onDone?.({
        chapter: { chapter_number: 3, title: '第3章', content: '新章正文' },
        context_manifest: {
          entries: [{ slot_id: 'chapter_tail', tokens: 42 }],
          skipped: [{ slot_id: 'beat', reason: 'empty' }],
          dropped: [],
        },
        rewrite: false,
        saved: true,
        manifest_persisted: true,
      })
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="generate-btn"]').trigger('click')
    await flushPromises()

    const params = mockGenerateV2.mock.calls[0][0]
    expect(params.instruction).toBeUndefined()          // 生成模式：不带指令 → 后端才落盘清单
    expect(params.chapter_number).toBe(3)               // 现有最大章号 + 1
    const slots = wrapper.findAll('[data-testid="manifest-slot"]').map((s) => s.attributes('data-slot'))
    expect(slots).toEqual(['chapter_tail'])
    expect(wrapper.find('[data-testid="manifest-skipped"]').text()).toContain('beat')
    expect(wrapper.find('[data-testid="manifest-persist-warn"]').exists()).toBe(false)
  })

  it('P1-3："读取本章历史清单"能从磁盘取回（不再是必然失败的按钮）', async () => {
    mockFetchManifest.mockResolvedValue({
      ok: true,
      manifest: { entries: [{ slot_id: 'mainline', tokens: 30 }], skipped: [], dropped: [] },
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="load-manifest-btn"]').trigger('click')
    await flushPromises()

    expect(mockFetchManifest).toHaveBeenCalledWith('novel_a', 2)
    const slots = wrapper.findAll('[data-testid="manifest-slot"]').map((s) => s.attributes('data-slot'))
    expect(slots).toEqual(['mainline'])
  })

  it('P1-4：清单写盘失败时明确警示（不能看起来像"没注入过"）', async () => {
    mockGenerateV2.mockImplementation(async function* (
      _params: any,
      hooks?: { onDone?: (p: any) => void },
    ) {
      hooks?.onDone?.({
        chapter: { chapter_number: 3, content: 'x' },
        context_manifest: { entries: [{ slot_id: 'beat', tokens: 10 }], skipped: [], dropped: [] },
        rewrite: false,
        saved: true,
        manifest_persisted: false,                      // 写盘失败
      })
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('[data-testid="generate-btn"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="manifest-persist-warn"]').exists()).toBe(true)
  })
})
