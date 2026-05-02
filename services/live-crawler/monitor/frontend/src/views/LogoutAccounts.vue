<template>
  <div class="login-monitor">
    <div class="page-header">
      <div>
        <h1 class="page-title">登录状态监控</h1>
        <p class="page-subtitle">聚焦账号登出、重新登录与恢复全量执行过程，不再展示旧恢复任务链路。</p>
      </div>
      <div class="header-actions">
        <div class="search-bar">
          <input
            v-model.trim="searchAccountId"
            class="search-input"
            type="text"
            placeholder="输入账号 ID 查看历史"
            @keydown.enter="searchAccount"
          >
          <button class="search-btn" @click="searchAccount">查询</button>
        </div>
        <button class="refresh-btn" @click="refreshCurrentView" :disabled="loadingList || loadingDetail">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M21 2v6h-6M3 22v-6h6M21 13A9 9 0 006.2 6.2L3 8M3 11a9 9 0 0014.8 6.8L21 16"/>
          </svg>
          刷新
        </button>
      </div>
    </div>

    <div class="monitor-grid">
      <aside class="sidebar-panel">
        <div class="panel-head">
          <div>
            <div class="panel-title">当前登出账号</div>
            <div class="panel-caption">{{ logoutAccounts.length }} 个账号等待重新登录后自动恢复</div>
          </div>
          <el-select
            v-model="platformFilter"
            class="platform-select"
            size="small"
            placeholder="平台筛选"
            @change="loadLogoutAccounts"
          >
            <el-option label="全部平台" value="" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="Shopee" value="shopee" />
          </el-select>
        </div>

        <div class="stats-strip">
          <div class="stats-card">
            <span class="stats-value danger">{{ logoutAccounts.length }}</span>
            <span class="stats-label">Logout</span>
          </div>
          <div class="stats-card">
            <span class="stats-value">{{ tiktokLogoutCount }}</span>
            <span class="stats-label">TikTok</span>
          </div>
          <div class="stats-card">
            <span class="stats-value">{{ shopeeLogoutCount }}</span>
            <span class="stats-label">Shopee</span>
          </div>
        </div>

        <div v-if="logoutAccounts.length" class="account-list">
          <button
            v-for="account in logoutAccounts"
            :key="account.account_id"
            class="account-item"
            :class="{ active: selectedAccountId === account.account_id && selectedSource === 'list' }"
            @click="selectAccount(account.account_id, 'list')"
          >
            <div class="account-item-top">
              <span class="account-id">{{ account.account_id }}</span>
              <span class="status-chip danger">logout</span>
            </div>
            <div class="account-meta">{{ account.platform || '-' }} · {{ account.group_name || '未分组' }}</div>
            <div class="account-meta">登出时间：{{ formatDateTime(account.logout_at) }}</div>
            <div v-if="account.logout_reason" class="account-reason">{{ account.logout_reason }}</div>
          </button>
        </div>

        <div v-else class="empty-sidebar">
          <div class="empty-title">当前没有登出账号</div>
          <div class="empty-text">你仍然可以在顶部输入账号 ID，查看某个账号过去的登录状态历史。</div>
        </div>
      </aside>

      <section class="detail-panel">
        <div class="detail-head">
          <div>
            <div class="panel-title">账号详情</div>
            <div v-if="selectedAccountId" class="detail-title-line">
              <span class="detail-account">{{ selectedAccountId }}</span>
              <span class="status-chip" :class="statusTone(snapshot?.status)">
                {{ snapshot?.status || (selectedSource === 'manual' ? '手动查看' : '未选择账号') }}
              </span>
            </div>
            <div v-else class="panel-caption">从左侧选择登出账号，或手动输入账号 ID 查看历史。</div>
          </div>
          <div class="detail-actions">
            <button
              class="recovery-btn"
              :disabled="!selectedAccountId || resolvedPlatform !== 'tiktok' || recoveryLoading"
              @click="triggerRecovery"
            >
              {{ recoveryLoading ? '记录中...' : '记录恢复请求' }}
            </button>
          </div>
        </div>

        <div v-if="selectedAccountId" class="snapshot-grid">
          <div class="snapshot-card">
            <span class="snapshot-label">平台</span>
            <span class="snapshot-value">{{ resolvedPlatform || '-' }}</span>
          </div>
          <div class="snapshot-card">
            <span class="snapshot-label">分组</span>
            <span class="snapshot-value">{{ resolvedGroupName || '-' }}</span>
          </div>
          <div class="snapshot-card">
            <span class="snapshot-label">当前状态</span>
            <span class="snapshot-value">{{ snapshot?.status || '暂无快照' }}</span>
          </div>
        </div>

        <div v-if="selectedAccountId" class="status-board">
          <div class="status-card">
            <div class="status-card-title">状态快照</div>
            <div v-if="snapshot" class="status-lines">
              <div class="status-line">
                <span>登出时间</span>
                <strong>{{ formatDateTime(snapshot.logout_at) }}</strong>
              </div>
              <div class="status-line">
                <span>登录时间</span>
                <strong>{{ formatDateTime(snapshot.login_at) }}</strong>
              </div>
              <div class="status-line">
                <span>登出原因</span>
                <strong>{{ snapshot.logout_reason || '-' }}</strong>
              </div>
              <div class="status-line">
                <span>查看来源</span>
                <strong>{{ selectedSource === 'manual' ? '手动查询' : '登出列表' }}</strong>
              </div>
            </div>
            <div v-else class="status-empty">
              当前没有这条账号的状态快照，右侧时间线仍可展示已记录的历史事件。
            </div>
          </div>

          <div class="status-card emphasis">
            <div class="status-card-title">恢复动作说明</div>
            <div class="status-lines">
              <div class="status-line">
                <span>按钮语义</span>
                <strong>仅记录手动恢复请求事件</strong>
              </div>
              <div class="status-line">
                <span>自动行为</span>
                <strong>最近事件为 logout → login 时，下一轮调度自动恢复全量</strong>
              </div>
              <div class="status-line">
                <span>当前限制</span>
                <strong>{{ resolvedPlatform === 'tiktok' ? '支持当前账号记录恢复请求' : '仅 TikTok 支持手动记录' }}</strong>
              </div>
            </div>
          </div>
        </div>

        <div class="timeline-panel">
          <div class="timeline-head">
            <div class="panel-title">历史事件时间线</div>
            <div class="panel-caption">按时间倒序展示登出、登录恢复与恢复全量执行过程。</div>
          </div>

          <div v-if="loadingDetail" class="timeline-empty">正在加载账号事件...</div>

          <div v-else-if="events.length" class="timeline-list">
            <article v-for="event in events" :key="event.id" class="timeline-item">
              <div class="timeline-marker" :class="eventTone(event.event_type)"></div>
              <div class="timeline-content">
                <div class="timeline-top">
                  <div class="timeline-title-wrap">
                    <span class="timeline-title">{{ eventLabel(event.event_type) }}</span>
                    <span class="status-chip ghost">{{ event.platform || '-' }}</span>
                  </div>
                  <time class="timeline-time">{{ formatDateTime(event.event_time) }}</time>
                </div>
                <div class="timeline-meta">
                  分组：{{ event.group_name || '-' }}
                  <span v-if="event.batch_id"> · 批次：{{ event.batch_id }}</span>
                </div>
                <div v-if="event.detail && Object.keys(event.detail).length" class="timeline-detail">
                  <span
                    v-for="(value, key) in event.detail"
                    :key="`${event.id}-${key}`"
                    class="detail-chip"
                  >
                    {{ key }}: {{ formatDetailValue(value) }}
                  </span>
                </div>
              </div>
            </article>
          </div>

          <div v-else class="timeline-empty">
            当前账号还没有历史事件记录。
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fetchAccountLoginEvents,
  fetchAccountLoginStatus,
  fetchLogoutAccounts,
  triggerAccountRecovery,
} from '../api'

const loadingList = ref(false)
const loadingDetail = ref(false)
const recoveryLoading = ref(false)

const platformFilter = ref('')
const searchAccountId = ref('')
const logoutAccounts = ref([])
const selectedAccountId = ref('')
const selectedSource = ref('list')
const snapshot = ref(null)
const events = ref([])

onMounted(async () => {
  await loadLogoutAccounts()
})

const currentAccount = computed(() =>
  logoutAccounts.value.find((account) => account.account_id === selectedAccountId.value) || null
)

const resolvedPlatform = computed(() =>
  snapshot.value?.platform || currentAccount.value?.platform || events.value[0]?.platform || ''
)

const resolvedGroupName = computed(() =>
  snapshot.value?.group_name || currentAccount.value?.group_name || events.value[0]?.group_name || ''
)

const tiktokLogoutCount = computed(() =>
  logoutAccounts.value.filter((account) => account.platform === 'tiktok').length
)

const shopeeLogoutCount = computed(() =>
  logoutAccounts.value.filter((account) => account.platform === 'shopee').length
)

async function loadLogoutAccounts() {
  loadingList.value = true
  try {
    const response = await fetchLogoutAccounts(platformFilter.value || undefined)
    logoutAccounts.value = response.data.accounts || []

    if (!selectedAccountId.value && logoutAccounts.value.length) {
      await loadAccountDetails(logoutAccounts.value[0].account_id, 'list')
      return
    }

    if (
      selectedSource.value === 'list' &&
      selectedAccountId.value &&
      !logoutAccounts.value.some((account) => account.account_id === selectedAccountId.value)
    ) {
      if (logoutAccounts.value.length) {
        await loadAccountDetails(logoutAccounts.value[0].account_id, 'list')
      }
    }
  } catch (error) {
    ElMessage.error('加载登出账号列表失败')
  } finally {
    loadingList.value = false
  }
}

async function loadAccountDetails(accountId, source = 'list') {
  if (!accountId) {
    return
  }

  loadingDetail.value = true
  selectedAccountId.value = accountId
  selectedSource.value = source
  snapshot.value = null
  events.value = []

  const [statusResult, eventsResult] = await Promise.allSettled([
    fetchAccountLoginStatus(accountId),
    fetchAccountLoginEvents(accountId),
  ])

  if (statusResult.status === 'fulfilled') {
    snapshot.value = statusResult.value.data
  } else if (statusResult.reason?.response?.status !== 404) {
    ElMessage.error('加载账号状态快照失败')
  }

  if (eventsResult.status === 'fulfilled') {
    events.value = eventsResult.value.data.events || []
  } else {
    ElMessage.error('加载账号历史事件失败')
  }

  loadingDetail.value = false
}

async function selectAccount(accountId, source = 'list') {
  await loadAccountDetails(accountId, source)
}

async function searchAccount() {
  if (!searchAccountId.value) {
    ElMessage.warning('请输入账号 ID')
    return
  }
  await loadAccountDetails(searchAccountId.value, 'manual')
}

async function refreshCurrentView() {
  await loadLogoutAccounts()
  if (selectedAccountId.value) {
    await loadAccountDetails(selectedAccountId.value, selectedSource.value)
  }
}

async function triggerRecovery() {
  if (!selectedAccountId.value) {
    ElMessage.warning('请先选择账号')
    return
  }
  if (resolvedPlatform.value !== 'tiktok') {
    ElMessage.warning('当前仅支持 TikTok 账号手动标记下轮全量恢复')
    return
  }

  recoveryLoading.value = true
  try {
    const response = await triggerAccountRecovery(selectedAccountId.value, {
      platform: resolvedPlatform.value,
      group_name: resolvedGroupName.value || '',
    })
    ElMessage.success(response.data.message || '已记录手动恢复请求事件')
    await loadLogoutAccounts()
    await loadAccountDetails(selectedAccountId.value, selectedSource.value)
  } catch (error) {
    const detail = error.response?.data?.detail || error.message || '未知错误'
    ElMessage.error(`标记失败: ${detail}`)
  } finally {
    recoveryLoading.value = false
  }
}

function formatDateTime(value) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatDetailValue(value) {
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false'
  }
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  return String(value)
}

function eventLabel(eventType) {
  const labelMap = {
    logout: '检测到登出',
    login: '检测到当前为登录态',
    logout_detected: '检测到登出',
    login_restored: '检测到当前为登录态',
    full_recovery_marked: '已记录手动恢复请求',
    full_recovery_started: '调度开始恢复全量',
    full_recovery_succeeded: '恢复全量成功',
    full_recovery_failed: '恢复全量失败',
  }
  return labelMap[eventType] || eventType
}

function eventTone(eventType) {
  const toneMap = {
    logout: 'danger',
    login: 'success',
    logout_detected: 'danger',
    login_restored: 'success',
    full_recovery_marked: 'warning',
    full_recovery_started: 'info',
    full_recovery_succeeded: 'success',
    full_recovery_failed: 'danger',
  }
  return toneMap[eventType] || 'neutral'
}

function statusTone(status) {
  if (status === 'logout') {
    return 'danger'
  }
  if (status === 'online') {
    return 'success'
  }
  return 'ghost'
}
</script>

<style scoped>
.login-monitor {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.5px;
  color: var(--text-primary);
}

.page-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 760px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.search-bar {
  display: flex;
  align-items: center;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.search-input {
  width: 240px;
  padding: 10px 12px;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  font-family: var(--font-mono);
}

.search-btn,
.refresh-btn,
.recovery-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-secondary);
  padding: 10px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}

.search-btn {
  border: none;
  border-left: 1px solid var(--border-color);
  border-radius: 0;
  height: 100%;
}

.refresh-btn:hover,
.search-btn:hover,
.recovery-btn:hover {
  color: var(--text-primary);
  border-color: var(--text-secondary);
}

.refresh-btn:disabled,
.recovery-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.recovery-btn {
  background: linear-gradient(135deg, rgba(83, 155, 245, 0.12), rgba(163, 113, 247, 0.08));
  border-color: rgba(83, 155, 245, 0.35);
  color: var(--accent-blue);
  min-width: 158px;
}

.monitor-grid {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.sidebar-panel,
.detail-panel {
  background: linear-gradient(180deg, rgba(22, 27, 34, 0.96), rgba(13, 17, 23, 0.96));
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 18px;
  box-shadow: 0 18px 50px rgba(1, 4, 9, 0.22);
}

.panel-head,
.detail-head,
.timeline-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--text-primary);
}

.panel-caption {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.platform-select {
  width: 120px;
}

:deep(.platform-select .el-input__wrapper) {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  box-shadow: none !important;
}

.stats-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 18px 0;
}

.stats-card,
.snapshot-card,
.status-card {
  background: rgba(33, 38, 45, 0.82);
  border: 1px solid rgba(48, 54, 61, 0.8);
  border-radius: var(--radius-md);
}

.stats-card {
  padding: 14px 12px;
}

.stats-value {
  display: block;
  font-family: var(--font-mono);
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.stats-value.danger {
  color: #ff7b72;
}

.stats-label {
  display: block;
  margin-top: 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-muted);
}

.account-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 720px;
  overflow: auto;
}

.account-item {
  text-align: left;
  width: 100%;
  padding: 14px;
  background: rgba(22, 27, 34, 0.72);
  border: 1px solid rgba(48, 54, 61, 0.8);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.account-item:hover,
.account-item.active {
  transform: translateY(-1px);
  border-color: rgba(248, 81, 73, 0.55);
  background: rgba(33, 38, 45, 0.92);
}

.account-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.account-id,
.detail-account {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.account-meta,
.account-reason {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.account-reason {
  color: #ffa657;
}

.empty-sidebar,
.timeline-empty {
  margin-top: 16px;
  padding: 18px;
  border: 1px dashed rgba(48, 54, 61, 0.85);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 13px;
}

.empty-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.empty-text {
  margin-top: 6px;
  line-height: 1.6;
}

.detail-title-line {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
}

.detail-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.snapshot-card {
  padding: 16px;
}

.snapshot-label {
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-muted);
}

.snapshot-value {
  display: block;
  margin-top: 10px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.status-board {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.status-card {
  padding: 16px;
}

.status-card.emphasis {
  background: linear-gradient(145deg, rgba(33, 38, 45, 0.96), rgba(33, 38, 45, 0.78));
}

.status-card-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.status-lines {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 14px;
}

.status-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.status-line strong {
  color: var(--text-primary);
  text-align: right;
}

.status-empty {
  margin-top: 14px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.timeline-panel {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--border-color);
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 18px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 14px;
}

.timeline-marker {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  margin-top: 5px;
  box-shadow: 0 0 0 6px rgba(255, 255, 255, 0.02);
}

.timeline-marker.success {
  background: var(--accent-green);
}

.timeline-marker.warning {
  background: #d29922;
}

.timeline-marker.info {
  background: var(--accent-blue);
}

.timeline-marker.danger {
  background: #ff7b72;
}

.timeline-marker.neutral {
  background: var(--text-muted);
}

.timeline-content {
  background: rgba(22, 27, 34, 0.68);
  border: 1px solid rgba(48, 54, 61, 0.8);
  border-radius: var(--radius-md);
  padding: 14px;
}

.timeline-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.timeline-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.timeline-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.timeline-time,
.timeline-meta {
  font-size: 12px;
  color: var(--text-muted);
}

.timeline-meta {
  margin-top: 8px;
}

.timeline-detail {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.detail-chip,
.status-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.4px;
}

.detail-chip {
  background: rgba(33, 38, 45, 0.95);
  border: 1px solid rgba(48, 54, 61, 0.9);
  color: var(--text-secondary);
}

.status-chip.success {
  background: rgba(63, 185, 80, 0.14);
  border: 1px solid rgba(63, 185, 80, 0.28);
  color: var(--accent-green);
}

.status-chip.danger {
  background: rgba(248, 81, 73, 0.14);
  border: 1px solid rgba(248, 81, 73, 0.26);
  color: #ff7b72;
}

.status-chip.ghost {
  background: rgba(110, 118, 129, 0.14);
  border: 1px solid rgba(110, 118, 129, 0.24);
  color: var(--text-secondary);
}

@media (max-width: 1180px) {
  .monitor-grid {
    grid-template-columns: 1fr;
  }

  .snapshot-grid,
  .status-board {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .search-input {
    width: 180px;
  }

  .snapshot-grid,
  .status-board {
    grid-template-columns: 1fr;
  }

  .timeline-top,
  .status-line,
  .panel-head,
  .detail-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
