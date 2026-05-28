# Phase 4B: 删除 SQLite / 补采系统 / 监控前端

> 关联: [architecture-simplification.md](./2026-05-06-architecture-simplification.md) Phase 4
> 前置: [Phase 4A 日报 Agent](./2026-05-28-phase4a-daily-report-agent.md) 必须验收稳定运行 1-2 周
> 优先级: P3
> 工期: 3-4 天
> 状态: 已完成(2026-05-28)

---

## 背景

Phase 4A 上线后,采集报告完全由日志驱动,SQLite 不再必要。本 phase 移除以下三块过时基础设施:

1. **live-crawler SQLite 存储**: `monitor/db.py` 及关联 23+ 模块
2. **补采系统**: `monitor/recrawl/` 整个目录 + 旧 `live-monitor/ReCrawl/`
3. **监控前端**: `live-monitor/static/` 8 个 HTML 页面

执行前必须确认 Phase 4A 已稳定运行,否则会失去采集监控能力。

---

## 删除清单

### A. live-crawler SQLite 存储

| 路径 | 说明 |
|---|---|
| `services/live-crawler/monitor/db.py` | SQLite schema 初始化 |
| `services/live-crawler/monitor/data/` | monitor.db 所在目录(运行时数据) |

### B. live-crawler 补采系统

| 路径 | 说明 |
|---|---|
| `services/live-crawler/monitor/recrawl/__init__.py` | 入口 `auto_detect_and_recrawl()` |
| `services/live-crawler/monitor/recrawl/gap_detector.py` | 缺口检测 |
| `services/live-crawler/monitor/recrawl/recovery_detector.py` | 登出恢复检测 |
| `services/live-crawler/monitor/recrawl/executor.py` | 补采任务执行(18KB) |
| `services/live-crawler/monitor/recrawl/models.py` | recrawl_tasks 表 CRUD |
| `services/live-crawler/monitor/recrawl/proxy.py` | 代理选择 |
| `services/live-crawler/monitor/api/recrawl_routes.py` | FastAPI 补采路由 |

### C. live-crawler 监控周边(评估完成)

| 路径 | 决定 | 原因 |
|---|---|---|
| `services/live-crawler/monitor/server.py` | **保留最小 Cookie API** | 前端与监控 API 下线；`/api/cookies/{account_id}` 仍是 adspower-server → live-crawler Cookie 写入通道 |
| `services/live-crawler/monitor/tracker.py` | **删除 CollectionMonitor 类**，`extract_target_date` 迁移到 `utils/` | 主流程已不调用 CollectionMonitor；`extract_target_date` 仍被 `crawlers/browser/tiktok.py:277` 引用 |
| `services/live-crawler/monitor/api/batches.py` | **删除** | 纯监控面板 API，前端下线后无消费方 |
| `services/live-crawler/monitor/api/accounts.py` | **删除** | 同上 |
| `services/live-crawler/monitor/api/registry_routes.py` | **删除** | 同上 |
| `services/live-crawler/monitor/api/overview.py` | **删除** | 同上 |
| `services/live-crawler/monitor/api/login_status_routes.py` | **删除** | 前端下线后无消费方；LoginStatusManager 内部逻辑保留 |
| `services/live-crawler/monitor/api/cookie_routes.py` | **保留，不动** | 是 adspower-server → live-crawler 的 Cookie 写入通道（`PUT /api/cookies/{account_id}`），Lazada 生产链路依赖 |
| `services/live-crawler/services/cookie_manager.py` | **保留，不动** | Lazada HTTP 采集器 10+ 处引用，是 Lazada cookies 唯一来源；等 TikTok HTTP 重构完成后随 `account_credentials` 表统一迁移（见 `2026-05-28-tiktok-http-refactor.md` §15） |

### D. live-monitor 监控前端

| 路径 | 说明 |
|---|---|
| `services/live-monitor/static/` | 8 个 HTML 页面(login/offlineTask/configGenerator 等) |

### E. live-monitor 旧补采

| 路径 | 说明 |
|---|---|
| `services/live-monitor/ReCrawl/re_crawl_1.py` | 旧 MySQL 补采脚本 |
| `services/live-monitor/start_scheduler.py` 中的补采调度 | 移除 01:00 cron 调用 |

### F. 文档与规则

| 路径 | 处理 |
|---|---|
| `.claude/rules/http-recrawl-spec.md` | 若存在则删除 |
| `docs/archive/2026-03-14-auto-recrawl*.md` | 已在 archive,保留作历史参考 |

---

## 执行步骤

### 1. 前置检查

- [ ] 确认 Phase 4A 已上线 ≥ 7 天且无故障
- [ ] 备份 `services/live-crawler/monitor/data/monitor.db`(若存在)到团队共享目录
- [ ] 通知团队当天采集监控将切换,前端页面将下线
- [ ] 创建分支 `refactor/phase4b-remove-sqlite`

### 2. 删除 live-crawler 补采系统

- [ ] `git rm -r services/live-crawler/monitor/recrawl/`
- [ ] `git rm services/live-crawler/monitor/api/recrawl_routes.py`
- [ ] 修改 `services/live-crawler/main.py`:移除 `auto_detect_and_recrawl()` 调用与 import
- [ ] 修改 `services/live-crawler/monitor/server.py`:移除 recrawl 路由注册(暂时保留 server.py)
- [ ] 全局搜索 `from .recrawl` / `from monitor.recrawl` / `recrawl_tasks` 残留引用,逐一清理
- [ ] 跑 `pytest services/live-crawler/tests/`,删除/修复涉及补采的测试
- [ ] 提交: `git commit -m "refactor(live-crawler): 删除补采系统"`

### 3. 删除 live-crawler SQLite 存储与监控 API

- [ ] 将 `extract_target_date` 从 `monitor/tracker.py` 迁移到 `utils/time_utils.py`（或同类 utils 文件）
- [ ] 更新 `crawlers/browser/tiktok.py:277` 的 import 路径
- [ ] `git rm services/live-crawler/monitor/tracker.py`（CollectionMonitor 类整体删除）
- [ ] `git rm services/live-crawler/monitor/api/batches.py`
- [ ] `git rm services/live-crawler/monitor/api/accounts.py`
- [ ] `git rm services/live-crawler/monitor/api/registry_routes.py`
- [ ] `git rm services/live-crawler/monitor/api/overview.py`
- [ ] `git rm services/live-crawler/monitor/api/login_status_routes.py`
- [ ] `git rm services/live-crawler/monitor/server.py`（已无路由可挂，整体删除）
- [ ] `git rm services/live-crawler/monitor/db.py`
- [ ] `git rm -r services/live-crawler/monitor/data/`（若已入 git；否则确认 .gitignore 已排除）
- [ ] 全局搜索 `import sqlite3` / `monitor.db` 残留引用
- [ ] 跑 `pytest services/live-crawler/`,确保无回归
- [ ] 提交: `git commit -m "refactor(live-crawler): 删除 SQLite 存储与监控 API"`

### 4. 删除 live-monitor 监控前端

- [ ] `git rm -r services/live-monitor/static/`
- [ ] 修改 `services/live-monitor/app.py`:移除 `app.mount("/static", ...)` 与相关路由
- [ ] 移除 `app.py` 中所有渲染 HTML 页面的 endpoint(如 `/login`、`/doc` 等)
- [ ] 验证 `app.py` 启动正常,核心 API(`/get_roominfo`、`/api/cookies/*`)无回归
- [ ] 提交: `git commit -m "refactor(live-monitor): 删除监控前端 HTML 页面"`

### 5. 删除 live-monitor 旧补采

- [ ] `git rm -r services/live-monitor/ReCrawl/`
- [ ] 修改 `services/live-monitor/start_scheduler.py`:移除 01:00 补采调度
- [ ] 全局搜索 `re_crawl_1` 引用清理
- [ ] 提交: `git commit -m "refactor(live-monitor): 删除旧补采脚本"`

### 6. 清理文档与规则

- [ ] 检查 `.claude/rules/http-recrawl-spec.md` 是否存在,存在则删除
- [ ] 修改 `services/live-crawler/CLAUDE.md`:移除补采/SQLite 相关约束章节
- [ ] 修改 `services/live-monitor/CLAUDE.md`:移除前端/旧补采相关章节
- [ ] 修改 `services/live-crawler/README.md`:更新「项目结构」目录树
- [ ] 修改 `services/live-monitor/README.md`:更新「项目结构」目录树
- [ ] 提交: `git commit -m "docs: 同步删除 SQLite/补采/前端后的文档"`

### 7. 验收

- [ ] live-crawler 启动正常,采集任务跑通(增量 + 全量各一次)
- [ ] live-monitor 启动正常,核心 API 响应正常
- [ ] Phase 4A 日报 Agent 仍正常运行,飞书收到当天报告
- [ ] 全仓 `grep -r "sqlite\|recrawl\|monitor\.db"` 无残留
- [ ] 跑全量测试 `pytest`,通过率不低于改动前
- [ ] 勾选 [`docs/ROADMAP.md`](../ROADMAP.md) 对应条目
- [ ] PR 标题: `refactor: 删除 SQLite 存储、补采系统、监控前端`

---

## 验收清单

- [ ] `services/live-crawler/monitor/recrawl/` 目录不存在
- [ ] `services/live-crawler/monitor/db.py` 不存在
- [ ] `services/live-monitor/static/` 目录不存在
- [ ] `services/live-monitor/ReCrawl/` 目录不存在
- [ ] live-crawler、live-monitor 双服务启动正常
- [ ] 采集任务无回归(增量 + 全量验收)
- [ ] Phase 4A 日报正常输出

---

## 风险与回滚

| 风险 | 缓解 | 回滚 |
|---|---|---|
| 删除 SQLite 后 cookie_manager 数据丢失 | 改造前导出 cookies 到文件,改造后从文件导入 | git revert + 恢复 monitor.db 备份 |
| 23+ 模块改动引入采集回归 | 分批改、每步跑 pytest、灰度部署 | 按 commit 粒度 git revert |
| `monitor/server.py` 删除后某监控脚本失效 | 删除前全仓 grep 引用 | 暂缓删除,改为返回 410 Gone |
| 团队有人依赖 static/ 页面做日常运维 | 提前 1 周通知,统计实际使用 | git checkout 恢复目录 |
| Phase 4A 日报突然失效又恰逢删除窗口 | 严格执行前置检查(4A 稳定 ≥ 7 天) | 暂停本 phase,先修 4A |

---

## 完成后

- [ ] 本 plan 移到 `docs/archive/2026-05-28-phase4b-remove-sqlite-recrawl-frontend.md`
- [ ] 更新 [`docs/plans/2026-05-06-architecture-simplification.md`](./2026-05-06-architecture-simplification.md) Phase 4 章节标记完成
- [ ] 代码量统计:对比改动前后行数,记入 ROADMAP「最近完成」
