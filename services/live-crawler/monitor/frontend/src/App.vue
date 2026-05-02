<template>
  <div class="app-shell dark">
    <!-- 顶部导航 -->
    <header class="nav-bar">
      <div class="nav-left">
        <div class="nav-brand" @click="$router.push('/')">
          <div class="brand-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
            </svg>
          </div>
          <span class="brand-text">LiveLab</span>
          <span class="brand-tag">MONITOR</span>
        </div>
        <nav class="nav-links" aria-label="主导航">
          <router-link to="/" class="nav-link-item" exact-active-class="active">采集总览</router-link>
          <router-link to="/batches" class="nav-link-item" active-class="active">批次历史</router-link>
          <router-link to="/logout-accounts" class="nav-link-item" active-class="active">登录状态</router-link>
        </nav>
      </div>
      <div class="nav-status" role="status" aria-label="系统状态">
        <span class="status-dot" aria-hidden="true"></span>
        <span class="status-text">SYSTEM ONLINE</span>
      </div>
    </header>

    <!-- 主内容 -->
    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style>
/* ====== CSS Variables — GitHub Dark / Console 风格 ====== */
:root {
  --bg-primary: #0d1117;
  --bg-secondary: #161b22;
  --bg-card: #161b22;
  --bg-card-hover: #1c2129;
  --bg-elevated: #21262d;
  --border-color: #30363d;
  --border-subtle: #21262d;

  --text-primary: #e6edf3;
  --text-secondary: #8b949e;
  --text-muted: #484f58;

  --accent-blue: #539bf5;
  --accent-green: #3fb950;
  --accent-amber: #d29922;
  --accent-red: #f85149;
  --accent-purple: #a371f7;

  --font-display: 'Outfit', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Cascadia Code', monospace;

  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
}

/* ====== Reset & Base ====== */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-display);
  -webkit-font-smoothing: antialiased;
}

/* Element Plus 暗色覆盖 */
.dark {
  --el-bg-color: var(--bg-card);
  --el-bg-color-overlay: var(--bg-elevated);
  --el-text-color-primary: var(--text-primary);
  --el-text-color-regular: var(--text-secondary);
  --el-border-color: var(--border-color);
  --el-border-color-light: var(--border-color);
  --el-fill-color-blank: var(--bg-card);
  --el-color-primary: var(--accent-blue);
  --el-mask-color: rgba(1, 4, 9, 0.8);
}

/* el-dialog 覆盖 */
.dark .el-dialog {
  background: var(--bg-secondary) !important;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg) !important;
}
.dark .el-dialog__header {
  border-bottom: 1px solid var(--border-color);
  padding: 16px 20px;
}
.dark .el-dialog__title {
  color: var(--text-primary);
  font-family: var(--font-display);
  font-weight: 600;
}
.dark .el-dialog__body {
  padding: 16px 20px 20px;
}

/* el-table 覆盖 */
.dark .el-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: var(--bg-elevated);
  --el-table-row-hover-bg-color: rgba(177, 186, 196, 0.04);
  --el-table-border-color: var(--border-color);
  --el-table-text-color: var(--text-primary);
  --el-table-header-text-color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 13px;
}
.dark .el-table th.el-table__cell {
  font-weight: 600;
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.5px;
}
.dark .el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell {
  background: rgba(177, 186, 196, 0.02);
}
.dark .el-table--enable-row-hover .el-table__body tr:hover > td.el-table__cell {
  background: rgba(177, 186, 196, 0.04);
}

/* el-tag 覆盖 */
.dark .el-tag {
  border: none;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
}

/* el-page-header 覆盖 */
.dark .el-page-header {
  --el-page-header-padding: 0;
}
.dark .el-page-header__icon {
  color: var(--text-secondary);
}

/* 滚动条 */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* ====== App Shell ====== */
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

/* ====== Nav Bar ====== */
.nav-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 48px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.nav-brand:hover { opacity: 0.8; }

.brand-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-elevated);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-secondary);
}

.brand-text {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.3px;
  color: var(--text-primary);
}

.brand-tag {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 1px;
  color: var(--text-muted);
  background: var(--bg-elevated);
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid var(--border-color);
}

/* ====== 导航链接 ====== */
.nav-links {
  display: flex;
  align-items: center;
  gap: 2px;
}

.nav-link-item {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  transition: color 0.15s, background 0.15s;
}
.nav-link-item:hover {
  color: var(--text-primary);
  background: rgba(177, 186, 196, 0.06);
}
.nav-link-item.active {
  color: var(--text-primary);
  background: rgba(177, 186, 196, 0.08);
}

.nav-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-green);
  animation: pulse-dot 2s ease-in-out infinite;
}

.status-text {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ====== Main ====== */
.main-content {
  flex: 1;
  padding: 24px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}

/* ====== 全局 Focus 样式 ====== */
:focus-visible {
  outline: 2px solid var(--accent-blue);
  outline-offset: 2px;
}

.dark .el-button:focus-visible,
.dark .el-select:focus-visible,
.dark .el-radio-button__original-radio:focus-visible + .el-radio-button__inner {
  outline: 2px solid var(--accent-blue);
  outline-offset: 2px;
}

/* ====== 尊重 reduced-motion 偏好 ====== */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}

/* ====== 响应式：导航栏 ====== */
@media (max-width: 640px) {
  .nav-bar { padding: 0 12px; height: 44px; }
  .nav-left { gap: 12px; }
  .brand-tag { display: none; }
  .nav-link-item { font-size: 12px; padding: 4px 8px; }
  .main-content { padding: 16px 12px; }
}

/* ====== Page Transition ====== */
.page-fade-enter-active { transition: opacity 0.2s ease-out; }
.page-fade-leave-active { transition: opacity 0.12s ease-in; }
.page-fade-enter-from { opacity: 0; }
.page-fade-leave-to { opacity: 0; }
</style>
