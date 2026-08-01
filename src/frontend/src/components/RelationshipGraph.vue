<template>
  <div class="relationship-graph">
    <div class="graph-toolbar">
      <div class="toolbar-left">
        <span class="graph-title">人物关系图谱</span>
        <el-tag size="small" type="info">{{ characters.length }} 个角色</el-tag>
        <el-tag size="small" type="success">{{ links.length }} 条关系</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :icon="Refresh" @click="resetGraph">重置视图</el-button>
      </div>
    </div>

    <div ref="chartRef" class="graph-canvas" />

    <!-- 角色详情弹窗 -->
    <el-dialog v-model="showDetail" :title="detailChar?.name || ''" width="480px">
      <template v-if="detailChar">
        <div class="detail-header">
          <el-avatar :size="56" :style="{ backgroundColor: getColorByTag(detailChar.tags) }">
            {{ detailChar.name.charAt(0) }}
          </el-avatar>
          <div class="detail-meta">
            <div class="detail-tags">
              <el-tag v-for="t in detailChar.tags" :key="t" size="small" round>{{ t }}</el-tag>
            </div>
          </div>
        </div>
        <el-descriptions :column="1" border size="small" class="detail-body">
          <el-descriptions-item label="描述">{{ detailChar.description || '暂无' }}</el-descriptions-item>
          <el-descriptions-item label="性格">{{ detailChar.personality || '暂无' }}</el-descriptions-item>
          <el-descriptions-item label="外貌">{{ detailChar.appearance || '暂无' }}</el-descriptions-item>
          <el-descriptions-item label="背景">{{ detailChar.background || '暂无' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="detailRelations.length" class="detail-relations">
          <h4>关系纽带</h4>
          <div v-for="r in detailRelations" :key="r.target" class="relation-item">
            <span class="relation-label">{{ r.relation }}</span>
            <el-tag size="small" round>{{ getCharName(r.target) }}</el-tag>
            <span class="relation-desc">{{ r.description }}</span>
          </div>
        </div>
      </template>
      <template #footer>
        <el-button type="primary" @click="showDetail = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { Refresh } from '@element-plus/icons-vue'
import type { CharacterCard } from '../stores/characters'

const props = defineProps<{
  characters: CharacterCard[]
}>()

defineEmits<{
  select: [id: string]
}>()

const chartRef = ref<HTMLDivElement>()
const showDetail = ref(false)
const detailChar = ref<CharacterCard | null>(null)
let chart: echarts.ECharts | null = null

// 计算节点和边
interface GraphNode extends echarts.GraphNode {
  id: string
  name: string
  symbolSize: number
  itemStyle: { color: string }
  category: number
}

interface GraphLink extends echarts.GraphEdge {
  source: string
  target: string
  label: { show: boolean; formatter: string }
  lineStyle: { width: number }
}

// 标签 → 颜色映射
const tagColorMap: Record<string, string> = {
  '主角': '#F5A623',
  '配角': '#4A90D9',
  '反派': '#D94A4A',
  '路人': '#999999',
}

function getColorByTag(tags: string[]): string {
  for (const t of tags) {
    if (tagColorMap[t]) return tagColorMap[t]
  }
  return '#7B68EE' // default purple
}

const links = computed(() => {
  const seen = new Set<string>()
  const result: GraphLink[] = []
  for (const char of props.characters) {
    for (const rel of char.relationships) {
      const key = [char.id, rel.target].sort().join('_')
      if (!seen.has(key)) {
        seen.add(key)
        result.push({
          source: char.id,
          target: rel.target,
          label: { show: true, formatter: rel.relation, fontSize: 10 },
          lineStyle: { width: 2 },
        })
      }
    }
  }
  return result
})

function buildNodes() {
  const charIds = new Set(props.characters.map((c) => c.id))
  const linkCount = new Map<string, number>()
  for (const char of props.characters) {
    for (const rel of char.relationships) {
      if (charIds.has(rel.target)) {
        linkCount.set(char.id, (linkCount.get(char.id) || 0) + 1)
        linkCount.set(rel.target, (linkCount.get(rel.target) || 0) + 1)
      }
    }
  }

  const maxLinks = Math.max(1, ...linkCount.values())
  return props.characters.map((char) => ({
    id: char.id,
    name: char.name,
    symbolSize: 30 + (linkCount.get(char.id) || 0) / maxLinks * 30,
    itemStyle: { color: getColorByTag(char.tags) },
    category: 0,
    label: { show: true, fontSize: 12, fontWeight: 600, color: '#333' },
  } as GraphNode))
}

function getCharName(id: string): string {
  return props.characters.find((c) => c.id === id)?.name || id
}

const detailRelations = computed(() => {
  if (!detailChar.value) return []
  return detailChar.value.relationships.filter((r) =>
    props.characters.some((c) => c.id === r.target)
  )
})

function initChart() {
  if (!chartRef.value) return
  // 销毁旧实例
  if (chart) chart.dispose()

  chart = echarts.init(chartRef.value)
  const nodes = buildNodes()
  const graphLinks = links.value

  chart.setOption({
    tooltip: {
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          const char = props.characters.find((c) => c.id === params.data.id)
          if (!char) return params.name
          const rels = char.relationships
            .filter((r) => props.characters.some((c) => c.id === r.target))
            .map((r) => `  → ${getCharName(r.target)} (${r.relation})`)
          return `<b>${char.name}</b><br/>
            ${char.description ? `📝 ${char.description}<br/>` : ''}
            ${rels.length ? `🔗 关系 (${rels.length})：<br/>${rels.join('<br/>')}` : '无关联关系'}
          `
        }
        return ''
      },
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        force: {
          repulsion: 300,
          edgeLength: 200,
          layoutAnimation: true,
          friction: 0.1,
        },
        roam: true,
        draggable: true,
        data: nodes,
        edges: graphLinks,
        categories: [{ name: '角色' }],
        label: {
          show: true,
          position: 'bottom',
          fontSize: 12,
          fontWeight: 600,
        },
        edgeLabel: {
          show: true,
          fontSize: 10,
          color: '#666',
        },
        lineStyle: {
          color: 'source',
          curveness: 0.2,
          width: 2,
          opacity: 0.7,
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: {
            width: 3,
          },
        },
        blur: {
          opacity: 0.2,
        },
        zoom: 1,
      },
    ],
  })

  // 点击节点 → 显示详情
  chart.on('click', (params: any) => {
    if (params.dataType === 'node') {
      const char = props.characters.find((c) => c.id === params.data.id)
      if (char) {
        detailChar.value = char
        showDetail.value = true
      }
    }
  })
}

function resetGraph() {
  if (chart) {
    chart.clear()
    initChart()
  }
}

// 窗口大小变化时自适应
function handleResize() {
  chart?.resize()
}

onMounted(async () => {
  await nextTick()
  initChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})

// 角色数据变化时刷新图表
watch(() => props.characters, () => {
  nextTick(() => initChart())
}, { deep: true })
</script>

<style scoped>
.relationship-graph {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 500px;
}

.graph-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.graph-title {
  font-weight: 600;
  font-size: 15px;
}

.graph-canvas {
  flex: 1;
  min-height: 450px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.detail-header {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
}

.detail-meta {
  flex: 1;
}

.detail-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.detail-body {
  margin-bottom: 16px;
}

.detail-relations h4 {
  margin: 0 0 8px;
  font-size: 14px;
}

.relation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid var(--el-border-color-light);
  font-size: 13px;
}

.relation-item:last-child {
  border-bottom: none;
}

.relation-label {
  color: var(--el-color-primary);
  font-weight: 500;
  min-width: 48px;
}

.relation-desc {
  color: var(--el-text-color-secondary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
