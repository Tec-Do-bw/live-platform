# Live Platform - 直播监控与数据采集平台

> Monorepo 项目，整合直播间监控、视频流录制、浏览器管理、商家数据采集四大模块。

## 子项目

| 子项目 | 路径 | 说明 | 来源仓库 |
|--------|------|------|----------|
| 直播间监控 | `services/live-monitor/` | 主备高可用架构，房间检测、状态管理、GMV 采集 | liveSpider_Serverv3 |
| 直播流录制 | `services/live-stream/` | FFmpeg 推流、视频切割、OSS 上传 | live-straem |
| 浏览器管理 | `services/adspower-server/` | AdsPower 浏览器管理、CDP 投屏转发、登录监控 | livelab/adspower-server |
| 数据采集 | `services/live-crawler/` | TikTok/Shopee/Lazada 双轨采集（浏览器+HTTP） | livelab/live_dp |

业务规则详见 `.claude/references/` 目录：
- 采集模式与登出恢复：`collection-mode-rules.md`
- 登录回调规格：`login-callback-spec.md`
- Shopee 特殊规则：`shopee-special-rules.md`

## 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.12 |
| Web 框架 | FastAPI |
| 爬虫引擎 | DrissionPage（浏览器）、HTTP（Lazada） |
| 浏览器管理 | AdsPower API + 指纹浏览器 |
| 视频处理 | FFmpeg |
| 消息队列 | Kafka |
| 对象存储 | 阿里云 OSS |
| 前端 | Vue3 + Element Plus |
| 监控存储 | SQLite |
| 部署 | 单机部署，FastAPI 托管前端静态文件 |

## 命令

> **环境**：Windows 11 + CMD（.bat 启动）/ Git Bash（git 操作，使用 Unix 风格路径）。pytest 必须从各服务目录运行。

### 快速启动

各服务独立启动：

| 服务 | 启动命令 |
|------|----------|
| 直播间监控 | `cd services/live-monitor && python main.py` |
| 直播流录制 | `cd services/live-stream && bash start.sh` |
| 浏览器管理 | `cd services/adspower-server && python -m app.main` |
| 数据采集 | `cd services/live-crawler && python main.py --mode scheduler` |

### 常用命令

| 命令 | 用途 |
|------|------|
| `cd services/live-crawler && python main.py --mode once --crawl-type realtime` | Lazada 实时采集 |
| `cd services/live-crawler && python main.py --mode full` | 全量采集（串行） |
| `cd services/live-crawler && python -m monitor.server` | 启动采集监控面板（端口 8777） |
| `cd services/live-crawler && python -m cookie_keeper` | 启动 Cookie 养号服务 |
| `cd services/live-monitor && curl http://localhost:8080/health` | 检查监控服务健康状态 |

## 环境配置

### Python 环境
```bash
pip install -r services/live-monitor/requirements.txt
pip install -r services/live-stream/requirements.txt
pip install -r services/adspower-server/requirements.txt
pip install -r services/live-crawler/requirements.txt
```

### 环境区分

通过 `APP_ENV=dev/pro` 区分开发和生产环境；具体配置以代码和环境变量默认值为准。

### 前端环境
```bash
cd services/live-crawler/monitor/frontend && npm install
```

## 代码规范

- **所有代码注释、docstring、commit message 使用中文**（技术术语保持英文）
- Python 使用 Python 3.12，类型提示使用 `str | None` 风格（非 `Optional[str]`）
- 测试用 pytest，运行单个测试而非全套
- 前端使用 Vue3 Composition API + `<script setup>` 语法

## IMPORTANT: 工作流规则

1. **写代码前**必须阅读对应子项目的 CLAUDE.md
2. **新增/删除文件后**更新对应子项目的 CLAUDE.md 架构章节
3. **重要技术决策**记录到对应子项目 CLAUDE.md 中
4. **先 Plan 再编码**：复杂任务先用 Plan Mode 输出步骤，确认后再实现
5. **必须提供验证**：实现后运行测试/lint，不要产出未验证的代码
6. **任务追踪**：功能/Bug/待办用 `gh issue create` 创建 Issue，完成后提交时用 `fixes #编号` 自动关闭

## gh CLI 路径问题

Windows 环境下 Git Bash 可能找不到 `gh` 命令，需要用完整路径：
```bash
"/c/Program Files/GitHub CLI/gh.exe" pr create ...
```

## 文档管理规则

- **单一权威源**：每份技术文档只在一个位置维护，其他位置通过路径引用，禁止复制副本
- **层级继承**：子项目 CLAUDE.md 不重复根 CLAUDE.md 的通用规则，仅记录子项目特有约束
- **历史文档归档**：已完成的计划、被取代的设计 → 移入 `docs/archive/`
- **目录约定**：`docs/superpowers/` 放 plans/specs，`{子项目}/doc/documentation/` 放对接文档，`{子项目}/doc/specs/` 放功能规格
