## ADDED Requirements

### Requirement: BaseHttpCrawler 标准采集流程
BaseHttpCrawler SHALL 提供 `start_crawl()` 方法，实现以下标准流程：
1. 通过 CookieManager 获取各端口的 Cookie
2. 调用 `resolve_collection_mode()` 判断全量/增量（读取养号服务记录的登录态事件）
3. 调用 `build_tasks(cookies, is_full)` 构造第一阶段采集任务
4. 通过 downloader 批量执行 HTTP 请求
5. 解析响应并上报数据
6. 调用 `build_next_tasks(phase, results)` 检查是否有后续阶段
7. 重复步骤 4-6 直到无后续阶段
8. 记录监控数据

**职责边界约束**：
- BaseHttpCrawler SHALL NOT 判断登录状态（不实现 check_login_from_response）
- BaseHttpCrawler SHALL NOT 发送 send_login_callback
- BaseHttpCrawler SHALL NOT 上报养号服务
- Cookie 管理、登录态判定、登录回调完全由养号服务负责

#### Scenario: 单阶段采集成功
- **WHEN** Cookie 存在且 build_tasks 返回任务列表，build_next_tasks 返回空列表
- **THEN** 系统 SHALL 执行一轮请求、解析上报、记录监控

#### Scenario: 多阶段采集成功
- **WHEN** Cookie 存在且 build_next_tasks 在 phase=2 时返回非空任务列表
- **THEN** 系统 SHALL 依次执行阶段 1 和阶段 2 的请求，每阶段都解析上报

#### Scenario: Cookie 不存在时跳过采集
- **WHEN** CookieManager 返回的 Cookie 为 None（账号无 Cookie 记录）
- **THEN** 系统 SHALL 跳过采集，记录日志

#### Scenario: 多阶段采集部分失败告警
- **WHEN** 某阶段中某个任务重试达到上限仍失败
- **THEN** 系统 SHALL 发送机器人告警（包含采集 ID、阶段号、异常信息），失败任务跳过，用成功结果继续下一阶段

#### Scenario: 多阶段采集完全失败终止
- **WHEN** 某阶段所有任务均失败（0 个成功结果）
- **THEN** 系统 SHALL 终止采集，发送机器人告警，调用 finish_account(status='error')

### Requirement: BaseHttpCrawler 抽象方法定义
BaseHttpCrawler SHALL 定义以下抽象方法，子类 MUST 实现：
- `get_platform_name() -> str`: 返回平台标识
- `build_tasks(cookies: dict, is_full: bool) -> list[Task]`: 构造第一阶段采集任务（is_full 标识全量/增量）
- `parse_response(result: DownloadResult) -> dict | None`: 解析单个响应

BaseHttpCrawler SHALL NOT 定义 `check_login_from_response` 方法（登录态判定由养号服务负责）。

BaseHttpCrawler SHALL 提供以下可选覆写方法：
- `build_next_tasks(phase: int, results: list) -> list[Task]`: 多阶段采集钩子，默认返回空列表

#### Scenario: 子类实现所有抽象方法
- **WHEN** 子类实现了所有抽象方法
- **THEN** 子类 SHALL 能够通过 start_crawl() 执行完整采集流程

#### Scenario: 子类未实现抽象方法
- **WHEN** 子类未实现某个抽象方法
- **THEN** 实例化时 SHALL 抛出 TypeError

### Requirement: BaseHttpCrawler 监控集成
BaseHttpCrawler SHALL 在采集流程中调用 monitor 监控钩子：
- 采集开始时调用 `monitor.start_account()`
- 每个成功响应调用 `monitor.record()`
- 采集结束时调用 `monitor.finish_account()`

#### Scenario: 采集成功时记录监控
- **WHEN** 采集流程正常完成
- **THEN** 系统 SHALL 调用 start_account、record（每个成功响应）、finish_account(status='success')

#### Scenario: 采集失败时记录监控
- **WHEN** 采集流程因异常终止
- **THEN** 系统 SHALL 调用 finish_account(status='error')

### Requirement: BaseHttpCrawler Cookie 传递
BaseHttpCrawler SHALL 提供 `_cookie_header(cookies: dict) -> str` 方法，将 Cookie 字典拼接为 HTTP Cookie 头格式（`k1=v1; k2=v2`）。子类在 build_tasks 中通过 Task.headers 传递 Cookie。

#### Scenario: 多端口 Cookie 传递
- **WHEN** Lazada 账号有 sellercenter 和 live 两个端口的 Cookie
- **THEN** 不同端口的 Task SHALL 使用各自端口的 Cookie 头

### Requirement: 工厂类 HTTP 爬虫路由
LiveCrawler 工厂类 SHALL 新增 HTTP_CRAWLERS 字典，支持 HTTP 和浏览器采集双轨路由。当 platform 在 HTTP_CRAWLERS 中时，SHALL 创建对应的 HTTP 爬虫实例。

#### Scenario: 创建 HTTP 爬虫
- **WHEN** platform='lazada' 且 lazada 在 HTTP_CRAWLERS 中
- **THEN** 工厂类 SHALL 返回 LazadaHttpCrawler 实例

#### Scenario: 创建浏览器爬虫
- **WHEN** platform='tiktok' 且 tiktok 不在 HTTP_CRAWLERS 中
- **THEN** 工厂类 SHALL 返回 TikTokLiveCrawler 实例（现有行为不变）

#### Scenario: 获取所有支持平台
- **WHEN** 调用 get_supported_platforms()
- **THEN** SHALL 返回浏览器和 HTTP 平台的合集
