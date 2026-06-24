# Codex Instructions

本项目的长期规则以 `CLAUDE.md` 为单一权威源。

开始任何非琐碎任务前，先阅读根目录 `CLAUDE.md`。
编辑 `services/*` 下文件时，先阅读对应子项目的 `services/<name>/CLAUDE.md`。

遵循 `CLAUDE.md` 中的工作流、代码规范、文档维护规则与已知坑。

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

### 禁止事项

- 不要把 `origin` 改成 GitLab。
- 不要给 `origin` 配多个 push URL。
- 家里 Mac 不需要配置 `gitlab` remote。
- 不要修改 `$git-workflow` 让它默认双推 GitHub + GitLab；GitLab 同步只在公司 Windows 单独执行。


<claude-mem-context>
# Memory Context

# [live-platform] recent context, 2026-06-24 9:46am GMT+8

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (23,303t read) | 634,831t work | 96% savings

### May 29, 2026
1314 10:29a 🟣 TikTok HTTP Collector Implementation with Credential Management
1315 " ✅ Phase 4A & 4B Completion: SQLite Removal and Daily Report Agent
1316 " 🔵 Credential Endpoint Migration: PUT /api/credentials/{id}
### Jun 8, 2026
2153 10:24p 🔵 Git sync blocked by SSL/TLS connection error to GitHub
2154 " 🔵 Network SSL connectivity to GitHub confirmed broken at system level
2155 10:26p ✅ Local uncommitted modification detected in AGENTS.md
2156 " 🔵 Git fetch succeeds; local branch is 11 commits behind upstream
2157 " 🔵 Remote commits do not modify AGENTS.md; pull operation is safe
2158 " ✅ Git sync completed: 11 upstream commits merged with major TikTok crawler refactor
2162 10:28p 🔵 Local commit history shows 11-commit upstream merge with TikTok enhancements
2169 10:47p 🔵 Live-Crawler Project Structure Mapped
2170 " 🔵 Live-Crawler Codebase Scale Confirmed
2171 " 🔵 CodeGraph Tool Availability Investigation
2172 10:48p 🔵 CHAPI Project Identified as Alternative Code Analysis Tool
2173 " 🔵 TikTok HTTP Three-Chain Lifecycle Architecture Documented
2175 " 🔵 Live-Crawler Codebase Scale and Module Organization
2176 " 🔵 Code Analysis Tools Evaluation: CHAPI vs Understand
2179 10:49p ⚖️ Knowledge Graph Tool Selection Decision: Reject CHAPI/Understand, Adopt Hybrid Approach
2180 " 🔵 Login Callback Orchestration Pattern Mapped via Grep Analysis
2181 10:50p 🔵 Crawler Implementation Hierarchy Mapped
2182 " 🔵 Dependency Analysis: Core Module Integration Points Identified
2183 " ⚖️ Final Tool Selection Decision: Reject Both CHAPI and Understand; Commit to Zero-Cost Hybrid Approach
2184 10:51p ⚖️ Agent-Conducted Tool Research Completes: Formal Recommendation Against CHAPI and Understand
2185 11:01p 🔵 Shopee implementation constraints documented in special rules
2186 " 🔵 Live-crawler project architecture and Shopee implementation constraints
2187 " 🔵 Shopee account types and login flow architecture
2188 11:02p 🔵 Shopee account type permission hierarchy and API fallback strategy
2189 " 🔵 Shopee login detection and shop switching architecture documented
2190 " 🔵 Shopee account type matrix and system coverage analysis completed
2191 11:04p 🔵 Shopee login refactor approach options documented with three implementation strategies
2195 11:16p ⚖️ Shopee Login Refactor Roadmap — Five-Phase Plan
2196 11:17p ✅ Shopee Login Refactor Specification Suite — Full Delivery
2197 " ✅ Complete Shopee Login Documentation Deliverables — Account Matrix, Flow Diagrams, and Code Rules
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
**Investigated**: 已检查根目录说明、ROADMAP、若干研究/设计/计划文档，以及仓库内是否仍存在已删除的 services/live-platform 与旧 Phase 1 / MediaMTX 相关文件。也对 docs/research/tiktok-live-dashboard-apis、services/live-monitor 的相关设计/计划做了关键词扫查，核对过时入口与现役边界。

**Learned**: services/live-platform 目录与相关旧主体文档已不存在；根入口已改为将 Phase 1 / MediaMTX 资料视为历史归档。现役边界已明显转向 live-monitor + live-stream + live-crawler，其中 Redis bridge 与 live-monitor/live-stream 的职责划分是当前主线。研究摘要中仍残留少量“live-platform API / 下一步实现”式历史表述，但都已在相邻文档中标注为过时背景。

**Completed**: 完成了文件存在性验证、仓库关键词收口扫描，以及对 README、CLAUDE、AGENTS、ROADMAP、Redis bridge 规格/计划、TikTok 大屏研究摘要与 live-monitor 标准化文档的交叉比对。确认了已删除的 PRD、架构总览、MediaMTX ADR、Phase 1 计划不再作为现役入口。

**Next Steps**: 继续收敛 TikTok 大屏研究摘要与历史草案中的过时措辞，重点清理仍指向 live-platform 类/路由/调度器的旧引用，并确认 live-monitor 文档里所有历史项都已明确标记为背景或移出实施范围。


Access 635k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
