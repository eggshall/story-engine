<template>
  <div class="style-panel">
    <div class="style-panel-header">
      <h3>🎨 文风管理</h3>
      <el-button size="small" :icon="Refresh" text @click="refresh" :loading="loading" />
    </div>

    <!-- 已选文风 -->
    <div v-if="styleStore.selectedProfile" class="current-style">
      <div class="current-style-header">
        <span class="current-style-label">当前文风</span>
        <el-button size="small" text :icon="Close" @click="styleStore.clearSelection()"
          :disabled="styleStore.analyzing">
          取消
        </el-button>
      </div>
      <div class="style-card selected">
        <div class="style-name">{{ styleStore.selectedProfile.name }}</div>
        <div v-if="styleStore.selectedProfile.author" class="style-meta">
          作者: {{ styleStore.selectedProfile.author }}
          <span v-if="styleStore.selectedProfile.source_work">
            · 《{{ styleStore.selectedProfile.source_work }}》
          </span>
        </div>
        <div v-if="styleStore.selectedProfile.style_prompt" class="style-prompt-text">
          {{ styleStore.selectedProfile.style_prompt }}
        </div>
        <div class="style-tags" v-if="styleStore.selectedProfile.tags?.length">
          <el-tag v-for="tag in styleStore.selectedProfile.tags" :key="tag" size="small" type="info">{{
            tag }}</el-tag>
        </div>
      </div>
    </div>

    <!-- 搜索/筛选 -->
    <div class="style-toolbar">
      <el-input v-model="searchQuery" placeholder="搜索文风…" size="small" clearable
        @input="onSearch" :prefix-icon="Search" />
      <el-select v-model="genreFilter" placeholder="题材" size="small" clearable
        @change="onGenreChange" style="width:100px">
        <el-option v-for="g in styleStore.genres" :key="g" :label="g" :value="g" />
      </el-select>
    </div>

    <!-- 文风列表 -->
    <div v-if="loading" class="style-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
    </div>
    <div v-else-if="filteredProfiles.length === 0" class="style-empty">
      <p>暂无文风画像</p>
      <p class="style-empty-hint">选中一段文本 → 点击「分析文风」自动创建</p>
    </div>
    <div v-else class="style-list">
      <div v-for="profile in filteredProfiles" :key="profile.id"
        class="style-card"
        :class="{ 'is-selected': profile.id === styleStore.selectedProfileId }"
        @click="styleStore.selectProfile(profile.id)">
        <div class="style-name">{{ profile.name }}</div>
        <div v-if="profile.author" class="style-meta">
          {{ profile.author }}
          <span v-if="profile.source_work">· 《{{ profile.source_work }}》</span>
        </div>
        <div v-if="profile.style_prompt" class="style-prompt-text">
          {{ profile.style_prompt.slice(0, 60) }}{{ profile.style_prompt.length > 60 ? '…' : '' }}
        </div>
        <div class="style-card-footer">
          <el-tag v-if="profile.genre" size="small" type="warning">{{ profile.genre }}</el-tag>
          <el-button size="small" text :icon="Delete" @click.stop="onDelete(profile.id)" />
        </div>
      </div>
    </div>

    <!-- 分析按钮 -->
    <div class="style-actions">
      <el-button size="small" type="primary" :icon="MagicStick" :loading="styleStore.analyzing"
        :disabled="!currentText" @click="onAnalyze">
        分析当前文本
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Close, Search, Loading, Delete, MagicStick } from '@element-plus/icons-vue'
import { useStyleStore } from '../stores/style'

const props = defineProps<{
  currentText: string
}>()

const emit = defineEmits<{
  (e: 'style-selected', profileId: string): void
  (e: 'analysis-start'): void
  (e: 'analysis-done', result: { features: any; style_prompt: string }): void
}>()

const styleStore = useStyleStore()

const searchQuery = ref('')
const genreFilter = ref('')
const loading = ref(false)

const filteredProfiles = computed(() => {
  let list = styleStore.profiles
  if (genreFilter.value) {
    list = list.filter(p => p.genre === genreFilter.value)
  }
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(p =>
      p.name.toLowerCase().includes(q) ||
      p.author.toLowerCase().includes(q) ||
      p.source_work.toLowerCase().includes(q)
    )
  }
  return list
})

onMounted(async () => {
  loading.value = true
  await styleStore.loadProfiles()
  loading.value = false
})

async function refresh() {
  loading.value = true
  await styleStore.loadProfiles()
  loading.value = false
}

function onSearch() {
  // reactive filtering is already handled by computed
}

function onGenreChange(val: string) {
  genreFilter.value = val
}

async function onAnalyze() {
  if (!props.currentText || props.currentText.length < 50) {
    ElMessage.warning('请至少选择 50 字以上的文本来分析')
    return
  }
  emit('analysis-start')
  try {
    const result = await styleStore.analyzeText(props.currentText)
    emit('analysis-done', {
      features: result.features,
      style_prompt: result.style_prompt,
    })
    ElMessage.success('文风分析完成')
  } catch (e: any) {
    ElMessage.error('分析失败: ' + (e?.response?.data?.detail || e.message))
  }
}

async function onDelete(id: string) {
  try {
    await ElMessageBox.confirm('确定删除此文风画像？', '确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await styleStore.deleteProfile(id)
    ElMessage.success('已删除')
  } catch {
    // 取消
  }
}
</script>

<style scoped>
.style-panel {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow-y: auto;
}

.style-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.style-panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.current-style {
  background: #ecf5ff;
  border-radius: 6px;
  padding: 8px;
}

.current-style-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.current-style-label {
  font-size: 12px;
  color: #409eff;
  font-weight: 600;
}

.style-toolbar {
  display: flex;
  gap: 6px;
}

.style-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.style-card {
  padding: 8px 10px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.style-card:hover {
  border-color: #409eff;
  background: #ecf5ff;
}

.style-card.is-selected,
.style-card.selected {
  border-color: #409eff;
  background: #d9ecff;
}

.style-name {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.style-meta {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
}

.style-prompt-text {
  font-size: 11px;
  color: #606266;
  margin-top: 4px;
  line-height: 1.4;
}

.style-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.style-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
}

.style-loading,
.style-empty {
  text-align: center;
  padding: 20px;
  color: #909399;
}

.style-empty-hint {
  font-size: 12px;
  margin-top: 4px;
}

.style-actions {
  padding-top: 8px;
  border-top: 1px solid #ebeef5;
}
</style>
