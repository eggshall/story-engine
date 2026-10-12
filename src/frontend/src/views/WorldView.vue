<template>
  <div class="world-view">
    <div class="view-header">
      <h3>世界观设定</h3>
      <div class="header-actions">
        <el-select
          v-model="novelId"
          data-testid="novel-select"
          placeholder="选择小说"
          size="small"
          style="width: 200px"
        >
          <el-option v-for="n in novels" :key="n.id" :label="n.title" :value="n.id" />
        </el-select>
        <el-button
          v-if="activeTab === 'entries'"
          type="primary"
          :icon="Plus"
          :disabled="!novelId"
          data-testid="new-entry"
          @click="startNewEntry"
        >
          新建条目
        </el-button>
        <el-button
          v-if="activeTab === 'entries' && activeCategory !== 'all'"
          type="danger"
          plain
          size="small"
          data-testid="delete-lorebook"
          @click="removeLorebook"
        >
          删除设定集
        </el-button>
      </div>
    </div>

    <p v-if="errorMsg" class="err" data-testid="world-error">{{ errorMsg }}</p>
    <p v-else-if="!novelId" class="hint">先在上面选一本小说（设定集属于某一本书）</p>

    <el-tabs v-model="activeTab" class="world-tabs">
      <el-tab-pane label="条目" name="entries">
        <div class="world-content">
          <div class="world-categories">
            <el-menu :default-active="activeCategory">
              <el-menu-item index="all" data-testid="lorebook-all" @click="activeCategory = 'all'">
                <el-icon><Folder /></el-icon><span>全部</span>
              </el-menu-item>
              <el-menu-item
                v-for="b in books"
                :key="b.name"
                :index="b.name"
                :data-testid="`lorebook-${b.name}`"
                @click="activeCategory = b.name"
              >
                <el-icon><Collection /></el-icon><span>{{ b.name }}</span>
              </el-menu-item>
            </el-menu>
            <p v-if="books.length === 0" class="hint small">这本书还没有设定集</p>
          </div>
          <div class="world-entries">
            <div class="type-filter">
              <el-button
                size="small"
                :type="activeType === 'all' ? 'primary' : 'default'"
                data-testid="type-filter-all"
                @click="activeType = 'all'"
              >
                全部类型
              </el-button>
              <el-button
                v-for="o in filterTypes"
                :key="o.value"
                size="small"
                :type="activeType === o.value ? 'primary' : 'default'"
                :data-testid="`type-filter-${o.value}`"
                @click="activeType = o.value"
              >
                {{ o.label }}
              </el-button>
            </div>
            <div v-for="entry in filteredEntries" :key="entry.key" class="entry-card" @click="editEntry(entry)">
              <div class="entry-header">
                <span class="entry-name">{{ entry.entryId }}</span>
                <el-tag size="small">{{ entry.bookName }}</el-tag>
                <el-tag size="small" type="warning" data-testid="entry-category">{{
                  categoryLabel(entry.category)
                }}</el-tag>
                <el-tag v-if="!entry.enabled" size="small" type="info">已停用</el-tag>
                <span class="entry-priority">P{{ entry.priority }}</span>
              </div>
              <div class="entry-keys">
                <el-tag v-for="k in entry.keys" :key="k" size="small" type="info" round>{{ k }}</el-tag>
              </div>
              <div class="entry-content">{{ entry.content }}</div>
            </div>
            <div v-if="filteredEntries.length === 0" class="entries-empty">
              <el-empty :description="emptyDescription" />
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="地图" name="map">
        <div class="map-container">
          <div class="map-toolbar">
            <el-button size="small" type="primary" @click="selectMapImage">上传地图</el-button>
            <el-button
              size="small"
              data-testid="save-map"
              :loading="saving"
              :disabled="!novelId || saving"
              @click="saveMapData"
            >
              保存标记
            </el-button>
            <span v-if="saved" class="save-hint">已保存</span>
            <input
              ref="fileInput"
              type="file"
              accept="image/*"
              style="display:none"
              @change="onImageSelected"
            />
          </div>

          <!-- 诚实提示：后端目前只有占位接口，图片没有真的上传 -->
          <p class="hint">地图图片仅在<strong>本机预览</strong>，未上传到服务端（后端 `POST /map/image` 目前返回占位路径）。</p>
          <p v-if="mapNotice" class="err" data-testid="map-notice">{{ mapNotice }}</p>

          <div v-if="!mapImage" class="map-placeholder" @click="selectMapImage">
            <el-icon :size="48"><Picture /></el-icon>
            <p>点击上传地图图片（本机预览）</p>
            <p class="hint">支持 JPG / PNG 格式</p>
          </div>

          <div v-else class="map-area">
            <div ref="mapWrapper" class="map-image-wrapper" @click="onMapClick">
              <img :src="mapImage" alt="世界地图" class="map-image" />
              <div
                v-for="m in markers"
                :key="m.id"
                class="map-marker"
                :style="{ left: m.x + '%', top: m.y + '%' }"
                :title="m.name"
                @click.stop="selectMarker(m)"
              >
                <div class="marker-pin" :class="{ active: selectedMarkerId === m.id }">
                  <el-icon><Location /></el-icon>
                </div>
                <div class="marker-label">{{ m.name }}</div>
              </div>
            </div>
          </div>

          <div v-if="selectedMarker" class="marker-editor">
            <h4>标记编辑</h4>
            <el-form label-position="top" size="small">
              <el-form-item label="名称">
                <el-input v-model="selectedMarker.name" />
              </el-form-item>
              <el-form-item label="关联 Lore 条目">
                <el-select v-model="selectedMarker.lore_entry_id" filterable allow-create clearable style="width:100%">
                  <el-option
                    v-for="e in flatEntries"
                    :key="e.key"
                    :label="`${e.bookName} / ${e.entryId}`"
                    :value="e.key"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="描述">
                <el-input v-model="selectedMarker.description" type="textarea" :rows="2" />
              </el-form-item>
              <div class="marker-actions">
                <el-button size="small" type="danger" @click="deleteMarker">删除标记</el-button>
              </div>
            </el-form>
          </div>

          <div v-if="newMarkerPos" class="new-marker-form">
            <h4>新建标记 @ ({{ newMarkerPos.x.toFixed(1) }}%, {{ newMarkerPos.y.toFixed(1) }}%)</h4>
            <el-form label-position="top" size="small">
              <el-form-item label="名称">
                <el-input v-model="newMarkerForm.name" placeholder="标记名称" />
              </el-form-item>
              <el-form-item label="描述">
                <el-input v-model="newMarkerForm.description" type="textarea" :rows="2" />
              </el-form-item>
              <div class="marker-actions">
                <el-button size="small" type="primary" @click="addMarker">添加</el-button>
                <el-button size="small" @click="newMarkerPos = null">取消</el-button>
              </div>
            </el-form>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 条目编辑弹窗 -->
    <el-dialog v-model="showEditor" :title="editingEntry ? '编辑条目' : '新建条目'" width="500px">
      <el-form :model="entryForm" label-position="top">
        <el-form-item label="设定集" required>
          <el-input
            v-model="entryForm.bookName"
            :disabled="!!editingEntry"
            data-testid="form-book"
            placeholder="填已有设定集名，或输入新名字（即新建）"
          />
        </el-form-item>
        <el-form-item label="条目 ID">
          <el-input
            v-model="entryForm.entryId"
            :disabled="!!editingEntry"
            data-testid="form-entry-id"
            placeholder="留空自动生成"
          />
        </el-form-item>
        <el-form-item label="触发关键词">
          <el-select
            v-model="entryForm.keys"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入关键词，回车添加"
            data-testid="form-keys"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="类型">
          <el-select
            v-model="entryForm.category"
            data-testid="form-category"
            placeholder="选择类型"
            style="width: 100%"
          >
            <el-option v-for="o in categoryOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="设定内容">
          <el-input v-model="entryForm.content" type="textarea" :rows="6" data-testid="form-content" />
        </el-form-item>
        <el-form-item label="优先级（越大越先注入）">
          <el-input v-model.number="entryForm.priority" type="number" />
        </el-form-item>
        <el-form-item label="启用（停用后不参与关键词触发）">
          <el-checkbox v-model="entryForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="editingEntry" type="danger" plain data-testid="delete-entry" @click="removeEntry">
          删除条目
        </el-button>
        <el-button @click="showEditor = false">取消</el-button>
        <el-button type="primary" data-testid="save-entry" @click="saveEntry">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * 世界观页（N8 方案 A）：**设定集按小说绑定**，走 `/api/novel/{id}/lorebooks`。
 *
 * 改之前这一页是**两处虚构**：
 *   1. 「条目」tab 的 `entries` 是页面内写死的数组（一条「盖亚大陆」），刷新即丢；
 *   2. 「地图」tab 打的是 `/novel/current/map`，而服务端没有 `current` 这个概念 →
 *      拿 `novel_id="current"` 找书 → 404，还被空 catch 静默吞掉 —— 读写其实都是坏的。
 *
 * 本版的三条约定：
 *   - **左侧分类 = 本书的设定集名**（动态）。原来写死的六个分类（地理/历史/魔法/势力/人物/其他）
 *     退役：「类型」维度是方案 B 的议题（见 `docs/design/P7-MVP-PLAN.md` 第四切片），
 *     不在这里偷偷加字段。
 *   - 编辑态**不允许改设定集名与条目 ID**（输入框禁用）：删旧建新那类「静默吃掉另一条」
 *     的坑本项目已经踩过两次（N9 伏笔、素材库同名），这里从交互上关掉。
 *   - 地图图片只在本机预览、**未上传**，界面必须说清（后端 `/map/image` 目前是占位）。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Collection, Folder, Location, Picture, Plus } from '@element-plus/icons-vue'
import {
  createNovelLorebook,
  deleteNovelLorebook,
  errorDetail,
  fetchNovelLorebooks,
  fetchNovelMap,
  fetchNovels,
  saveNovelMap,
  updateNovelLorebook,
  type ApiLorebook,
  type ApiLorebookEntry,
  type ApiMapMarker,
  type NovelBrief,
} from '../utils/api'
import { useNovelStore } from '../stores/novel'

const novelStore = useNovelStore()

const novels = ref<NovelBrief[]>([])
const novelId = ref('')
const books = ref<ApiLorebook[]>([])
const errorMsg = ref('')

/** 记住作者上次选的书（与角色卡页共用同一个键，切页回来还是同一本） */
const LAST_NOVEL_KEY = 'story_last_novel'

function rememberNovel(id: string) {
  if (id && typeof localStorage !== 'undefined') localStorage.setItem(LAST_NOVEL_KEY, id)
}

// ── Tab ──
const activeTab = ref('entries')

// ── 条目（摊平本书全部设定集的条目；左侧按设定集过滤）──
interface FlatEntry {
  key: string
  bookName: string
  entryId: string
  keys: string[]
  content: string
  priority: number
  enabled: boolean
  /** 原样带着后端字段：编辑保存时**必须原样写回**，否则会被后端默认值打回（评审 P0-1） */
  category: string
  position: string
}

const activeCategory = ref('all')

/**
 * 条目「类型」取值表 —— 与后端 `src/story_engine/lore/categories.py::CATEGORY_LABELS`
 * **必须一致**（后端是唯一定义处：它的 `PLACE_CATEGORIES` 还决定哪些类型算"地名"、
 * 会进 `POST /{id}/analyze/consistency` 的一致性校验）。两边一旦漂移就会出现
 * "填了却不生效"的静默失效，所以后端 `TestCategoryVocabulary` 与
 * `e2e/worldview.e2e.ts` 各钉一道。
 */
const CATEGORY_OPTIONS = [
  { value: '地点', label: '地点' },
  { value: '物品', label: '物品' },
  { value: '规则', label: '规则' },
  { value: '势力', label: '势力' },
  { value: '世界观', label: '世界观' },
  { value: 'general', label: '其他' },
] as const

/** 与磁盘模型默认值一致：老条目（含第四切片之前建的）都是这个值，显示为「其他」，无需迁移 */
const DEFAULT_CATEGORY = 'general'

/**
 * 卡片/下拉上的显示文案。**未知取值原样返回**（历史数据里有「地理」「灵兽」这类
 * 不在 UI 表里的值）—— 兜底成「其他」会让同一条目在一屏里有三种身份：
 * 卡片显示「其他」、点「其他」过滤又找不到它、进编辑器却写着「地理（原有取值）」
 * （第五切片评审 P1-2）。
 */
function categoryLabel(value?: string): string {
  const hit = CATEGORY_OPTIONS.find((o) => o.value === value)
  if (hit) return hit.label
  return value && value.trim() ? value : '其他'
}

/** 类型过滤（'all' = 不按类型筛；与左侧「设定集」是两个独立的维度） */
const activeType = ref('all')

const flatEntries = computed<FlatEntry[]>(() =>
  books.value.flatMap((b) =>
    Object.entries(b.entries || {}).map(([entryId, e]) => ({
      key: `${b.name}::${entryId}`,
      bookName: b.name,
      entryId,
      keys: e.keys || [],
      content: e.content || '',
      priority: e.priority ?? 50,
      enabled: e.enabled !== false,
      category: e.category || 'general',
      position: e.position || 'after_char',
    })),
  ),
)

const filteredEntries = computed(() =>
  (
    activeCategory.value === 'all'
      ? flatEntries.value
      : flatEntries.value.filter((e) => e.bookName === activeCategory.value)
  ).filter((e) => activeType.value === 'all' || e.category === activeType.value),
)

/**
 * 过滤行用的类型清单 = UI 表 + **数据里实际出现的**未知取值（历史数据，如「地理」）。
 * 不把未知取值塞进「其他」桶：卡片标签按原值显示，过滤就必须能用同一个原值筛，
 * 否则又是"显示一种身份、过滤另一种身份"（第五切片评审 P1-2）。
 */
const filterTypes = computed(() => {
  const opts = CATEGORY_OPTIONS.map((o) => ({ value: o.value as string, label: o.label as string }))
  const seen = new Set(opts.map((o) => o.value))
  for (const e of flatEntries.value) {
    if (e.category && !seen.has(e.category)) {
      opts.push({ value: e.category, label: e.category })
      seen.add(e.category)
    }
  }
  return opts
})

/** 空态不能只说"暂无条目"：可能只是被筛选挡住了（第五切片评审 P2-2） */
const emptyDescription = computed(() => {
  if (!novelId.value) return '先选一本小说'
  if (flatEntries.value.length === 0) return '暂无条目'
  const dims = [activeCategory.value !== 'all' ? '设定集' : '', activeType.value !== 'all' ? '类型' : '']
  return `当前筛选（${dims.filter(Boolean).join(' + ')}）下没有条目 —— 试试「全部」或「全部类型」`
})

/** 回到"不筛"：两个过滤一起复位，避免只清一个导致列表恒空（第五切片评审 P2-2） */
function resetFilters() {
  activeCategory.value = 'all'
  activeType.value = 'all'
}

const showEditor = ref(false)
/** 编辑态用**结构化**身份，不用 `book::entry` 拼串再 split —— 名字里含 `::` 就解析错位（评审 P2-6） */
const editingBook = ref<string | null>(null)
const editingEntry = ref<string | null>(null)
/** 编辑前的原始条目：保存时以它为底合并，保证表单没暴露的后端字段（category/position）原样写回（评审 P0-1） */
const editingSnapshot = ref<ApiLorebookEntry | null>(null)
const entryForm = reactive({
  bookName: '',
  entryId: '',
  keys: [] as string[],
  content: '',
  priority: 50,
  enabled: true,
  category: DEFAULT_CATEGORY,
})

/**
 * 下拉选项：UI 的五个类型 + 「其他」。**编辑老条目时把它的原值也列进来** ——
 * 后端历史数据里有「地理」这类不在 UI 表里的取值，若下拉显示不出来、用户一保存就被
 * 改成「其他」，等于静默改写别人的数据（与评审 P0-1 同一类病）。
 */
const categoryOptions = computed(() => {
  const opts: { value: string; label: string }[] = CATEGORY_OPTIONS.map((o) => ({ ...o }))
  const cur = entryForm.category
  if (cur && !opts.some((o) => o.value === cur)) {
    opts.push({ value: cur, label: `${cur}（原有取值）` })
  }
  return opts
})

function resetEditor() {
  editingBook.value = null
  editingEntry.value = null
  editingSnapshot.value = null
}

function startNewEntry() {
  resetEditor()
  Object.assign(entryForm, {
    bookName: activeCategory.value !== 'all' ? activeCategory.value : books.value[0]?.name || '',
    entryId: '',
    keys: [],
    content: '',
    priority: 50,
    enabled: true,
    category: DEFAULT_CATEGORY,
  })
  showEditor.value = true
}

function editEntry(entry: FlatEntry) {
  editingBook.value = entry.bookName
  editingEntry.value = entry.entryId
  editingSnapshot.value =
    books.value.find((b) => b.name === entry.bookName)?.entries?.[entry.entryId] || null
  Object.assign(entryForm, {
    bookName: entry.bookName,
    entryId: entry.entryId,
    keys: [...entry.keys],
    content: entry.content,
    priority: entry.priority,
    enabled: entry.enabled,
    // 带上原值（含 UI 表里没有的历史取值），下拉会把它作为一个选项列出来
    category: entry.category || DEFAULT_CATEGORY,
  })
  showEditor.value = true
}

async function saveEntry() {
  if (!novelId.value) {
    ElMessage.warning('先选一本小说')
    return
  }
  const bookName = entryForm.bookName.trim()
  if (!bookName) {
    ElMessage.warning('设定集名不能为空')
    return
  }
  const entryId = (entryForm.entryId || '').trim() || `e${Date.now().toString(36)}`
  const existing = books.value.find((b) => b.name === bookName)
  const book: ApiLorebook = {
    name: bookName,
    description: existing?.description || '',
    entries: { ...(existing?.entries || {}) },
  }
  // 以**原条目**为底合并：`category`/`position` 这类表单没暴露的后端字段必须原样带回去。
  // 否则 PUT 整本会让它们被打回默认值 —— category 还被地名一致性校验依赖（评审 P0-1）。
  book.entries[entryId] = {
    ...(editingBook.value === bookName ? editingSnapshot.value || {} : {}),
    ...(existing?.entries?.[entryId] || {}),
    keys: entryForm.keys,
    content: entryForm.content,
    priority: Number(entryForm.priority) || 50,
    enabled: entryForm.enabled,
    category: entryForm.category || DEFAULT_CATEGORY,
  }
  const savedCategory = entryForm.category || DEFAULT_CATEGORY
  try {
    if (existing) await updateNovelLorebook(novelId.value, bookName, book)
    else await createNovelLorebook(novelId.value, book)
    showEditor.value = false
    resetEditor()
    // 存下来的这条会不会被**当前筛选**挡住（类型或设定集）？挡住就切回「全部」并说清，
    // 否则作者看到"已保存"却在列表里找不到刚存的条目（第五切片评审 P2-1）
    const hiddenByType = activeType.value !== 'all' && activeType.value !== savedCategory
    const hiddenByBook = activeCategory.value !== 'all' && activeCategory.value !== bookName
    if (hiddenByType || hiddenByBook) resetFilters()
    await loadBooks()
    ElMessage.success(
      hiddenByType || hiddenByBook
        ? '已保存（已切回「全部」，否则这条会被当前筛选挡住）'
        : '已保存',
    )
  } catch (e: any) {
    ElMessage.error(errorDetail(e, '保存失败'))
  }
}

async function removeEntry() {
  if (!editingBook.value || !editingEntry.value || !novelId.value) return
  const bookName = editingBook.value
  const entryId = editingEntry.value
  const book = books.value.find((b) => b.name === bookName)
  if (!book) return
  const remaining = Object.keys(book.entries).filter((k) => k !== entryId)
  const lastOne = remaining.length === 0
  try {
    // 删条目也要确认；「最后一条会连带删掉整个设定集」必须**单独说清**（评审 P1-2：
    // 原来删条目无确认，且删最后一条会连整本一起删却只提示「已删除」）
    await ElMessageBox.confirm(
      lastOne
        ? `「${entryId}」是「${bookName}」的最后一条条目，删除后这个设定集也会一起消失。`
        : `删除条目「${entryId}」？`,
      '确认删除',
      { type: 'warning' },
    )
  } catch {
    return // 作者取消
  }
  const entries = { ...book.entries }
  delete entries[entryId]
  try {
    // 最后一个条目被删掉 → 整本设定集也没意义了，一起删（不然留个空壳）
    if (lastOne) await deleteNovelLorebook(novelId.value, bookName)
    else await updateNovelLorebook(novelId.value, bookName, { ...book, entries })
    showEditor.value = false
    resetEditor()
    // 该设定集已消失 → 过滤条件要回退，否则左栏没有这一项、列表恒空（评审 P1-3）
    if (lastOne && activeCategory.value === bookName) resetFilters()
    await loadBooks()
    ElMessage.success(lastOne ? `已删除条目与设定集「${bookName}」` : '已删除')
  } catch (e: any) {
    ElMessage.error(errorDetail(e, '删除失败'))
  }
}

async function removeLorebook() {
  if (!novelId.value || activeCategory.value === 'all') return
  const name = activeCategory.value
  try {
    await ElMessageBox.confirm(`删除设定集「${name}」？它的全部条目都会一起没。`, '确认删除', {
      type: 'warning',
    })
  } catch {
    return // 作者取消
  }
  try {
    await deleteNovelLorebook(novelId.value, name)
    resetFilters()
    await loadBooks()
    ElMessage.success('已删除')
  } catch (e: any) {
    ElMessage.error(errorDetail(e, '删除失败'))
  }
}

// ── 加载 ──
async function loadBooks() {
  if (!novelId.value) {
    books.value = []
    return
  }
  try {
    books.value = await fetchNovelLorebooks(novelId.value)
    errorMsg.value = ''
  } catch (e: any) {
    books.value = []
    errorMsg.value = errorDetail(e, '读取设定集失败')
  }
}

onMounted(async () => {
  try {
    novels.value = await fetchNovels()
  } catch (e: any) {
    errorMsg.value = e?.message || '读取小说列表失败'
    return
  }
  // 选书优先级与角色卡页一致（三级）：写作页当前那本 > 上次记住的 > **最近更新的那本**。
  // 第三级要**显式按 updated 排序** —— 不能依赖 `list_novels()` 恰好按 updated 倒序返回，
  // 那是隐式依赖后端排序，后端一换序就漂移（评审 P2-4；CharactersView 是显式排的）。
  const remembered =
    typeof localStorage !== 'undefined' ? localStorage.getItem(LAST_NOVEL_KEY) || '' : ''
  const preferred = novelStore.currentNovel?.id || ''
  const byRecency = [...novels.value].sort((a, b) =>
    String(b.updated || '').localeCompare(String(a.updated || '')),
  )
  const ids = byRecency.map((n) => n.id)
  novelId.value = [preferred, remembered].find((id) => id && ids.includes(id)) || ids[0] || ''
})

// novelId 变化 → 记住 + 清**两个**过滤（设定集 + 类型）+ 清地图状态 + 重新拉
// （原来是手挂在 @change 上，容易漏；注释原先写"清过滤"却只清了 activeCategory，评审 P2-2）
watch(novelId, (id) => {
  if (!id) return
  rememberNovel(id)
  resetFilters()
  books.value = []
  // 地图状态必须随手一起清：否则从 A 书切到 B 书后仍显示 A 的图与标记，
  // 保存时还会把 A 的 image_path 写进 B（跨书污染，评审 P1-1）
  resetMapState()
  loadBooks()
})

// ── 地图（带 novel_id；失败不再静默）──
const mapImage = ref('')
const markers = ref<ApiMapMarker[]>([])
const mapNotice = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const mapWrapper = ref<HTMLElement | null>(null)
const saving = ref(false)
const saved = ref(false)
const selectedMarkerId = ref<string | null>(null)
const newMarkerPos = ref<{ x: number; y: number } | null>(null)
const newMarkerForm = reactive({ name: '', description: '' })

const selectedMarker = computed(
  () => markers.value.find((m) => m.id === selectedMarkerId.value) || null,
)

watch([novelId, activeTab], ([id, tab]) => {
  if (id && tab === 'map') loadMapData()
})

function selectMapImage() {
  fileInput.value?.click()
}

/** 清空一切与"当前这本书的地图"绑定的状态（切书时用，评审 P1-1） */
function resetMapState() {
  mapImage.value = ''
  markers.value = []
  selectedMarkerId.value = null
  newMarkerPos.value = null
  saved.value = false
  mapNotice.value = ''
}

function onImageSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  mapImage.value = URL.createObjectURL(file)
  saved.value = false // 换了图 → 上一次的"已保存"不再成立（评审 P2-8）
}

function onMapClick(e: MouseEvent) {
  if (!mapWrapper.value) return
  const rect = mapWrapper.value.getBoundingClientRect()
  newMarkerPos.value = {
    x: ((e.clientX - rect.left) / rect.width) * 100,
    y: ((e.clientY - rect.top) / rect.height) * 100,
  }
  newMarkerForm.name = ''
  newMarkerForm.description = ''
  selectedMarkerId.value = null
}

function addMarker() {
  if (!newMarkerPos.value || !newMarkerForm.name.trim()) return
  markers.value.push({
    id: crypto.randomUUID(),
    name: newMarkerForm.name.trim(),
    x: newMarkerPos.value.x,
    y: newMarkerPos.value.y,
    description: newMarkerForm.description,
  })
  newMarkerPos.value = null
  saved.value = false
}

function selectMarker(m: ApiMapMarker) {
  selectedMarkerId.value = m.id
  newMarkerPos.value = null
}

function deleteMarker() {
  if (!selectedMarkerId.value) return
  markers.value = markers.value.filter((m) => m.id !== selectedMarkerId.value)
  selectedMarkerId.value = null
  saved.value = false
}

async function loadMapData() {
  if (!novelId.value) return
  try {
    const data = await fetchNovelMap(novelId.value)
    // 先清后赋：`image_path` 为空时也必须把上一本书的图清掉（评审 P1-1）
    mapImage.value = data.image_path || ''
    markers.value = data.markers || []
    selectedMarkerId.value = null
    newMarkerPos.value = null
    saved.value = false
    mapNotice.value = ''
  } catch (e: any) {
    // 旧实现这里是空 catch：地图坏了但界面看不出来。现在报出来。
    mapNotice.value = `地图读取失败：${errorDetail(e, '未知错误')}`
    ElMessage.error(mapNotice.value)
  }
}

async function saveMapData() {
  if (!novelId.value) {
    ElMessage.warning('先选一本小说')
    return
  }
  saving.value = true
  saved.value = false
  try {
    await saveNovelMap(novelId.value, {
      // blob: 是本机临时地址，存进服务端没有意义（换个会话就失效）→ 不写它
      image_path: mapImage.value.startsWith('blob:') ? '' : mapImage.value,
      markers: markers.value.map((m) => ({
        id: m.id,
        name: m.name,
        x: m.x,
        y: m.y,
        lore_entry_id: m.lore_entry_id || '',
        description: m.description || '',
      })),
    })
    saved.value = true
    mapNotice.value = ''
    ElMessage.success('地图标记已保存')
  } catch (e: any) {
    mapNotice.value = `地图保存失败：${errorDetail(e, '未知错误')}`
    ElMessage.error(mapNotice.value)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.world-view { padding: 0; }
.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.view-header h3 { margin: 0; font-size: 18px; }
.header-actions { display: flex; align-items: center; gap: 8px; }
.err { color: var(--el-color-danger); font-size: 13px; margin: 0 0 8px; }
.hint { font-size: 13px; color: var(--el-text-color-secondary); margin: 0 0 8px; }
.hint.small { font-size: 12px; padding: 8px; }
.world-tabs { min-height: 400px; }
.world-content { display: flex; gap: 20px; }
.world-categories { width: 180px; min-width: 180px; }
.world-categories .el-menu { border-right: none; }
.world-entries { flex: 1; display: flex; flex-direction: column; gap: 12px; }
.type-filter { display: flex; flex-wrap: wrap; gap: 6px; }
.entry-card {
  padding: 14px; background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light); border-radius: 8px;
  cursor: pointer; transition: all 0.2s;
}
.entry-card:hover { border-color: var(--el-color-primary); }
.entry-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.entry-name { font-weight: 600; font-size: 15px; }
.entry-priority { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }
.entry-keys { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px; }
.entry-content { font-size: 13px; color: var(--el-text-color-regular); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.entries-empty { display: flex; justify-content: center; padding: 40px 0; }

/* 地图 */
.map-container { max-width: 800px; }
.map-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.save-hint { font-size: 12px; color: #52c41a; }
.map-placeholder {
  border: 2px dashed var(--el-border-color); border-radius: 12px;
  padding: 60px 20px; text-align: center; cursor: pointer;
  color: var(--el-text-color-secondary); transition: all 0.2s;
}
.map-placeholder:hover { border-color: var(--el-color-primary); color: var(--el-color-primary); }
.map-placeholder .hint { font-size: 12px; margin-top: 4px; }
.map-image-wrapper {
  position: relative; display: inline-block; cursor: crosshair;
  border: 1px solid var(--el-border-color-light); border-radius: 8px; overflow: hidden;
}
.map-image { display: block; max-width: 100%; height: auto; }
.map-marker {
  position: absolute; transform: translate(-50%, -50%); cursor: pointer; z-index: 10;
}
.marker-pin { color: #e74c3c; font-size: 20px; text-align: center; transition: all 0.2s; }
.marker-pin.active { color: #f5222d; font-size: 26px; }
.marker-label {
  position: absolute; left: 50%; top: 100%; transform: translateX(-50%);
  white-space: nowrap; font-size: 11px; background: rgba(0,0,0,0.7); color: #fff;
  padding: 1px 6px; border-radius: 3px; margin-top: 2px;
}
.marker-editor, .new-marker-form {
  margin-top: 16px; padding: 16px; background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light); border-radius: 8px; max-width: 400px;
}
.marker-editor h4, .new-marker-form h4 { margin: 0 0 12px; font-size: 14px; }
.marker-actions { display: flex; gap: 8px; }
</style>
