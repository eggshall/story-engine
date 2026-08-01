<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="context-menu-overlay"
      @click="close"
      @contextmenu.prevent="close"
    >
      <div
        class="context-menu"
        :style="{ left: x + 'px', top: y + 'px' }"
        @click.stop
      >
        <div class="menu-header">
          <span class="menu-selected-text">{{ displayText }}</span>
        </div>
        <div class="menu-divider" />

        <div class="menu-item" @click="onAction('polish')">
          <span class="menu-icon">✨</span>
          <div class="menu-label">
            <span class="menu-title">润色</span>
            <span class="menu-desc">优化语法、用词和表达</span>
          </div>
        </div>

        <div class="menu-item" @click="onAction('expand')">
          <span class="menu-icon">📖</span>
          <div class="menu-label">
            <span class="menu-title">扩写</span>
            <span class="menu-desc">在原文基础上丰富细节</span>
          </div>
        </div>

        <div class="menu-item" @click="onAction('summarize')">
          <span class="menu-icon">📌</span>
          <div class="menu-label">
            <span class="menu-title">缩写</span>
            <span class="menu-desc">保留核心内容，精简篇幅</span>
          </div>
        </div>

        <div class="menu-item" @click="onAction('continue')">
          <span class="menu-icon">▶️</span>
          <div class="menu-label">
            <span class="menu-title">续写</span>
            <span class="menu-desc">延续当前文段继续写作</span>
          </div>
        </div>

        <div class="menu-divider" />

        <div class="menu-item" @click="onAction('de-ai')">
          <span class="menu-icon">🧹</span>
          <div class="menu-label">
            <span class="menu-title">去AI味</span>
            <span class="menu-desc">消除生硬表达，让文字更自然</span>
          </div>
        </div>

        <div class="menu-item" @click="onAction('analyze-style')">
          <span class="menu-icon">🔍</span>
          <div class="menu-label">
            <span class="menu-title">风格分析</span>
            <span class="menu-desc">分析节奏、语气和写作风格</span>
          </div>
        </div>

        <!-- 加载状态 -->
        <div v-if="loading" class="menu-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ loadingText }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Loading } from '@element-plus/icons-vue'

const props = defineProps<{
  visible: boolean
  x: number
  y: number
  selectedText: string
  loading: boolean
  loadingAction: string
}>()

const emit = defineEmits<{
  action: [type: string]
  close: []
}>()

const actionLabels: Record<string, string> = {
  polish: '润色中…',
  expand: '扩写中…',
  summarize: '缩写中…',
  continue: '续写中…',
  'de-ai': '去AI味中…',
  'analyze-style': '分析中…',
}

const loadingText = computed(() => actionLabels[props.loadingAction] || '处理中…')

const displayText = computed(() => {
  const text = props.selectedText
  if (text.length <= 30) return text
  return text.slice(0, 12) + '…' + text.slice(-12)
})

function onAction(type: string) {
  emit('action', type)
}

function close() {
  emit('close')
}
</script>

<style scoped>
.context-menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
}

.context-menu {
  position: absolute;
  width: 240px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.15);
  padding: 6px;
  z-index: 10000;
}

.menu-header {
  padding: 8px 10px;
}

.menu-selected-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
  background: var(--el-fill-color-lighter);
  padding: 2px 8px;
  border-radius: 4px;
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-divider {
  height: 1px;
  background: var(--el-border-color-lighter);
  margin: 4px 0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.menu-item:hover {
  background: var(--el-color-primary-light-9);
}

.menu-icon {
  font-size: 16px;
  width: 24px;
  text-align: center;
  flex-shrink: 0;
}

.menu-label {
  flex: 1;
  min-width: 0;
}

.menu-title {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.menu-desc {
  display: block;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 1px;
}

.menu-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px;
  font-size: 12px;
  color: var(--el-color-primary);
}
</style>
