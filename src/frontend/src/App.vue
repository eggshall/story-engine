\n<template>
  <el-container class="app-container">
    <!-- 左侧导航 -->
    <el-aside width="220px" class="app-sidebar">
      <div class="sidebar-header">
        <h2 class="app-title">📖 故事引擎</h2>
      </div>
      <el-menu
        :router="true"
        :default-active="route.path"
        class="sidebar-menu"
      >
        <el-menu-item index="/writing">
          <el-icon><Edit /></el-icon>
          <span>写作</span>
        </el-menu-item>
        <el-menu-item index="/characters">
          <el-icon><User /></el-icon>
          <span>角色卡</span>
        </el-menu-item>
        <el-menu-item index="/outline">
          <el-icon><List /></el-icon>
          <span>大纲</span>
        </el-menu-item>
        <el-menu-item index="/world">
          <el-icon><Collection /></el-icon>
          <span>世界观</span>
        </el-menu-item>
        <el-menu-item index="/research">
          <el-icon><Search /></el-icon>
          <span>资料检索</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { onMounted } from 'vue'
import { useSettingsStore } from './stores/settings'

const route = useRoute()
const settings = useSettingsStore()

onMounted(() => {
  settings.loadModels()
})
</script>

<style scoped>
.app-container {
  height: 100vh;
  overflow: hidden;
}

.app-sidebar {
  background-color: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 20px 16px 12px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.app-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.sidebar-menu {
  border-right: none;
  flex: 1;
}

.app-main {
  background-color: var(--el-bg-color-page);
  padding: 20px;
  overflow-y: auto;
  height: 100vh;
}
</style>
