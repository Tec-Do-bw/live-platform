# 直播数据采集系统

基于 DrissionPage 和 HTTP 双轨采集架构的直播数据采集系统，支持 TikTok、Shopee、Lazada 多平台、多账号并发采集。

## 功能特性

- **多平台支持**: TikTok、Shopee（浏览器采集）、Lazada（HTTP 采集）
- **双轨采集架构**: 浏览器采集（DrissionPage + AdsPower）+ HTTP 批量采集（Downloader）
- **Cookie 养号服务**: HTTP 采集体系登录态管理，定时刷新 Cookie
- **多账号采集**: 配置账号列表或从 AdsPower 分组动态获取
- **新账号自动全量**: 自动检测新增账号，首次采集执行全量模式
- **日报 Agent**: 基于日志生成每日采集报告并推送飞书

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 环境配置

通过 `APP_ENV` 环境变量区分开发/生产环境：

| 环境 | APP_ENV | 说明 |
|------|---------|------|
| 开发环境 | `dev`（默认） | 使用 test01 回调地址、测试 Kafka、DEBUG 日志 |
| 生产环境 | `pro` | 使用 livelabstar.com 回调地址、生产 Kafka、INFO 日志 |

**配置差异**：

| 配置项 | dev | pro |
|--------|-----|-----|
| 日志级别 | DEBUG | INFO |
| Kafka | `10.206.2.154:9092,...` | `alikafka-pre-cn-*.alikafka.aliyuncs.com:9092,...`（可通过环境变量覆盖） |
| 回调 URL | test01-patrick-star.tec-develop.cn | www.livelabstar.com |
| 数据服务器 URL | test01-patrick-star.tec-develop.cn | www.livelabstar.com |

**环境变量覆盖**（可选）：
```bash
# 覆盖 Kafka 地址
export KAFKA_BOOTSTRAP_SERVERS="custom-kafka:9092"

# 覆盖回调 Token
export LOGIN_CALLBACK_ACCESS_TOKEN="custom_token"

# 覆盖日志级别
export LOG_LEVEL="WARNING"
```

### 3. 运行

**快速启动（Windows CMD 双击运行）**：
- `start_pro.bat` — 生产环境（定时任务）

**命令行启动**：

```bash
# Bash / Git Bash
APP_ENV=dev python main.py --mode once          # 开发环境增量采集
APP_ENV=pro python main.py --mode scheduler     # 生产环境定时任务

# Windows CMD
set APP_ENV=dev && python main.py --mode once
set APP_ENV=pro && python main.py --mode scheduler
```

**其他运行模式**：

```bash
# Lazada 实时采集（只查询 Online 直播间）
python main.py --mode once --crawl-type realtime

# 全量采集（串行）
python main.py --mode full

# 全量采集（多进程并发）
python main.py --mode full --workers N

# 指定平台采集（只采集 TikTok）
python main.py --mode full --platform tiktok

# 指定多个平台采集
python main.py --mode full --platform tiktok --platform shopee

# 增量模式也支持平台过滤
python main.py --mode once --platform lazada

# 启动 Cookie 养号服务（独立进程）
python -m cookie_keeper

# 启动 Cookie 写入 API（供 adspower-server 回写 Cookie）
python -m monitor.server
```

### 4. 首次部署

```bash
# 将现有账号标记为"已采集"，避免重复全量
python scripts/init_tracker.py
```

## 系统架构

```
live_dp/
├── main.py                    # 主入口
├── core/                      # 核心配置
│   ├── apollo/               # Apollo 配置中心客户端
│   ├── config_base.py        # 基础配置（平台、账号、Kafka、定时任务等）
│   ├── collection_mode.py    # 采集模式判断
│   └── collection_tracker.py # 采集追踪（新账号检测）
├── crawlers/                  # 采集器根目录
│   ├── browser/              # 浏览器采集器（TikTok、Shopee）
│   │   ├── base.py          # BaseLiveCrawler 抽象基类
│   │   ├── live_crawler.py  # LiveCrawler 工厂类（双轨路由）
│   │   ├── tiktok.py        # TikTok 爬虫
│   │   └── shopee.py        # Shopee 爬虫
│   └── http/                 # HTTP 采集器（Lazada、TikTok）
│       ├── base.py          # BaseHttpCrawler 抽象基类
│       ├── lazada.py        # Lazada HTTP 采集器
│       └── tiktok/          # TikTok HTTP 采集器
│           ├── collector.py # 纯函数 fetch_* + collect_tiktok 编排
│           └── adapter.py   # start_crawl 适配层
├── services/                  # 共享业务服务
│   ├── cookie_manager.py     # Cookie 统一管理（CRUD）
│   ├── data_reporter.py      # 数据上报（重试、落盘）
│   └── login_callback.py     # 登录回调 + 登出恢复检测
├── cookie_keeper/             # Cookie 养号服务（HTTP 采集体系登录态管理）
│   ├── __main__.py           # 独立进程入口
│   ├── keeper.py             # CookieKeeperScheduler 调度器
│   ├── browser_refresher.py  # BrowserRefresher 浏览器刷新器
│   └── tiktok_refresher.py   # TikTok account_credentials 刷新器
├── jobs/                      # 独立任务入口
│   └── refresh_tiktok_credentials.py # TikTok 凭据刷新任务
├── downloader/                # HTTP 批量下载器（代理管理）
│   ├── core.py               # Downloader 核心
│   ├── models.py             # 请求/响应模型
│   └── config.py             # 下载器配置
├── scheduler/                 # 定时调度
│   └── task_scheduler.py     # APScheduler 多时间点调度
├── monitor/                   # Cookie API + 登录状态兼容层
│   ├── __init__.py           # 历史监控埋点 no-op + 保留业务表连接
│   ├── server.py             # Cookie 写入 API 服务入口
│   ├── api/
│   │   └── cookie_routes.py  # adspower-server Cookie 回写通道
│   ├── login_status_manager.py # 登录状态事件管理
│   ├── recovery_events.py    # 登出恢复事件写入
│   ├── classifier.py         # API URL/请求体分类器
│   └── registry.py           # API 类型注册表（可扩展）
├── webdriver/                 # 浏览器驱动
│   └── browserapi.py         # AdsPower API 封装
├── scripts/                   # 辅助脚本
│   ├── init_tracker.py       # 初始化采集追踪文件
│   ├── migrate_account_credentials.py # cookies → account_credentials 迁移脚本
│   ├── list_shopee_accounts.py # 列出 Shopee 账号
│   ├── daily_report.py       # 每日采集报告主入口(日志驱动 + OpenAI + 飞书)
│   ├── log_parser.py         # 日志预过滤/结构化解析
│   ├── status_tracker.py     # account_status.json 读写,跨天累计登出天数
│   ├── openai_client.py      # OpenAI 调用封装(失败降级纯文本)
│   ├── feishu_webhook.py     # 飞书富文本卡片推送
│   └── prompts/
│       └── daily_report.md   # OpenAI Prompt 模板
├── utils/                     # 工具模块
│   ├── adspower_client.py    # AdsPower API 统一客户端（含限流重试，见规则七）
│   ├── credentials.py        # account_credentials 读写
│   ├── headers.py            # HTTP 采集请求头构造
│   ├── http_session.py       # curl_cffi Session 工厂 + sync_retry
│   ├── kafka_client.py       # Kafka 客户端
│   ├── types.py              # HTTP 采集共享类型与异常
│   └── logger.py             # loguru 日志
└── tests/                     # 测试
    ├── crawlers/             # 采集器测试
    ├── services/             # 共享服务测试
    └── monitor/              # Cookie、登录状态、注册表相关测试
```

## 测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行 monitor 兼容层测试
python -m pytest tests/monitor/ -v
```

## 动态账号管理

系统支持两种账号配置方式：

**固定配置（测试环境）**

```python
"use_dynamic_users": False,
"user_ids": ['account_1', 'account_2']
```

**动态获取（生产环境）**

```python
"use_dynamic_users": True,
"group_names": ['TikTok主账号', 'TikTok测试账号']
```

从 AdsPower 分组实时获取账号，支持多分组合并采集。

## 新账号自动全量采集

`CollectionTracker` 维护已完成全量采集的账号记录（`resource/collection_tracker.json`），自动检测新账号执行全量，成功后标记为增量模式。

首次部署运行 `python scripts/init_tracker.py` 将现有账号初始化为"已采集"。

## 注意事项

1. 并发采集（`--workers N`）仅在 `--mode full` 时生效
2. AdsPower 浏览器需提前启动
3. Kafka 服务必须可访问
4. `resource/collection_tracker.json` 为运行时数据，不提交 git
5. 日志位于 `logs/` 目录，按日期自动轮转

## 日报 Agent 部署

每天早上 10:00 自动分析 T-1 日志,飞书推送采集情况报告(完整度/异常 Top/问题账号/趋势对比)。

### 1. 配置环境变量

```bash
# 飞书 Webhook(选填):默认复用 ALERT_CONFIG['webhook_url'](与运行时告警同一个机器人)
# 仅当日报需要走独立机器人时才设置以覆盖
export FEISHU_DAILY_REPORT_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
# 飞书自定义机器人加签密钥(选填,启用了"自定义关键词加签"才需要)
export FEISHU_DAILY_REPORT_SECRET="your_secret"

# OpenAI API(选填,未配置时降级为纯文本日报)
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"     # 默认 gpt-4o-mini
```

### 2. 手动验证

```bash
# 分析昨天的日志,只打印不推送
python -m scripts.daily_report --dry-run

# 指定日期补发
python -m scripts.daily_report --date 2026-05-06
```

### 3. 添加 cron(参考 cron.txt)

```cron
0 10 * * * cd /opt/live-crawler && /usr/bin/python3 -m scripts.daily_report >> logs/daily_report_cron.log 2>&1
```

### 4. 状态文件

`account_status.json`(运行时数据,gitignored)记录每个账号最后一次成功采集日期,用于跨天计算"连续登出天数"。损坏时会自动备份为 `account_status.json.broken` 并重建。

## 许可证

Private - 仅供内部使用

**Author**: XBW
