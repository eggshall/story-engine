\n<template>
  <div class="outline-view">
    <div class="view-header">
      <h3>大纲管理</h3>
      <div class="header-actions">
        <el-select v-model="selectedNovelId" placeholder="选择小说" style="width: 200px; margin-right: 8px">
          <el-option v-for="n in novelStore.novels" :key="n.id" :label="n.title" :value="n.id" />
        </el-select>
        <el-button type="primary" :icon="MagicStick" :loading="generating" @click="generateOutline">
          生成大纲
        </el-button>
        <el-button :icon="Plus" @click="addChapter">添加章节</el-button>
      </div>
    </div>

    <div v-if="!selectedNovelId" class="outline-empty">
      <el-empty description="选择一部小说查看大纲" />
    </div>

    <div v-else class="outline-content">
      <!-- 左侧：章节树 -->
      <div class="outline-tree">
        <div
          v-for="(ch, idx) in chapters"
          :key="ch.number"
          :class="['chapter-item', { active: selectedChapter?.number === ch.number }]"
          @click="selectChapter(ch.number)"
        >
          <div class="chapter-number">第{{ ch.number }}章</div>
          <div class="chapter-title">{{ ch.title || '未命名' }}</div>
          <el-button size="small" text :icon="Delete" @click.stop="removeChapter(idx)" />
        </div>
      </div>

      <!-- 右侧：章节详情 -->
      <div class="outline-detail" v-if="selectedChapter">
        <el-form label-position="top">
          <el-form-item label="章节标题">
            <el-input v-model="selectedChapter.title" />
          </el-form-item>
          <el-form-item label="概要">
            <el-input v-model="selectedChapter.summary" type="textarea" :rows="4" />
          </el-form-item>
          <el-form-item label="剧情节点">
            <el-input
              v-model="selectedChapter.beats"
              type="textarea"
              :rows="6"
              placeholder="每行一个剧情节点 / 场景"
            />
          </el-form-item>
          <el-form-item label="关键词">
            <el-select
              v-model="selectedChapter.keywords"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="输入关键词"
              style="width: 100%"
            >
              <el-option v-for="kw in selectedChapter.keywords" :key="kw" :label="kw" :value="kw" />
            </el-select>
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { MagicStick, Plus, Delete } from '@element-plus/icons-vue'
import { useNovelStore } from '../stores/novel'
import { generateOutlineStream } from '../utils/api'

const novelStore = useNovelStore()
const selectedNovelId = ref('')
const generating = ref(false)

interface ChapterOutline {
  number: number
  title: string
  summary: string
  beats: string
  keywords: string[]
}

const chapters = ref<ChapterOutline[]>([])
const selectedChapter = computed(() =>
  chapters.value.find((c) => c.number === selectedChapterNumber.value)
)
const selectedChapterNumber = ref(1)

function selectChapter(n: number) {
  selectedChapterNumber.value = n
}

function addChapter() {
  const num = chapters.value.length + 1
  chapters.value.push({
    number: num,
    title: '',
    summary: '',
    beats: '',
    keywords: [],
  })
  selectedChapterNumber.value = num
}

function removeChapter(idx: number) {
  chapters.value.splice(idx, 1)
  chapters.value.forEach((c, i) => (c.number = i + 1))
}

async function generateOutline() {
  if (!selectedNovelId.value) return
  generating.value = true
  try {
    chapters.value = []
    for await (const token of generateOutlineStream({ novel_id: selectedNovelId.value })) {
      // 逐步累积
    }
  } finally {
    generating.value = false
  }
}

watch(selectedNovelId, () => {
  chapters.value = []
  selectedChapterNumber.value = 1
})
</script>

<style scoped>
.outline-view {
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
.header-actions {
  display: flex;
  align-items: center;
}
.outline-empty {
  display: flex;
  justify-content: center;
  padding: 60px 0;
}
.outline-content {
  display: flex;
  gap: 20px;
}
.outline-tree {
  width: 260px;
  min-width: 260px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.chapter-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  cursor: pointer;
  gap: 8px;
  transition: all 0.2s;
}
.chapter-item:hover, .chapter-item.active {
  border-color: var(--el-color-primary);
}
.chapter-number {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.chapter-title {
  flex: 1;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.outline-detail {
  flex: 1;
  background: var(--el-bg-color);
  padding: 20px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-light);
}
</style>
