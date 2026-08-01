import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ModelInfo } from '../utils/api'
import { fetchModels, updateModel as apiUpdateModel, testModel as apiTestModel } from '../utils/api'

export const useSettingsStore = defineStore('settings', () => {
  const models = ref<ModelInfo[]>([])
  const currentModel = ref('')
  const loading = ref(false)

  async function loadModels() {
    loading.value = true
    try {
      models.value = await fetchModels()
      if (!currentModel.value && models.value.length > 0) {
        currentModel.value = models.value[0].model_id
      }
    } finally {
      loading.value = false
    }
  }

  function setModel(modelId: string) {
    currentModel.value = modelId
  }

  async function updateModel(
    name: string,
    config: Partial<Pick<ModelInfo, 'enabled' | 'api_key' | 'base_url' | 'temperature' | 'max_tokens'>>
  ): Promise<boolean> {
    try {
      const updated = await apiUpdateModel(name, config)
      // Update local state
      const idx = models.value.findIndex(m => m.name === name)
      if (idx >= 0) {
        models.value[idx] = updated
      }
      return true
    } catch {
      return false
    }
  }

  async function testConnection(name: string): Promise<{ status: string; message: string }> {
    return await apiTestModel(name)
  }

  return { models, currentModel, loading, loadModels, setModel, updateModel, testConnection }
})
