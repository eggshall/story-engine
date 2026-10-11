\n<template>
  <div class="characters-view">
    <div class="view-header">
      <h3>角色卡管理</h3>
      <div class="header-right">
        <!-- N8：角色卡属于某一本小说，先选书 -->
        <el-select
          v-model="novelId"
          data-testid="novel-select"
          placeholder="选择小说"
          size="small"
          style="width: 200px"
          @change="loadCharacters"
        >
          <el-option v-for="n in novels" :key="n.id" :label="n.title" :value="n.id" />
        </el-select>
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="cards">📇 角色卡片</el-radio-button>
          <el-radio-button value="graph">🔗 关系图谱</el-radio-button>
        </el-radio-group>
        <el-button size="small" data-testid="open-library" :disabled="!novelId" @click="openLibrary">
          从素材库导入
        </el-button>
        <el-button v-if="viewMode === 'cards'" type="primary" :icon="Plus" :disabled="!novelId"
          data-testid="new-character" @click="startNewCharacter">
          新建角色
        </el-button>
      </div>
    </div>

    <p v-if="errorMsg" class="err" data-testid="char-error">{{ errorMsg }}</p>

    <!-- 角色卡片模式 -->
    <template v-if="viewMode === 'cards'">
      <div class="char-grid">
        <CharacterCard
          v-for="char in cards"
          :key="char.id"
          :char="char"
          @select="editCharacter"
        />
        <div v-if="cards.length === 0" class="char-empty" data-testid="char-empty">
          <el-empty :description="emptyHint" />
        </div>
      </div>
    </template>

    <!-- 关系图谱模式 -->
    <template v-else>
      <RelationshipGraph :characters="cards" />
    </template>

    <!-- 从素材库导入 -->
    <el-dialog v-model="showLibrary" title="从素材库导入（复制一份进本书）" width="520px">
      <p v-if="libraryCards.length === 0" class="empty-hint">
        素材库还是空的：先把某本书里的角色卡「另存为素材」，别的书就能一键复制。
      </p>
      <div v-else class="lib-list">
        <div v-for="c in libraryCards" :key="c.name" class="lib-item" data-testid="library-item"
          :data-name="c.name">
          <span class="lib-name">{{ c.name }}</span>
          <span class="lib-desc">{{ c.description }}</span>
          <el-button size="small" type="primary" :loading="importing === c.name"
            @click="doImport(c.name)">导入</el-button>
        </div>
      </div>
    </el-dialog>

    <!-- 角色编辑器弹窗 -->
    <el-dialog
      v-model="showEditor"
      :title="editingChar ? '编辑角色' : '新建角色'"
      width="600px"
    >
      <el-form :model="form" label-position="top">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="角色名" required>
              <el-input v-model="form.name" placeholder="角色名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标签">
              <el-select v-model="form.tags" multiple filterable allow-create default-first-option
                placeholder="选择或输入标签" style="width: 100%">
                <el-option label="主角" value="主角" />
                <el-option label="配角" value="配角" />
                <el-option label="反派" value="反派" />
                <el-option label="路人" value="路人" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="角色描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="性格">
          <el-input v-model="form.personality" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="外貌描写">
          <el-input v-model="form.appearance" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="背景故事">
          <el-input v-model="form.background" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="出场描写">
          <el-input v-model="form.first_mes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="editingChar" data-testid="to-library" @click="saveToLibrary">另存为素材</el-button>
        <el-button v-if="editingChar" type="danger" plain data-testid="delete-char" @click="removeCharacter">
          删除
        </el-button>
        <el-button @click="showEditor = false">取消</el-button>
        <el-button type="primary" :loading="saving" data-testid="save-char" @click="saveCharacter">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, reactive } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import CharacterCard from '../components/CharacterCard.vue'
import RelationshipGraph from '../components/RelationshipGraph.vue'
import {
  createNovelCharacter,
  deleteNovelCharacter,
  exportCharacterToLibrary,
  fetchLibraryCharacters,
  fetchNovelCharacters,
  fetchNovels,
  importCharacter,
  updateNovelCharacter,
  type ApiCharacterCard,
  type NovelBrief,
} from '../utils/api'
import { useNovelStore } from '../stores/novel'

const novelStore = useNovelStore()

const novels = ref<NovelBrief[]>([])
const novelId = ref('')
const apiCards = ref<ApiCharacterCard[]>([])
const errorMsg = ref('')

/** 记住作者上次选的书：刷新/切页回来还在同一本上（比"猜最近更新的那本"可靠） */
const LAST_NOVEL_KEY = 'story_last_novel'

function rememberNovel(id: string) {
  if (id && typeof localStorage !== 'undefined') localStorage.setItem(LAST_NOVEL_KEY, id)
}

/** 老组件（CharacterCard/RelationshipGraph）要 `id` 字段，用名字兜一个稳定的 id */
const cards = computed(() =>
  apiCards.value.map((c) => ({ ...c, id: c.name, tags: c.tags || [], relationships: c.relationships || [] })),
)
const emptyHint = computed(() =>
  !novelId.value ? '先在上面选一本小说（角色卡属于某一本书）' : '这本书还没有角色卡，点击「新建角色」添加',
)

const viewMode = ref<'cards' | 'graph'>('cards')
const showEditor = ref(false)
const editingChar = ref<string | null>(null)
const saving = ref(false)

const showLibrary = ref(false)
const libraryCards = ref<ApiCharacterCard[]>([])
const importing = ref('')

const form = reactive({
  name: '',
  description: '',
  personality: '',
  appearance: '',
  background: '',
  first_mes: '',
  tags: [] as string[],
})

onMounted(async () => {
  try {
    novels.value = await fetchNovels()
  } catch (e: any) {
    errorMsg.value = e?.message || '读取小说列表失败'
    return
  }
  // 选书的优先级：写作页当前那本 > 上次记住的那本 > 最近更新的那本
  const preferred = novelStore.currentNovel?.id || ''
  const remembered = typeof localStorage !== 'undefined' ? localStorage.getItem(LAST_NOVEL_KEY) || '' : ''
  const byRecency = [...novels.value].sort((a, b) =>
    String(b.updated || '').localeCompare(String(a.updated || '')),
  )
  const pick = (id: string) => (id && novels.value.some((n) => n.id === id) ? id : '')
  novelId.value = pick(preferred) || pick(remembered) || byRecency[0]?.id || ''
  if (novelId.value) {
    rememberNovel(novelId.value)
    await loadCharacters()
  }
})

async function loadCharacters() {
  if (!novelId.value) {
    apiCards.value = []
    return
  }
  rememberNovel(novelId.value)
  errorMsg.value = ''
  try {
    apiCards.value = await fetchNovelCharacters(novelId.value)
  } catch (e: any) {
    errorMsg.value = e?.message || '读取角色卡失败'
    apiCards.value = []
  }
}

function startNewCharacter() {
  editingChar.value = null
  Object.assign(form, {
    name: '', description: '', personality: '', appearance: '', background: '', first_mes: '', tags: [],
  })
  showEditor.value = true
}

function editCharacter(id: string) {
  const char = apiCards.value.find((c) => c.name === id)
  if (!char) return
  editingChar.value = id
  Object.assign(form, {
    name: char.name,
    description: char.description || '',
    personality: char.personality || '',
    appearance: char.appearance || '',
    background: char.background || '',
    first_mes: char.first_mes || '',
    tags: [...(char.tags || [])],
  })
  showEditor.value = true
}

async function saveCharacter() {
  if (!form.name || !novelId.value) return
  saving.value = true
  errorMsg.value = ''
  try {
    if (editingChar.value) {
      await updateNovelCharacter(novelId.value, editingChar.value, { ...form })
    } else {
      await createNovelCharacter(novelId.value, { ...form })
    }
    showEditor.value = false
    editingChar.value = null
    await loadCharacters()
  } catch (e: any) {
    errorMsg.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function removeCharacter() {
  if (!editingChar.value || !novelId.value) return
  try {
    await deleteNovelCharacter(novelId.value, editingChar.value)
    showEditor.value = false
    editingChar.value = null
    await loadCharacters()
  } catch (e: any) {
    errorMsg.value = e?.message || '删除失败'
  }
}

async function saveToLibrary() {
  if (!editingChar.value || !novelId.value) return
  try {
    await exportCharacterToLibrary(novelId.value, editingChar.value)
    errorMsg.value = ''
  } catch (e: any) {
    errorMsg.value = e?.message || '另存为素材失败'
  }
}

async function openLibrary() {
  showLibrary.value = true
  try {
    libraryCards.value = await fetchLibraryCharacters()
  } catch (e: any) {
    errorMsg.value = e?.message || '读取素材库失败'
  }
}

async function doImport(name: string) {
  if (!novelId.value) return
  importing.value = name
  errorMsg.value = ''
  try {
    await importCharacter(novelId.value, { source: 'library', name })
    showLibrary.value = false
    await loadCharacters()
  } catch (e: any) {
    errorMsg.value = e?.message || '导入失败'
  } finally {
    importing.value = ''
  }
}
</script>

<style scoped>
.characters-view {
  padding: 0;
}
.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.view-header h3 {
  margin: 0;
  font-size: 18px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.char-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.char-empty {
  grid-column: 1 / -1;
  display: flex;
  justify-content: center;
  padding: 40px 0;
}
.err {
  color: var(--el-color-danger);
  font-size: 12px;
  margin: 0 0 12px;
}
.empty-hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.lib-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 50vh;
  overflow-y: auto;
}
.lib-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
}
.lib-name {
  font-weight: 600;
  white-space: nowrap;
}
.lib-desc {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
