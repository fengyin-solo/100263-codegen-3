<template>
  <section class="page" data-module="leasing">
    <header class="page-head">
      <div>
        <h2>铺位招商</h2>
        <p class="page-desc">招商清单走抽屉里的两步式交接：先多选楼层整批暂存（只做格式与编号检查），逐条确认后才入库；已有铺位按编号更新租金与租期，缺号补成待签约。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openDrawer">
          招商清单交接<span v-if="pendingBadge" class="stage-badge">{{ pendingBadge }}</span>
        </button>
        <button class="btn" type="button" @click="exportRows">导出租金清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>铺位编号</span>
        <input v-model="filters.keyword" placeholder="按铺位编号检索" />
      </label>
      <label class="filter-item">
        <span>楼层</span>
        <select v-model="filters.floor">
          <option value="">全部楼层</option>
          <option v-for="floor in floors" :key="floor" :value="floor">{{ floor }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>签约状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table floor-table">
      <thead>
        <tr><th v-for="column in floorColumns" :key="column">{{ column }}</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in floorRows" :key="String(row['楼层'])">
          <td v-for="column in floorColumns" :key="column">{{ row[column] }}</td>
        </tr>
      </tbody>
    </table>

    <table class="data-table booth-table">
      <thead>
        <tr><th v-for="column in columns" :key="column">{{ column }}</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length" class="empty-state">暂无铺位明细，可通过招商清单交接补入</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 个铺位</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 两步式交接抽屉 -->
    <div v-if="drawerOpen" class="drawer-mask" @click.self="closeDrawer">
      <aside class="drawer">
        <header class="drawer-head">
          <div>
            <h3>招商清单交接</h3>
            <p class="drawer-step">第 {{ step }} 步 / 共 2 步：{{ step === 1 ? '多选楼层 · 整批暂存' : '逐条确认 · 入库' }}</p>
          </div>
          <button class="btn ghost" type="button" @click="closeDrawer">关闭</button>
        </header>

        <div class="drawer-body">
          <!-- 第一步：楼层多选 + 清单原文 -->
          <div v-show="step === 1">
            <fieldset class="floor-picker">
              <legend>本次交接涉及的楼层（可多选）</legend>
              <label v-for="floor in floors" :key="floor" class="floor-check">
                <input type="checkbox" :value="floor" v-model="selectedFloors" />
                <span>{{ floor }}</span>
              </label>
            </fieldset>

            <label class="paste-box">
              <span>招商清单原文（从表格整列复制，支持制表符/逗号分列；首行表头会自动跳过）</span>
              <textarea
                v-model="rawText"
                rows="10"
                placeholder="铺位编号&#10;楼层&#10;铺位类型&#10;面积&#10;租金&#10;租期&#10;1F-001&#9;1F&#9;餐饮&#9;86㎡&#9;19000&#9;2026-04-01~2027-03-31"
              ></textarea>
              <small>列顺序：铺位编号、楼层、铺位类型、面积、租金、租期；租金为空或不是数字的行会在暂存时整行退回。</small>
            </label>

            <p v-if="stageMessage" class="error-text">{{ stageMessage }}</p>

            <div class="parsed-preview">
              <span>已识别 {{ parsedRows.length }} 行数据</span>
            </div>
          </div>

          <!-- 第二步：待核对区 -->
          <div v-if="batch" v-show="step === 2">
            <div class="batch-meta">
              <span>批次 {{ batch.id }}</span>
              <span>楼层：{{ batch.floors.join('、') }}</span>
              <span>暂存于 {{ batch.created_at }}</span>
            </div>

            <div class="check-toolbar">
              <button class="btn" type="button" :disabled="batch.committed" @click="confirmAll(true)">全部确认</button>
              <button class="btn" type="button" :disabled="batch.committed" @click="confirmAll(false)">全部取消</button>
              <span>已确认 {{ confirmedCount }} / {{ batch.accepted.length }} 行</span>
            </div>

            <table class="data-table">
              <thead>
                <tr>
                  <th>行号</th><th>确认</th><th>铺位编号</th><th>楼层</th><th>铺位类型</th><th>面积</th><th>租金</th><th>租期</th><th>核对提示</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in batch.accepted" :key="item.line_no" :class="{ confirmed: item.confirmed }">
                  <td>{{ item.line_no }}</td>
                  <td>
                    <input
                      type="checkbox"
                      :checked="item.confirmed"
                      :disabled="batch.committed"
                      @change="toggleConfirm(item, ($event.target as HTMLInputElement).checked)"
                    />
                  </td>
                  <td>{{ item['铺位编号'] }}</td>
                  <td>{{ item['楼层'] }}</td>
                  <td>{{ item['铺位类型'] ?? '—' }}</td>
                  <td>{{ item['面积'] ?? '—' }}</td>
                  <td>{{ item['租金'] }}</td>
                  <td>{{ item['租期'] ?? '—' }}</td>
                  <td>
                    <span v-if="item.duplicate_lines.length" class="dup-tag">
                      重复行：第 {{ item.duplicate_lines.join('、') }} 行
                    </span>
                    <span v-else class="ok-text">通过</span>
                  </td>
                </tr>
                <tr v-if="!batch.accepted.length">
                  <td colspan="9" class="empty-state">本批没有通过检查的行，全部被退回，请返回上一步重新整理</td>
                </tr>
              </tbody>
            </table>

            <section v-if="batch.rejected.length" class="rejected-block">
              <h4>整行退回（{{ batch.rejected.length }} 行，不参与入库）</h4>
              <table class="data-table">
                <thead><tr><th>行号</th><th>铺位编号</th><th>楼层</th><th>原始租金</th><th>退回原因</th></tr></thead>
                <tbody>
                  <tr v-for="item in batch.rejected" :key="item.line_no">
                    <td>{{ item.line_no }}</td>
                    <td>{{ item.code ?? '—' }}</td>
                    <td>{{ item.floor ?? '—' }}</td>
                    <td>{{ item.rent ?? '—' }}</td>
                    <td class="error-text">{{ item.reason }}</td>
                  </tr>
                </tbody>
              </table>
            </section>

            <div v-if="lastResult" class="result-box">
              <h4>入库结果{{ lastDuplicated ? '（重复提交，未重复执行）' : '' }}</h4>
              <p>按编号更新 {{ lastResult.updated }} 行，新增待签约 {{ lastResult.inserted }} 个铺位，跳过重复确认 {{ lastResult.skipped.length }} 行，暂存退回 {{ lastResult.rejected_count }} 行。</p>
              <table class="data-table">
                <thead><tr><th>楼层</th><th>铺位条数</th><th>已签约</th><th>待签约</th></tr></thead>
                <tbody>
                  <tr v-for="floor in lastResult.floors" :key="String(floor['楼层'])">
                    <td>{{ floor['楼层'] }}</td><td>{{ floor['铺位条数'] }}</td><td>{{ floor['已签约'] }}</td><td>{{ floor['待签约'] }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <footer class="drawer-foot">
          <span v-if="stageError" class="error-text">{{ stageError }}</span>
          <template v-if="step === 1">
            <button class="btn" type="button" @click="closeDrawer">取消</button>
            <button class="btn primary" type="button" :disabled="staging" @click="submitStage">
              {{ staging ? '正在整批暂存…' : '整批暂存进待核对区' }}
            </button>
          </template>
          <template v-else-if="batch && !batch.committed">
            <button class="btn danger" type="button" @click="clearStage">整批清空</button>
            <button class="btn" type="button" @click="step = 1">返回上一步</button>
            <button class="btn primary" type="button" :disabled="committing || !batch.accepted.length || confirmedCount !== batch.accepted.length" @click="commitStage">
              {{ committing ? '正在入库…' : `确认无误，入库（${batch.accepted.length} 行）` }}
            </button>
          </template>
          <template v-else>
            <button class="btn primary" type="button" @click="closeDrawer">完成并关闭</button>
          </template>
        </footer>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/leasing'
const BATCH_KEY = 'leasing:stageBatchId'
const columns = ['铺位编号', '楼层', '铺位类型', '面积', '租金', '租期', '签约状态']
const floorColumns = ['楼层', '铺位条数', '已签约', '待签约']
const floors = ['1F', '2F', '3F', 'B1']
const statuses = ['待签约', '已签约']
const HEADER_ALIASES: Record<string, string> = {
  铺位编号: 'code', 编号: 'code',
  楼层: 'floor',
  铺位类型: 'type', 类型: 'type',
  面积: 'area',
  租金: 'rent', 租金单价: 'rent',
  租期: 'term', 租赁期限: 'term',
}

const rows = ref<Row[]>([])
const total = ref(0)
const floorRows = ref<Row[]>([])
const errorMessage = ref('')
const filters = ref({ keyword: '', floor: '', status: '' })

const drawerOpen = ref(false)
const step = ref(1)
const selectedFloors = ref<string[]>([])
const rawText = ref('')
const staging = ref(false)
const committing = ref(false)
const stageMessage = ref('')
const stageError = ref('')

interface AcceptedRow {
  line_no: number
  confirmed: boolean
  duplicate_lines: number[]
  铺位编号: string
  楼层: string
  铺位类型: string | null
  面积: string | null
  租金: number
  租期: string | null
}
interface RejectedRow {
  line_no: number
  code: string | null
  floor: string | null
  rent: string | null
  reason: string
}
interface CommitResult {
  batch_id: string
  updated: number
  inserted: number
  skipped: { line_no: number; code: string; reason: string }[]
  rejected_count: number
  floors: Row[]
}
interface Batch {
  id: string
  floors: string[]
  created_at: string
  accepted: AcceptedRow[]
  rejected: RejectedRow[]
  committed: boolean
  result: CommitResult | null
}
const batch = ref<Batch | null>(null)
const lastResult = ref<CommitResult | null>(null)
const lastDuplicated = ref(false)

const stats = computed(() => {
  const booths = floorRows.value.reduce((sum, item) => sum + Number(item['铺位条数'] || 0), 0)
  const signed = floorRows.value.reduce((sum, item) => sum + Number(item['已签约'] || 0), 0)
  const waiting = floorRows.value.reduce((sum, item) => sum + Number(item['待签约'] || 0), 0)
  return [
    { label: '铺位总数', value: booths },
    { label: '待签约', value: waiting },
    { label: '已签约', value: signed },
  ]
})

const pendingBadge = computed(() => {
  if (batch.value && !batch.value.committed && batch.value.accepted.length) {
    return `${confirmedCount.value}/${batch.value.accepted.length}`
  }
  return ''
})

const confirmedCount = computed(() => batch.value?.accepted.filter((item) => item.confirmed).length ?? 0)

interface ParsedRow {
  line_no: number
  code: string
  floor: string
  booth_type: string
  area: string
  rent: string
  term: string
}

const parsedRows = computed<ParsedRow[]>(() => parseSheet(rawText.value))

function splitLine(line: string): string[] {
  // 从表格整列复制时是制表符；手工用逗号拼的也兼容。
  const delimiter = line.includes('\t') ? '\t' : ','
  return line.split(delimiter).map((cell) => cell.trim())
}

function parseSheet(text: string): ParsedRow[] {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (!lines.length) return []

  let dataLines = lines
  const firstCells = splitLine(lines[0]).map((cell) => cell)
  const headerIndex = firstCells.map((cell) => HEADER_ALIASES[cell]).findIndex((key) => key === 'code')
  if (headerIndex >= 0) {
    dataLines = lines.slice(1)
  }

  const parsed: ParsedRow[] = []
  dataLines.forEach((line, idx) => {
    const cells = splitLine(line)
    const get = (pos: number) => cells[pos]?.trim() ?? ''
    let code = get(0)
    let floor = get(1)
    if (!floor) {
      const matched = code.match(/^(\dF|B1)-/)
      if (matched) floor = matched[1]
    }
    parsed.push({
      line_no: idx + 1,
      code,
      floor,
      booth_type: get(2),
      area: get(3),
      rent: get(4),
      term: get(5),
    })
  })
  return parsed
}

function resetFilters() {
  filters.value = { keyword: '', floor: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.floor) query.set('floor', filters.value.floor)
  if (filters.value.status) query.set('status', filters.value.status)
  query.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('铺位明细读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '铺位明细读取失败'
  }
  await reloadFloors()
}

async function reloadFloors() {
  try {
    const response = await request(`${ENDPOINT}/floors`)
    if (!response.ok) return
    const payload = await response.json()
    floorRows.value = payload.items ?? []
  } catch {
    // 汇总读不出来时保留旧值，明细列表不受影响
  }
}

function openDrawer() {
  drawerOpen.value = true
  step.value = batch.value && !batch.value.committed ? 2 : 1
  lastResult.value = batch.value?.result ?? null
  lastDuplicated.value = false
  stageError.value = ''
  stageMessage.value = ''
}

function closeDrawer() {
  drawerOpen.value = false
}

async function submitStage() {
  stageMessage.value = ''
  stageError.value = ''
  if (!selectedFloors.value.length) {
    stageMessage.value = '请至少勾选一个楼层'
    return
  }
  if (!parsedRows.value.length) {
    stageMessage.value = '清单内容为空，请先粘贴表格行'
    return
  }
  if (batch.value && !batch.value.committed && !window.confirm('待核对区已有一份未入库清单，本次暂存会整批替换旧清单，是否继续？')) {
    return
  }
  staging.value = true
  try {
    const response = await request(`${ENDPOINT}/stage`, {
      method: 'POST',
      body: JSON.stringify({ floors: selectedFloors.value, rows: parsedRows.value }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail ?? '整批暂存失败')
    batch.value = payload.batch as Batch
    localStorage.setItem(BATCH_KEY, payload.batch.id)
    lastResult.value = null
    lastDuplicated.value = false
    step.value = 2
    if (payload.batch.rejected.length) {
      stageError.value = `有 ${payload.batch.rejected.length} 行未通过检查已整行退回，核对后再入库`
    }
  } catch (error) {
    stageError.value = error instanceof Error ? error.message : '整批暂存失败'
  } finally {
    staging.value = false
  }
}

async function toggleConfirm(item: AcceptedRow, checked: boolean) {
  stageError.value = ''
  try {
    const response = await request(`${ENDPOINT}/stage/confirm`, {
      method: 'PATCH',
      body: JSON.stringify({ line_no: item.line_no, confirmed: checked }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.detail ?? payload.message ?? '确认状态未保存')
    item.confirmed = checked
  } catch (error) {
    stageError.value = error instanceof Error ? error.message : '确认状态未保存'
  }
}

async function confirmAll(checked: boolean) {
  if (!batch.value) return
  for (const item of batch.value.accepted) {
    if (item.confirmed !== checked) await toggleConfirm(item, checked)
  }
}

async function commitStage() {
  if (!batch.value) return
  stageError.value = ''
  committing.value = true
  try {
    const response = await request(`${ENDPOINT}/commit`, { method: 'POST' })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail ?? '入库未生效')
    batch.value.committed = true
    batch.value.result = payload.result as CommitResult
    lastResult.value = payload.result as CommitResult
    lastDuplicated.value = Boolean(payload.duplicated)
    localStorage.removeItem(BATCH_KEY)
    await reload()
  } catch (error) {
    stageError.value = error instanceof Error ? error.message : '入库未生效'
  } finally {
    committing.value = false
  }
}

async function clearStage() {
  if (!window.confirm('整批清空后待核对区一个不留，且无法恢复，是否继续？')) return
  stageError.value = ''
  try {
    const response = await request(`${ENDPOINT}/stage`, { method: 'DELETE' })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.detail ?? '清空失败')
    batch.value = null
    lastResult.value = null
    localStorage.removeItem(BATCH_KEY)
    rawText.value = ''
    selectedFloors.value = []
    step.value = 1
    drawerOpen.value = false
  } catch (error) {
    stageError.value = error instanceof Error ? error.message : '清空失败'
  }
}

async function restoreStage() {
  // 待核对区以服务端那份整批为准；本地只记住批次号。
  // 服务端整批在且编号对得上 → 抽屉可直接回到第二步；服务端没有 → 本地标记一并清掉，不留半批。
  const localId = localStorage.getItem(BATCH_KEY)
  try {
    const response = await request(`${ENDPOINT}/stage`)
    if (!response.ok) return
    const payload = await response.json()
    const serverBatch = payload.batch as Batch | null
    if (serverBatch) {
      // 服务端那份整批是唯一事实来源；编号对不上时同样以它为准（整批替换语义）。
      if (localId !== serverBatch.id) localStorage.setItem(BATCH_KEY, serverBatch.id)
      batch.value = serverBatch
    } else {
      // 服务端整批已清空：本地标记一并抹掉，绝不留「半批」。
      if (localId) localStorage.removeItem(BATCH_KEY)
    }
  } catch {
    // 恢复失败不阻塞明细页使用
  }
}

onMounted(() => {
  void reload()
  void restoreStage()
})
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.stage-badge {
  margin-left: 6px;
  background: #fff;
  color: var(--brand);
  border-radius: 10px;
  padding: 0 8px;
  font-size: 12px;
}
.floor-table { margin-bottom: 16px; }
.booth-table { margin-top: 4px; }
.filter-item select { padding: 4px 8px; border: 1px solid var(--border); border-radius: 6px; }

.drawer-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  justify-content: flex-end;
  z-index: 50;
}
.drawer {
  width: min(960px, 92vw);
  height: 100%;
  background: #f6f8fb;
  display: flex;
  flex-direction: column;
  box-shadow: -8px 0 24px rgba(15, 23, 42, 0.2);
}
.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 20px;
  background: #fff;
  border-bottom: 1px solid var(--border);
}
.drawer-head h3 { margin: 0 0 4px; }
.drawer-step { margin: 0; color: var(--muted); font-size: 12px; }
.drawer-body { flex: 1; overflow: auto; padding: 16px 20px; }
.drawer-foot {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  background: #fff;
  border-top: 1px solid var(--border);
}
.drawer-foot .error-text { margin-right: auto; }
.btn.danger { color: #b42318; border-color: #f0a9a0; }

.floor-picker {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  padding: 12px;
  margin: 0 0 12px;
}
.floor-picker legend { color: var(--muted); font-size: 12px; padding: 0 6px; }
.floor-check { display: inline-flex; align-items: center; gap: 6px; margin-right: 20px; font-size: 14px; }
.paste-box span { display: block; font-size: 13px; margin-bottom: 6px; }
.paste-box textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 13px;
  resize: vertical;
}
.paste-box small { display: block; color: var(--muted); margin-top: 6px; }
.parsed-preview { margin-top: 8px; color: var(--muted); font-size: 13px; }

.batch-meta { display: flex; gap: 16px; color: var(--muted); font-size: 12px; margin-bottom: 10px; }
.check-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 13px; }
.check-toolbar .btn { padding: 4px 10px; }
.confirmed { background: #f0fdf4; }
.dup-tag { color: #b54708; background: #fffaeb; border: 1px solid #fedf89; border-radius: 4px; padding: 1px 6px; font-size: 12px; }
.ok-text { color: #027a48; font-size: 12px; }
.rejected-block { margin-top: 16px; }
.rejected-block h4 { margin: 0 0 8px; color: #b42318; }
.result-box { margin-top: 16px; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.result-box h4 { margin: 0 0 8px; }
.result-box p { margin: 0 0 10px; font-size: 13px; }
</style>
