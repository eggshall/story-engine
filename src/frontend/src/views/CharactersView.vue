\n<template>
  <div class="characters-view">
    <div class="view-header">
      <h3>角色卡管理</h3>
      <div class="header-right">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="cards">📇 角色卡片</el-radio-button>
          <el-radio-button value="graph">🔗 关系图谱</el-radio-button>
        </el-radio-group>
        <el-button v-if="viewMode === 'cards'" type="primary" :icon="Plus" @click="showEditor = true; editingChar = null">
          新建角色
        </el-button>
      </div>
    </div>

    <!-- 角色卡片模式 -->
    <template v-if="viewMode === 'cards'">
      <div class="char-grid">
        <CharacterCard
          v-for="char in store.characters"
          :key="char.id"
          :char="char"
          @select="editCharacter"
        />
        <div v-if="store.characters.length === 0" class="char-empty">
          <el-empty description="暂无角色，点击「新建角色」添加" />
        </div>
      </div>
    </template>

    <!-- 关系图谱模式 -->
    <template v-else>
      <RelationshipGraph :characters="store.characters" />
    </template>

    <!-- 角色编辑器弹窗 -->
    <el-dialog
      v-model="showEditor"
      :title="editingChar ? '编辑角色' : '新建角色'"
      width="600px"
    >
      <el-form :model="form" label-position="top">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="角色名" required>
              <el-input v-model="form.name" placeholder="角色名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标签">
              <el-select v-model="form.tags" multiple filterable allow-create default-first-option
                placeholder="选择或输入标签" style="width: 100%">
                <el-option label="主角" value="主角" />
                <el-option label="配角" value="配角" />
                <el-option label="反派" value="反派" />
                <el-option label="路人" value="路人" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="角色描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="性格">
          <el-input v-model="form.personality" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="外貌描写">
          <el-input v-model="form.appearance" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="背景故事">
          <el-input v-model="form.background" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="出场描写">
          <el-input v-model="form.first_mes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditor = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCharacter">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import CharacterCard from '../components/CharacterCard.vue'
import RelationshipGraph from '../components/RelationshipGraph.vue'
import { useCharacterStore } from '../stores/characters'

const store = useCharacterStore()
const viewMode = ref<'cards' | 'graph'>('cards')
const showEditor = ref(false)
const editingChar = ref<string | null>(null)
const saving = ref(false)

const form = reactive({
  name: '',
  description: '',
  personality: '',
  appearance: '',
  background: '',
  first_mes: '',
  tags: [] as string[],
})

function editCharacter(id: string) {
  const char = store.characters.find((c) => c.id === id)
  if (!char) return
  editingChar.value = id
  Object.assign(form, {
    name: char.name,
    description: char.description,
    personality: char.personality,
    appearance: char.appearance,
    background: char.background,
    first_mes: char.first_mes,
    tags: [...char.tags],
  })
  showEditor.value = true
}

function saveCharacter() {
  if (!form.name) return
  saving.value = true
  try {
    if (editingChar.value) {
      store.updateChar(editingChar.value, { ...form })
    } else {
      store.addChar({
        id: crypto.randomUUID(),
        name: form.name,
        description: form.description,
        personality: form.personality,
        appearance: form.appearance,
        background: form.background,
        first_mes: form.first_mes,
        tags: form.tags,
        relationships: [],
      })
    }
    showEditor.value = false
    form.name = ''
    form.description = ''
    form.personality = ''
    form.appearance = ''
    form.background = ''
    form.first_mes = ''
    form.tags = []
    editingChar.value = null
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.characters-view {
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
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.char-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.char-empty {
  grid-column: 1 / -1;
  display: flex;
  justify-content: center;
  padding: 40px 0;
}
</style>
