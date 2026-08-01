import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const streaming = ref(false)
  const currentStream = ref('')
  const searching = ref(false)

  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
  }

  function clearMessages() {
    messages.value = []
  }

  function startStream() {
    streaming.value = true
    currentStream.value = ''
  }

  function appendStream(token: string) {
    currentStream.value += token
  }

  function finishStream() {
    if (currentStream.value) {
      messages.value.push({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: currentStream.value,
        timestamp: Date.now(),
      })
    }
    streaming.value = false
    currentStream.value = ''
  }

  return { messages, streaming, currentStream, addMessage, clearMessages, startStream, appendStream, finishStream }
})
