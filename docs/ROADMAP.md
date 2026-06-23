# Live Platform Roadmap

> 干什么 / 下一步干什么 / 刚干完什么。所有 plan 文档的总索引。
>
> **维护规则**:plan 完成 → 在「最近完成」勾选 + 标日期 + 把 plan 文件移到 `archive/`。

## 进行中 (In Progress)

- [ ] **架构精简化**(4 服务 → 2 核心 + 1 独立)→ [plans/2026-05-06-architecture-simplification.md](plans/2026-05-06-architecture-simplification.md)
- [ ] **Phase 1: live-platform 整合**(MediaMTX 录制底座)→ [plans/2026-05-07-live-platform-phase1.md](plans/2026-05-07-live-platform-phase1.md)
- [ ] **live-monitor/live-stream Redis 桥接**(FLV URL 状态、录制 lease、batch live-status API)→ [plans/2026-06-23-live-monitor-stream-redis-bridge.md](plans/2026-06-23-live-monitor-stream-redis-bridge.md)

## 下一步 (Next Up)

- [ ] (空,根据需要补充)

## 最近完成 (Recently Done · 仅显示最近 10 项)

- [x] 2026-06-09 Shopee 登录检测重构 Phase 1：主动验证快速路径 + 跨境店多店列表接口 + HTTP 切换
- [x] 2026-05-28 Phase 4B 删除 SQLite 监控面板、补采系统与旧前端
- [x] 2026-05-28 `/get_roominfo` 排除 `flv_url=error` 的采集失败房间
- [x] 2026-05-27 代理策略极简化 + Downloader 短响应自动重试
- [x] 2026-05-22 TiktokTool 短响应风控兜底 + 同步 IO 异步卸载 + region 对比脚本
- [x] 2026-05-22 Adspower 修复 Shopee 登录验证页面跳转竞态误报
- [x] 2026-05-22 TikTok 主播国家识别能力 + 直播流 URL 抓取规格
- [x] 2026-05-22 TiktokTool 下载器架构重构 + live-room-api 契约文档
- [x] 2026-05-22 三个拉流接口路由响应标准化 + 翻译层单测
- [x] 2026-05-22 接口响应标准化设计、规范、实施计划文档
- [x] 2026-05-22 live-platform 服务骨架与 Phase 1 代码实现 + MediaMTX 部署 ADR

## 长期参考 (Reference)

- [PRD v1.0](specs/PRD-live-platform-v1.0.md) — 产品需求
- [架构总览](specs/live-platform-architecture.md) — 系统层级与数据流
- [DDD 限界上下文](specs/DDD-domain-model-design.md) — 4 个限界上下文及职责边界
- [live-monitor/live-stream Redis 桥接](specs/live-monitor-stream-redis-bridge.md) — FLV URL 状态、录制 lease、batch live-status API
- [MediaMTX 部署 ADR](specs/2026-05-10-mediamtx-deployment-adr.md) — Docker Compose + host 网络 + bind mount
- 业务规则索引 → `.claude/rules/`(由 `paths` frontmatter 自动触发,编辑对应代码时自动加载)
- 子项目内规格 → `services/<name>/docs/specs/`(各服务自治)

## 已完成项目 (Archive)

`docs/archive/` 保留所有已完成 plan 的历史副本。如需翻阅:`ls docs/archive/`。
