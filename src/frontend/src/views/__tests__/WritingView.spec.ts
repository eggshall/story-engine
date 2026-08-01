import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

// Mock the API modules
const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
const mockChatStream = vi.fn()
const mockGenerateChapterStream = vi.fn()

vi.mock('../../utils/api', () => {
  const api = {
    get: (...args: any[]) => mockApiGet(...args),
    post: (...args: any[]) => mockApiPost(...args),
    defaults: { baseURL: '/api' },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  }
  return {
    default: api,
    chatStream: (...args: any[]) => mockChatStream(...args),
    generateChapterStream: (...args: any[]) => mockGenerateChapterStream(...args),
    exportMd: vi.fn(),
    fetchNovels: vi.fn(),
    fetchNovel: vi.fn(),
    createNovel: vi.fn(),
    fetchModels: vi.fn(),
    research: vi.fn(),
    generateOutlineStream: vi.fn(),
    // StylePanel onMounted → loadProfiles 走这里，必须 mock 掉避免真实请求
    fetchStyleProfiles: vi.fn().mockResolvedValue([]),
  }
})

// Mock the marked library
vi.mock('marked', () => ({
  marked: {
    parse: vi.fn((text: string) => text),
  },
}))

// Shared reactive state for novel store
const novelState: any = {
  currentNovel: null,
  currentChapter: null,
  loading: false,
  saving: false,
  novels: [],
  loadNovel: vi.fn(),
  loadNovels: vi.fn(),
  selectChapter: vi.fn(),
  addChapter: vi.fn(),
  deleteChapter: vi.fn(),
  saveCurrentChapter: vi.fn(),
  create: vi.fn(),
}

vi.mock('../../stores/novel', () => {
  const useNovelStore = vi.fn(() => novelState)
  return { useNovelStore }
})

vi.mock('../../stores/settings', () => {
  const useSettingsStore = vi.fn(() => ({
    models: [
      { name: 'test-model', provider: 'openai', model_id: 'test' },
    ],
  }))
  return { useSettingsStore }
})

import WritingView from '../WritingView.vue'

// Stub Element Plus components
const stubs = {
  'el-select': {
    template: '<div class="el-select-stub"><slot /></div>',
    props: ['modelValue', 'size', 'placeholder'],
  },
  'el-option': {
    template: '<div class="el-option-stub"><slot /></div>',
    props: ['label', 'value'],
  },
  'el-button': {
    template: '<button class="el-button-stub" :disabled="disabled || loading" @click.stop="$emit(\'click\')"><slot /></button>',
    props: ['disabled', 'loading', 'size', 'type', 'icon', 'text'],
  },
  'el-input': {
    template: '<input class="el-input-stub" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ['modelValue', 'placeholder', 'maxlength', 'size', 'type', 'rows', 'resize'],
  },
  'el-tabs': {
    template: '<div class="el-tabs-stub"><slot /></div>',
    props: ['modelValue'],
  },
  'el-tab-pane': {
    template: '<div class="el-tab-pane-stub"><slot /></div>',
    props: ['label', 'name'],
  },
  'el-dialog': {
    template: '<div class="el-dialog-stub" v-if="modelValue"><slot /></div>',
    props: ['modelValue', 'title', 'width', 'closeOnClickModal'],
  },
  'el-icon': {
    template: '<i class="el-icon-stub"><slot /></i>',
  },
}

// Mock the child components
const componentStubs = {
  NovelTree: {
    template: '<div class="novel-tree-stub">NovelTree</div>',
    props: ['currentId'],
  },
  AiChatPanel: {
    template: '<div class="ai-chat-panel-stub">AiChatPanel</div>',
  },
  ChapterPanel: {
    template: '<div class="chapter-panel-stub">ChapterPanel</div>',
  },
  ProgressPanel: {
    template: '<div class="progress-panel-stub">ProgressPanel</div>',
    props: ['novelId'],
  },
  ContextMenu: {
    template: '<div class="context-menu-stub" v-if="visible">ContextMenu</div>',
    props: ['visible', 'x', 'y', 'selectedText', 'loading', 'loadingAction'],
  },
}

// Helper: mount with a novel and chapter loaded
function mountWithNovel() {
  novelState.currentNovel = {
    id: 'test-novel',
    title: '测试小说',
    genre: '玄幻',
    author: '作者',
    word_count: 1000,
    chapter_count: 2,
    synopsis: '',
    characters: [],
    lorebooks: [],
    chapters: [
      { chapter_number: 1, title: '第一章', content: '测试内容' },
    ],
    created: '2026-01-01',
    updated: '2026-01-01',
  }
  novelState.currentChapter = {
    chapter_number: 1,
    title: '第一章',
    content: '测试内容',
    word_count: 4,
  }

  // Default mock responses
  mockApiGet.mockResolvedValue({ data: { data: null } })
  mockApiPost.mockResolvedValue({ data: { success: true, data: {} } })

  return mount(WritingView, {
    global: {
      stubs: { ...stubs, ...componentStubs },
    },
  })
}

describe('WritingView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
    // Reset novel state
    novelState.currentNovel = null
    novelState.currentChapter = null
  })

  // ─── Toolbar rendering ───

  it('renders toolbar when novel is loaded', async () => {
    const wrapper = mountWithNovel()
    await flushPromises()
    await wrapper.vm.$nextTick()

    // The topbar-right should exist
    const toolbar = wrapper.find('.topbar-right')
    expect(toolbar.exists()).toBe(true)

    // Should have buttons
    const buttons = wrapper.findAll('.el-button-stub')
    expect(buttons.length).toBeGreaterThanOrEqual(4)
  })

  it('has a "去AI味" button in the toolbar', async () => {
    const wrapper = mountWithNovel()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('.el-button-stub')
    const deaiBtn = buttons.find(b => b.text().includes('去AI味'))
    expect(deaiBtn).toBeDefined()
  })

  it('has a "一致性检查" button in the toolbar', async () => {
    const wrapper = mountWithNovel()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('.el-button-stub')
    const consistencyBtn = buttons.find(b => b.text().includes('一致性检查'))
    expect(consistencyBtn).toBeDefined()
  })

  it('has a "风格分析" button in the toolbar', async () => {
    const wrapper = mountWithNovel()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('.el-button-stub')
    const styleBtn = buttons.find(b => b.text().includes('风格分析'))
    expect(styleBtn).toBeDefined()
  })

  // ─── Consistency check button action ───

  it('calls consistency API when 一致性检查 button is clicked', async () => {
    mockApiPost.mockResolvedValue({
      data: {
        success: true,
        data: { issues: [], chapter_number: 1, checked_names: 0, checked_places: 0 },
      },
    })

    const wrapper = mountWithNovel()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('.el-button-stub')
    const consistencyBtn = buttons.find(b => b.text().includes('一致性检查'))
    expect(consistencyBtn).toBeDefined()

    await consistencyBtn!.trigger('click')
    await flushPromises()
    await wrapper.vm.$nextTick()

    // Should have called the consistency endpoint
    expect(mockApiPost).toHaveBeenCalledWith(
      '/novel/test-novel/analyze/consistency',
      { chapter_number: 1, text: '测试内容' },
    )
  })

  // ─── Style analysis button action ───

  it('calls style API when 风格分析 button is clicked', async () => {
    mockApiPost.mockResolvedValue({
      data: {
        success: true,
        data: {
          avg_sentence_length: 15.2,
          sentence_count: 3,
          total_chars: 50,
          techniques: ['短句开篇'],
          chapter_number: 1,
        },
      },
    })

    const wrapper = mountWithNovel()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('.el-button-stub')
    const styleBtn = buttons.find(b => b.text().includes('风格分析'))
    expect(styleBtn).toBeDefined()

    await styleBtn!.trigger('click')
    await flushPromises()
    await wrapper.vm.$nextTick()

    // Should have called the style endpoint
    expect(mockApiPost).toHaveBeenCalledWith(
      '/novel/test-novel/analyze/style',
      { chapter_number: 1, text: '测试内容' },
    )
  })

  // ─── 去AI味 button action ───

  it('calls chatStream when 去AI味 button is clicked', async () => {
    // Mock chatStream to yield a single token
    mockChatStream.mockImplementation(async function* () {
      yield '去AI味后的内容'
    })

    const wrapper = mountWithNovel()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('.el-button-stub')
    const deaiBtn = buttons.find(b => b.text().includes('去AI味'))
    expect(deaiBtn).toBeDefined()

    await deaiBtn!.trigger('click')
    await flushPromises()
    await wrapper.vm.$nextTick()

    // Should have called chatStream with de-ai prompt
    expect(mockChatStream).toHaveBeenCalled()
    const callArgs = mockChatStream.mock.calls[0][0]
    expect(callArgs.messages[0].content).toBe('测试内容')
    expect(callArgs.system_prompt).toContain('消除AI')
    expect(callArgs.mode).toBe('writing')
  })

  // ─── Toolbar buttons disabled when no novel ───

  it('does not render analysis buttons when no novel is selected', async () => {
    // Mount without setting a current novel (novelState already reset in beforeEach)
    const wrapper = mount(WritingView, {
      global: {
        stubs: { ...stubs, ...componentStubs },
      },
    })
    await flushPromises()
    await wrapper.vm.$nextTick()

    // The topbar-right might not exist or have different content
    const buttons = wrapper.findAll('.el-button-stub')
    const deaiBtn = buttons.find(b => b.text().includes('去AI味'))
    const consistencyBtn = buttons.find(b => b.text().includes('一致性检查'))
    const styleBtn = buttons.find(b => b.text().includes('风格分析'))

    // These buttons should either not exist or be disabled
    if (deaiBtn) {
      expect(deaiBtn.attributes('disabled')).toBeDefined()
    }
    if (consistencyBtn) {
      expect(consistencyBtn.attributes('disabled')).toBeDefined()
    }
    if (styleBtn) {
      expect(styleBtn.attributes('disabled')).toBeDefined()
    }
  })
})
