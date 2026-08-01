\n<template>
  <div class="chapter-panel">
    <!-- Header -->
    <div class="panel-header">
      <div class="panel-back" @click="$emit('back')">
        <el-icon><ArrowLeft /></el-icon>
        <span class="back-text">小说列表</span>
      </div>
      <el-button size="small" type="primary" :icon="Plus" @click="addChapter">新建章节</el-button>
    </div>

    <!-- Novel info -->
    <div class="panel-novel-info" v-if="novelStore.currentNovel">
      <div class="novel-icon">{{ novelStore.currentNovel.title.charAt(0) }}</div>
      <div class="novel-detail">
        <div class="novel-name">{{ novelStore.currentNovel.title }}</div>
        <div class="novel-meta">{{ novelStore.currentNovel.chapter_count }}章 · {{ formatWords(novelStore.currentNovel.word_count) }}字</div>
      </div>
    </div>

    <!-- Chapter list -->
    <div class="chapter-list">
      <div class="list-header">
        <span class="list-title">章节列表</span>
        <el-tooltip content="刷新" placement="top">
          <el-button size="small" text :icon="Refresh" @click="refreshNovel" />
        </el-tooltip>
      </div>

      <draggable
        v-if="chapters.length"
        v-model="chapters"
        item-key="chapter_number"
        handle=".drag-handle"
        :animation="200"
        @end="onReorder"
      >
        <template #item="{ element: ch }">
          <div
            :class="['chapter-item', { active: novelStore.currentChapter?.chapter_number === ch.chapter_number }]"
            @click="selectChapter(ch.chapter_number)"
          >
            <el-icon class="drag-handle"><Rank /></el-icon>
            <div class="ch-info">
              <div class="ch-title">{{ ch.title || `第${ch.chapter_number}章` }}</div>
              <div class="ch-meta">
                第{{ ch.chapter_number }}章 · {{ formatWords(ch.word_count || 0) }}字
              </div>
            </div>
            <el-button
              size="small" text :icon="Delete"
              class="ch-delete"
              @click.stop="confirmDelete(ch.chapter_number)"
            />
          </div>
        </template>
      </draggable>

      <div v-else class="chapter-empty">
        <p>还没有章节</p>
        <el-button size="small" @click="addChapter">创建第一章</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ArrowLeft, Plus, Delete, Rank, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useNovelStore } from '../stores/novel'
import api from '../utils/api'
import draggable from 'vuedraggable'

const emit = defineEmits<{ back: []; generate: [] }>()
const novelStore = useNovelStore()

// Use a copy for drag reorder
const chapters = ref<any[]>([])

watch(() => novelStore.currentNovel?.chapters, (val) => {
  chapters.value = val ? [...val] : []
}, { immediate: true })

function formatWords(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toLocaleString()
}

function selectChapter(num: number) {
  novelStore.selectChapter(num)
}

async function addChapter() {
  await novelStore.addChapter()
}

async function refreshNovel() {
  if (novelStore.currentNovel) {
    await novelStore.loadNovel(novelStore.currentNovel.id)
  }
}

async function onReorder() {
  if (!novelStore.currentNovel) return
  const order = chapters.value.map((c: any) => c.chapter_number)
  try {
    await api.post(`/novel/${novelStore.currentNovel.id}/chapters/reorder`, { order })
    await novelStore.loadNovel(novelStore.currentNovel.id)
  } catch { /* ignore */ }
}

function confirmDelete(chapterNumber: number) {
  ElMessageBox.confirm(`确定删除第${chapterNumber}章？`, '确认', {
    confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
  }).then(async () => {
    await novelStore.deleteChapter(chapterNumber)
    ElMessage.success(`已删除第${chapterNumber}章`)
  }).catch(() => {})
}
</script>

<style scoped>
.chapter-panel { display: flex; flex-direction: column; height: 100%; }
.panel-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--el-border-color-light);
}
.panel-back {
  display: flex; align-items: center; gap: 4px;
  cursor: pointer; font-size: 13px; color: var(--el-color-primary);
}
.panel-back:hover { opacity: 0.8; }
.back-text { font-weight: 500; }

.panel-novel-info {
  display: flex; align-items: center; gap: 12px;
  padding: 16px; border-bottom: 1px solid var(--el-border-color-lighter);
}
.novel-icon {
  width: 42px; height: 42px; border-radius: 10px;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 700;
}
.novel-detail { flex: 1; min-width: 0; }
.novel-name { font-weight: 600; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.novel-meta { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 2px; }

.chapter-list { flex: 1; overflow-y: auto; padding: 8px; }
.list-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 4px 8px; margin-bottom: 4px;
}
.list-title { font-size: 12px; font-weight: 600; color: var(--el-text-color-secondary); text-transform: uppercase; letter-spacing: 0.5px; }

.chapter-item {
  display: flex; align-items: center; gap: 6px;
  padding: 10px; margin: 2px 0;
  border-radius: 8px; cursor: pointer;
  transition: all 0.15s;
}
.chapter-item:hover { background: var(--el-fill-color-light); }
.chapter-item.active { background: var(--el-color-primary-light-9); }
.drag-handle { cursor: grab; color: var(--el-text-color-placeholder); font-size: 14px; }
.ch-info { flex: 1; min-width: 0; }
.ch-title { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ch-meta { font-size: 11px; color: var(--el-text-color-secondary); }
.ch-delete { opacity: 0; transition: opacity 0.15s; }
.chapter-item:hover .ch-delete { opacity: 1; }
.chapter-empty { text-align: center; padding: 40px 16px; color: var(--el-text-color-secondary); font-size: 13px; }
</style>
