<template>
  <div class="account-overview">
    <!-- 页面标题区 -->
    <div class="page-header">
      <div>
        <h1 class="page-title">账号总览</h1>
        <p class="page-subtitle">跨批次聚合视角，监控各账号采集完整性</p>
      </div>
      <div class="header-actions">
        <el-radio-group v-model="platformFilter" size="small" class="platform-filter" @change="loadOverview">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="tiktok">TikTok</el-radio-button>
          <el-radio-button label="shopee">Shopee</el-radio-button>
        </el-radio-group>

        <el-select
          v-model="days"
          class="days-select"
          size="small"
          @change="loadOverview"
        >
          <el-option :value="3" label="近 3 天" />
          <el-option :value="7" label="近 7 天" />
          <el-option :value="30" label="近 30 天" />
        </el-select>

        <el-radio-group v-model="statusFilter" size="small" class="status-filter">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="success">成功</el-radio-button>
          <el-radio-button label="partial">部分</el-radio-button>
          <el-radio-button label="failed">失败</el-radio-button>
        </el-radio-group>

        <router-link to="/batches" class="nav-link" aria-label="查看批次历史">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>
          </svg>
          <span>批次历史</span>
        </router-link>

        <button class="refresh-btn" @click="loadOverview" :class="{ spinning: loading }" aria-label="刷新数据" :disabled="loading">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21 2v6h-6M3 22v-6h6M21 13A9 9 0 006.2 6.2L3 8M3 11a9 9 0 0014.8 6.8L21 16"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- 账号卡片网格 -->
    <el-row :gutter="16" v-if="filteredAccounts.length">
      <el-col
        v-for="(account, idx) in filteredAccounts"
        :key="account.account_id"
        :xs="24" :sm="12" :md="8" :lg="6"
        class="card-col"
      >
        <article
          class="account-card"
          :style="{ animationDelay: idx * 50 + 'ms' }"
          @click="goDetail(account.account_id)"
          @keydown.enter="goDetail(account.account_id)"
          @keydown.space.prevent="goDetail(account.account_id)"
          role="button"
          tabindex="0"
          :aria-label="`查看账号 ${account.account_id} 详情，完整率 ${account.completeness}%`"
        >
          <!-- 卡片顶部：账号名 + 分组 -->
          <div class="card-top">
            <span class="account-name" :title="account.account_id">{{ account.account_id }}</span>
            <span class="group-badge" v-if="account.group_name">{{ account.group_name }}</span>
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
                  :stroke="ringColor(account.completeness)"
                  stroke-width="5"
                  stroke-linecap="round"
                  :stroke-dasharray="ringDash(account.completeness)"
                  stroke-dashoffset="0"
                  transform="rotate(-90 40 40)"
                  class="ring-progress"
                />
              </svg>
              <div class="ring-label">
                <span class="ring-value" :style="{ color: ringColor(account.completeness) }">
                  {{ account.completeness }}
                </span>
                <span class="ring-unit">%</span>
              </div>
            </div>

            <!-- 统计数字 -->
            <div class="metric-group">
              <div class="metric-row">
                <span class="metric-num">{{ account.total_rooms }}</span>
                <span class="metric-label">直播间</span>
              </div>
              <div class="metric-row">
                <span class="metric-num miss" :class="{ 'has-miss': account.missing_count > 0 }">
                  {{ account.missing_count }}
                </span>
                <span class="metric-label">缺失</span>
              </div>
            </div>
          </div>

          <!-- 底部操作 -->
          <div class="card-footer">
            <el-button
              v-if="account.missing_count > 0"
              type="warning"
              size="small"
              plain
              class="recrawl-card-btn"
              @click.stop="recrawlAccount(account)"
              :loading="account._recrawling"
              :disabled="account._recrawling"
            >
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M21 2v6h-6M3 22v-6h6M21 13A9 9 0 006.2 6.2L3 8M3 11a9 9 0 0014.8 6.8L21 16"/>
              </svg>
              一键补采
            </el-button>
            <span v-else class="all-ok">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              全部完成
            </span>
          </div>
        </article>
      </el-col>
    </el-row>

    <!-- 空状态 -->
    <div v-if="!loading && filteredAccounts.length === 0" class="empty-state">
      <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--text-muted)" stroke-width="1.5" aria-hidden="true">
        <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
      </svg>
      <p v-if="accounts.length === 0">暂无账号数据</p>
      <p v-else>当前筛选条件下无匹配账号</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchOverview, triggerRecrawl } from '../api'

const router = useRouter()
const accounts = ref([])
const days = ref(3)
const platformFilter = ref('')
const statusFilter = ref('all')
const loading = ref(false)

onMounted(() => loadOverview())

/**
 * 加载账号总览数据
 */
async function loadOverview() {
  loading.value = true
  try {
    const res = await fetchOverview(days.value, platformFilter.value || undefined)
    accounts.value = (res.data.accounts || []).map(a => ({ ...a, _recrawling: false }))
  } catch (err) {
    ElMessage.error('加载账号总览失败')
  } finally {
    loading.value = false
  }
}

/**
 * 按状态筛选账号
 */
const filteredAccounts = computed(() => {
  if (statusFilter.value === 'all') return accounts.value
  return accounts.value.filter(a => {
    if (statusFilter.value === 'success') return a.completeness === 100
    if (statusFilter.value === 'partial') return a.completeness > 0 && a.completeness < 100
    if (statusFilter.value === 'failed') return a.completeness === 0
    return true
  })
})

/**
 * 跳转到账号详情
 */
function goDetail(accountId) {
  router.push({ path: `/account/${accountId}`, query: { days: days.value } })
}

/**
 * 一键补采（账号级）
 */
async function recrawlAccount(account) {
  account._recrawling = true
  try {
    await triggerRecrawl({ account_id: account.account_id, level: 'account' })
    ElMessage.success(`已提交 ${account.account_id} 补采任务`)
    await loadOverview()
  } catch (err) {
    ElMessage.error(`补采请求失败: ${err.message || '未知错误'}`)
  } finally {
    account._recrawling = false
  }
}

// ===== 环形进度条工具函数 =====

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
</script>

<style scoped>
/* ====== 页面头部 ====== */
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 28px;
  flex-wrap: wrap;
  gap: 16px;
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

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

/* ====== 天数选择器 ====== */
.days-select {
  width: 110px;
}
:deep(.days-select .el-input__wrapper) {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  box-shadow: none !important;
}

/* ====== 状态筛选按钮组 ====== */
:deep(.status-filter .el-radio-button__inner) {
  background: var(--bg-card);
  border-color: var(--border-color);
  color: var(--text-secondary);
  font-size: 12px;
  padding: 5px 14px;
}
:deep(.status-filter .el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: var(--accent-blue);
  border-color: var(--accent-blue);
  color: #fff;
  box-shadow: -1px 0 0 0 var(--accent-blue);
}

/* ====== 平台筛选按钮组 ====== */
:deep(.platform-filter .el-radio-button__inner) {
  background: var(--bg-card);
  border-color: var(--border-color);
  color: var(--text-secondary);
  font-size: 12px;
  padding: 5px 14px;
}
:deep(.platform-filter .el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: var(--accent-blue);
  border-color: var(--accent-blue);
  color: #fff;
  box-shadow: -1px 0 0 0 var(--accent-blue);
}

/* ====== 导航链接 ====== */
.nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 13px;
  text-decoration: none;
  transition: all 0.2s;
  white-space: nowrap;
}
.nav-link:hover {
  border-color: var(--text-secondary);
  color: var(--text-primary);
}

/* ====== 刷新按钮 ====== */
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

/* ====== 卡片列布局 ====== */
.card-col {
  margin-bottom: 16px;
}

/* ====== 账号卡片 ====== */
.account-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 20px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  animation: card-in 0.3s ease-out both;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.account-card:hover {
  border-color: var(--text-muted);
  background: var(--bg-card-hover);
}

@keyframes card-in {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ====== 卡片顶部 ====== */
.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 8px;
}

.account-name {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.group-badge {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.5px;
  padding: 2px 8px;
  border-radius: 3px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  white-space: nowrap;
  flex-shrink: 0;
}

/* ====== 卡片指标区 ====== */
.card-metrics {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 16px;
  flex: 1;
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
  gap: 10px;
}

.metric-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.metric-num {
  font-family: var(--font-mono);
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.metric-num.miss {
  color: var(--text-muted);
}
.metric-num.has-miss {
  color: var(--accent-amber);
}

.metric-label {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  letter-spacing: 0.5px;
}

/* ====== 卡片底部 ====== */
.card-footer {
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
}

.recrawl-card-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
}

.all-ok {
  display: flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  color: var(--accent-green);
  letter-spacing: 0.5px;
}

/* ====== 空状态 ====== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 80px 0;
  color: var(--text-muted);
  font-size: 15px;
}

/* ====== 响应式 ====== */
@media (max-width: 640px) {
  .page-header { margin-bottom: 20px; }
  .page-title { font-size: 20px; }
  .header-actions { gap: 8px; }
  .card-metrics { gap: 14px; }
  .ring-container { width: 64px; height: 64px; }
  .ring-value { font-size: 16px; }
  .metric-num { font-size: 18px; }
  .empty-state { padding: 48px 0; }
}
</style>
