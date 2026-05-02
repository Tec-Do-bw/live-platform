# CLAUDE.md

> 通用编码规范、工作流规则见根目录 `CLAUDE.md`。以下仅记录 live_dp 特有规则。

## 项目概述

基于 DrissionPage 的直播数据采集系统，支持 TikTok、Shopee、Lazada 多平台、多账号并发采集。通过 AdsPower 指纹浏览器 API 管理账号，拦截平台 API 请求，将数据上报至后端服务器。内置采集完整性监控系统（monitor 模块），通过 SQLite + FastAPI + Vue3 实时查看采集状态。

## 目录结构

```
live_dp/
├── crawlers/                    # 采集器根目录
│   ├── browser/                # 浏览器采集器（TikTok、Shopee）
│   │   ├── base.py            # BaseLiveCrawler 抽象基类
│   │   ├── live_crawler.py    # LiveCrawler 工厂类
│   │   ├── tiktok.py          # TikTok 实现
│   │   ├── shopee.py          # Shopee 实现
│   │   └── mx_tiktok.py       # 墨西哥 TikTok 特化
│   └── http/                   # HTTP 采集器（Lazada 等纯 HTTP 平台）
│       └── base.py            # BaseHttpCrawler 抽象基类
├── services/                   # 共享业务服务
│   ├── cookie_manager.py      # Cookie 统一管理（CRUD）
│   ├── data_reporter.py       # 数据上报共享模块（重试、落盘）
│   └── login_callback.py      # 登录回调共享模块（回调 + 登出恢复检测）
├── cookie_keeper/              # Cookie 养号服务（HTTP 采集体系登录态管理）
│   ├── __init__.py            # 模块入口
│   ├── __main__.py            # 独立进程入口
│   ├── keeper.py              # CookieKeeperScheduler 调度器
│   ├── browser_refresher.py   # BrowserRefresher 浏览器刷新器
│   └── account_nurturing.py   # 账号养号策略
├── downloader/                 # HTTP 下载器（批量请求、代理管理）
│   ├── core.py                # Downloader 核心
│   ├── models.py              # 请求/响应模型
│   └── config.py              # 下载器配置
├── core/                       # 核心配置与工具
│   ├── apollo/                # Apollo 配置中心客户端
│   │   ├── apollo_client.py  # Apollo 客户端
│   │   ├── setting.py        # 配置模型
│   │   └── util.py           # 工具函数
│   ├── config_base.py         # 平台配置定义
│   ├── collection_mode.py     # 采集模式判断
│   └── collection_tracker.py  # 采集追踪
├── monitor/                    # 采集监控系统
├── scheduler/                  # 定时调度
├── webdriver/                  # AdsPower API 封装
└── tests/
    ├── crawlers/browser/      # 浏览器采集器测试
    ├── crawlers/http/         # HTTP 采集器测试
    ├── services/              # 共享服务测试
    └── monitor/               # 监控模块测试
```

## 运行命令

详见根目录 `CLAUDE.md`。额外命令：

```bash
# 初始化采集追踪文件（首次部署后运行一次）
python scripts/init_tracker.py

# 注入监控模拟数据（开发测试用）
python scripts/mock_monitor_data.py
```

## 核心架构

```
main.py
  └→ LiveCrawler(platform, browser_id, ...)  # 工厂类路由
       ├→ [浏览器] TikTok/Shopee → BaseLiveCrawler
       │     └→ start_crawl() → visit_page_and_collect() → data_reporter → monitor
       │
       └→ [HTTP] Lazada → BaseHttpCrawler
             └→ start_crawl() → Downloader.run() → parse_response() → data_reporter → monitor
```

### 关键模块

| 模块 | 职责 |
|------|------|
| `crawlers/browser/live_crawler.py` | 工厂类，双轨路由（浏览器/HTTP） |
| `crawlers/browser/base.py` | 浏览器采集抽象基类 |
| `crawlers/http/base.py` | HTTP 采集抽象基类，多阶段流程 |
| `services/data_reporter.py` | 数据上报（重试、落盘） |
| `services/login_callback.py` | 登录回调 + 登出恢复检测 |
| `services/cookie_manager.py` | Cookie 统一管理（CRUD） |
| `cookie_keeper/` | Cookie 养号服务（独立进程） |
| `downloader/` | HTTP 批量下载器（代理管理） |
| `core/collection_mode.py` | 采集模式判断（详见 `../.claude/references/collection-mode-rules.md`） |
| `core/collection_tracker.py` | 采集追踪，检测新账号 |
| `webdriver/browserapi.py` | AdsPower API 封装 |
| `monitor/` | 采集监控系统（SQLite + FastAPI + Vue3） |

### 监控系统

- 平台识别通过 `account_sessions.platform` 字段（非 group_name 猜测）
- API 类型注册表按平台分层（`monitor/registry.py`）
- 完整率计算、缺失检测、补采判断均通过 `platform` 字段区分
- 数据流：爬虫 → `monitor.record()` → SQLite → FastAPI (8777) → Vue3 前端

### 新账号自动全量采集

`CollectionTracker` 追踪已完成全量采集的账号（`resource/collection_tracker.json`）：
- `--mode once/scheduler`：新账号自动全量，老账号增量
- `--mode full`：强制所有账号全量
- 首次部署运行 `python scripts/init_tracker.py` 初始化现有账号

## 必须遵守的规则

### 规则一：LiveCrawler 必须传入 group_name 和 batch_id

所有调用 `LiveCrawler` 的地方必须从 account 对象中取出 `group_name` 并传入，同时传入 `batch_id`。

当前调用点：`main.py:run_once()`、`main.py:crawl_single_account()`、`scheduler/task_scheduler.py:execute_crawl_task()`。

### 规则二：Shopee 特殊规则

详见 `../.claude/references/shopee-special-rules.md`。

### 规则三：`result['success'] = self.login_status` 不得改回 True

`base.py:start_crawl()` 中 success 标记等于 login_status，保证登出账号不被误计为成功。

### 规则四：监控系统是"旁观者"

监控只记录事件，不干预采集逻辑。所有监控代码必须用 try/except 包裹，失败只记日志不抛出异常。

### 规则五：登出恢复流程

详见 `../.claude/references/collection-mode-rules.md`。

### 规则六：补采 HTTP 请求规格

详见 `../.claude/references/recrawl-http-spec.md`。

## 监控 API 类型扩展

`API_TYPE_REGISTRY` 按平台分层，新增 API 类型只需在对应平台层级添加 `{'key': '...', 'label': '...'}` 即可。

完整率计算通过 `get_room_types_for_completion()` 返回参与计算的 room 级 API 类型。

## 新增平台爬虫步骤

1. 继承 `BaseLiveCrawler`，实现三个抽象方法
2. 在 `crawlers/browser/live_crawler.py` 的 `PLATFORM_CRAWLERS` 中注册
3. 在 `core/config_base.py` 的 `PLATFORM_CONFIG` 中添加平台配置
4. 更新本文档的规则章节

## 测试

使用 pytest 框架，测试文件位于 `tests/` 目录。运行单个测试：`python -m pytest tests/monitor/test_classifier.py -v`

## 注意事项

- 并发采集（`--workers N`）仅在 `--mode full` 时生效
- `crawl_single_account` 必须定义在模块顶层（Windows spawn 要求），且不要在其中操作 `CollectionTracker`
- 运行时数据（`collection_tracker.json`、`monitor.db`）不提交 git
