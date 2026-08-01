<template>
  <div class="research-view">
    <div class="view-header">
      <h3>资料检索</h3>
    </div>

    <div class="research-layout">
      <!-- Main area -->
      <div class="research-main">
        <!-- Search bar -->
        <div class="search-bar">
          <el-input
            v-model="query"
            placeholder="输入搜索关键词，如：中世纪城堡建筑风格"
            size="large"
            clearable
            @keyup.enter="doSearch"
          />
          <el-button
            type="primary"
            size="large"
            :loading="searching"
            @click="doSearch"
          >
            搜索
          </el-button>
        </div>

        <!-- Save to lorebook option -->
        <div class="search-options">
          <el-checkbox v-model="saveToLorebook">保存结果到设定集 / 知识库</el-checkbox>
        </div>

        <!-- Loading skeleton -->
        <div v-if="searching" class="searching-indicator">
          <div class="loading-text">正在检索资料...</div>
        </div>

        <!-- Results area -->
        <div v-if="results && results.sources && results.sources.length > 0" class="results-area" :class="{ 'is-loading': searching }">
          <el-divider />

          <!-- Source cards -->
          <div class="sources-grid">
            <el-card
              v-for="(source, idx) in results.sources"
              :key="idx"
              class="source-card"
              shadow="hover"
            >
              <div class="source-header">
                <a
                  :href="source.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="source-title"
                >
                  {{ source.title }}
                </a>
                <el-tag size="small" :type="sourceTagType(source.source)">
                  {{ source.source }}
                </el-tag>
              </div>
              <div class="source-snippet">{{ source.snippet }}</div>
              <div v-if="source.snippet" class="source-footer">
                <el-checkbox
                  :model-value="selectedSources.has(idx)"
                  @update:model-value="(val: boolean) => toggleSource(idx, val)"
                >
                  存入选定条目
                </el-checkbox>
              </div>
            </el-card>
          </div>

          <!-- Summary section -->
          <div v-if="results.summary" class="summary-section">
            <el-collapse>
              <el-collapse-item title="📄 提取的页面内容摘要" name="summary">
                <div class="summary-content">{{ results.summary }}</div>
              </el-collapse-item>
            </el-collapse>
          </div>

          <div v-if="results.saved_to" class="save-info">
            <el-tag type="success">已保存到: {{ results.saved_to }}</el-tag>
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="!searching && (!results || !results.sources || results.sources.length === 0)" class="empty-state">
          <div class="empty-text">输入关键词开始搜索互联网资料</div>
          <div class="empty-hint">支持搜索：历史事件、文化风俗、科学技术、地理信息等</div>
        </div>
      </div>

      <!-- History sidebar -->
      <div class="research-history">
        <div class="history-header">
          <h4>搜索历史</h4>
        </div>
        <div v-if="history.length === 0" class="history-empty">
          暂无搜索记录
        </div>
        <el-timeline v-else>
          <el-timeline-item
            v-for="item in history"
            :key="item.query + item.timestamp"
            :timestamp="item.timestamp"
            placement="top"
          >
            <div class="history-item" @click="loadHistory(item.query)">
              {{ item.query }}
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { research } from '../utils/api'
import api from '../utils/api'

interface Source {
  title: string
  url: string
  snippet: string
  source: string
}

interface ResearchResult {
  query: string
  summary: string
  sources: Source[]
  saved_to: string
}

interface HistoryItem {
  query: string
  timestamp: string
  result_count: number
}

const query = ref('')
const searching = ref(false)
const results = ref<ResearchResult | null>(null)
const saveToLorebook = ref(false)
const history = ref<HistoryItem[]>([])
const selectedSources = ref(new Set<number>())

onMounted(() => {
  fetchHistory()
})

function sourceTagType(source: string): '' | 'success' | 'info' | 'warning' | 'danger' {
  const types: Record<string, '' | 'success' | 'info' | 'warning' | 'danger'> = {
    bing: '',
    so: 'success',
    sogou: 'warning',
  }
  return types[source] || 'info'
}

function toggleSource(idx: number, checked: boolean) {
  if (checked) {
    selectedSources.value.add(idx)
  } else {
    selectedSources.value.delete(idx)
  }
}

async function doSearch() {
  const q = query.value.trim()
  if (!q) {
    ElMessage.warning('请输入搜索关键词')
    return
  }

  searching.value = true
  results.value = null

  try {
    const data = await research({
      query: q,
      save_to_lore: saveToLorebook.value,
    })
    results.value = data
    // Refresh history
    fetchHistory()
  } catch (err: any) {
    ElMessage.error(err?.message || '搜索失败，请稍后重试')
  } finally {
    searching.value = false
  }
}

async function fetchHistory() {
  try {
    const res = await api.get('/research/')
    const data = res.data?.data || res.data || []
    history.value = Array.isArray(data) ? data : []
  } catch {
    // Silently fail — history is non-critical
  }
}

function loadHistory(pastQuery: string) {
  query.value = pastQuery
  doSearch()
}
</script>

<style scoped>
.research-view {
  padding: 0;
}

.view-header {
  margin-bottom: 20px;
}

.view-header h3 {
  margin: 0;
  font-size: 18px;
}

.research-layout {
  display: flex;
  gap: 24px;
}

.research-main {
  flex: 1;
  min-width: 0;
}

.search-bar {
  display: flex;
  gap: 12px;
}

.search-bar .el-input {
  flex: 1;
}

.search-options {
  margin-top: 10px;
}

.searching-indicator {
  text-align: center;
  padding: 40px 0;
}

.loading-text {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.results-area {
  margin-top: 16px;
}

.sources-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.source-card {
  border: 1px solid var(--el-border-color-light);
}

.source-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.source-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--el-color-primary);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 70%;
}

.source-title:hover {
  text-decoration: underline;
}

.source-snippet {
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.source-footer {
  margin-top: 8px;
}

.summary-section {
  margin-top: 16px;
}

.summary-content {
  font-size: 14px;
  line-height: 1.8;
  color: var(--el-text-color-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.save-info {
  margin-top: 12px;
}

.empty-state {
  text-align: center;
  padding: 80px 0;
}

.empty-text {
  font-size: 16px;
  color: var(--el-text-color-secondary);
}

.empty-hint {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
  margin-top: 8px;
}

/* History sidebar */
.research-history {
  width: 220px;
  min-width: 220px;
  border-left: 1px solid var(--el-border-color-light);
  padding-left: 16px;
}

.history-header h4 {
  margin: 0 0 12px 0;
  font-size: 15px;
}

.history-empty {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
  padding: 20px 0;
  text-align: center;
}

.history-item {
  cursor: pointer;
  color: var(--el-color-primary);
  font-size: 13px;
  padding: 4px 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-item:hover {
  text-decoration: underline;
}
</style>
