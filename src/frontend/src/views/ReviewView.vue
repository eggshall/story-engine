<template>
  <div class="review-view">
    <!-- 顶部：选书/选章 + 校验 -->
    <div class="toolbar">
      <el-select
        v-model="novelId"
        class="sel-novel"
        data-testid="novel-select"
        placeholder="选择小说"
        @change="onNovelChange"
      >
        <el-option v-for="n in novels" :key="n.id" :label="n.title" :value="n.id" />
      </el-select>
      <el-select
        v-model="chapterNumber"
        class="sel-chapter"
        data-testid="chapter-select"
        placeholder="选择章节"
        @change="onChapterChange"
      >
        <el-option
          v-for="c in chapters"
          :key="c.chapter_number"
          :label="`第${c.chapter_number}章 ${c.title || ''}`"
          :value="c.chapter_number"
        />
      </el-select>
      <el-button
        type="primary"
        data-testid="check-btn"
        :loading="checking"
        :disabled="!viewedText || rewriting || checking || generating"
        @click="runCheck"
      >
        校验当前正文
      </el-button>
      <span
        v-if="report"
        class="level-tag"
        data-testid="report-level"
        :data-level="report.level"
      >{{ levelLabel }}</span>
      <span v-if="errorMsg" class="err" data-testid="error">{{ errorMsg }}</span>
    </div>

    <div class="columns">
      <!-- ── 左：正文 ───────────────────────────── -->
      <section class="panel col-draft">
        <header class="panel-head">
          <span class="panel-title">正文</span>
          <span class="switch">
            <a
              :class="{ on: viewMode === 'draft' }"
              data-testid="tab-draft"
              @click="viewMode = 'draft'"
            >草稿</a>
            <a
              v-if="candidate !== null"
              :class="{ on: viewMode === 'candidate' }"
              data-testid="tab-candidate"
              @click="viewMode = 'candidate'"
            >候选稿</a>
          </span>
          <span class="wc">{{ viewedText.length }} 字</span>
        </header>
        <div class="text" data-testid="draft-text">
          <template v-if="canHighlight">
            <span>{{ viewedText.slice(0, highlight!.start) }}</span><mark data-testid="highlight">{{
              viewedText.slice(highlight!.start, highlight!.end)
            }}</mark><span>{{ viewedText.slice(highlight!.end) }}</span>
          </template>
          <template v-else>{{ viewedText || '（这一章还没有正文）' }}</template>
        </div>
      </section>

      <!-- ── 中：校验清单 ───────────────────────── -->
      <section class="panel col-check">
        <header class="panel-head">
          <span class="panel-title">校验清单</span>
          <label class="show-ok">
            <input v-model="showOk" type="checkbox" data-testid="show-ok"> 显示已通过项
          </label>
        </header>

        <p v-if="report?.incomplete" class="incomplete" data-testid="incomplete-banner">
          有 {{ report.skipped_rules.length }} 条规则这次没判定（缺基线：{{ skippedLabels }}）
          —— 不是"没问题"，是"还没法判"。
        </p>
        <p v-if="!report" class="empty" data-testid="check-empty">还没校验。点上面的按钮跑一遍。</p>
        <p v-else-if="!visibleFindings.length" class="empty" data-testid="check-clean">
          这一遍没有可执行的问题。
        </p>

        <div v-for="group in visibleGroups" :key="group.rule_id" class="group">
          <div class="group-head">
            <span class="group-name">{{ group.rule_name }}</span>
            <span class="group-count">{{ group.items.length }}</span>
          </div>
          <div
            v-for="(f, i) in group.items"
            :key="`${group.rule_id}-${i}`"
            class="finding"
            data-testid="finding"
            :data-rule="f.rule_id"
            :data-level="f.level"
            @click="focusFinding(f)"
          >
            <span class="dot" :data-level="f.level" />
            <div class="finding-body">
              <div class="suggestion">{{ f.suggestion }}</div>
              <div v-if="f.location?.excerpt" class="excerpt">「{{ f.location.excerpt }}」</div>
              <div v-if="f.location" class="pos">
                第 {{ (f.location.paragraph_index ?? 0) + 1 }} 段 · 字符 {{ f.location.start }}–{{ f.location.end }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ── 右：待决项 / 修改意见 ───────────────── -->
      <section class="panel col-actions">
        <header class="panel-head"><span class="panel-title">待决项 · 我给的修改意见</span></header>

        <textarea
          v-model="instruction"
          class="instruction"
          data-testid="instruction-input"
          rows="6"
          placeholder="例：把开头两段的环境描写删掉，直接从对话进入；章末加一个未解的问题"
        />
        <div class="quick">
          <button
            v-for="q in QUICK_INSTRUCTIONS"
            :key="q"
            class="chip"
            data-testid="quick-instruction"
            @click="instruction = q"
          >{{ q }}</button>
        </div>

        <el-button
          type="primary"
          data-testid="rewrite-btn"
          :loading="rewriting"
          :disabled="!novelId || !chapterNumber || !instruction.trim() || generating"
          @click="rewrite"
        >
          带指令重写
        </el-button>
        <el-button
          data-testid="save-btn"
          :disabled="!candidate || rewriting || rewriteFailed"
          @click="saveCandidate"
        >
          保存为本章正文
        </el-button>
        <el-button
          data-testid="generate-btn"
          :loading="generating"
          :disabled="!novelId || rewriting || generating"
          @click="generateNextChapter"
        >
          按节拍写下一章
        </el-button>
        <p v-if="candidate !== null && !rewriteFailed" class="hint" data-testid="candidate-hint">
          候选稿只在这里预览，还没有覆盖磁盘 —— 满意再点保存（{{ candidate.length }} 字）。
        </p>
        <p v-if="rewriteFailed" class="hint" data-testid="rewrite-failed">
          这次重写没有正常收尾，候选稿是半截的：不能保存（可以手动复制走）。
        </p>

        <div class="manifest">
          <div class="panel-sub">本次注入清单</div>
          <template v-if="manifest?.entries?.length">
            <span
              v-for="e in manifest.entries"
              :key="e.slot_id"
              class="slot"
              data-testid="manifest-slot"
              :data-slot="e.slot_id"
            >{{ e.slot_id }} · {{ e.tokens }}t</span>
          </template>
          <p v-else-if="manifest" class="tiny">没有注入任何槽位。</p>
          <p v-else class="tiny">还没有记录（生成或重写一次就会出现）。</p>
          <p v-if="manifest?.skipped?.length" class="tiny" data-testid="manifest-skipped">
            缺料：{{ manifest.skipped.map((s: any) => s.slot_id).join('、') }}
          </p>
          <p v-if="manifest?.dropped?.length" class="tiny" data-testid="manifest-dropped">
            被裁：{{ manifest.dropped.map((d: any) => d.slot_id).join('、') }}（超预算）
          </p>
          <!-- 评审 P1-4：写盘失败不能看起来像"没注入过" -->
          <p v-if="manifestPersisted === false" class="warn" data-testid="manifest-persist-warn">
            注意：这份清单没能写进磁盘（下次刷新就查不到了）——注入本身是成功的。
          </p>
          <p class="tiny">清单记录的是"生成这一章时注入了什么"，之后保存/改写正文不会更新它。</p>
          <el-button size="small" data-testid="load-manifest-btn" @click="loadManifest">
            读取本章历史清单
          </el-button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  checkChapter,
  fetchChapterManifest,
  fetchNovel,
  fetchNovels,
  generateChapterV2Stream,
  saveChapterContent,
  type CheckFinding,
  type CheckReport,
  type NovelBrief,
  type NovelDetail,
} from '../utils/api'

/** 快捷指令：按 N5 的规则命名，作者一眼知道点下去会改什么 */
const QUICK_INSTRUCTIONS = [
  '删掉"值得注意的是/毋庸置疑"这类套话',
  '章末加一个未解的问题，留下钩子',
  '把超过 300 字的段落拆成两三段',
]

const RULE_LABELS: Record<string, string> = {
  dialogue_ratio: '对话占比',
  pov_consistency: '视角一致性',
}

const route = useRoute()

const novels = ref<NovelBrief[]>([])
const novelId = ref('')
const chapterNumber = ref<number | null>(null)
const novel = ref<NovelDetail | null>(null)

const report = ref<CheckReport | null>(null)
const checking = ref(false)
const showOk = ref(false)
const errorMsg = ref('')
const highlight = ref<{ start: number; end: number } | null>(null)
/** 高亮偏移只对**被校验过的那段文本**有意义 —— 换了文本就必须清掉，否则会标错位置 */
const checkedText = ref('')

const viewMode = ref<'draft' | 'candidate'>('draft')
const candidate = ref<string | null>(null)
const instruction = ref('')
const rewriting = ref(false)
const generating = ref(false)
/** 这次重写没有正常收尾（SSE error / 网络断）→ 候选稿是半截的，禁止保存 */
const rewriteFailed = ref(false)
const manifest = ref<any>(null)
/** 清单是否真的写进了磁盘（v2 生成模式的 done 载荷回报；重写模式不报 = 不适用） */
const manifestPersisted = ref<boolean | null>(null)

/**
 * 重写/生成代号：每次发起 +1，切章/切书再 +1。
 * 作用是**作废在途的流**（N6 评审 P0-1）：作者重写到一半切去看别的章时，
 * 旧流的 token 还在到达 —— 若继续往已清空的 candidate 上拼，`null + "词"` 会得到
 * `"null词"`，保存按钮又恰好可点，就会把脏串覆盖到新选中的那一章。
 */
let runSeq = 0

const chapters = computed(() =>
  [...((novel.value?.chapters as any[]) || [])].sort(
    (a, b) => a.chapter_number - b.chapter_number,
  ),
)
const currentChapter = computed(
  () => chapters.value.find((c) => c.chapter_number === chapterNumber.value) || null,
)
const draftText = computed(() => currentChapter.value?.content || '')
const viewedText = computed(() =>
  viewMode.value === 'candidate' && candidate.value !== null ? candidate.value : draftText.value,
)
const canHighlight = computed(
  () => !!highlight.value && viewedText.value === checkedText.value,
)
const levelLabel = computed(() => {
  const lv = report.value?.level
  return lv === 'alert' ? '有必须处理的' : lv === 'warn' ? '有可改的' : '没发现问题'
})
const skippedLabels = computed(() =>
  (report.value?.skipped_rules || []).map((r) => RULE_LABELS[r] || r).join('、'),
)
const visibleFindings = computed(() =>
  (report.value?.findings || []).filter((f) => showOk.value || f.level !== 'ok'),
)
const visibleGroups = computed(() => {
  const order = report.value?.rules_run || []
  return order
    .map((rid) => {
      const items = visibleFindings.value.filter((f) => f.rule_id === rid)
      return { rule_id: rid, rule_name: items[0]?.rule_name || rid, items }
    })
    .filter((g) => g.items.length)
})

onMounted(async () => {
  await loadNovels()
  // 深链支持：`/review?novel=<id>&chapter=<n>`（写作页"去审稿"跳过来时带上当前书/章）
  const qNovel = String(route.query.novel || '')
  // query 值可能是数组（?chapter=1&chapter=2）→ Number() 会得到 NaN，必须挡住（P2-3）
  const rawChapter = Array.isArray(route.query.chapter) ? route.query.chapter[0] : route.query.chapter
  const qChapter = Number.parseInt(String(rawChapter ?? ''), 10)
  if (qNovel && novels.value.some((n) => n.id === qNovel)) {
    novelId.value = qNovel
    await onNovelChange(qNovel)
    if (Number.isFinite(qChapter) && qChapter > 0
        && chapters.value.some((c) => c.chapter_number === qChapter)) {
      chapterNumber.value = qChapter
    }
  }
})

async function loadNovels() {
  try {
    novels.value = await fetchNovels()
    if (novels.value.length && !novelId.value) {
      novelId.value = novels.value[0].id
      await onNovelChange(novelId.value)
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '读取小说列表失败'
  }
}

async function onNovelChange(id: string) {
  errorMsg.value = ''
  invalidateRun()                       // 作废在途的流（P0-1）
  try {
    novel.value = await fetchNovel(id)
  } catch (e: any) {
    errorMsg.value = e?.message || '读取小说失败'   // P2-3：@change 触发的失败也要有提示
    return
  }
  report.value = null
  highlight.value = null
  checkedText.value = ''
  candidate.value = null
  rewriteFailed.value = false
  viewMode.value = 'draft'
  manifest.value = null
  manifestPersisted.value = null
  // 默认停在**最后一段有正文**的章节：审稿页就是给"刚写完的那章"用的
  const withContent = chapters.value.filter((c) => (c.content || '').length)
  const target = withContent.length ? withContent[withContent.length - 1] : chapters.value[0]
  chapterNumber.value = target ? target.chapter_number : null
}

async function onChapterChange() {
  invalidateRun()                       // 同上：切章必须作废在途的流
  report.value = null
  highlight.value = null
  checkedText.value = ''
  candidate.value = null
  rewriteFailed.value = false
  viewMode.value = 'draft'
  manifest.value = null
  manifestPersisted.value = null
}

/** 作废所有在途的流（它们的 token 之后会被丢弃） */
function invalidateRun() {
  runSeq += 1
  rewriting.value = false
  generating.value = false
}

async function runCheck() {
  if (!novelId.value || !chapterNumber.value || rewriting.value || checking.value) return
  errorMsg.value = ''
  checking.value = true
  try {
    // 当前正在看什么就校验什么（草稿 or 候选稿）；同时把书/章带上，
    // 好让后端的"对话占比"能拿前序章节做基线（否则这条规则永远 skipped，评审 P1-2）
    const text = viewedText.value
    const rep = await checkChapter({
      text,
      novel_id: novelId.value,
      chapter_number: chapterNumber.value,
    })
    report.value = rep
    checkedText.value = text          // 成功后才认账（P2-2）
    highlight.value = null
  } catch (e: any) {
    errorMsg.value = e?.message || '校验失败'
    report.value = null               // 失败就清干净，别让旧报告挂在半截文本上（P2-2）
    highlight.value = null
    checkedText.value = ''
  } finally {
    checking.value = false
  }
}

function focusFinding(f: CheckFinding) {
  if (!f.location) return
  highlight.value = { start: f.location.start, end: f.location.end }
}

async function rewrite() {
  if (!novelId.value || !chapterNumber.value || !instruction.value.trim()) return
  const runId = ++runSeq
  errorMsg.value = ''
  rewriting.value = true
  rewriteFailed.value = false
  candidate.value = ''
  viewMode.value = 'candidate'
  report.value = null
  highlight.value = null
  checkedText.value = ''
  manifest.value = null
  manifestPersisted.value = null
  try {
    for await (const token of generateChapterV2Stream(
      {
        novel_id: novelId.value,
        chapter_number: chapterNumber.value,
        instruction: instruction.value,
      },
      {
        onDone: (payload) => {
          if (runId !== runSeq) return
          if (payload?.context_manifest) manifest.value = payload.context_manifest
          manifestPersisted.value = null          // 重写不落盘：不适用
        },
      },
    )) {
      if (runId !== runSeq) return                 // 已切章/切书 → 丢弃这个流（P0-1）
      candidate.value = (candidate.value ?? '') + token
    }
    if (runId !== runSeq) return
  } catch (e: any) {
    if (runId !== runSeq) return
    errorMsg.value = e?.message || '重写失败'
    // 评审 P1-1：流没正常收尾 → 候选稿是半截的。留着给作者看/复制，但**禁止保存**，
    // 免得一键把半截稿覆盖整章（覆盖是不可逆的）。
    rewriteFailed.value = true
  } finally {
    if (runId === runSeq) rewriting.value = false
  }
}

/** 按节拍写下一章（走装配器）：让"注入清单落盘"在界面上真的可达（评审 P1-3） */
async function generateNextChapter() {
  if (!novelId.value || generating.value) return
  const nextNumber = chapters.value.length
    ? Math.max(...chapters.value.map((c) => c.chapter_number)) + 1
    : 1
  const runId = ++runSeq
  errorMsg.value = ''
  generating.value = true
  candidate.value = null
  rewriteFailed.value = false
  viewMode.value = 'draft'
  report.value = null
  highlight.value = null
  checkedText.value = ''
  manifest.value = null
  manifestPersisted.value = null
  try {
    for await (const _token of generateChapterV2Stream(
      { novel_id: novelId.value, chapter_number: nextNumber },
      {
        onDone: (payload) => {
          if (runId !== runSeq) return
          if (payload?.context_manifest) manifest.value = payload.context_manifest
          manifestPersisted.value = typeof payload?.manifest_persisted === 'boolean'
            ? payload.manifest_persisted
            : null
        },
      },
    )) {
      // 生成模式由后端落盘，这里不需要预览 token
    }
    if (runId !== runSeq) return
    // 先把这次生成带回来的清单留住 —— onNovelChange 会清空 manifest（它按"换书"语义重置），
    // 但生成完正是作者最想核"这次注入了什么"的时刻（N6 评审 P1-3）。
    const doneManifest = manifest.value
    const donePersisted = manifestPersisted.value
    const id = novelId.value
    await onNovelChange(id)                        // 重新载入（新章已在磁盘上）
    manifest.value = doneManifest
    manifestPersisted.value = donePersisted
    const created = chapters.value.find((c) => c.chapter_number === nextNumber)
    if (created) {
      chapterNumber.value = created.chapter_number
      await runCheck()                             // 写完立刻校验一遍，作者直接看清单
    }
  } catch (e: any) {
    if (runId === runSeq) errorMsg.value = e?.message || '生成失败'
  } finally {
    if (runId === runSeq) generating.value = false
  }
}

async function saveCandidate() {
  if (!novelId.value || !chapterNumber.value) return
  if (!candidate.value || rewriteFailed.value) return       // 半截稿不许保存（P1-1）
  errorMsg.value = ''
  try {
    const keep = chapterNumber.value
    await saveChapterContent(novelId.value, keep, candidate.value)
    candidate.value = null
    rewriteFailed.value = false
    await onNovelChange(novelId.value)
    chapterNumber.value = keep
    await runCheck()                                        // 存完再看一眼这份正文
  } catch (e: any) {
    errorMsg.value = e?.message || '保存失败'
  }
}

async function loadManifest() {
  if (!novelId.value || !chapterNumber.value) return
  try {
    const res = await fetchChapterManifest(novelId.value, chapterNumber.value)
    if (res.ok) {
      manifest.value = res.manifest
      manifestPersisted.value = true
      errorMsg.value = ''
    } else {
      manifest.value = null
      manifestPersisted.value = null
      errorMsg.value = res.message || '读不到注入清单'
    }
  } catch (e: any) {
    errorMsg.value = e?.message || '读取注入清单失败'      // P2-4：网络异常也要有提示
  }
}
</script>

<style scoped>
.review-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.sel-novel {
  width: 200px;
}
.sel-chapter {
  width: 220px;
}
.level-tag {
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  border: 1px solid var(--el-border-color);
}
.level-tag[data-level='alert'] {
  color: var(--el-color-danger);
  border-color: var(--el-color-danger);
}
.level-tag[data-level='warn'] {
  color: var(--el-color-warning);
  border-color: var(--el-color-warning);
}
.err {
  color: var(--el-color-danger);
  font-size: 12px;
}
.columns {
  display: grid;
  grid-template-columns: 10fr 7fr 7fr;
  gap: 12px;
  align-items: start;
}
.panel {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 10px;
  min-height: 320px;
}
.panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.panel-title {
  font-weight: 600;
}
.panel-sub {
  font-weight: 600;
  margin: 10px 0 6px;
}
.switch a {
  cursor: pointer;
  color: var(--el-text-color-secondary);
  margin-right: 6px;
}
.switch a.on {
  color: var(--el-color-primary);
  font-weight: 600;
}
.wc,
.tiny {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.text {
  white-space: pre-wrap;
  line-height: 1.9;
  max-height: 62vh;
  overflow-y: auto;
}
mark {
  background: #fff3b0;
  padding: 1px 0;
}
.incomplete {
  font-size: 12px;
  color: var(--el-color-warning);
  margin: 0 0 8px;
}
.empty {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.group {
  margin-bottom: 10px;
}
.group-head {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}
.group-count {
  color: var(--el-text-color-secondary);
  font-weight: 400;
}
.finding {
  display: flex;
  gap: 6px;
  padding: 6px;
  border-radius: 4px;
  cursor: pointer;
}
.finding:hover {
  background: var(--el-fill-color-light);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 6px;
  flex: none;
  background: var(--el-color-info);
}
.dot[data-level='alert'] {
  background: var(--el-color-danger);
}
.dot[data-level='warn'] {
  background: var(--el-color-warning);
}
.suggestion {
  font-size: 13px;
}
.excerpt,
.pos {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.instruction {
  width: 100%;
  box-sizing: border-box;
  font-family: inherit;
  line-height: 1.7;
  padding: 6px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
}
.quick {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin: 6px 0;
}
.chip {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--el-border-color);
  background: transparent;
  cursor: pointer;
}
.hint {
  font-size: 12px;
  color: var(--el-color-warning);
}
.warn {
  font-size: 12px;
  color: var(--el-color-danger);
}
.slot {
  display: inline-block;
  font-size: 12px;
  padding: 1px 8px;
  margin: 2px 4px 2px 0;
  border-radius: 10px;
  background: var(--el-fill-color-light);
}
.show-ok {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: auto;
}
</style>
