# CLAUDE.md

> 通用编码规范、工作流规则见根 `CLAUDE.md`。项目结构、启动命令、运行模式、监控面板、动态账号管理、测试见 `README.md`。本文仅记录约束与设计决策。

## 项目定位

基于 DrissionPage 和 HTTP 双轨采集架构的直播数据采集系统，支持 TikTok、Shopee（浏览器）、Lazada（HTTP）多平台、多账号并发。

## 必须遵守的规则

### 规则一：LiveCrawler 必须传入 group_name 和 batch_id

所有调用 `LiveCrawler` 的地方必须从 account 对象取出 `group_name` 并传入，同时传入 `batch_id`。

当前调用点：`main.py:run_once()`、`main.py:crawl_single_account()`、`scheduler/task_scheduler.py:execute_crawl_task()`。

### 规则二：Shopee 特殊规则

详见 `../../.claude/references/shopee-special-rules.md`。

### 规则三：`result['success'] = self.login_status` 不得改回 True

`crawlers/browser/base.py:start_crawl()` 中 `success` 标记**必须**等于 `login_status`，保证登出账号不被误计为成功。

### 规则四：监控系统是"旁观者"

监控只记录事件，不干预采集逻辑。所有监控代码**必须**用 try/except 包裹，失败只记日志不抛出异常。

### 规则五：登出恢复流程

详见 `../../.claude/references/collection-mode-rules.md`、`../../.claude/references/logout-recovery-flow.md`。

### 规则六：补采 HTTP 请求规格

详见 `../../.claude/references/recrawl-http-spec.md`。

### 规则七：AdsPower API 调用必须通过统一客户端

所有 AdsPower API 调用**必须**通过 `utils/adspower_client.py` 的 `AdsPowerClient` 发起，**禁止**裸用 `requests.get/post` 直接请求 AdsPower。

- 工厂函数 `get_adspower_client()` 从 Settings 读取 base_url；自定义 base_url 用 `AdsPowerClient(base_url=url)`
- 内置限流重试（识别 `code=-1` + msg 含 "too many"/"rate"，指数退避 5 次）与连接异常重试
- 调用方只需处理 `AdsPowerRateLimitError`（重试耗尽）与 `AdsPowerApiError`（业务错误）

### 规则八：TikTok 采集时间窗口

详见 `../../.claude/references/tiktok-collection-time.md`。

## 设计决策

### 平台识别基于 `account_sessions.platform` 字段

监控系统的平台识别**必须**通过 `account_sessions.platform` 字段，**禁止**从 `group_name` 猜测。完整率计算、缺失检测、补采判断均按 `platform` 字段区分。

### 新账号自动全量采集

`CollectionTracker`（`resource/collection_tracker.json`）追踪已完成全量的账号：
- `--mode once/scheduler`：新账号自动全量，老账号增量
- `--mode full`：强制所有账号全量
- 首次部署运行 `python scripts/init_tracker.py` 初始化现有账号

### 多进程入口约束

- 并发采集（`--workers N`）仅在 `--mode full` 时生效
- `crawl_single_account` **必须**定义在模块顶层（Windows spawn 要求）
- **不要**在 `crawl_single_account` 内操作 `CollectionTracker`

### 运行时数据不入 git

`resource/collection_tracker.json`、`monitor/data/monitor.db` 为运行时数据，禁止提交。
