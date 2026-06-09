# CLAUDE.md

> 通用编码规范、工作流规则见根 `CLAUDE.md`。项目结构、启动命令、运行模式、动态账号管理、测试见 `README.md`。本文仅记录约束与设计决策。
>
> 业务规则已迁移到 `.claude/rules/`,由 `paths` frontmatter 自动触发,编辑对应代码时会被自动加载到上下文,无需手动 @import;以下"详见"链接仅供人类阅读时跳转。

## 项目定位

基于 DrissionPage 和 HTTP 双轨采集架构的直播数据采集系统，支持 TikTok、Shopee（浏览器）、Lazada（HTTP）多平台、多账号并发。

## 必须遵守的规则

### 规则一：LiveCrawler 必须传入 group_name 和 batch_id

所有调用 `LiveCrawler` 的地方必须从 account 对象取出 `group_name` 并传入，同时传入 `batch_id`。

当前调用点：`main.py:run_once()`、`main.py:crawl_single_account()`、`scheduler/task_scheduler.py:execute_crawl_task()`。

### 规则二：Shopee 特殊规则

详见 `../../.claude/rules/shopee-special-rules.md`。

### 规则三：`result['success'] = self.login_status` 不得改回 True

`crawlers/browser/base.py:start_crawl()` 中 `success` 标记**必须**等于 `login_status`，保证登出账号不被误计为成功。

### 规则四：登出恢复流程

详见 `../../.claude/rules/collection-mode-rules.md`、`../../.claude/rules/logout-recovery-flow.md`。

### 规则五：AdsPower API 调用必须通过统一客户端

所有 AdsPower API 调用**必须**通过 `utils/adspower_client.py` 的 `AdsPowerClient` 发起，**禁止**裸用 `requests.get/post` 直接请求 AdsPower。

- 工厂函数 `get_adspower_client()` 从 Settings 读取 base_url；自定义 base_url 用 `AdsPowerClient(base_url=url)`
- 内置限流重试（识别 `code=-1` + msg 含 "too many"/"rate"，指数退避 5 次）与连接异常重试
- 调用方只需处理 `AdsPowerRateLimitError`（重试耗尽）与 `AdsPowerApiError`（业务错误）

### 规则六：TikTok 采集时间窗口

详见 `../../.claude/rules/tiktok-collection-time.md`。

## 设计决策

### 新账号自动全量采集

`CollectionTracker`（`resource/collection_tracker.json`）追踪已完成全量的账号：
- `--mode once/scheduler`：新账号自动全量，老账号增量
- `--mode full`：强制所有账号全量
- 首次部署运行 `python scripts/init_tracker.py` 初始化现有账号

### 多进程入口约束

- 并发采集（`--workers N`）仅在 `--mode full` 时生效
- `crawl_single_account` **必须**定义在模块顶层（Windows spawn 要求）
- **不要**在 `crawl_single_account` 内操作 `CollectionTracker`——子进程各自有独立内存副本，标记不会回传主进程，会导致追踪数据丢失。并发模式下应在主进程 `as_completed` 循环中统一标记，且仅在全量采集成功后标记（失败不标记以便下次重试）

### Cookie 与登录状态保留表

`monitor/__init__.py` 暂时保留 Cookie 与登录状态表连接能力，兼容 Lazada Cookie 链路与 `LoginStatusManager`。不要新增采集监控面板、批次完整率或补采相关能力；Cookie 持久化后续随 `account_credentials` 迁移统一处理。

### 运行时数据不入 git

`resource/collection_tracker.json` 为运行时数据，禁止提交。

### Shopee 跨境店 HTTP 切换（2026-06-09）

跨境店切换店铺改用 HTTP API 替代浏览器点击，避免前端控件异常导致的切换失败：

- **`_switch_to_shop`**：入口，根据 `is_cross_border` 分流跨境/本土切换逻辑
- **`_switch_to_shop_by_http`**（跨境店）：
  1. POST `switch_merchant_shop/` 切换店铺
  2. POST `set_language/` 设置语言（必需）
  3. GET `get_session/` 校验 `current_shop_id` 是否匹配
  4. HTTP 403 触发 `cookie_expired` 回调
- **`_switch_to_shop_by_browser`**（本土店）：保持原浏览器点击逻辑（导航到店铺列表页 → 点击 Details）
- **`_get_shop_region_from_list`**：查询目标店铺所在 `region`（switch API 必需参数）

**测试覆盖**：`tests/crawlers/browser/test_shopee_switch_to_shop.py`（5 个用例）
