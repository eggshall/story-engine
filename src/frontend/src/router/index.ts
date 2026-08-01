import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/writing',
    },
    {
      path: '/writing',
      name: 'writing',
      component: () => import('../views/WritingView.vue'),
      meta: { title: '写作', icon: 'Edit' },
    },
    {
      path: '/characters',
      name: 'characters',
      component: () => import('../views/CharactersView.vue'),
      meta: { title: '角色卡', icon: 'User' },
    },
    {
      path: '/outline',
      name: 'outline',
      component: () => import('../views/OutlineView.vue'),
      meta: { title: '大纲', icon: 'List' },
    },
    {
      path: '/world',
      name: 'world',
      component: () => import('../views/WorldView.vue'),
      meta: { title: '世界观', icon: 'Collection' },
    },
    {
      path: '/research',
      name: 'research',
      component: () => import('../views/ResearchView.vue'),
      meta: { title: '资料检索', icon: 'Search' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
      meta: { title: '设置', icon: 'Setting' },
    },
  ],
})

export default router
