<template>
  <div class="progress-panel">
    <!-- 章节进度 -->
    <div class="progress-section">
      <div class="section-title">📖 章节进度</div>
      <div class="chapter-progress-bar">
        <el-progress
          :percentage="chapterPercentage"
          :stroke-width="16"
          :text-inside="true"
          :format="chapterProgressFormat"
          :color="chapterPercentage >= 80 ? '#67C23A' : chapterPercentage >= 40 ? '#E6A23C' : '#409EFF'"
        />
      </div>
      <div class="chapter-input-row">
        <span class="label">已完成</span>
        <span class="value-num">{{ completedChapters }}</span>
        <span class="label">/ 计划</span>
        <el-input-number
          v-model="plannedChapters"
          :min="0"
          :max="999"
          size="small"
          class="planned-input"
          controls-position="right"
        />
        <span class="label">章</span>
      </div>
    </div>

    <!-- 字数统计 -->
    <div class="progress-section">
      <div class="section-title">✍️ 字数统计</div>
      <div class="word-stats-grid">
        <div class="word-stat-card accent">
          <div class="stat-number">{{ formatWords(totalWords) }}</div>
          <div class="stat-subtitle">总字数</div>
        </div>
        <div class="word-stat-card">
          <div class="stat-number">{{ formatWords(wordStats.today) }}</div>
          <div class="stat-subtitle">今日</div>
        </div>
        <div class="word-stat-card">
          <div class="stat-number">{{ formatWords(wordStats.week) }}</div>
          <div class="stat-subtitle">本周</div>
        </div>
        <div class="word-stat-card">
          <div class="stat-number">{{ formatWords(wordStats.month) }}</div>
          <div class="stat-subtitle">本月</div>
        </div>
      </div>
    </div>

    <!-- 写作阶段 -->
    <div class="progress-section">
      <div class="section-title">🎯 当前阶段</div>
      <el-radio-group v-model="writingStage" size="small" class="stage-group">
        <el-radio-button value="大纲">
          <el-icon><List /></el-icon> 大纲
        </el-radio-button>
        <el-radio-button value="写作">
          <el-icon><Edit /></el-icon> 写作
        </el-radio-button>
        <el-radio-button value="精修">
          <el-icon><Finished /></el-icon> 精修
        </el-radio-button>
      </el-radio-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { List, Edit, Finished } from '@element-plus/icons-vue'
import { useNovelStore } from '../stores/novel'

const props = defineProps<{
  novelId: string | null
}>()

const novelStore = useNovelStore()

// ── 章节进度 ──
const plannedChapters = ref(10)
const STORAGE_KEY_PLANNED = `novel-planned-${props.novelId || 'default'}`

// 从 localStorage 加载计划章节数
const savedPlanned = localStorage.getItem(STORAGE_KEY_PLANNED)
if (savedPlanned) plannedChapters.value = parseInt(savedPlanned, 10)

watch(plannedChapters, (val) => {
  if (props.novelId) {
    localStorage.setItem(STORAGE_KEY_PLANNED, String(val))
  }
}, { immediate: true })

watch(() => props.novelId, (newId) => {
  if (newId) {
    const saved = localStorage.getItem(`novel-planned-${newId}`)
    if (saved) plannedChapters.value = parseInt(saved, 10)
    else plannedChapters.value = 10
  }
})

const completedChapters = computed(() => {
  if (!novelStore.currentNovel?.chapters) return 0
  return novelStore.currentNovel.chapters.length
})

const chapterPercentage = computed(() => {
  if (plannedChapters.value <= 0) return 0
  return Math.min(100, Math.round((completedChapters.value / plannedChapters.value) * 100))
})

function chapterProgressFormat(pct: number) {
  return `${completedChapters.value}/${plannedChapters.value} 章 (${pct}%)`
}

// ── 字数统计 ──
const totalWords = computed(() => {
  return novelStore.currentNovel?.word_count || 0
})

interface WordStats {
  today: number
  week: number
  month: number
}

function loadWordStats(): WordStats {
  try {
    const raw = localStorage.getItem('novel-word-stats')
    if (!raw) return { today: 0, week: 0, month: 0 }
    const data = JSON.parse(raw)
    const now = new Date()
    const today = now.toISOString().slice(0, 10)

    // 清理过期数据 — 只保留最近30天
    const dayKeys = Object.keys(data).filter((k) => k.match(/^\d{4}-\d{2}-\d{2}$/))
    const todayStats = data[today] || 0

    // 本周统计
    const dayOfWeek = now.getDay()
    const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    const monday = new Date(now)
    monday.setDate(now.getDate() + mondayOffset)
    const mondayStr = monday.toISOString().slice(0, 10)

    let weekTotal = 0
    let monthTotal = 0
    const currentMonth = today.slice(0, 7)

    for (const key of dayKeys) {
      if (key >= mondayStr && key <= today) {
        weekTotal += data[key] || 0
      }
      if (key.slice(0, 7) === currentMonth) {
        monthTotal += data[key] || 0
      }
    }

    return { today: todayStats, week: weekTotal, month: monthTotal }
  } catch {
    return { today: 0, week: 0, month: 0 }
  }
}

const wordStats = ref<WordStats>(loadWordStats())

// 每次保存章节时刷新字数统计 (由外部调用)
function refreshStats() {
  wordStats.value = loadWordStats()
}

// 记录当天字数
function recordTodayWords(count: number) {
  try {
    const raw = localStorage.getItem('novel-word-stats')
    const data = raw ? JSON.parse(raw) : {}
    const today = new Date().toISOString().slice(0, 10)
    data[today] = (data[today] || 0) + count
    localStorage.setItem('novel-word-stats', JSON.stringify(data))
    refreshStats()
  } catch { /* ignore */ }
}

defineExpose({ refreshStats, recordTodayWords })

// ── 写作阶段 ──
const writingStage = ref('写作')
const STORAGE_KEY_STAGE = `novel-stage-${props.novelId || 'default'}`

const savedStage = localStorage.getItem(STORAGE_KEY_STAGE)
if (savedStage) writingStage.value = savedStage

watch(writingStage, (val) => {
  if (props.novelId) {
    localStorage.setItem(STORAGE_KEY_STAGE, val)
  }
}, { immediate: true })

watch(() => props.novelId, (newId) => {
  if (newId) {
    const saved = localStorage.getItem(`novel-stage-${newId}`)
    if (saved) writingStage.value = saved
    else writingStage.value = '写作'
  }
})

// ── 工具 ──
function formatWords(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return n.toLocaleString()
}
</script>

<style scoped>
.progress-panel {
  min-width: 320px;
  max-width: 400px;
}

.progress-section {
  margin-bottom: 16px;
}

.progress-section:last-child {
  margin-bottom: 0;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}

/* 章节进度 */
.chapter-progress-bar {
  margin-bottom: 8px;
}

.chapter-input-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.chapter-input-row .label {
  white-space: nowrap;
}

.value-num {
  font-weight: 700;
  color: var(--el-color-primary);
  font-size: 15px;
}

.planned-input {
  width: 80px;
}

/* 字数统计 */
.word-stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.word-stat-card {
  text-align: center;
  padding: 12px 8px;
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.word-stat-card.accent {
  background: linear-gradient(135deg, var(--el-color-primary-light-8), var(--el-color-primary-light-9));
}

.stat-number {
  font-size: 16px;
  font-weight: 700;
  color: var(--el-color-primary);
  line-height: 1.3;
}

.word-stat-card.accent .stat-number {
  font-size: 20px;
}

.stat-subtitle {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

/* 写作阶段 */
.stage-group {
  display: flex;
  width: 100%;
}

.stage-group .el-radio-button {
  flex: 1;
}

.stage-group .el-radio-button :deep(.el-radio-button__inner) {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}
</style>
