import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useStyleStore } from '../../stores/style'
import AiChatPanel from '../AiChatPanel.vue'

// mock 掉 chatStream，避免真实网络请求
vi.mock('../../utils/api', () => ({
  chatStream: vi.fn().mockImplementation(async function* () {}),
}))

import { chatStream } from '../../utils/api'
const chatStreamMock = chatStream as unknown as ReturnType<typeof vi.fn>

const STYLE_PROMPT = '冷峻犀利，多用短句。'

function createWrapper() {
  return mount(AiChatPanel, {
    global: {
      // 使用 setActivePinia 的实例，保证测试能直接操作 store
      stubs: {
        // 渲染真实表单元素，便于交互
        'el-input': {
          props: ['modelValue'],
          template:
            '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
        },
        'el-select': {
          props: ['modelValue'],
          template:
            '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
        },
        'el-option': {
          props: ['value'],
          template: '<option :value="value"><slot /></option>',
        },
        'el-button': {
          template: '<button @click="$emit(\'click\', $event)"><slot /></button>',
        },
        'el-switch': true,
        'el-tooltip': { template: '<span><slot /></span>' },
        'el-icon': { template: '<span><slot /></span>' },
      },
    },
  })
}

/** 切到写作模式 */
async function switchToWriteMode(wrapper: ReturnType<typeof createWrapper>) {
  const selects = wrapper.findAll('select')
  await selects[0].setValue('write')
}

/** 输入文本并发送 */
async function sendMessage(wrapper: ReturnType<typeof createWrapper>, text: string) {
  await wrapper.find('textarea').setValue(text)
  await wrapper.find('.input-footer button').trigger('click')
}

describe('AiChatPanel — 文风注入 (P5)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    chatStreamMock.mockClear()
  })

  it('写作模式下携带已选文风的 stylePrompt 发送', async () => {
    const styleStore = useStyleStore()
    styleStore.profiles = [
      { id: 's1', name: '冷峻', author: '鲁迅', style_prompt: STYLE_PROMPT },
    ] as any
    styleStore.selectedProfileId = 's1'

    const wrapper = createWrapper()
    await switchToWriteMode(wrapper)
    await sendMessage(wrapper, '写一个开头')

    expect(chatStreamMock).toHaveBeenCalledTimes(1)
    const args = chatStreamMock.mock.calls[0][0]
    expect(args.stylePrompt).toBe(STYLE_PROMPT)
  })

  it('未选文风时不传 stylePrompt', async () => {
    const wrapper = createWrapper()
    await switchToWriteMode(wrapper)
    await sendMessage(wrapper, '写一个开头')

    expect(chatStreamMock).toHaveBeenCalledTimes(1)
    const args = chatStreamMock.mock.calls[0][0]
    expect(args.stylePrompt || '').toBe('')
  })

  it('闲聊模式下即使选了文风也不传 stylePrompt', async () => {
    const styleStore = useStyleStore()
    styleStore.profiles = [
      { id: 's1', name: '冷峻', author: '鲁迅', style_prompt: STYLE_PROMPT },
    ] as any
    styleStore.selectedProfileId = 's1'

    const wrapper = createWrapper()
    await sendMessage(wrapper, '今天天气怎么样')

    expect(chatStreamMock).toHaveBeenCalledTimes(1)
    const args = chatStreamMock.mock.calls[0][0]
    expect(args.stylePrompt || '').toBe('')
  })
})
