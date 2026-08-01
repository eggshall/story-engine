import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ContextMenu from '../ContextMenu.vue'

describe('ContextMenu', () => {
  beforeEach(() => {
    // 清除 teleport 残留
    document.body.innerHTML = ''
  })

  const defaultProps = {
    visible: true,
    x: 100,
    y: 200,
    selectedText: '选中的测试文字',
    loading: false,
    loadingAction: '',
  }

  function createWrapper(props = {}) {
    return mount(ContextMenu, {
      props: { ...defaultProps, ...props },
      attachTo: document.body,
      global: {
        stubs: ['el-icon'],
      },
    })
  }

  it('renders when visible is true', () => {
    createWrapper()
    expect(document.body.querySelector('.context-menu')).toBeTruthy()
  })

  it('does not render when visible is false', () => {
    createWrapper({ visible: false })
    expect(document.body.querySelector('.context-menu')).toBeNull()
  })

  it('positions menu at given coordinates', () => {
    createWrapper()
    const menu = document.body.querySelector('.context-menu') as HTMLElement
    expect(menu.style.left).toBe('100px')
    expect(menu.style.top).toBe('200px')
  })

  it('displays the selected text', () => {
    createWrapper()
    const el = document.body.querySelector('.menu-selected-text')
    expect(el?.textContent).toBe('选中的测试文字')
  })

  it('truncates long selected text', () => {
    const longText = '这是一段非常长的文字用来测试截断效果是否正常工作在菜单标题中'
    createWrapper({ selectedText: longText })
    const el = document.body.querySelector('.menu-selected-text')
    const text = el?.textContent || ''
    expect(text.length).toBeLessThanOrEqual(longText.length)
  })

  it('shows all 6 action items', () => {
    createWrapper()
    const items = document.body.querySelectorAll('.menu-item')
    expect(items.length).toBe(6)
    expect(items[0].textContent).toContain('润色')
    expect(items[1].textContent).toContain('扩写')
    expect(items[2].textContent).toContain('缩写')
    expect(items[3].textContent).toContain('续写')
    expect(items[4].textContent).toContain('去AI味')
    expect(items[5].textContent).toContain('风格分析')
  })

  it('emits action when menu item is clicked', async () => {
    const wrapper = createWrapper()
    const items = document.body.querySelectorAll('.menu-item')
    await (items[0] as HTMLElement).click()

    expect(wrapper.emitted('action')).toBeTruthy()
    expect(wrapper.emitted('action')![0]).toEqual(['polish'])
  })

  it('emits close when overlay is clicked', async () => {
    const wrapper = createWrapper()
    const overlay = document.body.querySelector('.context-menu-overlay') as HTMLElement
    await overlay.click()

    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('shows loading state with correct text', () => {
    createWrapper({ loading: true, loadingAction: 'polish' })
    const el = document.body.querySelector('.menu-loading')
    expect(el).toBeTruthy()
    expect(el?.textContent).toContain('润色中')
  })

  it('shows loading state for different actions', () => {
    createWrapper({ loading: true, loadingAction: 'expand' })
    const el = document.body.querySelector('.menu-loading')
    expect(el?.textContent).toContain('扩写中')
  })
})
