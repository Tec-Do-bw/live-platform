# live-platform 子项目清理报告

> 日期：2026-06-24
> 范围：删除 `services/live-platform/`，清理主体文档，修正仍保留文档中的过时入口与现役状态描述。

## 结论

已按当前清理目标删除 `services/live-platform/` 整个子项目，并移除常规入口中的 Phase 1 / MediaMTX 整合服务状态。仓库现役服务目录恢复为：

- `services/live-monitor/`
- `services/live-stream/`
- `services/adspower-server/`
- `services/live-crawler/`

`README.md`、`CLAUDE.md`、`AGENTS.md`、`docs/ROADMAP.md` 已同步改为：`services/live-platform/` 不再是现役子项目；Phase 1 / MediaMTX 资料仅作历史参考。

## Wiki 参考

执行前按 `kb-lookup` 规则先读本地 Wiki：

- `wiki/INDEX.md`：定位到 `topics/claude-md-best-practices`、`topics/claude-md-mechanisms`、`topics/prompt-mentor-guide`、`topics/workflow-skill-patterns`。
- `topics/claude-md-best-practices.md`：根 `CLAUDE.md` 应保持薄，只放全局约束和文档地图；条件规则放子目录或 rules。
- `topics/claude-md-mechanisms.md`：根文件负责文档地图与按需披露，子目录 `CLAUDE.md` 承载模块特有背景。
- `topics/prompt-mentor-guide.md`：长任务用 Goal / Context / Constraints / Done when / Stop if / Scope / Checkpoint / Maker-Checker 控制执行边界。
- `topics/workflow-skill-patterns.md`：用渐进式披露和分层 token 预算组织规则，不把历史细节复制到多个入口。

这些规则影响了本次决策：`CLAUDE.md` 保留完整权威说明，`AGENTS.md` 只补 Codex 执行入口提示；旧研究文档只加 superseded / 历史说明，不复制一份新规格；现役规范集中指向 `docs/specs/live-monitor-stream-redis-bridge.md` 与 `docs/specs/tiktok-live-dashboard-data-api-service.md`。

## 删除范围

### 已删除目录

- `services/live-platform/`

### 已删除主体文档

- `docs/plans/2026-05-06-architecture-simplification.md`
- `docs/plans/2026-05-07-live-platform-phase1.md`
- `docs/specs/2026-05-10-mediamtx-deployment-adr.md`
- `docs/specs/PRD-live-platform-v1.0.md`
- `docs/specs/live-platform-architecture.md`
- `docs/superpowers/plans/2026-06-17-live-platform-review-fixes.md`

删除理由：这些文档主体围绕 `services/live-platform/`、Phase 1 整合服务或 MediaMTX recorder，不应继续留在常规文档入口中。

## 修改范围

- `README.md`：移除 `services/live-platform/` 目录树、子项目入口和 MediaMTX 现役方向描述。
- `CLAUDE.md`：移除第五个子项目，保留历史删除说明，技术栈移除 MediaMTX。
- `AGENTS.md`：补充 Codex 入口提示，说明 `services/live-platform/` 已删除；原有未提交 memory context 保持不回滚。
- `docs/ROADMAP.md`：移除 Phase 1 / 架构精简化进行中项，移除已删 specs 的长期参考入口。
- `docs/specs/live-monitor-stream-redis-bridge.md` 与对应 plan：将 `services/live-platform` key shape 改为历史设计来源，不再作为现役 recorder。
- `services/live-monitor/docs/designs/2026-05-25-live-room-api-standardization.md` 与对应 plan：将聚合代理改造改为历史项。
- `docs/research/tiktok-live-dashboard-apis/*`：保留研究过程，加 superseded / 历史方案说明，现役接口边界指向 `docs/specs/tiktok-live-dashboard-data-api-service.md`。

## 残留引用分类

### 已清理

- 根入口不再把 `services/live-platform/` 列为现役子项目。
- `docs/ROADMAP.md` 不再链接已删除的 Phase 1 plan、MediaMTX ADR、旧 PRD、旧架构总览。
- `services/live-platform/` 文件名扫描已清空，仓库文件列表中不再存在该目录。
- `rg --files | rg "(live-platform|phase1|phase-1|mediamtx)"` 只剩 `docs/archive/2026-06-09-shopee-login-refactor-phase1.md`，与本次服务删除无关。

### 合理保留的历史引用

- 仓库名、remote URL、根目录代码块中的 `live-platform/`：这是仓库名，不是已删服务目录。
- `AGENTS.md` 中 `<claude-mem-context>` 的旧观察记录：属于本机 memory context，保留以避免回滚用户已有未提交改动。
- `docs/specs/live-monitor-stream-redis-bridge.md` 和 `docs/plans/2026-06-23-live-monitor-stream-redis-bridge.md`：仅把旧 Redis key shape 作为历史设计来源。
- `services/live-monitor/docs/*2026-05-25-live-room-api-standardization.md`：保留旧聚合代理引用，但明确为历史项。
- `docs/research/tiktok-live-dashboard-apis/*`：保留早期研究正文，已标注现役接口边界以 `docs/specs/tiktok-live-dashboard-data-api-service.md` 为准。
- `docs/archive/` 与其他子项目文档中的普通 `Phase 1`：属于其他项目阶段或历史归档，不是 `services/live-platform/` 现役引用。

### 需要用户确认

- 外部 Zadig / 平台配置：repo 内未发现 `.github/`、`.gitlab-ci*`、Zadig、k8s、helm、根 Docker Compose 等强依赖，但 Zadig 服务配置可能在平台外部，删除代码前后仍建议在 Zadig UI 或配置中心确认没有继续部署 `live-platform` / `mediamtx` 服务。
- 如果希望“硬清理”研究目录正文，可进一步重写 `docs/research/tiktok-live-dashboard-apis/README.md`、`summary.md`、`COMPLETION-REPORT.md`，把旧 live-platform 架构图从正文移到更短的历史附录。本次仅做过时标注，保留调研过程。

## 验证命令

已执行：

```bash
git status -sb
find services -maxdepth 2 -type d | sort
test ! -d services/live-platform && echo "services/live-platform absent"
rg -n "services/live-platform|live-platform|Phase 1|Phase1|MediaMTX|mediamtx" README.md CLAUDE.md AGENTS.md docs services/live-monitor services/live-stream services/adspower-server services/live-crawler
rg --files | rg "(live-platform|phase1|phase-1|mediamtx)"
git diff --stat
```

结果摘要：

- `services/live-platform absent`
- `find services -maxdepth 2 -type d` 仅列出现役四个子服务及其子目录。
- 文件名扫描只剩 Shopee 登录重构 `phase1` 归档文件。
- 引用扫描剩余项均已分类为历史引用、仓库名、memory context、其他子项目 phase 或外部确认点。

## 未运行项

未运行 pytest / build：本次不修改现役业务代码，主要变更是删除已废弃子项目与文档治理；现役四个子项目代码未改。
