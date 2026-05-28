# Live Platform

> 整合直播间监控、视频流录制、浏览器管理、商家数据采集的一站式平台。
>
> AI 协作约束与设计决策见 [`CLAUDE.md`](CLAUDE.md);开发进度看 [`docs/ROADMAP.md`](docs/ROADMAP.md)。

## 项目结构

```
live-platform/
├── services/
│   ├── live-monitor/       # 直播间监控(主备 HA,房间检测、状态管理)
│   ├── live-stream/        # 直播流录制(FFmpeg 推流、视频切割、OSS 上传)
│   ├── adspower-server/    # AdsPower 浏览器管理(登录态、CDP 投屏)
│   ├── live-crawler/       # 商家后台数据采集(TikTok/Shopee/Lazada)
│   └── live-platform/      # Phase 1 整合服务(live-monitor + live-stream + MediaMTX,进行中)
├── docs/
│   ├── ROADMAP.md          # 进度索引
│   ├── plans/              # 进行中的实施计划
│   ├── specs/              # 长期参考(PRD/架构/ADR)
│   ├── archive/            # 已完成/废弃
│   └── superpowers/        # Skill 体系自治区
└── .claude/                # AI 协作配置(rules / references / agents / commands)
```

## 四大模块

| 模块 | 目录 | 职责 | 来源仓库 |
|------|------|------|----------|
| 直播间监控 | `services/live-monitor` | 监控开播状态,主备高可用,房间检测与数据同步 | liveSpider_Serverv3 |
| 直播流录制 | `services/live-stream` | FFmpeg 拉流切片,推送 OSS | live-straem |
| 浏览器管理 | `services/adspower-server` | AdsPower 指纹浏览器、CDP 投屏、多平台登录监控 | livelab/adspower-server |
| 数据采集 | `services/live-crawler` | 双轨采集(浏览器+HTTP),TikTok/Shopee/Lazada 商家后台 | livelab/live_dp |

## 业务流程

```
1. live-monitor 监控直播间 → 检测到开播
2. live-stream 拉取视频流 → FFmpeg 切割 → 推送 OSS
3. adspower-server 管理浏览器环境 → 投屏授权登录 → 登录态管理
4. live-crawler 采集商家后台数据 → Kafka 上报
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.12 |
| Web 框架 | FastAPI |
| 爬虫引擎 | DrissionPage(浏览器)、HTTP(Lazada) |
| 浏览器管理 | AdsPower API + 指纹浏览器 |
| 视频处理 | FFmpeg(现) / MediaMTX(Phase 1 整合方向) |
| 消息队列 | Kafka |
| 对象存储 | 阿里云 OSS |
| 前端 | Vue3 + Element Plus |
| 监控存储 | SQLite |
| 部署 | 单机部署,FastAPI 托管前端静态文件 |

## 环境配置

### Python 依赖

```bash
pip install -r services/live-monitor/requirements.txt
pip install -r services/live-stream/requirements.txt
pip install -r services/adspower-server/requirements.txt
pip install -r services/live-crawler/requirements.txt
```

### 前端依赖

```bash
cd services/live-crawler/monitor/frontend && npm install
```

### 环境变量

通过 `APP_ENV=dev/pro` 区分开发与生产,具体配置以代码与环境变量默认值为准。

## 快速启动

各服务独立启动:

| 服务 | 启动命令 |
|------|----------|
| 直播间监控 | `cd services/live-monitor && python main.py` |
| 直播流录制 | `cd services/live-stream && bash start.sh` |
| 浏览器管理 | `cd services/adspower-server && python -m app.main` |
| 数据采集 | `cd services/live-crawler && python main.py --mode scheduler` |

## 常用命令

| 命令 | 用途 |
|------|------|
| `cd services/live-crawler && python main.py --mode once --crawl-type realtime` | Lazada 实时采集 |
| `cd services/live-crawler && python main.py --mode full` | 全量采集(串行) |
| `cd services/live-crawler && python -m monitor.server` | 启动采集监控面板(端口 8777) |
| `cd services/live-crawler && python -m cookie_keeper` | 启动 Cookie 养号服务 |
| `curl http://localhost:8080/health` | 检查 live-monitor 健康状态 |

## 子项目文档

- [直播间监控 (live-monitor)](services/live-monitor/README.md)
- [直播流录制 (live-stream)](services/live-stream/README.md)
- [浏览器管理 (adspower-server)](services/adspower-server/README.md)
- [数据采集 (live-crawler)](services/live-crawler/README.md)
- [Phase 1 整合 (live-platform)](services/live-platform/README.md)
