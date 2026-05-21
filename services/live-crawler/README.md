# 直播数据采集系统

基于 DrissionPage 和 HTTP 双轨采集架构的直播数据采集系统，支持 TikTok、Shopee、Lazada 多平台、多账号并发采集，内置采集完整性监控面板。

## 功能特性

- **多平台支持**: TikTok、Shopee（浏览器采集）、Lazada（HTTP 采集）
- **双轨采集架构**: 浏览器采集（DrissionPage + AdsPower）+ HTTP 批量采集（Downloader）
- **Cookie 养号服务**: HTTP 采集体系登录态管理，定时刷新 Cookie
- **多账号采集**: 配置账号列表或从 AdsPower 分组动态获取
- **新账号自动全量**: 自动检测新增账号，首次采集执行全量模式
- **采集监控**: 内置 Web 面板，实时查看采集完整性和直播间数据

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

# 启动监控面板（端口 8777）
python -m monitor.server
```

### 4. 首次部署

```bash
# 将现有账号标记为"已采集"，避免重复全量
python scripts/init_tracker.py
```

## 采集监控系统

内置的采集完整性监控系统，在爬虫采集过程中自动记录 API 调用情况，通过 Web 面板实时查看。

启动监控服务后，浏览器访问 `http://localhost:8777` 即可查看监控面板。

> **关于前端产物**：`monitor/frontend/dist/` 目录已提交到 Git 仓库。部署时只需 `git pull` 即可直接启动监控服务，无需安装 Node.js 或重新构建前端。
>
> 仅在前端代码有修改时，才需要重新构建并提交产物：
> ```bash
> cd monitor/frontend
> npm install && npm run build
> git add dist/ && git commit -m "build(monitor): 重新构建前端产物"
> ```

### 监控架构

```
爬虫采集流程
    |
    +-- crawlers/browser/base.py: send_api_request()
    |       |
    |       +-- [钩子] monitor/tracker.py --> 写入 SQLite
    |
    +-- main.py / scheduler/task_scheduler.py
            |
            +-- 采集开始/结束时 start_batch/finish_batch

FastAPI 监控服务 (monitor/server.py, 端口 8777)
    |
    +-- REST API: /api/batches, /api/batches/{id}/accounts, /api/accounts/{id}/rooms
    |
    +-- 托管 Vue3 前端 (monitor/frontend/dist/)
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
│   │   ├── base.py          # BaseLiveCrawler 抽象基类 + 监控钩子
│   │   ├── live_crawler.py  # LiveCrawler 工厂类（双轨路由）
│   │   ├── tiktok.py        # TikTok 爬虫
│   │   └── shopee.py        # Shopee 爬虫
│   └── http/                 # HTTP 采集器（Lazada）
│       └── base.py          # BaseHttpCrawler 抽象基类
├── services/                  # 共享业务服务
│   ├── cookie_manager.py     # Cookie 统一管理（CRUD）
│   ├── data_reporter.py      # 数据上报（重试、落盘）
│   └── login_callback.py     # 登录回调 + 登出恢复检测
├── cookie_keeper/             # Cookie 养号服务（HTTP 采集体系登录态管理）
│   ├── __main__.py           # 独立进程入口
│   ├── keeper.py             # CookieKeeperScheduler 调度器
│   └── browser_refresher.py  # BrowserRefresher 浏览器刷新器
├── downloader/                # HTTP 批量下载器（代理管理）
│   ├── core.py               # Downloader 核心
│   ├── models.py             # 请求/响应模型
│   └── config.py             # 下载器配置
├── scheduler/                 # 定时调度
│   └── task_scheduler.py     # APScheduler 多时间点调度
├── monitor/                   # 采集监控系统
│   ├── db.py                 # SQLite 数据库初始化（WAL 模式）
│   ├── tracker.py            # CollectionMonitor 采集记录器
│   ├── classifier.py         # API URL/请求体分类器
│   ├── registry.py           # API 类型注册表（可扩展）
│   ├── server.py             # FastAPI 服务入口
│   ├── api/                  # REST API 路由
│   ├── frontend/             # Vue3 + Element Plus 前端
│   └── data/monitor.db       # SQLite 数据库文件（运行时生成）
├── webdriver/                 # 浏览器驱动
│   └── browserapi.py         # AdsPower API 封装
├── scripts/                   # 辅助脚本
│   ├── init_tracker.py       # 初始化采集追踪文件
│   ├── list_shopee_accounts.py # 列出 Shopee 账号
│   └── mock_monitor_data.py  # 注入监控模拟数据
├── utils/                     # 工具模块
│   ├── adspower_client.py    # AdsPower API 统一客户端（含限流重试，见规则七）
│   ├── kafka_client.py       # Kafka 客户端
│   └── logger.py             # loguru 日志
└── tests/                     # 测试
    ├── crawlers/             # 采集器测试
    ├── services/             # 共享服务测试
    └── monitor/              # 监控模块单元测试（24 个测试）
```

## 测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行监控模块测试
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
4. `resource/collection_tracker.json` 和 `monitor/data/monitor.db` 为运行时数据，不提交 git
5. 日志位于 `logs/` 目录，按日期自动轮转

## 许可证

Private - 仅供内部使用

**Author**: XBW
