<template>
  <section class="page" data-module="leasing">
    <header class="page-head">
      <div>
        <h2>招商交接管理</h2>
        <p class="page-desc">多选楼层整批暂存进待核对区，只做格式与编号检查，逐条确认后才入库。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportShops">导出铺位清单</button>
      </div>
    </header>

    <!-- 楼层汇总：铺位条数跟着明细一起重算 -->
    <div class="stat-row">
      <article v-for="floor in floorSummary" :key="floor.楼层" class="stat-card">
        <span class="stat-label">{{ floor.楼层 }}</span>
        <strong class="stat-value">{{ floor.铺位条数 }} 铺</strong>
      </article>
    </div>

    <!-- 铺位明细 -->
    <form class="filter-bar" @submit.prevent="reloadShops">
      <label class="filter-item">
        <span>铺位编号</span>
        <input v-model="shopFilters.keyword" placeholder="按铺位编号检索" />
      </label>
      <label class="filter-item">
        <span>楼层</span>
        <select v-model="shopFilters.floor">
          <option value="">全部楼层</option>
          <option v-for="f in floorOptions" :key="f" :value="f">{{ f }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>签约状态</span>
        <select v-model="shopFilters.status">
          <option value="">全部状态</option>
          <option v-for="s in shopStatuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetShopFilters">重置</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>铺位编号</th>
          <th>楼层</th>
          <th>租金</th>
          <th>租期</th>
          <th>签约状态</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in shops" :key="row.id">
          <td>{{ row.铺位编号 }}</td>
          <td>{{ row.楼层 }}</td>
          <td>{{ row.租金 }}</td>
          <td>{{ row.租期 }}</td>
          <td>{{ row.签约状态 }}</td>
        </tr>
        <tr v-if="!shops.length">
          <td colspan="5" class="empty-state">暂无铺位数据</td>
        </tr>
      </tbody>
    </table>

    <!-- 暂存交接抽屉：两步式交接 -->
    <section class="drawer">
      <header class="drawer-head">
        <h3>暂存交接区</h3>
        <p class="page-desc">第一步：多选楼层整批暂存（只做格式与编号检查）；第二步：逐条确认后整批入库。</p>
      </header>

      <!-- 多选楼层 -->
      <div class="stage-picker">
        <span class="picker-label">选择楼层：</span>
        <label v-for="f in floorOptions" :key="f" class="check-item">
          <input type="checkbox" :value="f" v-model="selectedFloors" />
          <span>{{ f }}</span>
        </label>
        <button class="btn primary" type="button" @click="stageBatch" :disabled="!selectedFloors.length">整批暂存</button>
      </div>

      <!-- 暂存批次列表 -->
      <div v-for="batch in batches" :key="batch.id" class="batch-card">
        <header class="batch-head">
          <div>
            <strong>{{ batch.批次号 }}</strong>
            <span class="batch-meta">
              楼层：{{ batch.楼层.join('、') }} · {{ batch.rows.length }} 行 · {{ batch.创建时间 }}
            </span>
          </div>
          <span class="batch-status" :class="statusClass(batch.状态)">{{ batch.状态 }}</span>
        </header>

        <table class="data-table">
          <thead>
            <tr>
              <th>行号</th>
              <th>铺位编号</th>
              <th>楼层</th>
              <th>租金</th>
              <th>租期</th>
              <th>校验</th>
              <th>核对状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in batch.rows" :key="row.id" :class="{ 'row-invalid': !row.有效, 'row-dup': row.重复 }">
              <td>
                {{ row.行号 }}
                <span v-if="row.重复" class="dup-tag" :title="'重复行号：' + row.重复行号.join('、')">重复</span>
              </td>
              <td>{{ row.铺位编号 || '—' }}</td>
              <td>{{ row.楼层 }}</td>
              <td>
                <span v-if="row.租金有效">{{ row.租金 }}</span>
                <span v-else class="invalid-text">{{ row.租金_raw === '' || row.租金_raw === null ? '空' : row.租金_raw }}</span>
              </td>
              <td>{{ row.租期 }}</td>
              <td>
                <span v-if="row.有效" class="ok-text">通过</span>
                <span v-else class="invalid-text">{{ row.退回原因 }}</span>
                <div v-if="row.重复" class="dup-note">重复行号：{{ row.重复行号.join('、') }}</div>
              </td>
              <td>{{ row.核对状态 }}</td>
              <td>
                <button
                  v-if="row.核对状态 === '待核对' && row.有效 && batch.状态 === '待核对'"
                  class="link"
                  type="button"
                  @click="confirmRow(batch, row)"
                >确认入库</button>
                <span v-else>—</span>
              </td>
            </tr>
          </tbody>
        </table>

        <footer class="batch-foot">
          <span class="batch-summary">
            共 {{ batch.rows.length }} 行，
            有效 {{ validCount(batch) }} 行，
            退回 {{ rejectCount(batch) }} 行，
            已确认 {{ confirmedCount(batch) }} 行
          </span>
          <div class="batch-actions">
            <button
              v-if="batch.状态 === '待核对'"
              class="btn primary"
              type="button"
              @click="confirmAll(batch)"
            >整批入库</button>
            <button
              v-if="batch.状态 === '待核对'"
              class="btn ghost"
              type="button"
              @click="discardBatch(batch)"
            >整批清空</button>
          </div>
        </footer>
      </div>

      <div v-if="!batches.length" class="empty-state">暂无暂存批次，勾选楼层后整批暂存</div>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条铺位记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-if="infoMessage" class="info-text">{{ infoMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>
type Batch = Record<string, any>

const ENDPOINT = '/api/leasing'
const shopStatuses = ['待签约', '已签约', '已退租']

const shops = ref<Row[]>([])
const total = ref(0)
const floorSummary = ref<Row[]>([])
const floorOptions = ref<string[]>([])
const batches = ref<Batch[]>([])
const selectedFloors = ref<string[]>([])
const shopFilters = ref<Record<string, string>>({ keyword: '', floor: '', status: '' })
const errorMessage = ref('')
const infoMessage = ref('')

function statusClass(status: string): string {
  const map: Record<string, string> = { '待核对': 'status-pending', '已入库': 'status-done', '已清空': 'status-discarded' }
  return map[status] ?? ''
}

function validCount(batch: Batch): number {
  return batch.rows.filter((r: Row) => r.有效).length
}
function rejectCount(batch: Batch): number {
  return batch.rows.filter((r: Row) => !r.有效).length
}
function confirmedCount(batch: Batch): number {
  return batch.rows.filter((r: Row) => r.核对状态 === '已确认').length
}

async function reloadShops() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (shopFilters.value.keyword) params.set('keyword', shopFilters.value.keyword)
  if (shopFilters.value.floor) params.set('floor', shopFilters.value.floor)
  if (shopFilters.value.status) params.set('status', shopFilters.value.status)
  try {
    const response = await request(`${ENDPOINT}?${params}`)
    if (!response.ok) throw new Error('铺位列表读取失败')
    const payload = await response.json()
    shops.value = payload.items ?? []
    total.value = payload.total ?? shops.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '铺位列表读取失败'
  }
}

async function reloadFloors() {
  try {
    const response = await request(`${ENDPOINT}/floors`)
    if (!response.ok) throw new Error('楼层汇总读取失败')
    const payload = await response.json()
    floorSummary.value = payload.items ?? []
    floorOptions.value = payload.options ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '楼层汇总读取失败'
  }
}

async function reloadBatches() {
  try {
    const response = await request(`${ENDPOINT}/staging`)
    if (!response.ok) throw new Error('暂存批次读取失败')
    const payload = await response.json()
    batches.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '暂存批次读取失败'
  }
}

function resetShopFilters() {
  shopFilters.value = { keyword: '', floor: '', status: '' }
  void reloadShops()
}

function exportShops() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function stageBatch() {
  errorMessage.value = ''
  infoMessage.value = ''
  if (!selectedFloors.value.length) {
    errorMessage.value = '请先勾选要交接的楼层'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/staging`, {
      method: 'POST',
      body: JSON.stringify({ floors: selectedFloors.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '暂存失败')
    }
    infoMessage.value = payload.message || '已整批暂存'
    selectedFloors.value = []
    await reloadBatches()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '暂存失败'
  }
}

async function confirmRow(batch: Batch, row: Row) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/staging/${batch.id}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ row_ids: [row.id] }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '入库失败')
    }
    infoMessage.value = payload.message || '已入库'
    await Promise.all([reloadBatches(), reloadShops(), reloadFloors()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '入库失败'
  }
}

async function confirmAll(batch: Batch) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/staging/${batch.id}/confirm`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '整批入库失败')
    }
    infoMessage.value = payload.message || '已整批入库'
    await Promise.all([reloadBatches(), reloadShops(), reloadFloors()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '整批入库失败'
  }
}

async function discardBatch(batch: Batch) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/staging/${batch.id}/discard`, { method: 'POST' })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '清空失败')
    }
    infoMessage.value = payload.message || '已整批清空'
    await reloadBatches()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '清空失败'
  }
}

onMounted(() => {
  void Promise.all([reloadShops(), reloadFloors(), reloadBatches()])
})
</script>

<style scoped>
.drawer {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
}
.drawer-head h3 { margin: 0 0 4px; font-size: 15px; }
.stage-picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px dashed var(--border);
  margin-bottom: 10px;
}
.picker-label { font-size: 13px; color: var(--muted); }
.check-item { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; cursor: pointer; }
.batch-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
}
.batch-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f8fafc;
  border-bottom: 1px solid var(--border);
}
.batch-meta { margin-left: 8px; font-size: 12px; color: var(--muted); font-weight: normal; }
.batch-status { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.status-pending { background: #fef3c7; color: #92400e; }
.status-done { background: #d1fae5; color: #065f46; }
.status-discarded { background: #e5e7eb; color: #6b7280; }
.batch-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f8fafc;
  border-top: 1px solid var(--border);
}
.batch-summary { font-size: 12px; color: var(--muted); }
.batch-actions { display: flex; gap: 6px; }
.row-invalid { background: #fef2f2; }
.row-dup { background: #fffbeb; }
.dup-tag {
  display: inline-block;
  margin-left: 4px;
  font-size: 11px;
  color: #92400e;
  background: #fef3c7;
  border-radius: 4px;
  padding: 0 4px;
}
.dup-note { font-size: 11px; color: #92400e; margin-top: 2px; }
.invalid-text { color: #b42318; font-size: 12px; }
.ok-text { color: #065f46; font-size: 12px; }
.info-text { color: #065f46; }
</style>
