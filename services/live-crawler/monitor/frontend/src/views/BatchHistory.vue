<template>
  <div class="dashboard">
    <!-- 页面标题区 -->
    <div class="page-header">
      <div>
        <h1 class="page-title">批次历史</h1>
        <p class="page-subtitle">查看历史采集批次及其完整性</p>
      </div>
      <div class="header-actions">
        <button class="refresh-btn" @click="loadBatches" :class="{ spinning: loading }" aria-label="刷新批次列表" :disabled="loading">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21 2v6h-6M3 22v-6h6M21 13A9 9 0 006.2 6.2L3 8M3 11a9 9 0 0014.8 6.8L21 16"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- 批次卡片列表 -->
    <div class="batch-grid">
      <article
        v-for="(batch, idx) in batches"
        :key="batch.batch_id"
        class="batch-card"
        :style="{ animationDelay: idx * 60 + 'ms' }"
        @click="toggleBatch(batch)"
        @keydown.enter="toggleBatch(batch)"
        @keydown.space.prevent="toggleBatch(batch)"
        role="button"
        tabindex="0"
        :aria-label="`查看批次 ${batch.batch_id}，完整率 ${batch.completeness}%，共 ${batch.total_accounts} 个账号`"
      >
        <!-- 卡片顶部：批次ID + 模式标签 -->
        <div class="card-top">
          <span class="batch-id">{{ batch.batch_id }}</span>
          <span class="mode-badge" :class="'mode-' + batch.mode">{{ batch.mode }}</span>
        </div>

        <!-- 核心指标行 -->
        <div class="card-metrics">
          <!-- 完整率环形图 -->
          <div class="ring-container" aria-hidden="true">
            <svg viewBox="0 0 80 80" class="ring-svg">
              <circle cx="40" cy="40" r="34" fill="none" stroke="var(--border-color)" stroke-width="5"/>
              <circle
                cx="40" cy="40" r="34"
                fill="none"
                :stroke="ringColor(batch.completeness)"
                stroke-width="5"
                stroke-linecap="round"
                :stroke-dasharray="ringDash(batch.completeness)"
                stroke-dashoffset="0"
                transform="rotate(-90 40 40)"
                class="ring-progress"
              />
            </svg>
            <div class="ring-label">
              <span class="ring-value" :style="{ color: ringColor(batch.completeness) }">
                {{ batch.completeness }}
              </span>
              <span class="ring-unit">%</span>
            </div>
          </div>

          <!-- 账号统计 -->
          <div class="metric-group">
            <div class="metric-item">
              <span class="metric-num">{{ batch.success_accounts }}</span>
              <span class="metric-sep">/</span>
              <span class="metric-total">{{ batch.total_accounts }}</span>
            </div>
            <span class="metric-label">ACCOUNTS</span>
          </div>
        </div>

        <!-- 时间信息 -->
        <div class="card-time">
          <div class="time-row">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
            </svg>
            <span>{{ formatTime(batch.started_at) }}</span>
          </div>
          <div class="time-row" v-if="batch.finished_at">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/>
            </svg>
            <span>{{ formatTime(batch.finished_at) }}</span>
          </div>
          <span v-else class="time-running">
            <span class="running-dot" aria-hidden="true"></span> 进行中
          </span>
        </div>
      </article>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && batches.length === 0" class="empty-state" role="status">
      <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--text-muted)" stroke-width="1.5" aria-hidden="true">
        <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>
      </svg>
      <p>暂无采集批次数据</p>
    </div>

    <!-- 账号列表弹窗 -->
    <el-dialog
      v-model="showAccounts"
      :title="'批次 ' + selectedBatch"
      width="90%"
      top="5vh"
      destroy-on-close
    >
      <div class="dialog-stats" v-if="accountStats">
        <div class="stat-chip" :class="{ active: !statusFilter }" @click="statusFilter = null">
          <span class="stat-chip-label">总账号</span>
          <span class="stat-chip-val">{{ accountStats.total }}</span>
        </div>
        <div class="stat-chip success" :class="{ active: statusFilter === 'success' }" @click="toggleFilter('success')">
          <span class="stat-chip-label">成功</span>
          <span class="stat-chip-val">{{ accountStats.success }}</span>
        </div>
        <div class="stat-chip warning" :class="{ active: statusFilter === 'partial' }" @click="toggleFilter('partial')">
          <span class="stat-chip-label">部分</span>
          <span class="stat-chip-val">{{ accountStats.partial }}</span>
        </div>
        <div class="stat-chip danger" :class="{ active: statusFilter === 'failed' }" @click="toggleFilter('failed')">
          <span class="stat-chip-label">失败</span>
          <span class="stat-chip-val">{{ accountStats.failed }}</span>
        </div>
      </div>

      <el-table :data="filteredAccounts" stripe class="account-table" :row-class-name="accountRowClass">
        <el-table-column prop="account_id" label="账号 ID" width="180">
          <template #default="{ row }">
            <span class="mono-text">{{ row.account_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="group_name" label="分组" width="160" />
        <el-table-column prop="platform" label="平台" width="100" align="center">
          <template #default="{ row }">
            <span class="platform-tag" :class="'pt-' + row.platform">{{ row.platform === 'shopee' ? 'Shopee' : 'TikTok' }}</span>
          </template>
        </el-table-column>

        <!-- 账号级 API 状态指示器（动态列） -->
        <el-table-column
          v-for="apiType in allAccountApiTypes"
          :key="apiType"
          :label="apiType"
          width="110"
          align="center"
        >
          <template #default="{ row }">
            <span v-if="apiType in row.api_status" class="status-indicator" :class="'s-' + (row.api_status[apiType] || 'missing')">
              <span class="indicator-dot"></span>
              {{ statusLabel(row.api_status[apiType]) }}
            </span>
            <span v-else class="status-indicator s-na">—</span>
          </template>
        </el-table-column>

        <!-- 直播间完成度 -->
        <el-table-column label="直播间" width="120" align="center">
          <template #default="{ row }">
            <div class="room-bar-wrap">
              <div class="room-bar-bg">
                <div
                  class="room-bar-fill"
                  :style="{
                    width: row.total_rooms ? (row.room_success / row.total_rooms * 100) + '%' : '0%',
                    background: row.room_success === row.total_rooms && row.total_rooms > 0 ? 'var(--accent-green)' : 'var(--accent-amber)'
                  }"
                ></div>
              </div>
              <span class="room-bar-text">{{ row.room_success }}/{{ row.total_rooms }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <span class="status-badge" :class="'sb-' + row.status">{{ row.status }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="70" align="center">
          <template #default="{ row }">
            <button class="detail-btn" @click="goDetail(row.account_id)" :aria-label="`查看账号 ${row.account_id} 详情`">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchBatches, fetchAccounts } from '../api'

const router = useRouter()
const batches = ref([])
const accounts = ref([])
const showAccounts = ref(false)
const selectedBatch = ref('')
const loading = ref(false)
const statusFilter = ref(null)

onMounted(() => loadBatches())

async function loadBatches() {
  loading.value = true
  try {
    const res = await fetchBatches()
    batches.value = res.data.batches
  } catch {
    ElMessage.error('加载批次列表失败')
  } finally {
    loading.value = false
  }
}

async function toggleBatch(batch) {
  selectedBatch.value = batch.batch_id
  statusFilter.value = null
  const res = await fetchAccounts(batch.batch_id)
  accounts.value = res.data.accounts
  showAccounts.value = true
}

function goDetail(accountId) {
  showAccounts.value = false
  router.push({ path: `/account/${accountId}`, query: { batch_id: selectedBatch.value } })
}

const allAccountApiTypes = computed(() => {
  const types = new Set()
  for (const acc of accounts.value) {
    for (const key of Object.keys(acc.api_status || {})) {
      types.add(key)
    }
  }
  return [...types]
})

const accountStats = computed(() => {
  if (!accounts.value.length) return null
  return {
    total: accounts.value.length,
    success: accounts.value.filter(a => a.status === 'success').length,
    partial: accounts.value.filter(a => a.status === 'partial').length,
    failed: accounts.value.filter(a => !['success', 'partial'].includes(a.status)).length,
  }
})

// 按状态筛选账号列表
const filteredAccounts = computed(() => {
  if (!statusFilter.value) return accounts.value
  if (statusFilter.value === 'failed') {
    return accounts.value.filter(a => !['success', 'partial'].includes(a.status))
  }
  return accounts.value.filter(a => a.status === statusFilter.value)
})

function toggleFilter(status) {
  statusFilter.value = statusFilter.value === status ? null : status
}

function ringColor(pct) {
  if (pct >= 90) return 'var(--accent-green)'
  if (pct >= 50) return 'var(--accent-amber)'
  return 'var(--accent-red)'
}

function ringDash(pct) {
  const circumference = 2 * Math.PI * 34
  const filled = (pct / 100) * circumference
  return `${filled} ${circumference}`
}

function formatTime(ts) {
  if (!ts) return '-'
  const d = new Date(ts)
  if (isNaN(d)) return ts
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function statusLabel(s) {
  if (s === 'success') return 'OK'
  if (s === 'failed') return 'FAIL'
  return 'N/A'
}

function accountRowClass({ row }) {
  if (row.status === 'failed' || row.status === 'login_failed') return 'row-failed'
  return ''
}
</script>

<style scoped>
/* ====== Page Header ====== */
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 28px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.5px;
  color: var(--text-primary);
  line-height: 1.2;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 4px;
}

.refresh-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}
.refresh-btn:hover {
  border-color: var(--text-secondary);
  color: var(--text-primary);
}
.refresh-btn.spinning svg {
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ====== Batch Grid ====== */
.batch-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.batch-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 20px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  animation: card-in 0.3s ease-out both;
}
.batch-card:hover {
  border-color: var(--text-muted);
  background: var(--bg-card-hover);
}

@keyframes card-in {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Card Top */
.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.batch-id {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.mode-badge {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1px;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 3px;
  border: 1px solid var(--border-color);
}
.mode-scheduler { color: var(--accent-blue); }
.mode-once { color: var(--accent-purple); }
.mode-full { color: var(--accent-amber); }

/* Card Metrics */
.card-metrics {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 16px;
}

.ring-container {
  position: relative;
  width: 80px;
  height: 80px;
  flex-shrink: 0;
}

.ring-svg { width: 100%; height: 100%; }

.ring-progress {
  transition: stroke-dasharray 0.8s ease;
}

.ring-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1px;
}

.ring-value {
  font-family: var(--font-mono);
  font-size: 20px;
  font-weight: 700;
}

.ring-unit {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

.metric-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-item {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.metric-num {
  font-family: var(--font-mono);
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
}

.metric-sep {
  font-family: var(--font-mono);
  font-size: 18px;
  color: var(--text-muted);
  margin: 0 2px;
}

.metric-total {
  font-family: var(--font-mono);
  font-size: 18px;
  color: var(--text-muted);
}

.metric-label {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1.5px;
  color: var(--text-muted);
}

/* Card Time */
.card-time {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.time-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.time-running {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--accent-green);
  font-weight: 500;
}

.running-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-green);
  animation: pulse-dot 1.5s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ====== Empty State ====== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 80px 0;
  color: var(--text-muted);
  font-size: 15px;
}

/* ====== Dialog Stats ====== */
.dialog-stats {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.stat-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 8px;
  background: rgba(100, 116, 139, 0.1);
  border: 1px solid var(--border-color);
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}
.stat-chip:hover { opacity: 0.85; }
.stat-chip.active { border-width: 2px; }
.stat-chip.success { background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.2); }
.stat-chip.warning { background: rgba(245, 158, 11, 0.08); border-color: rgba(245, 158, 11, 0.2); }
.stat-chip.danger { background: rgba(239, 68, 68, 0.08); border-color: rgba(239, 68, 68, 0.2); }
.stat-chip.success.active { background: rgba(16, 185, 129, 0.18); border-color: var(--accent-green); }
.stat-chip.warning.active { background: rgba(245, 158, 11, 0.18); border-color: var(--accent-amber); }
.stat-chip.danger.active { background: rgba(239, 68, 68, 0.18); border-color: var(--accent-red); }

.stat-chip-label {
  font-size: 12px;
  color: var(--text-muted);
}

.stat-chip-val {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.stat-chip.success .stat-chip-val { color: var(--accent-green); }
.stat-chip.warning .stat-chip-val { color: var(--accent-amber); }
.stat-chip.danger .stat-chip-val { color: var(--accent-red); }

/* ====== Status Indicator ====== */
.status-indicator {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.indicator-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.s-success .indicator-dot { background: var(--accent-green); }
.s-success { color: var(--accent-green); }

.s-failed .indicator-dot { background: var(--accent-red); }
.s-failed { color: var(--accent-red); }

.s-missing .indicator-dot { background: var(--text-muted); opacity: 0.4; }
.s-missing { color: var(--text-muted); }

/* ====== Room Bar ====== */
.room-bar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.room-bar-bg {
  flex: 1;
  height: 6px;
  background: var(--border-color);
  border-radius: 3px;
  overflow: hidden;
}

.room-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}

.room-bar-text {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

/* ====== Status Badge ====== */
.status-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  padding: 3px 10px;
  border-radius: 20px;
  text-transform: uppercase;
  white-space: nowrap;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-block;
}
.sb-success { background: rgba(16, 185, 129, 0.12); color: var(--accent-green); }
.sb-partial { background: rgba(245, 158, 11, 0.12); color: var(--accent-amber); }
.sb-failed, .sb-login_failed { background: rgba(239, 68, 68, 0.12); color: var(--accent-red); }

/* ====== Detail Button ====== */
.detail-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
}
.detail-btn:hover {
  border-color: var(--text-secondary);
  color: var(--text-primary);
  background: rgba(177, 186, 196, 0.04);
}

/* ====== Mono Text ====== */
.mono-text {
  font-family: var(--font-mono);
  font-size: 13px;
}

/* ====== Failed Row ====== */
:deep(.row-failed td) {
  background: rgba(248, 81, 73, 0.04) !important;
}

/* ====== Platform Tag ====== */
.platform-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 3px;
}
.pt-tiktok { color: var(--accent-blue); background: rgba(56, 139, 253, 0.08); }
.pt-shopee { color: #ee4d2d; background: rgba(238, 77, 45, 0.08); }
.s-na { color: var(--text-muted); opacity: 0.3; }

/* ====== 响应式 ====== */
@media (max-width: 640px) {
  .page-title { font-size: 20px; }
  .batch-grid { grid-template-columns: 1fr; }
  .card-metrics { gap: 16px; }
  .ring-container { width: 64px; height: 64px; }
  .ring-value { font-size: 16px; }
  .metric-num { font-size: 22px; }
  .dialog-stats { flex-wrap: wrap; gap: 8px; }
  .stat-chip { padding: 4px 10px; }
  .empty-state { padding: 48px 0; }
}
</style>
