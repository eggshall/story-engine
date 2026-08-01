import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface CharacterCard {
  id: string
  name: string
  description: string
  personality: string
  background: string
  appearance: string
  first_mes: string
  relationships: { target: string; relation: string; description: string }[]
  tags: string[]
}

export const useCharacterStore = defineStore('characters', () => {
  const characters = ref<CharacterCard[]>([])
  const currentChar = ref<CharacterCard | null>(null)

  function selectChar(id: string) {
    currentChar.value = characters.value.find((c) => c.id === id) || null
  }

  function addChar(char: CharacterCard) {
    characters.value.push(char)
  }

  function updateChar(id: string, data: Partial<CharacterCard>) {
    const idx = characters.value.findIndex((c) => c.id === id)
    if (idx >= 0) {
      characters.value[idx] = { ...characters.value[idx], ...data }
    }
  }

  function removeChar(id: string) {
    characters.value = characters.value.filter((c) => c.id !== id)
    if (currentChar.value?.id === id) currentChar.value = null
  }

  return { characters, currentChar, selectChar, addChar, updateChar, removeChar }
})
