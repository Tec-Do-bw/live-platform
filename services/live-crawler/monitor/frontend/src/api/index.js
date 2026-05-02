import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const fetchBatches = (limit = 20) => api.get('/batches', { params: { limit } })
export const fetchAccounts = (batchId, platform) => api.get(`/batches/${batchId}/accounts`, { params: { platform } })
export const fetchRooms = (accountId, batchId) => api.get(`/accounts/${accountId}/rooms`, { params: { batch_id: batchId } })
export const fetchRegistry = () => api.get('/registry')
export const fetchAccountDetail = (batchId, accountId) => api.get(`/batches/${batchId}/accounts/${accountId}`)

// 账号总览
export const fetchOverview = (days = 3, platform) => api.get('/overview', { params: { days, platform } })
export const fetchAccountOverview = (accountId, days = 3) => api.get(`/overview/${accountId}`, { params: { days } })

// 补采
export const triggerRecrawl = (data) => api.post('/recrawl/trigger', data)
export const fetchRecrawlTasks = (params) => api.get('/recrawl/tasks', { params })

// 登录状态监控
export const fetchLogoutAccounts = (platform) => api.get('/accounts/logout-list', { params: { platform } })
export const fetchAccountLoginStatus = (accountId) => api.get(`/accounts/${accountId}/login-status`)
export const fetchAccountLoginEvents = (accountId, limit = 100) =>
  api.get(`/accounts/${accountId}/login-events`, { params: { limit } })
export const triggerAccountRecovery = (accountId, data) =>
  api.post(`/accounts/${accountId}/trigger-recovery`, data)
