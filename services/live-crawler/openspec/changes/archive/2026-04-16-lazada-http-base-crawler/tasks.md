## 1. 共享服务模块抽取

- [x] 1.1 创建 `services/data_reporter.py`，从 BaseLiveCrawler.send_api_request 抽取逻辑（包括重试、落盘、登录事件写入）
- [x] 1.2 创建 `services/login_callback.py`，从 BaseLiveCrawler.send_login_callback 抽取逻辑（包括回调和登出恢复检测）
- [x] 1.3 为共享模块编写单元测试：`tests/services/test_data_reporter.py` 和 `tests/services/test_login_callback.py`
- [x] 1.4 修改 `crawlers/browser/base.py` 中的 BaseLiveCrawler，将 send_api_request 改为调用共享模块（send_login_callback 保持原有实现，待后续统一迁移）
- [x] 1.5 运行现有浏览器采集测试验证无回归：`pytest tests/crawlers/browser/ -v`

## 2. BaseHttpCrawler 基类实现

- [x] 2.1 创建 `crawlers/http/__init__.py`
- [x] 2.2 创建 `crawlers/http/base.py`，实现 BaseHttpCrawler 抽象基类
- [x] 2.3 实现 `start_crawl()` 标准流程（Cookie 获取、多阶段循环、监控集成）
- [x] 2.4 实现抽象方法定义：`get_platform_name()`、`build_tasks(cookies, is_full)`、`parse_response()`（不实现 check_login_from_response，登录态由养号服务负责）
- [x] 2.5 实现可选钩子：`build_next_tasks(phase, results)` 默认返回空列表
- [x] 2.6 实现辅助方法：`_cookie_header()`、`format_message()`、`send_request()`（不实现 send_login_callback，登录回调由养号服务负责）
- [x] 2.7 集成 CookieManager 读取 Cookie
- [x] 2.8 集成 downloader 发送 HTTP 请求
- [x] 2.9 集成 monitor 监控钩子（start_account、record、finish_account）
- [x] 2.10 集成 resolve_collection_mode() 判断全量/增量
- [x] 2.11 实现采集异常时的机器人告警通知（任务重试失败、阶段完全失败）

## 3. 工厂类路由扩展

- [x] 3.1 修改 `crawlers/factory.py`，新增 HTTP_CRAWLERS 字典
- [x] 3.2 修改 LiveCrawler.__new__()，优先检查 HTTP_CRAWLERS，再检查 PLATFORM_CRAWLERS
- [x] 3.3 新增 `get_supported_platforms()` 类方法，返回浏览器和 HTTP 平台的合集
- [x] 3.4 为工厂类路由编写单元测试：`tests/crawlers/test_factory.py`

## 4. 单元测试

- [x] 4.1 创建 `tests/crawlers/http/__init__.py`
- [x] 4.2 创建 `tests/crawlers/http/test_base.py`，测试 BaseHttpCrawler 标准流程
- [x] 4.3 测试单阶段采集场景（build_next_tasks 返回空列表）
- [x] 4.4 测试多阶段采集场景（build_next_tasks 返回非空任务列表）
- [x] 4.5 测试 Cookie 不存在时跳过采集场景
- [x] 4.6 测试监控钩子调用（start_account、record、finish_account）
- [x] 4.7 测试抽象方法未实现时抛出 TypeError
- [x] 4.8 运行所有测试验证：`pytest tests/crawlers/http/test_base.py -v`

## 5. 验收

- [x] 5.1 运行所有单元测试：`pytest tests/crawlers/http/ -v`
- [x] 5.2 运行浏览器采集测试验证无回归：`pytest tests/crawlers/browser/ -v`
- [x] 5.3 检查代码覆盖率，确保核心流程被测试覆盖
- [x] 5.4 更新 `live_dp/CLAUDE.md` 架构章节，记录新增的 crawlers/http/ 和 services/ 模块
