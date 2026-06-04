# Live Platform - 直播监控与数据采集平台

> Monorepo,4 个子服务。详细启动命令、环境配置见 [`README.md`](README.md)。

## 子项目

| 子项目 | 路径 | 职责 |
|--------|------|------|
| 直播间监控 | [`services/live-monitor/`](services/live-monitor/CLAUDE.md) | 主备高可用,房间检测、状态管理、GMV 采集 |
| 直播流录制 | [`services/live-stream/`](services/live-stream/CLAUDE.md) | FFmpeg 推流、视频切割、OSS 上传 |
| 浏览器管理 | [`services/adspower-server/`](services/adspower-server/CLAUDE.md) | AdsPower 浏览器、CDP 投屏、登录监控 |
| 数据采集 | [`services/live-crawler/`](services/live-crawler/CLAUDE.md) | TikTok/Shopee/Lazada 双轨采集(浏览器+HTTP) |
| Phase 1 整合服务 | [`services/live-platform/`](services/live-platform/CLAUDE.md) | live-monitor + live-stream + MediaMTX(进行中) |

## 文档地图

| 你需要 | 去哪里看 |
|--------|----------|
| 当前在做什么、下一步、最近完成 | [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| 长期参考(架构/PRD/ADR/数据模型) | [`docs/specs/`](docs/specs/) |
| 进行中的实施计划(含 task checklist) | [`docs/plans/`](docs/plans/) |
| 业务规则(采集模式、登录回调、Shopee 特殊规则等) | [`.claude/rules/`](.claude/rules/)(由 `paths` frontmatter 自动触发,编辑对应代码时自动加载) |
| 子项目结构与启动 | 对应子项目 `README.md` |
| 子项目约束与设计决策 | 对应子项目 `CLAUDE.md` |

## 技术栈

Python 3.12 · FastAPI · DrissionPage(浏览器爬虫)+ HTTP(Lazada)· AdsPower API · FFmpeg / MediaMTX · Kafka · 阿里云 OSS · Vue3 + Element Plus · SQLite

## 已知坑

- **loguru 用 f-string**:`logger.info(f"msg={var}")`,禁用 `logger.info("msg=%s", var)`(% 占位符在 loguru 不生效)

## 代码规范

- 注释、docstring、commit message 使用中文(技术术语保持英文)
- Python 类型提示用 `str | None` 风格(非 `Optional[str]`)
- 测试用 pytest,运行单个测试而非全套
- 前端用 Vue3 Composition API + `<script setup>`

## IMPORTANT: 工作流规则

`.claude/rules/` 下规则按 `paths` 自动触发,无需手动加载:

| 规则文件 | 触发条件 | 核心要求 |
|----------|----------|----------|
| `read-before-write.md` | 编辑 `services/*/` 文件 | 先读对应子项目 CLAUDE.md |
| `update-docs-on-structure-change.md` | 新增/删除文件、plan 完成 | 更新子项目 README 目录树 + ROADMAP 维护 |
| `chinese-comments.md` | 写代码时 | 注释、docstring、commit 用中文 |
| `single-source-of-truth.md` | 编辑文档时 | 禁止复制副本,用路径引用 |
| `live-room-api-contract.md` | 修改 `services/live-monitor/utils/*Tool.py` | 维护爬虫工具返回值契约 |
| `collection-mode-rules.md` | 编辑 live-crawler 采集调度入口 | 全量/增量/登出恢复模式判断优先级 |
| `logout-recovery-flow.md` | 编辑 live-crawler base/scheduler/login 相关代码 | 即时恢复(2 轮)与 Fallback(3 轮)路径 |
| `login-callback-spec.md` | 编辑 adspower-server 或 live-crawler 登录回调代码(含 tiktok HTTP adapter/refresher) | 浏览器侧三态 vs HTTP 侧二态、reason 字段、回调优先级与去重 |
| `shopee-special-rules.md` | 编辑 live-crawler shopee 相关代码 | page_urls 模板、时区 T-1、域名映射、JS 注入采集 |
| `tiktok-collection-time.md` | 编辑 live-crawler tiktok(http collector/browser)/browserapi | 增量 T-3、全量 T-28、禁用 SETTLEMENT_HOUR |
| `tiktok-http-lifecycle.md` | 编辑 tiktok HTTP 三链路(adapter/collector/refresher/refresh_routes/login_monitor) | 登录态一律走 HTTP account_info、回调三铁律、三链路衔接契约 |

其他工作流约定:

- **先 Plan 再编码**:非琐碎任务先用 Plan Mode 输出步骤,确认后再实现
- **重要技术决策**:记录到对应子项目 CLAUDE.md
- **任务追踪**:大颗粒度走 [`docs/ROADMAP.md`](docs/ROADMAP.md);bug/feature 走 `gh issue create`,完成时 commit 用 `fixes #N` 自动关闭

## 文档管理规则

- **单一权威源**:每份文档只在一处维护,其他位置用路径引用,禁止复制副本
- **层级继承**:子项目 CLAUDE.md 不重复根规则,只记子项目特有约束
- **目录语义 = 状态语义**:
  - `specs/` — 长期有效的参考(PRD / 架构 / ADR / 数据模型 / 接口规范);响应样本放 `specs/example_data/`
  - `plans/` — 进行中的实施计划(含 `- [ ]` checklist),完成后移到 `archive/`
  - `archive/` — 已完成或被取代的历史
  - `superpowers/` — Superpowers Skill 体系自治区,例外
- **命名**:kebab-case 英文(`deployment-guide.md`);带日期用 `YYYY-MM-DD-<topic>.md`
- **plan 完成时**:勾选 ROADMAP + 移文件到 archive(详见 `update-docs-on-structure-change.md`)
