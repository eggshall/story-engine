import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useCharacterStore } from '../characters'

describe('character store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  const sampleChar = {
    id: 'char-1',
    name: '林月',
    description: '天才剑客，性格孤傲',
    personality: '冷静果断',
    appearance: '长发及腰，一袭白衣',
    background: '自幼习剑，师从无名老人',
    first_mes: '你终于来了。',
    tags: ['主角'],
    relationships: [{ target: 'char-2', relation: '师徒', description: '授业恩师' }],
  }

  it('starts with an empty character list', () => {
    const store = useCharacterStore()
    expect(store.characters).toHaveLength(0)
    expect(store.currentChar).toBeNull()
  })

  it('adds a character', () => {
    const store = useCharacterStore()
    store.addChar({ ...sampleChar })

    expect(store.characters).toHaveLength(1)
    expect(store.characters[0].name).toBe('林月')
    expect(store.characters[0].relationships).toHaveLength(1)
  })

  it('selects a character by id', () => {
    const store = useCharacterStore()
    store.addChar({ ...sampleChar })
    store.addChar({
      ...sampleChar,
      id: 'char-2',
      name: '无名老人',
      tags: ['配角'],
    })

    store.selectChar('char-2')
    expect(store.currentChar).not.toBeNull()
    expect(store.currentChar!.name).toBe('无名老人')

    store.selectChar('nonexistent')
    expect(store.currentChar).toBeNull()
  })

  it('updates a character', () => {
    const store = useCharacterStore()
    store.addChar({ ...sampleChar })

    store.updateChar('char-1', { name: '林月·改', personality: '热情开朗' })

    expect(store.characters[0].name).toBe('林月·改')
    expect(store.characters[0].personality).toBe('热情开朗')
    // 未更新的字段保持不变
    expect(store.characters[0].description).toBe('天才剑客，性格孤傲')
  })

  it('removes a character and clears selection if removed', () => {
    const store = useCharacterStore()
    store.addChar({ ...sampleChar })
    store.addChar({
      ...sampleChar,
      id: 'char-2',
      name: '无名老人',
    })

    store.selectChar('char-1')
    store.removeChar('char-1')

    expect(store.characters).toHaveLength(1)
    expect(store.characters[0].id).toBe('char-2')
    // currentChar 应该是被删除的角色，会被清空
    expect(store.currentChar).toBeNull()
  })

  it('does not affect other characters when removing', () => {
    const store = useCharacterStore()
    store.addChar({ ...sampleChar })
    const char2 = {
      ...sampleChar,
      id: 'char-2',
      name: '无名老人',
      tags: ['配角'],
      relationships: [] as { target: string; relation: string; description: string }[],
    }
    store.addChar(char2)

    store.removeChar('char-1')

    expect(store.characters).toHaveLength(1)
    expect(store.characters[0].name).toBe('无名老人')
    expect(store.characters[0].relationships).toEqual([])
  })

  it('supports multiple characters with relationships', () => {
    const store = useCharacterStore()
    store.addChar({ ...sampleChar })
    store.addChar({
      ...sampleChar,
      id: 'char-2',
      name: '无名老人',
      tags: ['配角'],
      relationships: [{ target: 'char-1', relation: '徒弟', description: '关门弟子' }],
    })

    expect(store.characters).toHaveLength(2)
    // char-1 的关系指向 char-2
    expect(store.characters[0].relationships[0].target).toBe('char-2')
    // char-2 的关系指向 char-1
    expect(store.characters[1].relationships[0].target).toBe('char-1')
  })
})
