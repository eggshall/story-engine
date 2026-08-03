\n<template>
  <div class="ai-chat-panel">
    <div class="chat-header">
      <span class="chat-title">AI 助手</span>
      <el-button size="small" :icon="Delete" text @click="clearChat" />
    </div>

    <!-- 工具栏：模式 + 模型 + 搜索 -->
    <div class="chat-toolbar">
      <el-select v-model="mode" size="small" style="width: 110px" @change="onModeChange">
        <el-option label="💬 闲聊" value="chat" />
        <el-option label="✍️ 写作" value="write" />
      </el-select>
      <el-select
        v-model="selectedModel"
        size="small"
        placeholder="模型"
        style="width: 130px"
        :disabled="mode === 'write'"
      >
        <el-option
          v-for="m in settings.models"
          :key="m.model_id"
          :label="m.name"
          :value="m.name"
        />
      </el-select>
      <el-tooltip content="联网搜索后回答" placement="top">
        <el-switch
          v-model="searchEnabled"
          size="small"
          active-text="🌐"
          inactive-text=""
          style="margin-left: 4px"
        />
      </el-tooltip>
    </div>

    <!-- 搜索提示条 -->
    <div v-if="searchEnabled && chat.searching" class="search-bar">
      <el-icon class="is-loading" :size="14"><Loading /></el-icon>
      <span>正在搜索: {{ searchQuery }}</span>
    </div>

    <!-- 消息列表 -->
    <div class="chat-messages" ref="msgListRef">
      <div
        v-for="msg in chat.messages"
        :key="msg.id"
        :class="['message', msg.role]"
      >
        <div class="message-label">
          {{ msg.role === 'user' ? '你' : 'AI' }}
        </div>
        <div class="message-content" v-html="renderMarkdown(msg.content)" />
      </div>

      <!-- 流式输出 -->
      <div v-if="chat.streaming" class="message assistant">
        <div class="message-label">AI</div>
        <!-- 思考过程面板（通用，不依赖模型标签） -->
        <details v-if="thinkPanelText" class="think-block" open>
          <summary>
            {{ thinkPanelIcon }} {{ thinkPanelTitle }}
          </summary>
          <div class="think-content">{{ thinkPanelText }}</div>
        </details>
        <div class="message-content streaming" v-html="renderMarkdown(chat.currentStream)" />
      </div>
    </div>

    <!-- 输入区 -->
    <div class="chat-input">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="3"
        placeholder="输入想法或指令… (Ctrl+Enter 发送)"
        :disabled="chat.streaming"
        @keydown.enter.ctrl="sendMessage"
      />
      <div class="input-footer">
        <span class="mode-hint">{{ mode === 'write' ? '专业写作模式' : searchEnabled ? '联网搜索模式' : '普通闲聊模式' }}</span>
        <el-button
          type="primary"
          :icon="Promotion"
          :loading="chat.streaming"
          :disabled="!inputText.trim()"
          @click="sendMessage"
        >
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { Delete, Promotion, Loading } from '@element-plus/icons-vue'
import { marked } from 'marked'
import { useChatStore } from '../stores/chat'
import { useSettingsStore } from '../stores/settings'
import { useStyleStore } from '../stores/style'
import { chatStream } from '../utils/api'

const chat = useChatStore()
const settings = useSettingsStore()
const styleStore = useStyleStore()
const inputText = ref('')
const selectedModel = ref('')
const mode = ref('chat')
const searchEnabled = ref(false)
const searchQuery = ref('')
const msgListRef = ref<HTMLElement>()

onMounted(() => {
  if (settings.models.length > 0) {
    // 按当前模式选择对应模型
    onModeChange(mode.value)
  }
})

function onModeChange(val: string) {
  // 专业写作默认用第一个可用远程模型（通常是 deepseek）
  // 普通闲聊默认用本地模型
  if (val === 'write') {
    const remote = settings.models.find((m) => m.provider !== 'local')
    if (remote) selectedModel.value = remote.name
    searchEnabled.value = false
  } else {
    const local = settings.models.find((m) => m.provider === 'local')
    if (local) selectedModel.value = local.name
  }
}

function renderMarkdown(text: string): string {
  let processed = text

  // 已完成的回复（非流式）：将 <think> 渲染为可折叠块
  processed = processed.replace(
    /<think[^>]*>([\s\S]*?)<\/think>/gi,
    (_match, content) => {
      const md = marked.parse(content || '', { async: false }) as string
      return `<details class="think-block">
  <summary>🤔 思考过程</summary>
  <div class="think-content">${md}</div>
</details>`
    }
  )
  // 流式输出中未闭合的 <think：移除（由模板层通用面板展示）
  processed = processed.replace(/<think[^>]*>[\s\S]*$/i, '').trim()

  // 渲染 markdown
  return marked.parse(processed, { async: false }) as string
}

// ── 思考过程面板（通用方案B） ──
const hasThinkTags = computed(() => /<think/i.test(chat.currentStream))

const thinkPanelText = computed(() => {
  if (!chat.streaming) return ''
  const stream = chat.currentStream
  const thinkMatch = stream.match(/<think[^>]*>([\s\S]*?)(?:<\/think>|$)/i)
  if (thinkMatch && thinkMatch[1].trim()) {
    return thinkMatch[1].trim()
  }
  return '正在处理你的请求…'
})

const thinkPanelIcon = computed(() => {
  if (!chat.streaming) return '✅'
  if (hasThinkTags.value) return '🤔'
  return '⏳'
})

const thinkPanelTitle = computed(() => {
  if (!chat.streaming) return '思考完成'
  if (hasThinkTags.value) return 'AI 思考中...'
  return '处理中...'
})

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || chat.streaming) return

  chat.addMessage({ id: crypto.randomUUID(), role: 'user', content: text, timestamp: Date.now() })
  inputText.value = ''
  searchQuery.value = text.slice(0, 80)

  // 记录搜索状态
  if (searchEnabled.value) chat.searching = true

  chat.startStream()

  try {
    const msgs = chat.messages.map((m) => ({ role: m.role, content: m.content }))
    // P5+: 写作模式下携带已选文风 — profileId 完整注入(特征+样本)，兜底 stylePrompt
    const profile = styleStore.selectedProfile
    const stylePrompt =
      mode.value === 'write' ? (profile?.style_prompt || '') : ''
    const profileId = mode.value === 'write' ? (profile?.id || '') : ''
    for await (const token of chatStream({
      messages: msgs,
      model: selectedModel.value,
      mode: mode.value,
      search: searchEnabled.value,
      stylePrompt,
      profileId,
    })) {
      chat.appendStream(token)
      await nextTick()
      scrollToBottom()
    }
  } catch (err: any) {
    chat.appendStream(`\n\n> ❌ 错误: ${err.message}`)
  } finally {
    chat.searching = false
    chat.finishStream()
    await nextTick()
    scrollToBottom()
  }
}

function clearChat() {
  chat.clearMessages()
}

function scrollToBottom() {
  if (msgListRef.value) {
    msgListRef.value.scrollTop = msgListRef.value.scrollHeight
  }
}
</script>

<style scoped>
.ai-chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
  border-left: 1px solid var(--el-border-color-light);
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.chat-title {
  font-weight: 600;
  font-size: 14px;
}

.chat-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-light);
  flex-wrap: wrap;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  font-size: 12px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.message {
  margin-bottom: 16px;
}

.message.user {
  text-align: right;
}

.message.user .message-content {
  background: var(--el-color-primary-light-9);
  display: inline-block;
  padding: 8px 12px;
  border-radius: 8px;
  text-align: left;
  max-width: 90%;
}

.message.assistant .message-content {
  padding: 8px 12px;
  line-height: 1.7;
  font-size: 14px;
}

/* 思考过程折叠块 */
.message-content :deep(.think-block) {
  margin: 8px 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  overflow: hidden;
}

.message-content :deep(.think-block summary) {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  user-select: none;
  display: flex;
  align-items: center;
  gap: 4px;
}

.message-content :deep(.think-block summary:hover) {
  background: var(--el-fill-color);
}

.message-content :deep(.think-block[open] summary) {
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.message-content :deep(.think-content) {
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  max-height: 300px;
  overflow-y: auto;
}

.message-content :deep(.think-content p) {
  margin: 4px 0;
}

.message-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.message-content.streaming {
  border-right: 2px solid var(--el-color-primary);
  animation: blink 0.8s step-end infinite;
}

@keyframes blink {
  50% { border-color: transparent; }
}

.chat-input {
  padding: 10px 16px;
  border-top: 1px solid var(--el-border-color-light);
}

.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.mode-hint {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
</style>
