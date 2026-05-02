# Change: Lazada HTTP 采集系统 - Phase 2: BaseHttpCrawler 基类

## Why

当前 live_dp 采集架构完全依赖 AdsPower + DrissionPage 浏览器自动化，所有平台（TikTok、Shopee）都需要浏览器实例运行。这导致资源开销大、请求频率无法灵活控制、新平台接入困难。Lazada 可通过纯 HTTP 请求采集，不需要浏览器渲染，是建立独立 HTTP 采集体系的理想试点。

Phase 1 已完成 Cookie 基础设施（cookies 表 + CookieManager + Cookie API），现在需要建立 HTTP 采集的标准流程和基类，为 Lazada 及未来其他 HTTP 平台提供统一抽象。

## What Changes

- 新增 `crawlers/http/base.py` - BaseHttpCrawler 抽象基类
  - 定义 `start_crawl()` 标准流程（支持多阶段采集）
  - 定义 `build_tasks()` / `build_next_tasks()` 抽象方法（子类实现）
  - 定义 `parse_response()` / `check_login_from_response()` 抽象方法
  - 集成 CookieManager 读取 Cookie
  - 集成 downloader 发送 HTTP 请求
  - 集成 monitor 监控钩子
- 抽取共享模块到 `services/`
  - `services/data_reporter.py` - 从 BaseLiveCrawler.send_api_request 抽取（150+ 行复杂逻辑：重试、落盘、登录事件写入）
  - `services/login_callback.py` - 从 BaseLiveCrawler.send_login_callback 抽取（回调逻辑 + 登出恢复检测），供浏览器采集器和未来养号服务共用
- 修改 `crawlers/browser/base.py` - BaseLiveCrawler 的 send_api_request 改为调用 services/ 共享模块（send_login_callback 保持原有实现）
- 修改 `crawlers/factory.py` - 新增 HTTP_CRAWLERS 路由，支持 HTTP 和浏览器采集双轨

## Capabilities

### New Capabilities
- `http-crawler-base`: BaseHttpCrawler 基类定义，包含标准采集流程、多阶段支持、监控集成
- `shared-services`: 数据上报和登录回调共享模块，供浏览器和 HTTP 采集器共用

### Modified Capabilities
无（不修改现有规格，仅新增 HTTP 采集能力）

## Impact

- 受影响代码：
  - `crawlers/browser/base.py` - BaseLiveCrawler 重构为调用共享模块
  - `crawlers/factory.py` - 新增 HTTP 爬虫路由
  - 新增 `crawlers/http/` 目录
  - 新增 `services/data_reporter.py` 和 `services/login_callback.py`
- 受影响测试：
  - 现有浏览器采集测试需验证无回归（`tests/crawlers/browser/`）
  - 新增 HTTP 基类单元测试（`tests/crawlers/http/test_base.py`）
- 依赖：
  - 依赖 Phase 1 的 CookieManager 和 cookies 表
  - 依赖现有 downloader 模块（never_primp）
  - 依赖现有 monitor 监控系统
