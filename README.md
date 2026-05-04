# Live Platform - 直播监控与数据采集平台

> 整合直播间监控、视频流录制、浏览器管理、商家数据采集的一站式平台。

## 项目结构

```
live-platform/
├── services/
│   ├── live-monitor/       # 直播间监控系统（主备高可用，房间检测、状态管理）
│   ├── live-stream/        # 直播流录制（FFmpeg 推流、视频切割、OSS 上传）
│   ├── adspower-server/    # AdsPower 浏览器管理（登录态管理、CDP 投屏转发）
│   └── live-crawler/       # 直播商家后台数据采集（TikTok/Shopee/Lazada）
├── docs/                   # 项目文档
└── README.md
```

## 四大模块

| 模块 | 目录 | 职责 | 来源仓库 |
|------|------|------|----------|
| 直播间监控 | `services/live-monitor` | 监控直播间开播状态，主备高可用架构，房间检测与数据同步 | liveSpider_Serverv3 |
| 直播流录制 | `services/live-stream` | 获取实时视频流，FFmpeg 视频切割，推送到 OSS | live-straem |
| 浏览器管理 | `services/adspower-server` | AdsPower 指纹浏览器管理，CDP 投屏转发，多平台登录监控 | livelab/adspower-server |
| 数据采集 | `services/live-crawler` | 双轨采集架构（浏览器+HTTP），TikTok/Shopee/Lazada 商家后台数据采集 | livelab/live_dp |

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
| 爬虫引擎 | DrissionPage（浏览器）、HTTP（Lazada） |
| 浏览器管理 | AdsPower API + 指纹浏览器 |
| 视频处理 | FFmpeg |
| 消息队列 | Kafka |
| 对象存储 | 阿里云 OSS |
| 前端 | Vue3 + Element Plus |
| 监控存储 | SQLite |

## 快速开始

各模块独立运行，详见各自子项目文档：

- [直播间监控](services/live-monitor/CLAUDE.md)
- [直播流录制](services/live-stream/CLAUDE.md)
- [浏览器管理](services/adspower-server/README.md)
- [数据采集](services/live-crawler/README.md)
