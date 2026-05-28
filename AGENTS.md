# Codex Instructions

本项目的长期规则以 `CLAUDE.md` 为单一权威源。

开始任何非琐碎任务前，先阅读根目录 `CLAUDE.md`。
编辑 `services/*` 下文件时，先阅读对应子项目的 `services/<name>/CLAUDE.md`。

遵循 `CLAUDE.md` 中的工作流、代码规范、文档维护规则与已知坑。


<claude-mem-context>
# Memory Context

# [live-platform] recent context, 2026-05-28 11:51pm GMT+8

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (17,785t read) | 3,516,329t work | 99% savings

### May 28, 2026
S272 Generate TikTok collection flow diagrams and refactored design document; compare current vs. refactored architecture based on real API inspection (May 28 at 5:21 PM)
S273 Design and document Phase 4 monitoring simplification with two-stage rollout approach: Phase 4A adds daily report Agent without breaking existing systems; Phase 4B removes SQLite, recrawl subsystem, and frontend after validation (May 28 at 5:21 PM)
S274 Refactor TikTok collection architecture: simplify from multi-file async design to single-file synchronous collector.py with unified account_credentials table, eliminating signature layer complexity (May 28 at 5:29 PM)
S275 更新 TikTok HTTP 化重构计划文档，基于真实 CURL 验证简化架构设计，并清理临时对比文档 (May 28 at 5:31 PM)
S276 Implement Phase 4A: daily report system for live crawler with log parsing, account state tracking, OpenAI integration, and Feishu notifications (May 28 at 5:42 PM)
S277 smart-commit: Submit Phase 4A daily reporting infrastructure to feature branch (May 28 at 5:47 PM)
S278 Implement Phase 4B plan: Remove SQLite and recrawl frontend - specifically removing monitor.record() instrumentation hooks from Shopee crawler (May 28 at 6:20 PM)
1116 6:45p 🔵 SQLite dependency mapping across live-crawler codebase
1117 " 🔵 Entry points and data flow for SQLite removal refactoring
1118 6:46p ⚖️ Task created: Decouple login callbacks and proxy tools from monitor subtree
1119 " 🔵 Tracker and monitor calls distributed across runtime paths
1120 " 🔵 Browser crawler monitor integration pattern
1121 6:47p 🔵 Monitor module serves dual purpose: collection tracking and real-time monitoring dashboard
1122 " ✅ Task 8 marked in_progress: Decouple login callbacks and proxy tools from monitor subtree
1123 " 🔵 Scripts directory also uses LoginStatusManager and monitor.conn
1124 6:48p 🔵 Login callback abstraction layer and cookie API endpoint identified
1125 " 🔵 Utils directory structure and adspower_client module location
1126 " ✅ Created utils/adspower_proxy.py - migrated from monitor/recrawl/proxy.py
1127 " 🔵 Lazada crawler imports proxy from monitor.recrawl.proxy - needs update
1128 " ✅ Updated crawlers/http/lazada.py import path from monitor.recrawl.proxy to utils.adspower_proxy
1129 6:49p ✅ Refactored monitor/__init__.py - removed CollectionMonitor, added get_db_connection()
1130 " ✅ Updated main.py import from get_monitor to get_db_connection
1131 " ✅ Removed monitor.start_batch() call from main.py _run_once_impl()
1132 " ✅ Updated main.py to pass get_db_connection() to LoginStatusManager instead of monitor.conn
1133 6:50p ✅ Removed monitor.finish_batch() and auto_detect_and_recrawl() calls from main.py
1134 " ✅ Updated scheduler/task_scheduler.py import from get_monitor to get_db_connection
1135 7:06p ✅ Removed monitoring hook from session_detail collection in Shopee crawler
1136 " ✅ Removed monitoring hook from replay_detail collection in Shopee crawler
S279 Update Phase 4B refactoring plan with concrete execution steps for removing live-crawler monitoring subsystem, based on completed assessment of production dependencies. (May 28 at 7:07 PM)
1137 7:08p 🔵 Phase 4B task list structure and current progress state
1138 7:09p 🔵 Monitor API usage in Lazada HTTP crawler for partial status reporting
1139 " 🔵 Monitor API usage in HTTP base crawler and browser API for request context persistence
1140 " ✅ Removed unused monitor import from HTTP base crawler _process_results method
1141 " 🔵 Monitor API usage in Lazada HTTP crawler for partial status reporting
1142 " ✅ Removed monitor.finish_account() call from Lazada HTTP crawler partial status reporting
1143 7:10p 🔵 Monitor API usage in browser API for request context persistence in supplementary collection
1144 7:12p 🔵 Account login events table schema and usage across monitor module
1145 " 🔵 Monitor module database schema and live-monitor service structure
1146 " ⚖️ 采用 subagent-driven-development 并行子代理执行任务
1147 7:21p ✅ live-monitor 静态前端下线：删除 HTML 页面与相关路由
1148 " ✅ monitor/db.py Phase 4B 精简：仅保留 3 张业务表
1149 " ✅ Phase C 收尾：全仓 get_monitor 引用清零，切换至 get_db_connection
1150 9:52p 🔵 Phase 4B Refactoring Plan: Remove SQLite & Recrawl System
1151 " ⚖️ Phase 4B Monitoring Assessment Complete: Selective Deletion Strategy
1152 9:53p ✅ Phase 4B Execution Plan Refined: Concrete Deletion Steps
S280 Finalize Phase 4B monitoring assessment plan and commit coordinated refactoring strategy with TikTok HTTP refactor plan. (May 28 at 9:53 PM)
1153 9:55p ✅ Phase 4B Plan Document Modified and Staged for Commit
1154 " ✅ Phase 4B and TikTok HTTP Refactor Plans Committed
S281 Claude-Mem observer initialized to track a primary session executing a refactoring plan to remove SQLite and recrawl functionality from a live platform project (May 28 at 10:23 PM)
1174 10:34p 🔵 Phase 4B Step 2 Scope: live-crawler Recrawl System Removal
1175 10:37p 🔵 Recrawl System Removal: Complete Dependency Map and Test Inventory
1177 10:38p ✅ Phase 4B Step 2: Recrawl System Deletion and Proxy Migration Completed
1178 " ✅ Phase 4B Step 2 Complete: All Recrawl System Deletions Applied Successfully
1179 10:39p 🔵 Remaining Recrawl References After Step 2 Deletion
1180 " 🔵 Git Status Confirms Phase 4B Step 2 Patch Application
1181 10:40p 🔵 Recrawl Directory Cleanup Status: __pycache__ Remains After Deletion
1183 " ✅ Test Cleanup and Migration: Recrawl Mock Removal and Proxy Test Relocation
1184 " ✅ Phase 4B Step 2 Final Cleanup: Test Migration and Directory Removal Complete
1186 10:41p 🔵 Phase 4B Step 2 Completion Status: Recrawl Directory Fully Deleted, All Changes Staged
1187 " 🔵 test_login_status_api.py: 5 Test Cases Reference Deleted recrawl_tasks Table

Access 3516k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>