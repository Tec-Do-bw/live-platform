import { createRouter, createWebHistory } from 'vue-router'
import AccountOverview from '../views/AccountOverview.vue'
import AccountDetail from '../views/AccountDetail.vue'
import BatchHistory from '../views/BatchHistory.vue'
import LogoutAccounts from '../views/LogoutAccounts.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: AccountOverview },
    { path: '/account/:accountId', component: AccountDetail, props: true },
    { path: '/batches', component: BatchHistory },
    { path: '/logout-accounts', component: LogoutAccounts },
  ]
})
