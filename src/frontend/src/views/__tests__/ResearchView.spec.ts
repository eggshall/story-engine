import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ResearchView from '../ResearchView.vue'

// Mock the API modules
const mockResearch = vi.fn()
const mockApiGet = vi.fn()
const mockApiPost = vi.fn()

vi.mock('../../utils/api', () => {
  const api = {
    get: (...args: any[]) => mockApiGet(...args),
    post: (...args: any[]) => mockApiPost(...args),
    defaults: { baseURL: '/api' },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  }
  return {
    default: api,
    research: (...args: any[]) => mockResearch(...args),
  }
})

// Stub Element Plus components
const stubs = {
  'el-input': {
    template: '<input class="el-input-stub" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ['modelValue'],
  },
  'el-button': {
    template: '<button class="el-button-stub" :disabled="disabled" @click.stop="$emit(\'click\')"><slot /></button>',
    props: ['disabled', 'loading'],
  },
  'el-card': {
    template: '<div class="el-card-stub"><slot /></div>',
  },
  'el-tag': {
    template: '<span class="el-tag-stub"><slot /></span>',
    props: ['type', 'size'],
  },
  'el-checkbox': {
    template: '<label class="el-checkbox-stub"><input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" /><slot /></label>',
    props: ['modelValue'],
  },
  'el-collapse': {
    template: '<div class="el-collapse-stub"><slot /></div>',
  },
  'el-collapse-item': {
    template: '<div class="el-collapse-item-stub"><slot name="title" /><slot /></div>',
    props: ['title', 'name'],
  },
  'el-timeline': {
    template: '<div class="el-timeline-stub"><slot /></div>',
  },
  'el-timeline-item': {
    template: '<div class="el-timeline-item-stub"><slot /></div>',
    props: ['timestamp', 'placement'],
  },
  'el-icon': {
    template: '<i class="el-icon-stub"><slot /></i>',
  },
  'el-divider': {
    template: '<hr class="el-divider-stub" />',
  },
  'el-skeleton': {
    template: '<div class="el-skeleton-stub"><slot /></div>',
  },
}

// Helper: mount with default mocks
function mountView() {
  // Default mockApiGet returns empty history
  mockApiGet.mockResolvedValue({ data: { data: [] } })
  return mount(ResearchView, { global: { stubs } })
}

describe('ResearchView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
  })

  // ─── 1. Basic rendering ───

  it('renders search input and button', () => {
    const wrapper = mountView()

    // Should have a search input
    expect(wrapper.find('.el-input-stub').exists()).toBe(true)
    // Should have a search button
    const buttons = wrapper.findAll('.el-button-stub')
    const searchBtn = buttons.find(b => b.text().includes('搜索') || b.text().includes('Search'))
    expect(searchBtn).toBeDefined()
  })

  it('shows the view title', () => {
    const wrapper = mountView()
    expect(wrapper.text()).toContain('资料检索')
  })

  // ─── 2. Empty query validation ───

  it('does not call API when search is clicked with empty query', async () => {
    const wrapper = mountView()
    await flushPromises()

    const vm = wrapper.vm as any
    // Call doSearch directly with empty query
    vm.query = ''
    await vm.doSearch()
    await flushPromises()

    // API should NOT have been called
    expect(mockResearch).not.toHaveBeenCalled()
  })

  // ─── 3. Successful search ───

  it('calls research API with correct params when searching', async () => {
    mockApiGet.mockResolvedValue({ data: { data: [] } })

    const mockResult = {
      query: 'test query',
      summary: 'Summary text.',
      sources: [
        { title: 'Source One', url: 'https://example.com/1', snippet: 'Snippet 1', source: 'bing' },
      ],
      saved_to: 'lorebook',
    }
    mockResearch.mockResolvedValue(mockResult)

    const wrapper = mount(ResearchView, { global: { stubs } })
    await flushPromises()

    const vm = wrapper.vm as any
    vm.query = 'test query'
    await vm.doSearch()
    await flushPromises()

    // API should have been called with correct params
    expect(mockResearch).toHaveBeenCalledWith({
      query: 'test query',
      save_to_lore: false,
    })
  })

  it('displays result cards after search', async () => {
    const mockResult = {
      query: 'dragons',
      summary: 'Dragons are mythical creatures.',
      sources: [
        { title: 'Dragon Wiki', url: 'https://dragons.com', snippet: 'About dragons...', source: 'bing' },
        { title: 'Dragon Lore', url: 'https://lore.com', snippet: 'Dragon history...', source: 'so' },
      ],
      saved_to: 'mythical-beasts',
    }
    mockResearch.mockResolvedValue(mockResult)
    mockApiGet.mockResolvedValue({ data: { data: [] } })

    const wrapper = mount(ResearchView, { global: { stubs } })
    await flushPromises()

    const vm = wrapper.vm as any
    vm.query = 'dragons'
    await vm.doSearch()
    await flushPromises()
    await wrapper.vm.$nextTick()

    // Check that results are stored on the component
    expect(vm.results).not.toBeNull()
    expect(vm.results.sources).toBeDefined()
    expect(vm.results.sources.length).toBe(2)
    expect(vm.results.sources[0].title).toBe('Dragon Wiki')

    // Should display source titles in the rendered output
    const html = wrapper.html()
    expect(html).toContain('Dragon Wiki')
    expect(html).toContain('Dragon Lore')
  })

  // ─── 4. Loading state ───

  it('shows loading state while searching', async () => {
    // Use a deferred promise so search never completes during test
    let resolveApi!: (value: any) => void
    const deferred = new Promise((resolve) => {
      resolveApi = resolve
    })
    mockResearch.mockReturnValue(deferred)
    mockApiGet.mockResolvedValue({ data: { data: [] } })

    const wrapper = mount(ResearchView, { global: { stubs } })
    await flushPromises()

    const vm = wrapper.vm as any
    vm.query = 'something'

    // Start search — don't await it
    const searchPromise = vm.doSearch()

    // Allow microtasks to flush (but the promise is still pending)
    await wrapper.vm.$nextTick()

    // The searching ref should be true while the promise is pending
    expect(vm.searching).toBe(true)

    // Resolve to clean up
    resolveApi({
      query: 'something',
      summary: '',
      sources: [],
      saved_to: '',
    })
    await searchPromise
    await flushPromises()
  })

  // ─── 5. History ───

  it('fetches search history on mount', async () => {
    const mockHistory = {
      data: {
        data: [
          { query: 'past query 1', timestamp: '2026-01-01', result_count: 3 },
          { query: 'past query 2', timestamp: '2026-01-02', result_count: 5 },
        ],
      },
    }
    mockApiGet.mockResolvedValueOnce(mockHistory)

    const wrapper = mount(ResearchView, { global: { stubs } })
    await flushPromises()
    await wrapper.vm.$nextTick()
    await flushPromises()

    // GET /api/research/ should have been called
    expect(mockApiGet).toHaveBeenCalledWith('/research/')
  })

  // ─── 6. Error handling ───

  it('handles search API errors gracefully', async () => {
    mockApiGet.mockResolvedValue({ data: { data: [] } })
    mockResearch.mockRejectedValue(new Error('Network error'))

    const wrapper = mount(ResearchView, { global: { stubs } })
    await flushPromises()

    const vm = wrapper.vm as any
    vm.query = 'error test'
    await vm.doSearch()
    await flushPromises()
    await wrapper.vm.$nextTick()

    // Should recover — searching should be false again
    expect(vm.searching).toBe(false)
  })

  // ─── 7. Save to lorebook checkbox ───

  it('has a save to lorebook checkbox', async () => {
    const wrapper = mountView()
    await flushPromises()

    // Should find a checkbox related to lorebook
    expect(wrapper.find('.el-checkbox-stub').exists()).toBe(true)
    expect(wrapper.text()).toMatch(/lorebook|设定集|知识库/)
  })
})
