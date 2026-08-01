\n<template>
  <div class="writing-view">
    <!-- 左侧面板：小说列表 / 章节列表 -->
    <div class="writing-sidebar">
      <template v-if="!novelStore.currentNovel">
        <NovelTree :current-id="currentId" @select="onSelectNovel" />
      </template>
      <template v-else>
        <ChapterPanel @back="novelStore.currentNovel = null" @generate="generateChapter" />
      </template>
    </div>

    <!-- 中间：编辑器 -->
    <div class="writing-editor">
      <!-- 顶部栏 -->
      <div class="editor-topbar">
        <div class="topbar-left" v-if="novelStore.currentNovel">
          <h2 class="novel-title">{{ novelStore.currentNovel.title }}</h2>
          <span class="novel-tag">{{ novelStore.currentNovel.genre }}</span>
          <span class="novel-stats">
            {{ chapterCount }}章 · {{ formatWords(novelStore.currentNovel.word_count) }}字
          </span>
        </div>
        <div class="topbar-right" v-if="novelStore.currentNovel">
          <el-select v-model="selectedModel" size="small" placeholder="模型" style="width:150px">
            <el-option v-for="m in settings.models" :key="m.name" :label="m.name" :value="m.name" />
          </el-select>
          <el-button size="small" type="primary" :icon="MagicStick" :loading="generating"
            :disabled="!novelStore.currentNovel" @click="generateChapter">
            生成
          </el-button>
          <el-button size="small" :icon="Download" :disabled="!novelStore.currentNovel" @click="exportNovel">
            导出
          </el-button>
          <el-button size="small" :icon="DataAnalysis" @click="showProgress = true">
            进度
          </el-button>
          <el-button size="small" :icon="Brush" :disabled="!novelStore.currentChapter" :loading="aiCleaning"
            @click="cleanAIStyle">
            去AI味
          </el-button>
          <el-button size="small" :icon="WarningFilled" :disabled="!novelStore.currentChapter"
            @click="checkConsistency">
            一致性检查
          </el-button>
          <el-button size="small" :icon="TrendCharts" :disabled="!novelStore.currentChapter"
            @click="analyzeStyle">
            风格分析
          </el-button>
          <el-button size="small" :icon="EditPen" :disabled="!novelStore.currentChapter"
            :type="activeRightPanel === 'style' ? 'primary' : ''"
            @click="toggleRightPanel('style')">
            文风
          </el-button>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!novelStore.currentNovel" class="editor-empty-state">
        <div class="empty-icon">✍️</div>
        <h3>选择一部小说开始写作</h3>
        <p class="empty-hint">从左侧列表选择已有小说，或点击 + 创建新作品</p>
      </div>

      <template v-else>
        <!-- 灵魂记忆提示条 -->
        <div v-if="novelMemory && showMemoryBar" class="memory-bar">
        <div class="memory-bar-left">
          <span class="memory-label">🧠 灵魂记忆</span>
          <span v-if="novelMemory.user_notes" class="memory-text" :title="novelMemory.user_notes">
            {{ novelMemory.user_notes.slice(0, 60) }}{{ novelMemory.user_notes.length > 60 ? '…' : '' }}
          </span>
          <span v-else class="memory-text memory-empty">暂无记忆，右击小说 → 灵魂记忆 添加</span>
        </div>
        <div class="memory-bar-right">
          <span v-if="novelMemory.style?.tone" class="memory-tag">{{ novelMemory.style.tone }}</span>
          <span v-if="novelMemory.writing_mode_pref" class="memory-tag">{{ novelMemory.writing_mode_pref }}</span>
          <el-button size="small" text :icon="Close" @click="showMemoryBar = false" />
        </div>
      </div>

      <!-- 编辑器内容 -->
      <div class="editor-area">
        <!-- 无选中章节 -->
        <div v-if="!novelStore.currentChapter" class="editor-chapter-empty">
          <p>← 从左侧选择章节开始编辑，或点击「新建章节」</p>
        </div>

        <!-- 有选中章节 -->
        <template v-else>
          <div class="chapter-title-bar">
            <el-input v-model="novelStore.currentChapter.title" class="chapter-title-input"
              placeholder="章节标题" maxlength="60" size="large" />
            <span class="word-counter">{{ contentLength }} 字</span>
          </div>

          <el-tabs v-model="editorMode" class="editor-tabs">
            <el-tab-pane label="✏️ 编辑" name="edit">
              <div class="editor-wrapper" @contextmenu.prevent="onEditorContextMenu">
                <el-input
                  v-model="novelStore.currentChapter.content"
                  type="textarea"
                  :rows="22"
                  class="chapter-editor"
                  placeholder="开始写作…"
                  resize="vertical"
                  ref="editorRef"
                />
              </div>
            </el-tab-pane>
            <el-tab-pane label="👁️ 预览" name="preview">
              <div class="preview-content editor-content" v-html="renderPreview" />
            </el-tab-pane>
            <el-tab-pane label="📊 分析" name="analyze">
              <div class="analysis-panel">
                <div class="stat-grid">
                  <div class="stat-card"><div class="stat-num">{{ contentLength }}</div><div class="stat-label">字数</div></div>
                  <div class="stat-card"><div class="stat-num">{{ paragraphCount }}</div><div class="stat-label">段落</div></div>
                  <div class="stat-card"><div class="stat-num">{{ sentenceCount }}</div><div class="stat-label">句子</div></div>
                  <div class="stat-card"><div class="stat-num">{{ dialogueCount }}</div><div class="stat-label">对话</div></div>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>

          <div class="editor-footer">
            <span class="save-status" v-if="novelStore.saving">
              <el-icon class="is-loading"><Loading /></el-icon> 保存中…
            </span>
            <span v-else class="save-status save-ok">💾 已自动保存</span>
            <div class="footer-actions">
              <el-button size="small" :icon="Refresh" @click="loadCurrentNovel">刷新</el-button>
              <el-button size="small" type="primary" :icon="Upload" :loading="novelStore.saving"
                @click="saveChapter">保存章节</el-button>
            </div>
          </div>
        </template>
      </div>
      </template>
    </div>

    <!-- 右侧：AI 对话面板 / 文风面板 -->
    <div class="writing-chat">
      <div class="right-panel-tabs">
        <el-radio-group v-model="activeRightPanel" size="small">
          <el-radio-button value="chat">💬 AI</el-radio-button>
          <el-radio-button value="style">🎨 文风</el-radio-button>
        </el-radio-group>
      </div>
      <AiChatPanel v-show="activeRightPanel === 'chat'" />
      <StylePanel
        v-show="activeRightPanel === 'style'"
        :current-text="selectedTextForAnalysis"
        @style-selected="onStyleSelected"
        @analysis-start="onAnalysisStart"
        @analysis-done="onAnalysisDone"
      />
    </div>

    <!-- 写作进度弹窗 -->
    <el-dialog v-model="showProgress" title="📊 写作进度" width="420px" :close-on-click-modal="true" @open="onProgressOpen">
      <ProgressPanel ref="progressPanelRef" :novel-id="novelStore.currentNovel?.id || null" />
    </el-dialog>

    <!-- 右键菜单 -->
    <ContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :selected-text="contextMenu.selectedText"
      :loading="contextMenu.loading"
      :loading-action="contextMenu.loadingAction"
      @action="onContextAction"
      @close="closeContextMenu"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive } from 'vue'
import { MagicStick, Download, Upload, Refresh, Loading, Close, DataAnalysis, Brush, WarningFilled, TrendCharts, EditPen } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { marked } from 'marked'
import NovelTree from '../components/NovelTree.vue'
import AiChatPanel from '../components/AiChatPanel.vue'
import ChapterPanel from '../components/ChapterPanel.vue'
import ProgressPanel from '../components/ProgressPanel.vue'
import ContextMenu from '../components/ContextMenu.vue'
import StylePanel from '../components/StylePanel.vue'
import { useNovelStore } from '../stores/novel'
import { useSettingsStore } from '../stores/settings'
import { generateChapterStream, exportMd, chatStream } from '../utils/api'
import api from '../utils/api'

const novelStore = useNovelStore()
const settings = useSettingsStore()
const editorMode = ref('edit')
const selectedModel = ref('')
const generating = ref(false)
const currentId = ref('')
const novelMemory = ref<any>(null)
const showMemoryBar = ref(true)
const showProgress = ref(false)
const progressPanelRef = ref<InstanceType<typeof ProgressPanel> | null>(null)

// ── 文风 ──
const activeRightPanel = ref('chat')
const selectedTextForAnalysis = ref('')
const selectedStyleId = ref('')

function toggleRightPanel(panel: string) {
  activeRightPanel.value = activeRightPanel.value === panel ? 'chat' : panel
}

function onStyleSelected(profileId: string) {
  selectedStyleId.value = profileId
}

function onAnalysisStart() {
  selectedTextForAnalysis.value = novelStore.currentChapter?.content || ''
}

function onAnalysisDone(result: { features: any; style_prompt: string }) {
  // 可以在 chat panel 中显示分析结果
  ElMessage.success(`文风特征分析完成: ${result.style_prompt || '已保存'}`)
}

// ── 右键菜单 ──
const editorRef = ref<any>(null)
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  selectedText: '',
  loading: false,
  loadingAction: '',
  startOffset: 0,
  endOffset: 0,
})

const actionSystemPrompts: Record<string, string> = {
  polish: '你是一位专业文学编辑。请润色以下选中的文字，优化语法、用词和表达流畅度，保持原文风格和叙事角度。只返回润色后的文本，不要加任何解释。',
  expand: '你是一位擅长描写的作家。请扩写以下选中的文字，在保持原有风格和叙事的基础上，丰富细节描写、心理活动、环境氛围等。只返回扩写后的文本。',
  summarize: '你是一位精炼的编辑。请缩写以下选中的文字，保留核心信息和叙事主线，删减冗余修饰。保持原文的风格基调。只返回缩写后的文本。',
  continue: '你是一位创意写作者。请根据以下选中的文字风格和内容，自然续写一段。保持相同的叙事视角、语气和文风。只返回续写内容，不要重复原文。',
  'de-ai': '你是一位让文字回归自然的编辑。请修改以下文字，消除AI生成常见的痕迹：过于工整的句式、空洞的修饰词、生硬的排比、套路化表达。让文字像人类自然书写一样有温度和有呼吸感。只返回修改后的文本。',
  'analyze-style': '请分析以下文本的写作风格。从以下维度给出简洁分析：1) 整体节奏（紧凑/舒缓/有张有弛）2) 句式特点（长短句分布）3) 用词偏好（文言/口语/比喻等）4) 语气基调。用中文回复，简明扼要，200字以内。',
}

// 切换小说时加载灵魂记忆
watch(() => novelStore.currentNovel?.id, async (newId) => {
  if (newId) {
    try {
      const res = await api.get(`/novel/${newId}/memory`)
      novelMemory.value = res.data?.data || null
    } catch {
      novelMemory.value = null
    }
  } else {
    novelMemory.value = null
  }
})

// 计算属性
const chapterCount = computed(() => novelStore.currentNovel?.chapter_count || 0)
const contentLength = computed(() => novelStore.currentChapter?.content?.length || 0)
const paragraphCount = computed(() => {
  if (!novelStore.currentChapter?.content) return 0
  return novelStore.currentChapter.content.split('\n').filter((l: string) => l.trim()).length
})
const sentenceCount = computed(() => {
  if (!novelStore.currentChapter?.content) return 0
  return (novelStore.currentChapter.content.match(/[。！？\n]+/g) || []).length
})
const dialogueCount = computed(() => {
  if (!novelStore.currentChapter?.content) return 0
  return (novelStore.currentChapter.content.match(/[「『]/g) || []).length
})

const renderPreview = computed(() => {
  const content = novelStore.currentChapter?.content || ''
  return marked.parse(content, { async: false }) as string
})

function formatWords(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toLocaleString()
}

async function onSelectNovel(id: string) {
  currentId.value = id
  await novelStore.loadNovel(id)
}

async function loadCurrentNovel() {
  if (currentId.value) {
    await novelStore.loadNovel(currentId.value)
  }
}

async function saveChapter() {
  await novelStore.saveCurrentChapter()
  // 记录今日写作字数
  const content = novelStore.currentChapter?.content || ''
  if (content.length > 0) {
    progressPanelRef.value?.recordTodayWords(content.length)
  }
}

function onProgressOpen() {
  progressPanelRef.value?.refreshStats()
}

async function generateChapter() {
  if (!novelStore.currentNovel) return
  generating.value = true
  try {
    // 先创建新章节占位
    await novelStore.addChapter()
    const chNum = novelStore.currentNovel.chapter_count
    novelStore.selectChapter(chNum)
    novelStore.currentChapter!.content = ''

    for await (const token of generateChapterStream({
      novel_id: novelStore.currentNovel.id,
      chapter_number: chNum,
      model: selectedModel.value,
    })) {
      if (novelStore.currentChapter) {
        novelStore.currentChapter.content += token
      }
    }
    await novelStore.saveCurrentChapter()
  } finally {
    generating.value = false
  }
}

// ── 右键菜单：上下文事件 ──
function onEditorContextMenu(e: MouseEvent) {
  const target = e.target as HTMLElement
  const textarea = target.tagName === 'TEXTAREA' ? target : target.querySelector('textarea')
  if (!textarea) return

  const selected = textarea.value.substring(
    textarea.selectionStart,
    textarea.selectionEnd
  )
  if (!selected || !selected.trim()) {
    ElMessage.info('请先选中要处理的文字')
    return
  }

  contextMenu.selectedText = selected
  contextMenu.startOffset = textarea.selectionStart
  contextMenu.endOffset = textarea.selectionEnd
  contextMenu.x = e.clientX
  contextMenu.y = e.clientY
  contextMenu.visible = true
  contextMenu.loading = false
  contextMenu.loadingAction = ''
}

function closeContextMenu() {
  contextMenu.visible = false
  contextMenu.loading = false
}

async function onContextAction(type: string) {
  const text = contextMenu.selectedText
  if (!text) return

  const prompt = actionSystemPrompts[type]
  if (!prompt) return

  contextMenu.loading = true
  contextMenu.loadingAction = type

  try {
    let result = ''

    for await (const token of chatStream({
      messages: [
        { role: 'user', content: text },
      ],
      system_prompt: prompt,
      mode: 'writing',
      model: selectedModel.value || undefined,
    })) {
      result += token
    }

    // 处理结果
    if (type === 'analyze-style') {
      // 风格分析 → 弹窗展示
      ElMessageBox.alert(result, '🔍 写作风格分析', {
        type: 'info',
        dangerouslyUseHTMLString: false,
        width: '480px',
      })
    } else if (type === 'continue') {
      // 续写 → 插入到选中文本后面
      if (novelStore.currentChapter) {
        const content = novelStore.currentChapter.content
        const pos = contextMenu.endOffset
        novelStore.currentChapter.content =
          content.slice(0, pos) + '\n\n' + result.trim() + content.slice(pos)
      }
    } else {
      // 润色/扩写/缩写/去AI味 → 替换选中文字
      if (novelStore.currentChapter) {
        const content = novelStore.currentChapter.content
        const start = contextMenu.startOffset
        const end = contextMenu.endOffset
        novelStore.currentChapter.content =
          content.slice(0, start) + result.trim() + content.slice(end)
      }
    }

    ElMessage.success({
      message: getActionSuccessMessage(type),
      duration: 2000,
    })
  } catch (err: any) {
    ElMessage.error(`处理失败: ${err.message}`)
  } finally {
    closeContextMenu()
  }
}

function getActionSuccessMessage(type: string): string {
  const msgs: Record<string, string> = {
    polish: '✨ 润色完成',
    expand: '📖 扩写完成',
    summarize: '📌 缩写完成',
    continue: '▶️ 续写完成',
    'de-ai': '🧹 去AI味完成',
    'analyze-style': '🔍 分析已完成',
  }
  return msgs[type] || '✅ 处理完成'
}

async function exportNovel() {
  if (!novelStore.currentNovel) return
  try {
    const res = await api.post('/export/md', { novel_id: novelStore.currentNovel.id, export_all: true })
    ElMessage.success(`导出成功`)
  } catch (err: any) {
    ElMessage.error(`导出失败: ${err.message}`)
  }
}

// ── 去AI味 ──
const aiCleaning = ref(false)

async function cleanAIStyle() {
  if (!novelStore.currentNovel || !novelStore.currentChapter) return
  const content = novelStore.currentChapter.content
  if (!content.trim()) {
    ElMessage.warning('请先输入章节内容')
    return
  }

  aiCleaning.value = true
  try {
    let result = ''
    for await (const token of chatStream({
      messages: [{ role: 'user', content: content }],
      system_prompt: actionSystemPrompts['de-ai'],
      mode: 'writing',
      model: selectedModel.value || undefined,
    })) {
      result += token
    }
    novelStore.currentChapter.content = result.trim()
    ElMessage.success('🧹 去AI味完成')
  } catch (err: any) {
    ElMessage.error(`去AI味失败: ${err.message}`)
  } finally {
    aiCleaning.value = false
  }
}

// ── 一致性检查 ──

async function checkConsistency() {
  if (!novelStore.currentNovel || !novelStore.currentChapter) return
  const content = novelStore.currentChapter.content
  if (!content.trim()) {
    ElMessage.warning('请先输入章节内容')
    return
  }

  try {
    const res = await api.post(
      `/novel/${novelStore.currentNovel.id}/analyze/consistency`,
      { chapter_number: novelStore.currentChapter.chapter_number, text: content },
    )
    const data = res.data
    if (!data.success) {
      ElMessage.error(data.message || '一致性检查失败')
      return
    }

    const result = data.data
    const issues = result.issues || []
    if (issues.length === 0) {
      ElMessageBox.alert('✅ 未发现一致性问题，所有角色名和地名保持一致。', '📋 一致性检查', {
        type: 'success',
        width: '480px',
      })
    } else {
      const issueLines = issues.map((issue: any, i: number) => {
        const icon = issue.type === 'typo' ? '⚠️' : '🔍'
        return `${i + 1}. ${icon} [${issue.type}] ${issue.name}: ${issue.issue}`
      }).join('\n\n')
      ElMessageBox.alert(issueLines, '📋 一致性检查 — 发现问题', {
        type: 'warning',
        width: '520px',
        dangerouslyUseHTMLString: false,
      })
    }
  } catch (err: any) {
    ElMessage.error(`一致性检查失败: ${err.message}`)
  }
}

// ── 风格分析 ──

async function analyzeStyle() {
  if (!novelStore.currentNovel || !novelStore.currentChapter) return
  const content = novelStore.currentChapter.content
  if (!content.trim()) {
    ElMessage.warning('请先输入章节内容')
    return
  }

  try {
    const res = await api.post(
      `/novel/${novelStore.currentNovel.id}/analyze/style`,
      { chapter_number: novelStore.currentChapter.chapter_number, text: content },
    )
    const data = res.data
    if (!data.success) {
      ElMessage.error(data.message || '风格分析失败')
      return
    }

    const result = data.data
    const lines = [
      `📐 平均句长: ${result.avg_sentence_length || 0} 字/句`,
      `💬 对话占比: ${((result.dialogue_percentage || 0) * 100).toFixed(1)}%`,
      `🧠 心理描写占比: ${((result.psych_percentage || 0) * 100).toFixed(1)}%`,
      `📝 句子数: ${result.sentence_count || 0}`,
      `📊 总字数: ${result.total_chars || 0}`,
    ]
    if (result.techniques && result.techniques.length > 0) {
      lines.push(`\n✍️ 写作技法:\n${result.techniques.map((t: string) => `  · ${t}`).join('\n')}`)
    }
    if (result.top_adjectives && result.top_adjectives.length > 0) {
      lines.push(`\n📖 高频形容词: ${result.top_adjectives.slice(0, 5).join('、')}`)
    }
    if (result.top_verbs && result.top_verbs.length > 0) {
      lines.push(`\n🏃 高频动词: ${result.top_verbs.slice(0, 5).join('、')}`)
    }

    ElMessageBox.alert(lines.join('\n'), '🔍 写作风格分析', {
      type: 'info',
      width: '480px',
      dangerouslyUseHTMLString: false,
    })
  } catch (err: any) {
    ElMessage.error(`风格分析失败: ${err.message}`)
  }
}
</script>

<style scoped>
.writing-view {
  display: flex; height: calc(100vh - 40px); gap: 0;
}
.writing-sidebar {
  width: 280px; min-width: 280px;
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-light);
  overflow-y: auto;
}
.writing-editor {
  flex: 1; display: flex; flex-direction: column; min-width: 0;
}

/* Top Bar */
.editor-topbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 24px; border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
}
.topbar-left { display: flex; align-items: center; gap: 12px; }
.novel-title { margin: 0; font-size: 17px; font-weight: 700; }
.novel-tag { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.novel-stats { font-size: 12px; color: var(--el-text-color-secondary); }
.topbar-right { display: flex; align-items: center; gap: 8px; }

/* Empty state */
.editor-empty-state {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  color: var(--el-text-color-secondary);
}
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.editor-empty-state h3 { margin: 0 0 8px; font-size: 16px; color: var(--el-text-color-primary); }
.empty-hint { font-size: 13px; color: var(--el-text-color-placeholder); }

/* Editor */
.editor-area { flex: 1; display: flex; flex-direction: column; padding: 16px 24px; overflow: hidden; }
.editor-chapter-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--el-text-color-placeholder); font-size: 14px; }
.editor-wrapper { height: 100%; }

.chapter-title-bar {
  display: flex; align-items: center; gap: 12px; margin-bottom: 12px;
}
.chapter-title-input { font-size: 20px; font-weight: 600; }
.chapter-title-input :deep(.el-input__wrapper) { box-shadow: none !important; padding-left: 0; }
.chapter-title-input :deep(.el-input__inner) { font-size: 20px; font-weight: 600; }
.word-counter { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; }

.editor-tabs { flex: 1; display: flex; flex-direction: column; }
.editor-tabs :deep(.el-tabs__content) { flex: 1; overflow: hidden; }
.editor-tabs :deep(.el-tab-pane) { height: 100%; }
.editor-tabs :deep(.el-tabs__header) { margin-bottom: 8px; }

.chapter-editor { height: 100%; }
.chapter-editor :deep(.el-textarea__inner) {
  height: 100% !important; min-height: 400px;
  font-size: 15px; line-height: 1.9;
  padding: 16px; border: none; resize: vertical;
  font-family: 'Noto Serif SC', 'Source Han Serif SC', 'STSong', serif;
}

.preview-content {
  padding: 16px; height: 100%; overflow-y: auto;
  font-size: 15px; line-height: 2;
  font-family: 'Noto Serif SC', 'Source Han Serif SC', 'STSong', serif;
}

/* Analysis */
.analysis-panel { padding: 16px; }
.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.stat-card {
  text-align: center; padding: 20px; border-radius: 12px;
  background: var(--el-fill-color-lighter);
}
.stat-num { font-size: 28px; font-weight: 700; color: var(--el-color-primary); }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }

/* Footer */
.editor-footer {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 0; margin-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.save-status { font-size: 12px; color: var(--el-text-color-secondary); }
.save-ok { color: var(--el-color-success); }
.footer-actions { display: flex; gap: 8px; }

/* Right panel tabs */
.right-panel-tabs {
  padding: 8px 12px 0;
  text-align: center;
}

/* Chat panel */
.writing-chat { width: 360px; min-width: 360px; display: flex; flex-direction: column; }

/* 灵魂记忆提示条 */
.memory-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 16px; margin: 0 24px;
  background: linear-gradient(135deg, var(--el-color-warning-light-9), var(--el-color-primary-light-9));
  border-radius: 8px; font-size: 12px;
}
.memory-bar-left { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.memory-label { font-weight: 600; white-space: nowrap; }
.memory-text { color: var(--el-text-color-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.memory-empty { color: var(--el-text-color-placeholder); font-style: italic; }
.memory-bar-right { display: flex; align-items: center; gap: 6px; }
.memory-tag {
  font-size: 11px; padding: 1px 8px; border-radius: 4px;
  background: var(--el-bg-color); color: var(--el-color-primary);
}
</style>
