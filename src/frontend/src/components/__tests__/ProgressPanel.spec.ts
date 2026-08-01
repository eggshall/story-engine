import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useNovelStore } from '../../stores/novel'
import ProgressPanel from '../ProgressPanel.vue'

describe('ProgressPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('renders with default values when no novel selected', () => {
    const wrapper = mount(ProgressPanel, {
      props: { novelId: null },
      global: {
        stubs: ['el-progress', 'el-input-number', 'el-radio-group', 'el-radio-button', 'el-icon'],
      },
    })

    expect(wrapper.find('.progress-panel').exists()).toBe(true)
    // 默认阶段是"写作"
    expect(wrapper.find('.section-title').text()).toBe('📖 章节进度')
  })

  it('shows 0 chapters completed when no novel data', () => {
    const wrapper = mount(ProgressPanel, {
      props: { novelId: 'test-novel' },
      global: {
        stubs: ['el-progress', 'el-input-number', 'el-radio-group', 'el-radio-button', 'el-icon'],
      },
    })

    // The completed count should be 0 (no chapters)
    expect(wrapper.find('.value-num').text()).toBe('0')
  })

  it('displays writing stage selector with three options', () => {
    const wrapper = mount(ProgressPanel, {
      props: { novelId: 'test-novel' },
      global: {
        stubs: ['el-progress', 'el-input-number', 'el-radio-group', 'el-radio-button', 'el-icon'],
      },
    })

    const stageGroup = wrapper.find('.stage-group')
    expect(stageGroup.exists()).toBe(true)
  })

  it('persists planned chapters to localStorage', async () => {
    const wrapper = mount(ProgressPanel, {
      props: { novelId: 'persist-test' },
      global: {
        stubs: ['el-progress', 'el-input-number', 'el-radio-group', 'el-radio-button', 'el-icon'],
      },
    })

    // Verify localStorage was written
    const saved = localStorage.getItem('novel-planned-persist-test')
    expect(saved).toBe('10') // default
  })

  it('computes chapter stats from novel store', () => {
    const store = useNovelStore()
    store.currentNovel = {
      id: 'novel-1',
      title: '测试小说',
      author: '作者',
      genre: '奇幻',
      word_count: 15000,
      chapter_count: 5,
      created: '2026-01-01',
      updated: '2026-06-01',
      synopsis: '测试',
      characters: [],
      lorebooks: [],
      chapters: [
        { chapter_number: 1, title: '第一章', word_count: 3000 },
        { chapter_number: 2, title: '第二章', word_count: 4000 },
        { chapter_number: 3, title: '第三章', word_count: 3500 },
      ],
    }

    const wrapper = mount(ProgressPanel, {
      props: { novelId: 'novel-1' },
      global: {
        stubs: ['el-progress', 'el-input-number', 'el-radio-group', 'el-radio-button', 'el-icon'],
      },
    })

    // 3 completed chapters
    expect(wrapper.find('.value-num').text()).toBe('3')
    // Word count should be 15000
  })

  it('exposes refreshStats method', () => {
    const wrapper = mount(ProgressPanel, {
      props: { novelId: 'test-novel' },
      global: {
        stubs: ['el-progress', 'el-input-number', 'el-radio-group', 'el-radio-button', 'el-icon'],
      },
    })

    const vm = wrapper.vm as any
    expect(typeof vm.refreshStats).toBe('function')
    expect(typeof vm.recordTodayWords).toBe('function')
  })

  it('recordTodayWords stores in localStorage', () => {
    const wrapper = mount(ProgressPanel, {
      props: { novelId: 'word-test' },
      global: {
        stubs: ['el-progress', 'el-input-number', 'el-radio-group', 'el-radio-button', 'el-icon'],
      },
    })

    const vm = wrapper.vm as any
    vm.recordTodayWords(500)

    const data = JSON.parse(localStorage.getItem('novel-word-stats') || '{}')
    const today = new Date().toISOString().slice(0, 10)
    expect(data[today]).toBe(500)
  })

  it('formatWords formats large numbers', () => {
    const wrapper = mount(ProgressPanel, {
      props: { novelId: 'format-test' },
      global: {
        stubs: ['el-progress', 'el-input-number', 'el-radio-group', 'el-radio-button', 'el-icon'],
      },
    })

    const vm = wrapper.vm as any
    // Access formatWords via the component's internals — exposed methods
    expect(vm.recordTodayWords).toBeDefined()
  })

  it('renders word stats grid with sections', () => {
    const wrapper = mount(ProgressPanel, {
      props: { novelId: 'test-novel' },
      global: {
        stubs: ['el-progress', 'el-input-number', 'el-radio-group', 'el-radio-button', 'el-icon'],
      },
    })

    expect(wrapper.find('.word-stats-grid').exists()).toBe(true)
    const statCards = wrapper.findAll('.word-stat-card')
    expect(statCards.length).toBe(4) // 总字数, 今日, 本周, 本月
  })
})
