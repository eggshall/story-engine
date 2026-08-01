
<template>
  <div class="world-view">
    <div class="view-header">
      <h3>世界观设定</h3>
      <el-button v-if="activeTab === 'entries'" type="primary" :icon="Plus" @click="showEditor = true">新建条目</el-button>
    </div>

    <el-tabs v-model="activeTab" class="world-tabs">
      <el-tab-pane label="条目" name="entries">
        <div class="world-content">
          <div class="world-categories">
            <el-menu :default-active="activeCategory" @select="(i: string) => activeCategory = i">
              <el-menu-item index="all">
                <el-icon><Folder /></el-icon><span>全部</span>
              </el-menu-item>
              <el-menu-item index="地理">
                <el-icon><Location /></el-icon><span>地理</span>
              </el-menu-item>
              <el-menu-item index="历史">
                <el-icon><Timer /></el-icon><span>历史</span>
              </el-menu-item>
              <el-menu-item index="魔法">
                <el-icon><MagicStick /></el-icon><span>魔法/能力</span>
              </el-menu-item>
              <el-menu-item index="势力">
                <el-icon><OfficeBuilding /></el-icon><span>势力</span>
              </el-menu-item>
              <el-menu-item index="人物">
                <el-icon><UserFilled /></el-icon><span>人物</span>
              </el-menu-item>
            </el-menu>
          </div>
          <div class="world-entries">
            <div v-for="entry in filteredEntries" :key="entry.id" class="entry-card" @click="editEntry(entry)">
              <div class="entry-header">
                <span class="entry-name">{{ entry.name }}</span>
                <el-tag size="small">{{ entry.category }}</el-tag>
              </div>
              <div class="entry-keys">
                <el-tag v-for="k in entry.keys" :key="k" size="small" type="info" round>{{ k }}</el-tag>
              </div>
              <div class="entry-content">{{ entry.content }}</div>
            </div>
            <div v-if="filteredEntries.length === 0" class="entries-empty">
              <el-empty description="暂无条目" />
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="地图" name="map">
        <div class="map-container">
          <div class="map-toolbar">
            <el-button size="small" type="primary" @click="selectMapImage">上传地图</el-button>
            <el-button size="small" @click="saveMapData" :loading="saving" :disabled="!mapImage">保存标记</el-button>
            <span v-if="saved" class="save-hint">已保存</span>
            <input
              ref="fileInput"
              type="file"
              accept="image/*"
              style="display:none"
              @change="onImageSelected"
            />
          </div>

          <div v-if="!mapImage" class="map-placeholder" @click="selectMapImage">
            <el-icon :size="48"><Picture /></el-icon>
            <p>点击上传地图图片</p>
            <p class="hint">支持 JPG / PNG 格式</p>
          </div>

          <div v-else class="map-area">
            <div class="map-image-wrapper" ref="mapWrapper" @click="onMapClick">
              <img :src="mapImage" alt="世界地图" class="map-image" />
              <div
                v-for="m in markers"
                :key="m.id"
                class="map-marker"
                :style="{ left: m.x + '%', top: m.y + '%' }"
                @click.stop="selectMarker(m)"
                :title="m.name"
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
                    v-for="e in entries"
                    :key="e.id"
                    :label="e.name"
                    :value="e.id"
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
    <el-dialog v-model="showEditor" title="新建/编辑条目" width="500px">
      <el-form :model="entryForm" label-position="top">
        <el-form-item label="条目名称" required>
          <el-input v-model="entryForm.name" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="entryForm.category" style="width: 100%">
            <el-option label="地理" value="地理" />
            <el-option label="历史" value="历史" />
            <el-option label="魔法/能力" value="魔法" />
            <el-option label="势力" value="势力" />
            <el-option label="人物" value="人物" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="触发关键词">
          <el-select v-model="entryForm.keys" multiple filterable allow-create default-first-option
            placeholder="输入关键词，回车添加" style="width: 100%" />
        </el-form-item>
        <el-form-item label="设定内容">
          <el-input v-model="entryForm.content" type="textarea" :rows="6" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditor = false">取消</el-button>
        <el-button type="primary" @click="saveEntry">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Plus, Folder, Location, Timer, MagicStick, OfficeBuilding, UserFilled, Picture,
} from '@element-plus/icons-vue'
import api from '../utils/api'

interface LoreEntry {
  id: string
  name: string
  category: string
  keys: string[]
  content: string
}

interface MapMarker {
  id: string
  name: string
  x: number
  y: number
  lore_entry_id?: string
  description?: string
}

// ── Tab ──
const activeTab = ref('entries')

// ── 条目 ──
const entries = ref<LoreEntry[]>([
  { id: '1', name: '盖亚大陆', category: '地理', keys: ['大陆', '盖亚'], content: '故事发生的主要大陆，由五大王国统治。' },
])
const activeCategory = ref('all')
const showEditor = ref(false)
const editingId = ref<string | null>(null)
const entryForm = reactive({ name: '', category: '其他', keys: [] as string[], content: '' })

const filteredEntries = computed(() => {
  if (activeCategory.value === 'all') return entries.value
  return entries.value.filter((e) => e.category === activeCategory.value)
})

function editEntry(entry: LoreEntry) {
  editingId.value = entry.id
  Object.assign(entryForm, { name: entry.name, category: entry.category, keys: [...entry.keys], content: entry.content })
  showEditor.value = true
}

function saveEntry() {
  if (!entryForm.name) return
  if (editingId.value) {
    const idx = entries.value.findIndex((e) => e.id === editingId.value)
    if (idx >= 0) entries.value[idx] = { id: editingId.value, ...entryForm }
  } else {
    entries.value.push({ id: crypto.randomUUID(), ...entryForm })
  }
  showEditor.value = false
  editingId.value = null
  entryForm.name = ''
  entryForm.category = '其他'
  entryForm.keys = []
  entryForm.content = ''
}

// ── 地图 ──
const mapImage = ref('')
const markers = ref<MapMarker[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const mapWrapper = ref<HTMLElement | null>(null)
const saving = ref(false)
const saved = ref(false)
const selectedMarkerId = ref<string | null>(null)
const newMarkerPos = ref<{ x: number; y: number } | null>(null)
const newMarkerForm = reactive({ name: '', description: '' })

const selectedMarker = computed(() => markers.value.find(m => m.id === selectedMarkerId.value) || null)

function selectMapImage() {
  fileInput.value?.click()
}

function onImageSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const url = URL.createObjectURL(file)
  mapImage.value = url
  // Auto-load existing map data for this novel
  loadMapData()
}

function onMapClick(e: MouseEvent) {
  if (!mapWrapper.value) return
  const rect = mapWrapper.value.getBoundingClientRect()
  const x = ((e.clientX - rect.left) / rect.width) * 100
  const y = ((e.clientY - rect.top) / rect.height) * 100
  newMarkerPos.value = { x, y }
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

function selectMarker(m: MapMarker) {
  selectedMarkerId.value = m.id
  newMarkerPos.value = null
}

function deleteMarker() {
  if (!selectedMarkerId.value) return
  markers.value = markers.value.filter(m => m.id !== selectedMarkerId.value)
  selectedMarkerId.value = null
  saved.value = false
}

async function loadMapData() {
  try {
    const res = await api.get('/novel/current/map')
    const data = res.data?.data || res.data
    if (data?.markers?.length) {
      markers.value = data.markers
    }
    if (data?.image_path && !mapImage.value) {
      mapImage.value = data.image_path
    }
  } catch { /* 忽略 */ }
}

async function saveMapData() {
  saving.value = true
  saved.value = false
  try {
    await api.post('/novel/current/map', {
      image_path: mapImage.value,
      markers: markers.value.map(m => ({
        id: m.id,
        name: m.name,
        x: m.x,
        y: m.y,
        lore_entry_id: m.lore_entry_id || '',
        description: m.description || '',
      })),
    })
    saved.value = true
    ElMessage.success('地图标记已保存')
  } catch (err: any) {
    ElMessage.error(`保存失败: ${err.message}`)
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
.world-tabs { min-height: 400px; }
.world-content { display: flex; gap: 20px; }
.world-categories { width: 180px; min-width: 180px; }
.world-categories .el-menu { border-right: none; }
.world-entries { flex: 1; display: flex; flex-direction: column; gap: 12px; }
.entry-card {
  padding: 14px; background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light); border-radius: 8px;
  cursor: pointer; transition: all 0.2s;
}
.entry-card:hover { border-color: var(--el-color-primary); }
.entry-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.entry-name { font-weight: 600; font-size: 15px; }
.entry-keys { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px; }
.entry-content { font-size: 13px; color: var(--el-text-color-regular); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.entries-empty { display: flex; justify-content: center; padding: 40px 0; }

/* 地图 */
.map-container { max-width: 800px; }
.map-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
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
