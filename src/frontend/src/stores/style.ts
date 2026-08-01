import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { StyleProfileInfo } from '../utils/api'
import {
  fetchStyleProfiles as apiFetchProfiles,
  analyzeStyle as apiAnalyzeStyle,
  saveStyleProfile as apiSaveProfile,
  deleteStyleProfile as apiDeleteProfile,
} from '../utils/api'

export const useStyleStore = defineStore('style', () => {
  const profiles = ref<StyleProfileInfo[]>([])
  const selectedProfileId = ref('')
  const loading = ref(false)
  const analyzing = ref(false)

  const selectedProfile = computed(() =>
    profiles.value.find(p => p.id === selectedProfileId.value)
  )

  const genres = computed(() => {
    const gs = new Set(profiles.value.map(p => p.genre).filter(Boolean))
    return Array.from(gs).sort()
  })

  async function loadProfiles(genre = '') {
    loading.value = true
    try {
      profiles.value = await apiFetchProfiles(genre)
    } finally {
      loading.value = false
    }
  }

  function selectProfile(id: string) {
    selectedProfileId.value = id
  }

  function clearSelection() {
    selectedProfileId.value = ''
  }

  async function analyzeText(text: string, name = '', author = '', genre = '') {
    analyzing.value = true
    try {
      const result = await apiAnalyzeStyle({ text, name, author, genre })
      if (result.profile_id) {
        await loadProfiles()
        selectProfile(result.profile_id)
      }
      return result
    } finally {
      analyzing.value = false
    }
  }

  async function deleteProfile(id: string) {
    await apiDeleteProfile(id)
    if (selectedProfileId.value === id) {
      selectedProfileId.value = ''
    }
    await loadProfiles()
  }

  return {
    profiles,
    selectedProfileId,
    selectedProfile,
    loading,
    analyzing,
    genres,
    loadProfiles,
    selectProfile,
    clearSelection,
    analyzeText,
    deleteProfile,
  }
})
