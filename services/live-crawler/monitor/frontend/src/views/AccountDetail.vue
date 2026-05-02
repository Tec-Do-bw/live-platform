<template>
  <div class="account-detail">
    <!-- 顶部导航 -->
    <div class="detail-header">
      <button class="back-btn" @click="$router.push('/')" aria-label="返回账号总览">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        <span>返回总览</span>
      </button>
      <div class="detail-title">
        <span class="title-label">ACCOUNT</span>
        <h2 class="title-id">{{ accountId }}</h2>
      </div>
    </div>

    <!-- 数据概览卡片 -->
    <div class="overview-strip" v-if="detail">
      <div class="ov-card">
        <span class="ov-val">{{ detail.rooms.length }}</span>
        <span class="ov-label">直播场次</span>
      </div>
      <div class="ov-card">
        <span class="ov-val" :style="{ color: completenessColor }">
          {{ Math.round(detail.overall_completeness * 100) }}%
        </span>
        <span class="ov-label">直播间完整率</span>
      </div>
      <div class="ov-card">
        <span class="ov-val">{{ totalGMV }}</span>
        <span class="ov-label">总 GMV</span>
      </div>
    </div>

    <!-- 账号级指标 -->
    <div class="section" v-if="detail">
      <h3 class="section-title">账号级指标</h3>
      <div class="indicator-row">
        <div
          v-for="t in (platformRegistry.account_types || [])"
          :key="t.key"
          class="indicator-tag-wrap"
        >
          <div
            class="indicator-tag"
            :class="'tag-' + getStatus(detail.account_indicators[t.key])"
            :aria-label="t.label + '：' + statusText(getStatus(detail.account_indicators[t.key]))"
          >
            <svg v-if="getStatus(detail.account_indicators[t.key]) === 'success'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
            <svg v-else-if="getStatus(detail.account_indicators[t.key]) === 'failed' || getStatus(detail.account_indicators[t.key]) === 'empty'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
              <path d="M12 9v4M12 17h.01"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
            <span class="tag-label">{{ t.label }}</span>
          </div>
          <!-- 补采按钮 -->
          <el-button
            v-if="getStatus(detail.account_indicators[t.key]) === 'missing'"
            type="warning"
            size="small"
            text
            class="inline-recrawl"
            :loading="recrawlLoading[`account_${t.key}`]"
            :disabled="recrawlLoading[`account_${t.key}`]"
            @click="doRecrawl({ account_id: accountId, level: 'account', api_type: t.key }, `account_${t.key}`)"
          >补采</el-button>
          <el-button
            v-else
            size="small"
            text
            class="inline-recrawl dim"
            :loading="recrawlLoading[`account_${t.key}`]"
            :disabled="recrawlLoading[`account_${t.key}`]"
            @click="doRecrawl({ account_id: accountId, level: 'account', api_type: t.key }, `account_${t.key}`)"
          >补采</el-button>
        </div>
      </div>
    </div>

    <!-- 日期级指标 -->
    <div class="section" v-if="detail && detail.daily_stats.length">
      <h3 class="section-title">日期级指标（按天采集状态）</h3>
      <div class="daily-table-wrap" role="region" aria-label="日期级采集状态表" tabindex="0">
        <table class="daily-table">
          <caption class="sr-only">各 API 类型的每日采集状态</caption>
          <thead>
            <tr>
              <th scope="col" aria-label="API 类型"></th>
              <th scope="col" v-for="day in detail.daily_stats" :key="day.target_date">
                {{ formatDate(day.target_date) }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in (platformRegistry.daily_types || [])" :key="t.key">
              <td class="daily-label" scope="row">{{ t.label }}</td>
              <td
                v-for="day in detail.daily_stats"
                :key="day.target_date"
                class="daily-cell"
                :class="'cell-' + getStatus(day[t.key])"
                :aria-label="t.label + ' ' + formatDate(day.target_date) + '：' + statusText(getStatus(day[t.key]))"
              >
                <div class="daily-cell-inner">
                  <svg v-if="getStatus(day[t.key]) === 'success'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                  <svg v-else-if="getStatus(day[t.key]) === 'failed' || getStatus(day[t.key]) === 'empty'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
                    <path d="M12 9v4M12 17h.01"/>
                  </svg>
                  <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
                    <path d="M18 6L6 18M6 6l12 12"/>
                  </svg>
                  <!-- 日期级补采按钮 -->
                  <el-button
                    v-if="getStatus(day[t.key]) === 'missing'"
                    type="warning"
                    size="small"
                    text
                    class="cell-recrawl"
                    :loading="recrawlLoading[`daily_${t.key}_${day.target_date}`]"
                    :disabled="recrawlLoading[`daily_${t.key}_${day.target_date}`]"
                    @click="doRecrawl({ account_id: accountId, level: 'daily', api_type: t.key, target_date: day.target_date }, `daily_${t.key}_${day.target_date}`)"
                  >补采</el-button>
                  <el-button
                    v-else
                    size="small"
                    text
                    class="cell-recrawl dim"
                    :loading="recrawlLoading[`daily_${t.key}_${day.target_date}`]"
                    :disabled="recrawlLoading[`daily_${t.key}_${day.target_date}`]"
                    @click="doRecrawl({ account_id: accountId, level: 'daily', api_type: t.key, target_date: day.target_date }, `daily_${t.key}_${day.target_date}`)"
                  >补采</el-button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 直播场次列表 -->
    <div class="section" v-if="detail">
      <div class="section-header">
        <h3 class="section-title">直播场次列表</h3>
        <div class="type-legend">
          <span class="legend-item" v-for="t in (platformRegistry.room_types || [])" :key="t.key">{{ t.label }}</span>
        </div>
      </div>

      <div class="room-list" role="list" aria-label="直播场次">
        <div
          v-for="(room, idx) in detail.rooms"
          :key="room.room_id"
          class="room-row"
          role="listitem"
          :style="{ animationDelay: Math.min(idx, 20) * 40 + 'ms' }"
        >
          <div class="room-info">
            <div class="room-title-line">
              <span class="room-name" :title="room.room_name">{{ room.room_name || '未命名直播' }}</span>
              <span class="room-id">{{ room.room_id }}</span>
              <span class="room-completeness" :style="{ color: roomCompColor(room.completeness) }" :aria-label="`完整率 ${Math.round(room.completeness * 100)}%`">
                {{ Math.round(room.completeness * 100) }}%
              </span>
            </div>
            <div class="room-meta">
              <span class="meta-item">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                  <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
                </svg>
                {{ formatTimestamp(room.start_time) }}
              </span>
              <span class="meta-item" v-if="room.end_time">
                {{ formatDuration(room.start_time, room.end_time) }}
              </span>
              <span class="meta-item gmv" v-if="Number(room.revenue)">
                {{ room.currency_code }} {{ Number(room.revenue).toLocaleString() }}
              </span>
              <span class="meta-item" v-if="room.item_sold_cnt">
                {{ room.item_sold_cnt }} 单
              </span>
              <span class="meta-item" v-if="room.view_cnt">
                {{ room.view_cnt }} 观看
              </span>
            </div>
          </div>

          <div class="api-matrix" role="group" :aria-label="`直播间 ${room.room_id} API 状态`">
            <div
              v-for="t in (platformRegistry.room_types || [])"
              :key="t.key"
              class="api-cell-wrap"
            >
              <div
                class="api-cell"
                :class="'cell-' + getStatus(room.indicators[t.key])"
                :title="t.label + '：' + statusText(getStatus(room.indicators[t.key]))"
                :aria-label="t.label + '：' + statusText(getStatus(room.indicators[t.key]))"
              >
                <svg v-if="getStatus(room.indicators[t.key]) === 'success'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
                  <path d="M20 6L9 17l-5-5"/>
                </svg>
                <svg v-else-if="getStatus(room.indicators[t.key]) === 'failed'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
                  <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">
                  <path d="M5 12h14"/>
                </svg>
              </div>
              <!-- 直播间级补采按钮 -->
              <el-button
                v-if="getStatus(room.indicators[t.key]) === 'missing'"
                type="warning"
                size="small"
                text
                class="cell-recrawl"
                :loading="recrawlLoading[`room_${room.room_id}_${t.key}`]"
                :disabled="recrawlLoading[`room_${room.room_id}_${t.key}`]"
                @click="doRecrawl({ account_id: accountId, level: 'room', room_id: room.room_id, api_type: t.key }, `room_${room.room_id}_${t.key}`)"
              >补采</el-button>
              <el-button
                v-else
                size="small"
                text
                class="cell-recrawl dim"
                :loading="recrawlLoading[`room_${room.room_id}_${t.key}`]"
                :disabled="recrawlLoading[`room_${room.room_id}_${t.key}`]"
                @click="doRecrawl({ account_id: accountId, level: 'room', room_id: room.room_id, api_type: t.key }, `room_${room.room_id}_${t.key}`)"
              >补采</el-button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="detail.rooms.length === 0 && !loading" class="empty-rooms">
        <p>该时段下无直播间数据</p>
      </div>
    </div>

    <!-- 补采任务面板 -->
    <div class="section" v-if="detail">
      <el-card class="recrawl-panel" shadow="never">
        <template #header>
          <div class="recrawl-panel-header">
            <h3 class="section-title" style="margin-bottom:0">补采任务</h3>
            <el-button size="small" text @click="loadRecrawlTasks" :loading="recrawlTasksLoading" :disabled="recrawlTasksLoading" aria-label="刷新补采任务列表">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M21 2v6h-6M3 22v-6h6M21 13A9 9 0 006.2 6.2L3 8M3 11a9 9 0 0014.8 6.8L21 16"/>
              </svg>
              刷新
            </el-button>
          </div>
        </template>

        <el-table :data="recrawlTasks" stripe class="recrawl-table" v-if="recrawlTasks.length > 0">
          <el-table-column prop="source" label="来源" width="100">
            <template #default="{ row }">
              <span class="mono-text">{{ row.source || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="api_type" label="API 类型" width="160">
            <template #default="{ row }">
              <span class="mono-text">{{ row.api_type }}</span>
            </template>
          </el-table-column>
          <el-table-column label="目标" min-width="180">
            <template #default="{ row }">
              <span class="mono-text">{{ row.room_id || row.target_date || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="120" align="center">
            <template #default="{ row }">
              <el-tag
                :type="recrawlStatusType(row.status)"
                size="small"
                effect="dark"
              >{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="重试" width="80" align="center">
            <template #default="{ row }">
              <span class="mono-text">{{ row.retry_count || 0 }}/3</span>
            </template>
          </el-table-column>
        </el-table>

        <div v-else class="empty-recrawl">
          <p>暂无补采任务</p>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  fetchAccountDetail, fetchAccountOverview, fetchRegistry,
  triggerRecrawl, fetchRecrawlTasks,
} from '../api'

const props = defineProps({ accountId: String })
const route = useRoute()
const detail = ref(null)
const registry = ref({})
const loading = ref(true)
const recrawlLoading = reactive({})
const recrawlTasks = ref([])
const recrawlTasksLoading = ref(false)
const accountPlatform = ref('tiktok')

const platformRegistry = computed(() => {
  const r = registry.value
  return r[accountPlatform.value] || r['tiktok'] || {}
})

/**
 * 加载详情数据：根据路由参数自动选择 API
 * - 有 batch_id → 调用旧的批次详情 API（从批次历史页跳转）
 * - 无 batch_id → 调用新的跨批次聚合 API（从账号总览页跳转）
 */
async function loadDetail() {
  const batchId = route.query.batch_id
  const days = Number(route.query.days) || 3

  if (batchId) {
    // 批次模式：使用旧 API，返回格式已匹配模板
    const res = await fetchAccountDetail(batchId, props.accountId)
    detail.value = res.data
    // 直接使用后端返回的 platform 字段
    accountPlatform.value = detail.value?.platform || 'tiktok'
  } else {
    // 聚合模式：使用新 API，需要转换字段名以匹配模板
    const res = await fetchAccountOverview(props.accountId, days)
    const d = res.data
    detail.value = {
      account_id: props.accountId,
      // 将 account_level 数组转为 {api_type: {status, ...}} 字典
      account_indicators: Object.fromEntries(
        (d.account_level || []).map(a => [a.api_type, { status: a.status === 'missing' ? null : a.status }])
      ),
      // 将 daily_level 数组转为旧格式
      daily_stats: transformDailyLevel(d.daily_level || []),
      // 将 room_level 转为旧格式
      rooms: (d.room_level || []).map(r => ({
        room_id: r.room_id,
        room_name: r.room_name || '',
        start_time: r.start_time || 0,
        end_time: r.end_time || 0,
        revenue: r.revenue || '0',
        currency_code: r.currency_code || '',
        item_sold_cnt: r.item_sold_cnt || 0,
        view_cnt: r.view_cnt || 0,
        indicators: Object.fromEntries(
          (r.apis || []).map(a => [a.api_type, { status: a.status === 'missing' ? null : a.status }])
        ),
        completeness: r.apis ? r.apis.filter(a => a.status === 'success').length / (r.apis.length || 1) : 0,
      })),
      overall_completeness: (d.completeness || 0) / 100,
    }
    // 直接使用后端返回的 platform 字段
    accountPlatform.value = d.platform || 'tiktok'
  }
}

/**
 * 将新 API 的 daily_level 数组转为旧 API 的 daily_stats 格式
 * 新: [{target_date, api_type, status}] → 旧: [{target_date, live_stats: {status}}]
 */
function transformDailyLevel(dailyLevel) {
  const dateMap = {}
  for (const item of dailyLevel) {
    if (!dateMap[item.target_date]) {
      dateMap[item.target_date] = { target_date: item.target_date }
    }
    dateMap[item.target_date][item.api_type] = {
      status: item.status === 'missing' ? null : item.status,
    }
  }
  return Object.values(dateMap).sort((a, b) => a.target_date.localeCompare(b.target_date))
}

onMounted(async () => {
  try {
    const [, registryRes] = await Promise.all([
      loadDetail(),
      fetchRegistry(),
    ])
    registry.value = registryRes.data
    // 同时加载补采任务
    await loadRecrawlTasks()
  } finally {
    loading.value = false
  }
})

const completenessColor = computed(() => {
  if (!detail.value) return ''
  const pct = detail.value.overall_completeness * 100
  if (pct >= 90) return 'var(--accent-green)'
  if (pct >= 50) return 'var(--accent-amber)'
  return 'var(--accent-red)'
})

function roomCompColor(comp) {
  const pct = comp * 100
  if (pct >= 90) return 'var(--accent-green)'
  if (pct >= 50) return 'var(--accent-amber)'
  return 'var(--accent-red)'
}

const totalGMV = computed(() => {
  if (!detail.value || !detail.value.rooms.length) return '-'
  const currencies = {}
  for (const r of detail.value.rooms) {
    const code = r.currency_code || 'USD'
    currencies[code] = (currencies[code] || 0) + Number(r.revenue || 0)
  }
  const parts = Object.entries(currencies)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => `${k} ${v.toLocaleString()}`)
  return parts.join(' / ') || '-'
})

function getStatus(indicator) {
  if (!indicator || indicator.status === null || indicator.status === undefined) return 'missing'
  return indicator.status
}

/**
 * 状态的可读文本（用于 aria-label）
 */
function statusText(status) {
  const map = { success: '成功', failed: '失败', empty: '空数据', missing: '缺失' }
  return map[status] || status
}

function formatDate(dateStr) {
  // 'YYYY-MM-DD' → 'MM-DD'
  return dateStr ? dateStr.slice(5) : ''
}

function formatTimestamp(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
  })
}

function formatDuration(start, end) {
  if (!start || !end) return ''
  const minutes = Math.round((end - start) / 60)
  if (minutes < 60) return `${minutes}分钟`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${h}时${m}分`
}

/**
 * 触发补采请求
 * @param {Object} data - 补采参数
 * @param {string} loadingKey - loading 状态键
 */
async function doRecrawl(data, loadingKey) {
  recrawlLoading[loadingKey] = true
  try {
    await triggerRecrawl(data)
    ElMessage.success('补采任务已提交')
    // 成功后刷新页面数据
    await Promise.all([loadDetail(), loadRecrawlTasks()])
  } catch (err) {
    ElMessage.error(`补采请求失败: ${err.message || '未知错误'}`)
  } finally {
    recrawlLoading[loadingKey] = false
  }
}

/**
 * 加载补采任务列表
 */
async function loadRecrawlTasks() {
  recrawlTasksLoading.value = true
  try {
    const res = await fetchRecrawlTasks({ account_id: props.accountId })
    recrawlTasks.value = res.data.tasks || []
  } catch {
    // 补采任务接口可能尚未实现，静默忽略
    recrawlTasks.value = []
  } finally {
    recrawlTasksLoading.value = false
  }
}

/**
 * 补采任务状态对应 el-tag 类型
 */
function recrawlStatusType(status) {
  const map = {
    pending: 'info',
    running: 'warning',
    success: 'success',
    recrawl_failed: 'danger',
  }
  return map[status] || 'info'
}
</script>

<style scoped>
/* ====== Header ====== */
.detail-header {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 8px 16px;
  color: var(--text-secondary);
  font-family: var(--font-display);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.back-btn:hover {
  color: var(--text-primary);
  border-color: var(--text-muted);
}

.detail-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.title-label {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 2px;
  color: var(--text-muted);
}

.title-id {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

/* ====== Overview Strip ====== */
.overview-strip {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.ov-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
}

.ov-val {
  font-family: var(--font-mono);
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.ov-label {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ====== Section ====== */
.section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

/* ====== Account Indicator Tags ====== */
.indicator-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.indicator-tag-wrap {
  display: flex;
  align-items: center;
  gap: 4px;
}

.indicator-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
}

.tag-success {
  background: rgba(16, 185, 129, 0.12);
  color: var(--accent-green);
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.tag-failed, .tag-empty {
  background: rgba(245, 158, 11, 0.12);
  color: var(--accent-amber);
  border: 1px solid rgba(245, 158, 11, 0.2);
}

.tag-missing {
  background: rgba(100, 116, 139, 0.08);
  color: var(--text-muted);
  border: 1px solid var(--border-color);
}

.tag-label {
  font-family: var(--font-mono);
  font-size: 12px;
}

/* ====== 内联补采按钮 ====== */
.inline-recrawl {
  font-size: 11px;
  padding: 4px 10px;
  min-height: 28px;
}
.inline-recrawl.dim {
  opacity: 0.4;
}
.inline-recrawl.dim:hover {
  opacity: 1;
}

.cell-recrawl {
  font-size: 10px;
  padding: 4px 8px;
  min-height: 28px;
  min-width: 36px;
  margin-left: 2px;
}
.cell-recrawl.dim {
  opacity: 0.3;
}
.cell-recrawl.dim:hover {
  opacity: 1;
}

/* ====== Daily Stats Table ====== */
.daily-table-wrap {
  overflow-x: auto;
}

.daily-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.daily-table th, .daily-table td {
  padding: 10px 16px;
  text-align: center;
  border-bottom: 1px solid var(--border-color);
}

.daily-table th {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  letter-spacing: 0.5px;
}

.daily-label {
  text-align: left !important;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.daily-cell {
  font-weight: 700;
  font-size: 14px;
}

.daily-cell-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.daily-cell.cell-success { color: var(--accent-green); }
.daily-cell.cell-failed, .daily-cell.cell-empty { color: var(--accent-amber); }
.daily-cell.cell-missing { color: var(--text-muted); opacity: 0.4; }

/* ====== Type Legend ====== */
.type-legend {
  display: flex;
  gap: 6px;
}

.legend-item {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  padding: 3px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 4px;
}

/* ====== Room List ====== */
.room-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.room-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  transition: all 0.2s;
  animation: row-in 0.35s ease-out both;
}
.room-row:hover {
  border-color: var(--text-muted);
  background: var(--bg-card-hover);
}

@keyframes row-in {
  from { opacity: 0; transform: translateX(-12px); }
  to { opacity: 1; transform: translateX(0); }
}

.room-info {
  flex: 1;
  min-width: 0;
  margin-right: 20px;
}

.room-title-line {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.room-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 400px;
}

.room-id {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.room-completeness {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.room-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.meta-item.gmv {
  color: var(--accent-amber);
  font-weight: 600;
}

/* ====== API Matrix ====== */
.api-matrix {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.api-cell-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.api-cell {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.2s;
}

.cell-success {
  background: rgba(16, 185, 129, 0.12);
  color: var(--accent-green);
  border: 1px solid rgba(16, 185, 129, 0.2);
}
.cell-success:hover {
  background: rgba(63, 185, 80, 0.18);
}

.cell-failed {
  background: rgba(239, 68, 68, 0.12);
  color: var(--accent-red);
  border: 1px solid rgba(239, 68, 68, 0.2);
}
.cell-failed:hover {
  background: rgba(248, 81, 73, 0.18);
}

.cell-missing {
  background: rgba(100, 116, 139, 0.08);
  color: var(--text-muted);
  border: 1px solid var(--border-color);
  opacity: 0.5;
}

/* ====== 补采任务面板 ====== */
.recrawl-panel {
  background: var(--bg-card) !important;
  border-color: var(--border-color) !important;
  border-radius: var(--radius-md) !important;
}

:deep(.recrawl-panel .el-card__header) {
  border-bottom-color: var(--border-color);
  padding: 14px 20px;
}

:deep(.recrawl-panel .el-card__body) {
  padding: 0;
}

.recrawl-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mono-text {
  font-family: var(--font-mono);
  font-size: 12px;
}

.empty-recrawl {
  text-align: center;
  padding: 40px 0;
  color: var(--text-muted);
  font-size: 13px;
}

/* ====== Empty ====== */
.empty-rooms {
  text-align: center;
  padding: 60px 0;
  color: var(--text-muted);
  font-size: 14px;
}

/* ====== 屏幕阅读器专用（视觉隐藏） ====== */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* ====== 可滚动区域的焦点样式 ====== */
.daily-table-wrap:focus-visible {
  outline: 2px solid var(--accent-blue);
  outline-offset: 2px;
  border-radius: var(--radius-md);
}

/* ====== 响应式 ====== */
@media (max-width: 768px) {
  .detail-header { flex-direction: column; align-items: flex-start; gap: 12px; }
  .overview-strip { flex-direction: column; gap: 8px; }
  .ov-card { padding: 12px 16px; }
  .ov-val { font-size: 20px; }
  .room-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .room-info { margin-right: 0; width: 100%; }
  .room-name { max-width: 100%; }
  .api-matrix { width: 100%; justify-content: flex-start; flex-wrap: wrap; }
  .section-header { flex-direction: column; align-items: flex-start; gap: 8px; }
  .type-legend { flex-wrap: wrap; }
}

@media (max-width: 480px) {
  .room-title-line { flex-wrap: wrap; gap: 6px; }
  .room-meta { gap: 8px; }
  .indicator-row { gap: 6px; }
  .indicator-tag { padding: 6px 10px; font-size: 12px; }
  .daily-table th, .daily-table td { padding: 6px 8px; }
}
</style>
