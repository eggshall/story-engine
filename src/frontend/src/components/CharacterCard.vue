\n<template>
  <div class="character-card" @click="$emit('select', char.id)">
    <el-avatar :size="48" :style="{ backgroundColor: avatarColor }">
      {{ char.name.charAt(0) }}
    </el-avatar>
    <div class="card-info">
      <div class="card-name">{{ char.name }}</div>
      <div class="card-desc" :title="char.description">{{ char.description }}</div>
      <div class="card-tags">
        <el-tag v-for="tag in char.tags" :key="tag" size="small" round>{{ tag }}</el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CharacterCard } from '../stores/characters'

defineProps<{
  char: CharacterCard
  avatarColor?: string
}>()

defineEmits<{
  select: [id: string]
}>()
</script>

<style scoped>
.character-card {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}
.character-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.card-info {
  flex: 1;
  min-width: 0;
}
.card-name {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 4px;
}
.card-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 6px;
}
.card-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
</style>
