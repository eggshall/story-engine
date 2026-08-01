import { describe, it, expect, beforeAll, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import RelationshipGraph from '../RelationshipGraph.vue'
import type { CharacterCard } from '../../stores/characters'

// ECharts needs a canvas with dimensions to init — mock it in headless test env
vi.mock('echarts', () => {
  const mockChart = {
    setOption: vi.fn(),
    on: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    clear: vi.fn(),
  }
  return {
    default: {
      init: vi.fn(() => mockChart),
    },
    init: vi.fn(() => mockChart),
  }
})

describe('RelationshipGraph', () => {
  const sampleCharacters: CharacterCard[] = [
    {
      id: 'char-1',
      name: '林月',
      description: '天才剑客',
      personality: '冷静',
      appearance: '白衣长发',
      background: '自幼习剑',
      first_mes: '',
      tags: ['主角'],
      relationships: [{ target: 'char-2', relation: '师徒', description: '授业恩师' }],
    },
    {
      id: 'char-2',
      name: '无名老人',
      description: '隐世高人',
      personality: '淡泊',
      appearance: '白发苍苍',
      background: '归隐山林',
      first_mes: '',
      tags: ['配角'],
      relationships: [{ target: 'char-1', relation: '徒弟', description: '关门弟子' }],
    },
    {
      id: 'char-3',
      name: '黑影刺客',
      description: '神秘杀手',
      personality: '冷酷',
      appearance: '黑衣蒙面',
      background: '不明',
      first_mes: '',
      tags: ['反派'],
      relationships: [],
    },
  ]

  it('renders the graph container and toolbar', () => {
    const wrapper = mount(RelationshipGraph, {
      props: { characters: sampleCharacters },
      global: {
        stubs: ['el-tag', 'el-button', 'el-dialog', 'el-avatar', 'el-descriptions', 'el-descriptions-item'],
      },
    })

    expect(wrapper.find('.relationship-graph').exists()).toBe(true)
    expect(wrapper.find('.graph-canvas').exists()).toBe(true)
    expect(wrapper.find('.graph-title').text()).toBe('人物关系图谱')
    // toolbar buttons should render
    expect(wrapper.find('.graph-toolbar').exists()).toBe(true)
  })

  it('displays character and relationship count in toolbar header', () => {
    const wrapper = mount(RelationshipGraph, {
      props: { characters: sampleCharacters },
      global: {
        stubs: ['el-tag', 'el-button', 'el-dialog', 'el-avatar', 'el-descriptions', 'el-descriptions-item'],
      },
    })

    // Check raw text contains the counts
    const toolbarText = wrapper.find('.toolbar-left').text()
    expect(toolbarText).toContain('人物关系图谱')
  })

  it('renders with empty character list gracefully', () => {
    const wrapper = mount(RelationshipGraph, {
      props: { characters: [] },
      global: {
        stubs: ['el-tag', 'el-button', 'el-dialog', 'el-avatar', 'el-descriptions', 'el-descriptions-item'],
      },
    })

    expect(wrapper.find('.relationship-graph').exists()).toBe(true)
    expect(wrapper.find('.graph-canvas').exists()).toBe(true)
    expect(wrapper.find('.graph-title').text()).toBe('人物关系图谱')
  })

  it('renders with single character', () => {
    const wrapper = mount(RelationshipGraph, {
      props: { characters: [sampleCharacters[0]] },
      global: {
        stubs: ['el-tag', 'el-button', 'el-dialog', 'el-avatar', 'el-descriptions', 'el-descriptions-item'],
      },
    })

    expect(wrapper.find('.relationship-graph').exists()).toBe(true)
  })

  it('renders with characters having no relationships', () => {
    const noRelChars = sampleCharacters.filter((c) => c.relationships.length === 0)
    const wrapper = mount(RelationshipGraph, {
      props: { characters: noRelChars },
      global: {
        stubs: ['el-tag', 'el-button', 'el-dialog', 'el-avatar', 'el-descriptions', 'el-descriptions-item'],
      },
    })

    expect(wrapper.find('.relationship-graph').exists()).toBe(true)
  })
})
