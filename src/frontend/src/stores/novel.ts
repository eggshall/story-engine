import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { NovelBrief, NovelDetail, NovelCreateRequest } from '../utils/api'
import { fetchNovels, fetchNovel, createNovel } from '../utils/api'
import api from '../utils/api'

export interface ChapterItem {
  chapter_number: number
  title: string
  content?: string
  word_count?: number
}

export const useNovelStore = defineStore('novel', () => {
  const novels = ref<NovelBrief[]>([])
  const currentNovel = ref<NovelDetail | null>(null)
  const currentChapter = ref<ChapterItem | null>(null)
  const loading = ref(false)
  const saving = ref(false)

  async function loadNovels() {
    loading.value = true
    try {
      novels.value = await fetchNovels()
    } finally {
      loading.value = false
    }
  }

  async function loadNovel(id: string) {
    loading.value = true
    try {
      currentNovel.value = await fetchNovel(id)
    } finally {
      loading.value = false
    }
  }

  function selectChapter(chapterNumber: number) {
    if (!currentNovel.value) return
    const ch = currentNovel.value.chapters.find((c: any) => c.chapter_number === chapterNumber)
    if (ch) {
      currentChapter.value = {
        chapter_number: ch.chapter_number,
        title: ch.title || '',
        content: ch.content || '',
        word_count: ch.word_count || 0,
      }
    }
  }

  async function addChapter(title?: string) {
    if (!currentNovel.value) {
      ElMessage.warning('请先选择一部小说')
      return
    }
    try {
      const res = await api.post(`/novel/${currentNovel.value.id}/chapters`, { title: title || '' })
      await loadNovel(currentNovel.value.id)
      const ch = res.data?.data
      if (ch) {
        currentChapter.value = { chapter_number: ch.chapter_number, title: ch.title, content: '' }
        ElMessage.success(`已创建第${ch.chapter_number}章`)
      }
    } catch (err: any) {
      ElMessage.error(`创建失败: ${err?.response?.data?.message || err.message || '网络错误'}`)
    }
  }

  async function deleteChapter(chapterNumber: number) {
    if (!currentNovel.value) return
    try {
      await api.delete(`/novel/${currentNovel.value.id}/chapters/${chapterNumber}`)
      if (currentChapter.value?.chapter_number === chapterNumber) {
        currentChapter.value = null
      }
      await loadNovel(currentNovel.value.id)
      ElMessage.success(`已删除第${chapterNumber}章`)
    } catch (err: any) {
      ElMessage.error(`删除失败: ${err?.response?.data?.message || err.message || '网络错误'}`)
    }
  }

  async function saveCurrentChapter() {
    if (!currentNovel.value || !currentChapter.value) {
      ElMessage.warning('请先选择章节')
      return
    }
    saving.value = true
    try {
      await api.post(`/novel/${currentNovel.value.id}/chapters/${currentChapter.value.chapter_number}/save`, {
        title: currentChapter.value.title,
        content: currentChapter.value.content,
      })
      await loadNovel(currentNovel.value.id)
      ElMessage.success('💾 章节已保存')
    } catch (err: any) {
      ElMessage.error(`保存失败: ${err?.response?.data?.message || err.message || '网络错误'}`)
    } finally {
      saving.value = false
    }
  }

  async function create(data: NovelCreateRequest) {
    const novel = await createNovel(data)
    novels.value.unshift({
      id: novel.id,
      title: novel.title,
      author: novel.author,
      genre: novel.genre,
      word_count: novel.word_count,
      chapter_count: novel.chapter_count,
      created: novel.created,
      updated: novel.updated,
    })
    currentNovel.value = novel
    return novel
  }

  return {
    novels, currentNovel, currentChapter, loading, saving,
    loadNovels, loadNovel, selectChapter, addChapter, deleteChapter,
    saveCurrentChapter, create,
  }
})
