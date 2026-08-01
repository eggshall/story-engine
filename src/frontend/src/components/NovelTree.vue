\n<template>
  <div class="novel-tree" @contextmenu.prevent>
    <div class="tree-header">
      <span class="tree-title">📚 我的小说</span>
      <el-button size="small" type="primary" :icon="Plus" circle @click="showCreate = true" />
    </div>

    <div v-if="store.loading" class="tree-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
    </div>

    <div v-for="novel in store.novels" :key="novel.id"
      :class="['novel-item', { active: currentId === novel.id }]"
      @click="selectNovel(novel.id)"
      @contextmenu.prevent="contextMenu = { id: novel.id, title: novel.title, x: $event.clientX, y: $event.clientY }"
    >
      <div class="novel-info">
        <div class="novel-name">{{ novel.title }}</div>
        <div class="novel-meta">{{ novel.chapter_count }}章 · {{ formatWords(novel.word_count) }}字</div>
      </div>
      <el-button size="small" text :icon="MoreFilled" @click.stop="contextMenu = { id: novel.id, title: novel.title, x: $event.clientX, y: $event.clientY }" />
    </div>

    <div v-if="store.novels.length === 0 && !store.loading" class="tree-empty">
      <el-empty :image-size="60" description="暂无小说，点击 + 创建" />
    </div>

    <!-- 右击菜单 -->
    <teleport to="body">
      <div v-if="contextMenu" class="context-menu" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }">
        <div class="cm-item" @click="startRename(contextMenu.id); contextMenu = null">
          <el-icon><Edit /></el-icon> 重命名
        </div>
        <div class="cm-item" @click="exportNovel(contextMenu.id); contextMenu = null">
          <el-icon><Download /></el-icon> 导出 MD
        </div>
        <div class="cm-item" @click="showMemoryEditor = true; contextMenu = null">
          <el-icon><Memo /></el-icon> 灵魂记忆
        </div>
        <div class="cm-divider" />
        <div class="cm-item cm-danger" @click="confirmDelete(contextMenu.id); contextMenu = null">
          <el-icon><Delete /></el-icon> 删除小说
        </div>
      </div>
    </teleport>

    <!-- 新建弹窗 -->
    <el-dialog v-model="showCreate" title="新建小说" width="520px">
      <el-form :model="form" label-position="top">
        <el-form-item label="书名" required>
          <el-input v-model="form.title" placeholder="输入小说标题" maxlength="50" show-word-limit />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="作者">
              <el-input v-model="form.author" placeholder="作者名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="类型">
              <el-select v-model="form.genre" placeholder="选择" style="width: 100%">
                <el-option v-for="g in genres" :key="g" :label="g" :value="g" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="简介">
          <el-input v-model="form.synopsis" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="存储路径（可选）">
          <el-input v-model="form.save_path" placeholder="留空使用默认 data/novels/目录">
            <template #prepend>📁</template>
            <template #append>
              <el-button @click="showPathBrowser = true">浏览…</el-button>
            </template>
          </el-input>
          <div class="form-hint">
            默认保存在 data/novels/书名/ 下<br>
            支持 Windows 路径: <code>C:\Users\用户名\Desktop\小说</code>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="onCreate" :loading="creating">创建</el-button>
      </template>
    </el-dialog>

    <!-- 重命名弹窗 -->
    <el-dialog v-model="showRename" title="重命名" width="360px">
      <el-input v-model="renameText" placeholder="新书名" />
      <template #footer>
        <el-button @click="showRename = false">取消</el-button>
        <el-button type="primary" @click="onRename">确认</el-button>
      </template>
    </el-dialog>

    <!-- 灵魂记忆编辑弹窗 -->
    <el-dialog v-model="showMemoryEditor" title="🧠 灵魂记忆" width="500px">
      <el-form label-position="top">
        <el-form-item label="用户备注（给模型的提示）">
          <el-input v-model="memoryForm.user_notes" type="textarea" :rows="3" placeholder="这部小说的写作要求、注意事项…" />
        </el-form-item>
        <el-form-item label="自定义系统提示词">
          <el-input v-model="memoryForm.custom_system_prompt" type="textarea" :rows="3" placeholder="追加到 AI 系统提示词中的内容…" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="写作偏好">
              <el-select v-model="memoryForm.writing_mode_pref" style="width:100%">
                <el-option label="细腻描写" value="细腻" />
                <el-option label="简洁明快" value="简洁" />
                <el-option label="平衡" value="平衡" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="倾向模型">
              <el-select v-model="memoryForm.preferred_model" style="width:100%">
                <el-option v-for="m in settings.models" :key="m.name" :label="m.name" :value="m.name" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="showMemoryEditor = false">关闭</el-button>
        <el-button type="primary" @click="saveMemory">保存记忆</el-button>
      </template>
    </el-dialog>

    <!-- 路径选择器 -->
    <el-dialog v-model="showPathBrowser" title="选择存储位置 — 实际保存到 Windows 磁盘" width="480px">
      <p style="font-size:13px;color:var(--el-text-color-secondary);margin-bottom:12px;">
        文件将保存到 Windows 磁盘（通过 WSL 的 /mnt/ 访问），可在文件资源管理器中查看。
      </p>
      <div v-if="pathLoading" class="path-loading">
        <el-icon class="is-loading"><Loading /></el-icon> 加载路径…
      </div>
      <template v-else>
        <div
          v-for="item in pathSuggestions"
          :key="item.path"
          class="path-option"
          @click="selectPath(item.path)"
        >
          <span class="path-icon">{{ item.path.startsWith('/mnt/c/Users') ? '🖥️' : '💾' }}</span>
          <div>
            <div class="path-name">{{ item.label }}</div>
            <div class="path-value">{{ item.path }}</div>
          </div>
        </div>
        <div class="path-divider" />
        <div class="path-custom">
          <el-input v-model="customPathInput" placeholder="或手动输入完整路径，如 /mnt/d/novels" size="small">
            <template #prepend>📁</template>
          </el-input>
          <el-button size="small" @click="selectPath(customPathInput)" :disabled="!customPathInput.trim()">确认</el-button>
        </div>
      </template>
      <template #footer>
        <el-button @click="showPathBrowser = false">取消</el-button>
        <el-button type="primary" @click="form.save_path = customPathInput || form.save_path; showPathBrowser = false">使用</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { Plus, MoreFilled, Edit, Download, Memo, Delete, Loading } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useNovelStore } from '../stores/novel'
import { useSettingsStore } from '../stores/settings'
import api from '../utils/api'

const props = defineProps<{ currentId?: string }>()
const emit = defineEmits<{ select: [id: string] }>()

const store = useNovelStore()
const settings = useSettingsStore()
const genres = ['玄幻', '都市', '科幻', '历史', '悬疑', '言情', '武侠', '仙侠', '奇幻', '游戏', '轻小说', '其他']

// 创建
const showCreate = ref(false)
const creating = ref(false)
const showPathBrowser = ref(false)
const pathLoading = ref(false)
const pathSuggestions = ref<any[]>([])
const customPathInput = ref('')
const form = ref({ title: '', author: '', genre: '', synopsis: '', save_path: '' })

// 打开路径选择器时加载系统路径
watch(showPathBrowser, async (val) => {
  if (val) {
    pathLoading.value = true
    try {
      const res = await api.get('/system/paths')
      pathSuggestions.value = res.data?.data?.suggested || []
    } catch {
      pathSuggestions.value = []
    } finally {
      pathLoading.value = false
    }
  }
})

function selectPath(p: string) {
  if (p) {
    form.value.save_path = p
    showPathBrowser.value = false
  }
}

// 右击菜单
const contextMenu = ref<{ id: string; title: string; x: number; y: number } | null>(null)

// 重命名
const showRename = ref(false)
const renameText = ref('')
let renameTarget = ''

// 记忆编辑
const showMemoryEditor = ref(false)
const memoryForm = reactive({
  user_notes: '',
  custom_system_prompt: '',
  writing_mode_pref: '平衡',
  preferred_model: '',
})

function formatWords(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toLocaleString()
}

function selectNovel(id: string) {
  emit('select', id)
  contextMenu.value = null
  // 加载灵魂记忆
  loadMemory(id)
}

async function loadMemory(novelId: string) {
  try {
    const res = await api.get(`/novel/${novelId}/memory`)
    const data = res.data?.data || {}
    memoryForm.user_notes = data.user_notes || ''
    memoryForm.custom_system_prompt = data.custom_system_prompt || ''
    memoryForm.writing_mode_pref = data.writing_mode_pref || '平衡'
    memoryForm.preferred_model = data.preferred_model || ''
  } catch { /* ignore */ }
}

async function saveMemory() {
  if (!props.currentId) return
  try {
    await api.post(`/novel/${props.currentId}/memory`, { ...memoryForm })
    ElMessage.success('记忆已保存')
    showMemoryEditor.value = false
  } catch (e: any) {
    ElMessage.error('保存失败: ' + e.message)
  }
}

async function onCreate() {
  if (!form.value.title) return
  creating.value = true
  try {
    await store.create({
      title: form.value.title,
      author: form.value.author,
      genre: form.value.genre,
      synopsis: form.value.synopsis,
      save_path: form.value.save_path,
    })
    form.value = { title: '', author: '', genre: '', synopsis: '', save_path: '' }
    showCreate.value = false
  } finally {
    creating.value = false
  }
}

function confirmDelete(id: string) {
  if (!id) return
  const title = store.novels.find((n: any) => n.id === id)?.title || id
  ElMessageBox.confirm(
    `确定永久删除「${title}」？\n所有章节、角色、设定和记忆都将丢失，不可恢复。`,
    '⚠️ 确认删除',
    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning', distinguishCancelAndClose: true }
  ).then(async () => {
    try {
      const res = await api.delete(`/novel/${encodeURIComponent(id)}`)
      if (!res.data?.success) {
        throw new Error(res.data?.message || '删除请求失败')
      }
      // 清除当前选中
      if (store.currentNovel?.id === id) {
        store.currentNovel = null
      }
      // 重新从后端加载列表
      await store.loadNovels()
      ElMessage.success(`已删除「${title}」`)
    } catch (e: any) {
      ElMessage.error('删除失败: ' + (e.message || '未知错误'))
      console.error('Delete error:', e)
    }
  }).catch(() => {}) // 用户取消
}

function onRename() {
  if (!renameText.value || !renameTarget) return
  api.post(`/novel/${renameTarget}/update`, { title: renameText.value }).then(() => {
    store.loadNovels()
    showRename.value = false
    renameTarget = ''
    ElMessage.success('已重命名')
  }).catch(() => {
    ElMessage.error('重命名失败')
  })
}

function startRename(id: string) {
  renameTarget = id
  const novel = store.novels.find((n: any) => n.id === id)
  renameText.value = novel?.title || ''
  showRename.value = true
}

async function exportNovel(id: string) {
  try {
    const res = await api.post('/export/md', { novel_id: id, export_all: true })
    ElMessage.success(`导出成功: ${res.data?.data?.path || ''}`)
  } catch { ElMessage.error('导出失败') }
}

// 关闭右击菜单
function closeMenu() { contextMenu.value = null }
if (typeof window !== 'undefined') {
  document.addEventListener('click', closeMenu)
}
onMounted(() => store.loadNovels())
</script>

<style scoped>
.novel-tree { padding: 8px; height: 100%; overflow-y: auto; position: relative; }
.tree-header { display: flex; justify-content: space-between; align-items: center; padding: 8px; }
.tree-title { font-weight: 700; font-size: 15px; }
.tree-loading { text-align: center; padding: 20px; }
.tree-empty { padding: 20px 0; }

.novel-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; margin: 2px 0;
  border-radius: 8px; cursor: pointer;
  transition: all 0.15s;
}
.novel-item:hover { background: var(--el-fill-color-light); }
.novel-item.active { background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.novel-info { flex: 1; min-width: 0; }
.novel-name { font-size: 14px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.novel-meta { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 2px; }

.context-menu {
  position: fixed; z-index: 9999;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  padding: 4px 0;
  min-width: 140px;
}
.cm-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 16px; font-size: 13px; cursor: pointer;
}
.cm-item:hover { background: var(--el-fill-color-light); }
.cm-item.cm-danger { color: var(--el-color-danger); }
.cm-divider { height: 1px; background: var(--el-border-color-light); margin: 4px 0; }

.form-hint { font-size: 11px; color: var(--el-text-color-placeholder); margin-top: 4px; }
.form-hint code { font-size: 11px; background: var(--el-fill-color-light); padding: 1px 4px; border-radius: 2px; }

/* 路径选择器 */
.path-option {
  display: flex; align-items: center; gap: 12px;
  padding: 12px; margin: 4px 0;
  border-radius: 8px; cursor: pointer;
  transition: background 0.15s;
}
.path-option:hover { background: var(--el-fill-color-light); }
.path-icon { font-size: 24px; }
.path-name { font-size: 13px; font-weight: 500; }
.path-value { font-size: 11px; color: var(--el-text-color-secondary); font-family: monospace; }
.path-divider { height: 1px; background: var(--el-border-color-light); margin: 8px 0; }
.path-custom { display: flex; gap: 8px; align-items: center; padding: 8px 0; }
.path-custom .el-input { flex: 1; }
.path-loading { text-align: center; padding: 30px; color: var(--el-text-color-secondary); }
</style>
