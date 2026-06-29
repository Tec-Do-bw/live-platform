# Codex Instructions

本项目的长期规则以 `CLAUDE.md` 为单一权威源。

开始任何非琐碎任务前，先阅读根目录 `CLAUDE.md`。
编辑 `services/*` 下文件时，先阅读对应子项目的 `services/<name>/CLAUDE.md`。

遵循 `CLAUDE.md` 中的工作流、代码规范、文档维护规则与已知坑。

配置相关改动遵循 `.claude/rules/apollo-config.md`（Apollo 为唯一配置权威源,小写点分 key,引导参数走环境变量）。

仓库当前不再包含 `services/live-platform/`; 相关 Phase 1 / MediaMTX 资料仅作历史归档参考，不再当作现役子项目入口。

## Git 工作流与远程仓库策略

本项目的提交、发布、同步、PR 统一基于 `$git-workflow` skill，不直接把裸 `git commit` / `git push origin` 作为默认工作流。

### 远程仓库命名

- `origin`：GitHub，地址为 `https://github.com/Tec-Do-bw/live-platform.git`
- `gitlab`：公司 GitLab，地址为 `https://git.tec-do.com/live/live-platform`

`origin` 必须保持为 GitHub，因为 `$git-workflow publish` / `$git-workflow sync` / `$git-workflow pr` 默认围绕 `origin` 工作。

### 机器策略

- 家里 Mac：只配置并使用 `origin`，只推送 GitHub。
- 公司 Windows（LENOVO 21SJ / GZTD-03-00951）：同时维护 `origin` 与 `gitlab`，负责把 GitHub 上的提交同步到 GitLab。

### 日常操作

提交本地改动：

```bash
$git-workflow commit
```

发布当前分支到 GitHub：

```bash
$git-workflow publish
```

同步当前分支：

```bash
$git-workflow sync
```

创建 GitHub PR：

```bash
$git-workflow pr
```

公司 Windows 在 `$git-workflow publish` 成功后，如需同步 GitLab，再执行：

```bash
git push gitlab <current-branch>
```

首次同步当前分支到 GitLab 时使用：

```bash
git push -u gitlab <current-branch>
```

### 公司环境：同步 live-stream 到 live-spider

`services/live-stream/` 子目录额外有独立仓库 `https://git.tec-do.com/live/live-spider`，**只在公司 Windows 环境**执行同步（与 GitLab 同步策略一致）。

同步命令：

```bash
bash scripts/sync-live-spider.sh
```

也可以让 AI 代为执行（两种 CLI 均支持，底层都调上面这个脚本）：

- **Claude Code**：`/sync-live-spider`，或直接说「同步 live-spider」
- **Codex**：`/sync-live-spider`，或直接说「同步 live-spider」
- 命令定义：Claude Code 在 `.claude/commands/sync-live-spider.md`，Codex 在 `.codex/skills/sync-live-spider/SKILL.md`

- **推送语义**：覆盖式（force push）推送到 `live-spider` 的 `sync/live-platform` 分支，内容以 monorepo 为准
- **前置条件**：`services/live-stream/` 无未提交改动（脚本会自动检查）
- **执行时机**：通常在 `$git-workflow publish` 推送 GitHub 后、`git push gitlab` 推送 GitLab 后执行
- 脚本会自动补 remote（首次执行时）、抽取子目录历史、清理临时分支

详细用法与配置见脚本内注释（单一权威源）。

### 禁止事项

- 不要把 `origin` 改成 GitLab。
- 不要给 `origin` 配多个 push URL。
- 家里 Mac 不需要配置 `gitlab` remote，也不执行 `live-spider` 同步。
- 不要修改 `$git-workflow` 让它默认双推 GitHub + GitLab；GitLab 同步只在公司 Windows 单独执行。
- 不要把 `live-spider` remote 配成 push 通道混进 `$git-workflow` 默认流程；它只通过 `scripts/sync-live-spider.sh` 手动触发。


<claude-mem-context>
# Memory Context

# [live-platform] recent context, 2026-06-24 1:20pm GMT+8

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (16,163t read) | 348,033t work | 95% savings

### Jun 8, 2026
2197 11:17p ✅ Complete Shopee Login Documentation Deliverables — Account Matrix, Flow Diagrams, and Code Rules
2198 " 🔵 adspower-server Shopee API Service — Cross-Border/Domestic Shop Detection
2199 " 🔵 adspower-server login_monitor.py — Passive + Active Hybrid Implementation
2200 11:18p ✅ End-to-End Sequence Diagram — Shopee Login & Collection (Phases 1–5)
2201 " ✅ API Reference Stub + Flow Diagrams Section 4 — cb_option/Permission Decision Tables
2202 " ✅ Flow Diagrams Sections 4.3–4.5 — Domain Correction, Shop Switching, Callback Priority
2203 11:19p ✅ Shopee Login Refactor Documentation Suite — Complete Delivery
2204 " ✅ API Reference Complete — All 7 Shopee Endpoints Documented (Domestic & Cross-Border)
2205 " ✅ API Reference Complete with Appendices — Real-World Workflows & Code Index
2206 11:20p ✅ Shopee Login Refactor Documentation Suite — Complete Delivery (All 6 Specifications)
2210 11:22p ✅ account-type-matrix.md Created — 54-Scenario Enumeration + Boundary Issues
### Jun 15, 2026
2929 11:58p ✅ Git sync fetched feature/tiktok-crawler-refactor branch updates
2930 " ✅ Feature branch synced with 10 commits of architecture and service refactoring
### Jun 23, 2026
3245 12:39a ⚖️ Live-platform integration scope and data flow clarified
3246 12:42a ⚖️ Prepare Context.md for downstream AI handoff
### Jun 24, 2026
S426 初始化项目上下文并确认协作规则 (Jun 24 at 1:00 AM)
S427 Prepare to run a deep-research workflow after the user provides a research topic and constraints (Jun 24 at 2:00 AM)
S428 Explain TikTok live FLV URL validity, why an older FLV URL stopped working while a newer one works, and recommend an efficient recording strategy (Jun 24 at 2:04 AM)
S429 使用 workflow 审计 services/live-stream 与 services/live-monitor 在稳定拉流相关实现上的分歧和优化点 (Jun 24 at 2:08 AM)
S430 启动 workflow 审计 live-stream 与 live-monitor 稳定拉流差异 (Jun 24 at 2:12 AM)
S431 Initial readiness check after invoking the using-superpowers skill (Jun 24 at 2:14 AM)
S433 清理 live-platform 子项目与过时文档：先做只读盘点，再删除 services/live-platform/ 及相关主体文档，修正文档引用，并产出验证后的清理报告。 (Jun 24 at 2:18 AM)
3255 2:22a ⚖️ 项目清理提示词将先对齐方向再生成
3256 2:23a ⚖️ 项目清理方向聚焦 services/live-platform 与过期文档
S432 检查 live-platform 仓库当前工作树状态，并围绕 live-stream/live-monitor 稳定拉流、live-platform Redis/MediaMTX 集成与 Shopee 全量采集变更进行上下文勘察 (Jun 24 at 2:30 AM)
S434 Progress checkpoint for ongoing session (Jun 24 at 2:31 AM)
3260 2:40a ⚖️ Live-platform cleanup and wiki-first doc governance
S435 收口 live-platform 归档与过时引用清理检查 (Jun 24 at 3:02 AM)
3305 11:23a ✅ Live dashboard API spec and route migration scoped
3306 11:24a ⚖️ Planned spec and route work through brainstorming then writing-plans
3307 " ⚖️ Brainstorming workflow confirmed for spec and route migration
3308 " ⚖️ Writing-plans requirements confirmed for implementation handoff
3309 " 🔵 Repository governance and codegraph availability confirmed
3310 " 🔵 Prior live-platform cleanup and TikTok HTTP migration context found in memory
3311 11:25a 🔵 Repository governance now requires scoped reads and codegraph-first navigation
3312 " 🔵 Service boundaries and migration constraints were confirmed from subproject docs
3313 " 🔵 Prior live-platform workstreams already cover cleanup, sync, and TikTok HTTP refactor context
3314 " ✅ Working tree currently has one local modification
3315 " 🔵 live_status route blast radius and current ownership identified
3316 " 🔵 live-crawler already exposes a token-protected TikTok refresh API
3317 " 🔵 TikTok live dashboard research bundle now includes downstream API and raw request/response captures
3318 " 🔵 live-crawler service surface and test coverage map are now clear
3319 11:26a 🔵 live-status batch endpoint is a tiny FastAPI route backed by Redis repository
3320 " 🔵 live-crawler monitor server already aggregates API routers
3321 " 🔵 live-status batch route is tiny and isolated
3322 " 🔵 TikTok dashboard research bundle expanded to 6 raw API samples
3323 " ⚖️ live-crawler already has the right router aggregation pattern
3324 " 🔵 Repository governance and wiki precedents were confirmed
3325 " 🔵 Dashboard spec is stale against the latest research contract
3326 " 🔵 live-status batch route remains in live-monitor with a narrow Redis-backed contract
3327 " ⚖️ live-crawler already hosts the right operational API shape for migrated routes
3328 11:29a 🔵 Dashboard API spec is outdated relative to current research
3329 " 🔵 live-status batch endpoint remains a narrow Redis-backed contract in live-monitor
3330 " 🔵 live-crawler already has the right operational API host shape
3331 " ✅ Repo validation and roadmap context were clarified
3335 12:04p ⚖️ Live-dashboard API spec and route ownership were re-scoped
3336 12:23p ⚖️ Dashboard live-status batch auth and collector split
3337 12:39p ✅ Dashboard fetchers moved into TikTok real collector
3338 " ✅ TikTok dashboard fetchers moved to real_collector
3339 12:51p ⚖️ Spec approved, planning document generation started

Access 348k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
