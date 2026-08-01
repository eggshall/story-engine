
<template>
  <div class="settings-view">
    <h3>设置</h3>

    <el-card
      v-for="model in settings.models"
      :key="model.name"
      class="settings-card"
      shadow="never"
    >
      <template #header>
        <div class="model-header">
          <div class="model-title">
            <span class="model-name">{{ model.name }}</span>
            <span class="model-badge" :class="model.provider">{{ model.provider }}</span>
            <span v-if="!editing[model.name]" class="model-id">{{ model.model_id }}</span>
          </div>
          <div class="model-header-actions">
            <el-switch
              :model-value="model.enabled"
              @change="(val: boolean) => toggleEnabled(model.name, val)"
              size="small"
            />
            <el-button
              text
              :icon="editing[model.name] ? 'ArrowUpBold' : 'ArrowDownBold'"
              @click="toggleEdit(model.name)"
              size="small"
            />
          </div>
        </div>
      </template>

      <div v-if="editing[model.name]" class="model-edit-form">
        <el-form label-position="top" size="small">
          <el-form-item label="Base URL">
            <el-input
              v-model="editForm[model.name].base_url"
              placeholder="https://api.example.com/v1"
              clearable
            />
          </el-form-item>
          <el-form-item label="API Key">
            <el-input
              v-model="editForm[model.name].api_key"
              type="password"
              show-password
              :placeholder="model.api_key || '未配置'"
              clearable
            />
          </el-form-item>
          <el-form-item label="温度 (Temperature)">
            <el-slider
              v-model="editForm[model.name].temperature"
              :min="0"
              :max="2"
              :step="0.1"
              show-input
              style="width: 200px"
            />
          </el-form-item>
          <el-form-item label="最大 Token">
            <el-input-number
              v-model="editForm[model.name].max_tokens"
              :min="512"
              :max="65536"
              :step="512"
            />
          </el-form-item>
          <div class="form-actions">
            <el-button
              type="primary"
              size="small"
              @click="saveModel(model.name)"
              :loading="saving[model.name]"
            >
              保存
            </el-button>
            <el-button
              size="small"
              @click="testConnection(model.name)"
              :loading="testing[model.name]"
            >
              测试连接
            </el-button>
            <span
              v-if="testResults[model.name]"
              class="test-result"
              :class="testResults[model.name].status"
            >
              {{ testResults[model.name].message }}
            </span>
          </div>
        </el-form>
      </div>

      <div v-else class="model-summary">
        <span class="summary-row">
          <span class="label">地址：</span>{{ model.base_url || '默认' }}
        </span>
        <span class="summary-row">
          <span class="label">温度：</span>{{ model.temperature }}
        </span>
        <span class="summary-row">
          <span class="label">最大 Token：</span>{{ model.max_tokens }}
        </span>
      </div>
    </el-card>

    <el-card class="settings-card" shadow="never">
      <template #header>
        <span>写作参数</span>
      </template>
      <el-form label-position="top" style="max-width: 400px">
        <el-form-item label="默认模型">
          <el-select v-model="settings.currentModel" style="width: 100%">
            <el-option
              v-for="m in settings.models"
              :key="m.model_id"
              :label="m.name"
              :value="m.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="温度 (Temperature)">
          <el-slider v-model="temperature" :min="0" :max="2" :step="0.1" show-input />
        </el-form-item>
        <el-form-item label="最大 Token">
          <el-input-number v-model="maxTokens" :min="512" :max="16384" :step="512" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="small" @click="saveWritingParams" :loading="savingWritingParams">
            保存写作参数
          </el-button>
          <span v-if="writingParamsSaved" class="test-result ok" style="font-size: 12px; margin-left: 8px">
            已保存
          </span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="settings-card" shadow="never">
      <template #header>
        <span>项目导出</span>
      </template>
      <div style="font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 12px;">
        将小说项目导出为 JSON 文件，或从 JSON 文件恢复。
      </div>
      <el-form label-position="top" style="max-width: 100%">
        <el-form-item label="选择小说">
          <el-select v-model="selectedNovelId" style="width: 100%" placeholder="请选择要导出的小说">
            <el-option
              v-for="n in novels"
              :key="n.id"
              :label="n.title"
              :value="n.id"
            />
          </el-select>
        </el-form-item>
        <div class="form-actions" style="margin-bottom: 12px">
          <el-button
            type="primary"
            size="small"
            :disabled="!selectedNovelId || exporting"
            :loading="exporting"
            @click="handleExportJson"
          >
            导出 JSON
          </el-button>
          <span v-if="exportPath" class="test-result ok" style="font-size: 12px">
            已导出: {{ exportPath }}
          </span>
        </div>
      </el-form>

      <template v-if="novels.length > 0">
        <el-divider />
        <div style="font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 8px;">
          <b>导入项目</b> — 粘贴 JSON 数据或选择文件内容
        </div>
        <el-input
          v-model="importJsonData"
          type="textarea"
          :rows="4"
          placeholder='粘贴 JSON 数据，例如: {"title":"我的小说","chapters":[]}'
          style="margin-bottom: 8px"
        />
        <div class="form-actions">
          <el-button
            type="warning"
            size="small"
            :disabled="!importJsonData.trim()"
            :loading="importing"
            @click="handleImportJson"
          >
            导入
          </el-button>
          <span v-if="importResult" class="test-result ok" style="font-size: 12px">
            已导入: {{ importResult }}
          </span>
        </div>
      </template>
    </el-card>

    <el-card class="settings-card" shadow="never">
      <template #header>
        <span>项目信息</span>
      </template>
      <div style="font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 12px;">
        编辑已有小说的元信息（标题/作者/类型/简介）。
      </div>
      <el-form label-position="top" style="max-width: 100%">
        <el-form-item label="选择小说">
          <el-select v-model="metaNovelId" style="width: 100%" placeholder="请选择要编辑的小说" @change="loadNovelMeta">
            <el-option
              v-for="n in novels"
              :key="n.id"
              :label="n.title"
              :value="n.id"
            />
          </el-select>
        </el-form-item>
        <template v-if="metaNovelId">
          <el-form-item label="标题">
            <el-input v-model="metaTitle" />
          </el-form-item>
          <el-form-item label="作者">
            <el-input v-model="metaAuthor" />
          </el-form-item>
          <el-form-item label="类型">
            <el-input v-model="metaGenre" placeholder="奇幻/科幻/言情/..." />
          </el-form-item>
          <el-form-item label="简介">
            <el-input v-model="metaSynopsis" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="small" @click="saveNovelMeta" :loading="savingMeta">
              保存元信息
            </el-button>
            <span v-if="metaSaved" class="test-result ok" style="font-size: 12px; margin-left: 8px">
              已保存
            </span>
          </el-form-item>
        </template>
      </el-form>
    </el-card>

    <el-card class="settings-card" shadow="never">
      <template #header>
        <span>关于</span>
      </template>
      <p style="color: var(--el-text-color-secondary); line-height: 1.8">
        故事引擎 v0.5.0 · AI 小说生成系统<br>
        后端：FastAPI + Python 3.12<br>
        前端：Vue 3 + Element Plus + TypeScript<br>
        模型：DeepSeek v4 Pro / Qwen3.5-9B (本地)
      </p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDownBold, ArrowUpBold } from '@element-plus/icons-vue'
import { useSettingsStore } from '../stores/settings'
import { fetchNovels, exportJson, importJson, fetchSettings, saveSettings } from '../utils/api'

const settings = useSettingsStore()
const temperature = ref(0.7)
const maxTokens = ref(4096)
const savingWritingParams = ref(false)
const writingParamsSaved = ref(false)

// Per-model editing state
const editing = reactive<Record<string, boolean>>({})
const saving = reactive<Record<string, boolean>>({})
const testing = reactive<Record<string, boolean>>({})
const testResults = reactive<Record<string, { status: string; message: string }>>({})
const editForm = reactive<Record<string, {
  base_url: string
  api_key: string
  temperature: number
  max_tokens: number
}>>({})

function toggleEdit(name: string) {
  editing[name] = !editing[name]
  if (editing[name]) {
    const model = settings.models.find(m => m.name === name)
    if (model) {
      editForm[name] = {
        base_url: model.base_url || '',
        api_key: '',
        temperature: model.temperature,
        max_tokens: model.max_tokens,
      }
    }
  }
}

async function toggleEnabled(name: string, val: boolean) {
  const ok = await settings.updateModel(name, { enabled: val })
  if (ok) {
    ElMessage.success(val ? '模型已启用' : '模型已禁用')
  }
}

async function saveModel(name: string) {
  const form = editForm[name]
  if (!form) return
  saving[name] = true
  try {
    const config: Record<string, any> = {
      temperature: form.temperature,
      max_tokens: form.max_tokens,
    }
    if (form.base_url) config.base_url = form.base_url
    if (form.api_key) config.api_key = form.api_key

    const ok = await settings.updateModel(name, config)
    if (ok) {
      ElMessage.success('配置已保存')
      // Refresh edit form with updated values (masked key from backend)
      const model = settings.models.find(m => m.name === name)
      if (model) {
        editForm[name] = {
          base_url: model.base_url || '',
          api_key: '',
          temperature: model.temperature,
          max_tokens: model.max_tokens,
        }
      }
    } else {
      ElMessage.error('保存失败')
    }
  } finally {
    saving[name] = false
  }
}

async function testConnection(name: string) {
  testing[name] = true
  testResults[name] = { status: 'testing', message: '测试中…' }
  try {
    const result = await settings.testConnection(name)
    testResults[name] = result
    if (result.status === 'ok') {
      ElMessage.success(result.message)
    } else {
      ElMessage.warning(result.message)
    }
  } catch {
    testResults[name] = { status: 'error', message: '连接测试失败' }
    ElMessage.error('连接测试失败')
  } finally {
    testing[name] = false
  }
}

// ── 导出/导入 ──────────────────────────────────
const novels = ref<{ id: string; title: string }[]>([])
const selectedNovelId = ref('')
const exporting = ref(false)
const exportPath = ref('')
const importJsonData = ref('')
const importing = ref(false)
const importResult = ref('')

// ── 元信息编辑 ──────────────────────────────────
const metaNovelId = ref('')
const metaTitle = ref('')
const metaAuthor = ref('')
const metaGenre = ref('')
const metaSynopsis = ref('')
const savingMeta = ref(false)
const metaSaved = ref(false)
async function loadNovelMeta() {
  if (!metaNovelId.value) return
  try {
    const { fetchNovel } = await import('../utils/api')
    const novel = await fetchNovel(metaNovelId.value)
    metaTitle.value = novel.title
    metaAuthor.value = novel.author
    metaGenre.value = novel.genre
    metaSynopsis.value = novel.synopsis
    metaSaved.value = false
  } catch { /* 静默 */ }
}
async function saveNovelMeta() {
  if (!metaNovelId.value) return
  savingMeta.value = true
  metaSaved.value = false
  try {
    const api = (await import('../utils/api')).default
    await api.post(`/novel/${metaNovelId.value}/update`, {
      title: metaTitle.value,
      author: metaAuthor.value,
      genre: metaGenre.value,
      synopsis: metaSynopsis.value,
    })
    metaSaved.value = true
    ElMessage.success('元信息已保存')
    // 刷新小说列表
    await loadNovels()
  } catch (err: any) {
    ElMessage.error(`保存失败: ${err.message}`)
  } finally {
    savingMeta.value = false
  }
}

async function loadNovels() {
  try {
    novels.value = await fetchNovels()
  } catch { /* 静默 */ }
}

async function handleExportJson() {
  if (!selectedNovelId.value) return
  exporting.value = true
  exportPath.value = ''
  try {
    const result = await exportJson({ novel_id: selectedNovelId.value })
    exportPath.value = result.path
    ElMessage.success(`JSON 导出成功`)
  } catch (err: any) {
    ElMessage.error(`导出失败: ${err.message}`)
  } finally {
    exporting.value = false
  }
}

async function handleImportJson() {
  if (!importJsonData.value.trim()) return
  importing.value = true
  importResult.value = ''
  try {
    const result = await importJson({ json_data: importJsonData.value, force: true })
    importResult.value = `${result.title} (${result.chapter_count} 章)`
    ElMessage.success(`导入成功: ${result.title}`)
    // 刷新小说列表
    await loadNovels()
  } catch (err: any) {
    ElMessage.error(`导入失败: ${err.message}`)
  } finally {
    importing.value = false
  }
}

// ── 写作参数持久化 ──────────────────────────

async function loadSettings() {
  try {
    const s = await fetchSettings()
    temperature.value = s.temperature
    maxTokens.value = s.max_tokens
    settings.currentModel = s.default_model
  } catch { /* 默认值已经设置 */ }
}

async function saveWritingParams() {
  savingWritingParams.value = true
  writingParamsSaved.value = false
  try {
    await saveSettings({
      temperature: temperature.value,
      max_tokens: maxTokens.value,
      default_model: settings.currentModel,
    })
    writingParamsSaved.value = true
    ElMessage.success('写作参数已保存')
  } catch (err: any) {
    ElMessage.error(`保存失败: ${err.message}`)
  } finally {
    savingWritingParams.value = false
  }
}

onMounted(() => {
  if (settings.models.length === 0) {
    settings.loadModels()
  }
  loadSettings()
  loadNovels()
})
</script>

<style scoped>
.settings-view {
  max-width: 700px;
}
.settings-view h3 {
  margin: 0 0 20px;
  font-size: 18px;
}
.settings-card {
  margin-bottom: 16px;
}

.model-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.model-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.model-name {
  font-weight: 600;
  font-size: 14px;
}
.model-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--el-color-info-light-9);
  color: var(--el-text-color-secondary);
}
.model-badge.deepseek {
  background: #e8f4fd;
  color: #096dd9;
}
.model-badge.local {
  background: #f6ffed;
  color: #52c41a;
}
.model-badge.anthropic {
  background: #fff7e6;
  color: #d48806;
}
.model-id {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.model-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-summary {
  display: flex;
  gap: 20px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.summary-row .label {
  color: var(--el-text-color-placeholder);
}

.model-edit-form {
  padding-top: 8px;
}
.form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.test-result {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 3px;
}
.test-result.ok {
  background: #f6ffed;
  color: #52c41a;
}
.test-result.error {
  background: #fff2f0;
  color: #ff4d4f;
}
.test-result.testing {
  color: var(--el-text-color-placeholder);
}
</style>
