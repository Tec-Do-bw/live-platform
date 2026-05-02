# Design: BaseHttpCrawler 基类与共享服务抽取

## Context

当前 live_dp 采集架构中，所有平台（TikTok、Shopee）都继承自 `BaseLiveCrawler`，该基类深度绑定浏览器生命周期（AdsPower + DrissionPage）。核心流程包括：
1. 开启浏览器实例
2. 设置网络监听拦截 API 响应
3. 访问页面触发请求
4. 被动拦截响应并上报

这种模式对于需要 JS 渲染的平台（TikTok、Shopee）是必要的，但对于可通过纯 HTTP 请求采集的平台（Lazada）则过于重量级。

Phase 1 已完成 Cookie 基础设施（cookies 表 + CookieManager），现在需要：
1. 建立独立的 HTTP 采集基类，不依赖浏览器
2. 抽取 BaseLiveCrawler 中的共享逻辑（数据上报、登录回调），供两种采集模式共用
3. 保持现有浏览器采集器无回归

## Goals / Non-Goals

**Goals:**
- 定义 BaseHttpCrawler 抽象基类，提供标准 HTTP 采集流程
- 支持多阶段采集（如 Lazada 直播详情依赖直播列表）
- 抽取数据上报和登录回调为共享模块，避免代码重复
- 集成现有 downloader（never_primp）和 monitor 监控系统
- 在工厂类中支持 HTTP 和浏览器采集双轨路由

**Non-Goals:**
- 不实现具体平台采集逻辑（Lazada 实现在 Phase 3）
- 不修改现有浏览器采集器的核心流程
- 不改变数据上报格式或监控钩子接口
- httpcrawler不实现send_login_callback发送登录回调

## Decisions

### 决策 1: BaseHttpCrawler 不继承 BaseLiveCrawler

**选择**: 创建独立的 BaseHttpCrawler 基类，与 BaseLiveCrawler 平级

**原因**:
- BaseLiveCrawler 包含大量浏览器相关方法（get_driver、listen_api、visit_page_and_collect）
- 继承会引入不必要的依赖（AdsPower、DrissionPage）
- 两种采集模式的核心流程差异大（主动请求 vs 被动拦截）

**替代方案**: 让 BaseHttpCrawler 继承 BaseLiveCrawler 并覆写所有浏览器方法
- 被拒绝原因：违反里氏替换原则，子类无法正确替换父类

### 决策 2: 抽取共享模块到 services/

**选择**: 将 `send_api_request` 和 `send_login_callback` 抽取为独立模块

**原因**:
- `send_api_request` 包含 150+ 行复杂逻辑（重试、落盘、登录事件写入）
- `send_login_callback` 包含回调逻辑和登出恢复检测
- 多个模块需要这些功能，代码复制会导致维护困难

**实现方式**:
```python
# services/data_reporter.py
def send_api_request(message: dict, config: dict) -> bool:
    """数据上报共享逻辑"""
    # 原 BaseLiveCrawler.send_api_request 的实现

# services/login_callback.py  
def send_login_callback(account_id: str, platform: str, status: str, reason: str) -> bool:
    """登录回调共享逻辑"""
    # 原 BaseLiveCrawler.send_login_callback 的实现
```

**调用方说明**：
- `send_api_request`: BaseLiveCrawler 和 BaseHttpCrawler 都调用
- `send_login_callback`:
  - 浏览器采集器（BaseLiveCrawler）调用（现有行为）
  - HTTP 采集器（BaseHttpCrawler）不调用 — 不判断登录状态，不发送登录回调
  - 养号服务调用（未来）— 负责 Cookie 管理和登录态判定
- HTTP 采集器通过 `resolve_collection_mode()` 读取养号服务记录的登录态事件，判断全量/增量

### 决策 3: 多阶段采集通过 build_next_tasks 钩子实现

**选择**: 基类提供 `build_next_tasks(phase, results)` 可选钩子，默认返回空列表（单阶段）

**原因**:
- Lazada 直播详情采集依赖直播列表的 liveUuid（阶段 1 → 阶段 2）
- 不是所有平台都需要多阶段，单阶段应该是默认行为
- 子类按需覆写，保持灵活性

**流程**:
```
start_crawl():
    cookies = cookie_manager.get_cookies(account_id)
    is_full, reason = resolve_collection_mode(...)  # 读取养号服务记录的登录态事件
    phase = 1
    tasks = build_tasks(cookies, is_full)  # 第一阶段
    while tasks:
        results = downloader.run(tasks)
        parse_and_report(results)
        phase += 1
        tasks = build_next_tasks(phase, results)  # 下一阶段
```

### 决策 4: Cookie 通过 Task.headers 传递

**选择**: 在每个 Task 的 headers 中手动拼接 `Cookie: k1=v1; k2=v2`

**原因**:
- Downloader 的 Task.headers 会与 Client 级别 headers 合并（Task 优先）
- Lazada 有两个独立端口（sellercenter / live），不同 Task 使用不同 Cookie
- 手动拼接提供最大灵活性

**实现**:
```python
def _cookie_header(self, cookies: dict) -> str:
    return '; '.join(f'{k}={v}' for k, v in cookies.items())

tasks = [
    Task(
        url="https://sellercenter.lazada.co.th/api/...",
        headers={'Cookie': self._cookie_header(self.sc_cookies)},
        ...
    ),
]
```

### 决策 5: 工厂类双轨路由

**选择**: 在 LiveCrawler 工厂类中新增 HTTP_CRAWLERS 字典，优先检查 HTTP 爬虫

**原因**:
- main.py 统一调度，无需感知采集模式差异
- 未来可能有平台同时支持浏览器和 HTTP 模式（如 Shopee 迁移）
- 优先检查 HTTP 爬虫，因为 HTTP 模式性能更好

**实现**:
```python
class LiveCrawler:
    PLATFORM_CRAWLERS = {'tiktok': ..., 'shopee': ...}  # 浏览器
    HTTP_CRAWLERS = {'lazada': LazadaHttpCrawler}       # HTTP
    
    def __new__(cls, platform, ...):
        if platform in cls.HTTP_CRAWLERS:
            return cls.HTTP_CRAWLERS[platform](...)
        elif platform in cls.PLATFORM_CRAWLERS:
            return cls.PLATFORM_CRAWLERS[platform](...)
```

## Risks / Trade-offs

### 风险 1: 共享模块抽取可能引入回归

**风险**: 修改 BaseLiveCrawler 调用共享模块时，可能破坏现有浏览器采集器

**缓解措施**:
- 共享模块保持与原实现完全一致（复制粘贴 + 参数化）
- 运行现有浏览器采集测试验证无回归：`pytest tests/crawlers/browser/ -v`
- 先实现共享模块和单元测试，再修改 BaseLiveCrawler

### 风险 2: 多阶段采集可能导致复杂度增加

**风险**: build_next_tasks 钩子可能被滥用，导致采集流程难以理解

**缓解措施**:
- 文档明确说明：仅用于阶段间有数据依赖的场景（如列表 → 详情）
- 基类默认返回空列表，单阶段是默认行为
- 在 BaseHttpCrawler 的 docstring 中提供清晰示例

### 风险 3: Cookie 失效处理策略

采集器不负责 Cookie 有效性预判和登录态管理，只管采集：

**缓解措施**:
- 采集器从 CookieManager 获取 Cookie，不做有效性预检
- 采集器不判断登录状态，不上报养号服务
- Cookie 管理、登录态判定、send_login_callback 全部由养号服务负责
- 下次采集时，采集器通过 resolve_collection_mode() 读取登录态事件，判断全量/增量
- 多端口策略：允许部分端口继续采集，仅失效端口的任务跳过（由 CookieManager 返回的 Cookie 字典决定）

### Trade-off: 不复用 BaseLiveCrawler 的监控逻辑

**选择**: BaseHttpCrawler 直接调用 monitor API，不继承 BaseLiveCrawler

**代价**: 监控钩子调用代码有少量重复（start_account、record、finish_account）

**收益**: 完全解耦，HTTP 采集器不依赖浏览器相关代码

## Migration Plan

### 部署步骤

1. **Phase 2.1**: 实现共享模块
   - 创建 `services/data_reporter.py` 和 `services/login_callback.py`
   - 单元测试验证功能正确

2. **Phase 2.2**: 修改 BaseLiveCrawler
   - 将 `send_api_request` 和 `send_login_callback` 改为调用共享模块
   - 运行 `pytest tests/crawlers/browser/ -v` 验证无回归

3. **Phase 2.3**: 实现 BaseHttpCrawler
   - 创建 `crawlers/http/base.py`
   - 单元测试验证标准流程和多阶段支持

4. **Phase 2.4**: 修改工厂类
   - 在 `crawlers/factory.py` 中新增 HTTP_CRAWLERS 路由
   - 单元测试验证路由逻辑

### 回滚策略

- 如果共享模块抽取导致回归：
  - 回滚 BaseLiveCrawler 修改，恢复原 send_api_request / send_login_callback 实现
  - BaseHttpCrawler 直接复制这些方法（临时方案）
  
- 如果工厂类路由有问题：
  - 回滚 factory.py，HTTP 爬虫暂时不通过工厂类创建
  - 在 main.py 中临时添加 if platform == 'lazada' 分支

## Open Questions

1. ~~Cookie 有效性验证~~: 已决定 — 采集器不管 Cookie 有效性和登录态，由养号服务负责。采集器只管拿 Cookie 采集数据。

2. **监控钩子的 api_type 命名**: Lazada 的 api_type 如何命名？
   - 建议：`lazada_live_list`、`lazada_live_detail`、`lazada_daily_overview` 等
   - 待 Phase 3 实现时在 monitor/registry.py 中注册

3. **多阶段采集的错误处理**: 已决定 —
   - 阶段 N 某个任务重试 M 次仍失败 → 发送机器人告警（采集 ID + 异常信息）
   - 失败任务标记跳过，用成功结果继续下一阶段
   - 阶段完全失败（0 个成功结果）→ 终止采集 + 机器人告警
