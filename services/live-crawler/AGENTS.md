# AGENTS.md — AI 编码注意事项

本文件记录项目中容易被 AI 遗漏的关键约定，修改相关模块时必须同步检查以下规则。

---

## 规则一：LiveCrawler 必须传入 group_name 和 batch_id

`LiveCrawler` 工厂类的签名为：

```python
LiveCrawler(platform, browser_id, full_collection=False, group_name='', batch_id='')
```

`group_name` 用于 Shopee 平台根据 AdsPower 分组名自动识别国家域名（`com.my` / `co.id` / `co.th` / `com.sg` 等）。
`batch_id` 用于采集监控系统标识当前采集批次，格式为 `"2026-03-06_20:00"`。

**所有调用 `LiveCrawler` 的地方，都必须从 account 对象中取出 `group_name` 并传入，同时传入 `batch_id`：**

```python
group_name = account.get('group_name', '') if isinstance(account, dict) else ''
crawler = LiveCrawler(platform=platform, browser_id=user_id,
                      full_collection=full_collection, group_name=group_name,
                      batch_id=batch_id)
```

### 当前所有调用点（新增调用时必须同步更新此列表）

| 文件 | 位置 | 状态 |
|------|------|------|
| `main.py` | `run_once()` 串行循环内 | ✓ 已传入 |
| `main.py` | `crawl_single_account()` 并发工作函数 | ✓ 已传入 |
| `scheduler/task_scheduler.py` | `execute_crawl_task()` 串行循环内 | ✓ 已传入 |

---

## 规则二：Shopee page_urls 配置维护

`core/config_base.py` 中 `PLATFORM_CONFIG['shopee']['page_urls']` 统一使用 `shopee.com.my` 作为模板域名。

`ShopeeLiveCrawler.__init__` 会在运行时深拷贝配置并将 `com.my` 替换为对应国家域名，**不要在配置文件里直接写其他国家域名**。

---

## 规则三：登录状态影响 success 标记

`base.py` `start_crawl()` 中：

```python
result['success'] = self.login_status
```

`login_status` 默认 `True`，检测到账号登出后置 `False`。
**不要将此行改回 `result['success'] = True`**，否则登出账号会被错误计为采集成功。

---

## 规则四：CollectionTracker 标记操作仅在主进程中执行

`CollectionTracker`（`core/collection_tracker.py`）用于追踪已完成全量采集的账号。

**关键约束：**
- `mark_full_collected()` 和 `mark_full_collected_batch()` 只能在主进程中调用
- **不要在 `crawl_single_account()` 子进程函数中操作 tracker**（子进程各自有独立的内存副本，会导致数据丢失）
- 并发模式（`ProcessPoolExecutor`）下，在 `as_completed` 循环中由主进程统一标记

**标记时机：全量采集成功后才标记，失败不标记（确保下次重试）。**

### 当前标记调用点（新增调用时必须同步更新此列表）

| 文件 | 位置 | 说明 |
|------|------|------|
| `main.py` | `run_once()` 串行模式循环内 | 新账号全量采集成功后标记 |
| `main.py` | `run_once()` 并发模式 `as_completed` 循环内 | `--mode full` 成功后标记 |
| `scheduler/task_scheduler.py` | `execute_crawl_task()` 串行循环内 | 新账号全量采集成功后标记 |
| `scripts/init_tracker.py` | `main()` | 批量初始化标记（仅首次部署） |

---

## 规则五：监控钩子不阻塞爬虫主流程

`monitor/tracker.py` 中所有数据库写入操作都用 try/except 包裹，异常只记日志不抛出。**不要移除这些异常保护**，监控系统故障不应影响正常采集流程。

**监控钩子调用模式**：

```python
if self.batch_id:
    from monitor import get_monitor
    get_monitor().record(self.batch_id, self.browser_id, 'api_type', ...)
```

- 必须先检查 `self.batch_id` 非空（无 batch_id 时跳过监控）
- 使用延迟导入 `from monitor import get_monitor` 避免循环依赖

### 当前监控钩子调用点

| 文件 | 位置 | 记录内容 |
|------|------|----------|
| `spiders/tiktok.py` | `_handle_tiktok_live_list()` | `record_rooms()` 记录直播间列表及 GMV 数据 |
| `spiders/tiktok.py` | `_fetch_trend_chart_via_js()` 成功时 | `trend_gmv` + `trend_stats` 成功 |
| `spiders/tiktok.py` | `_fetch_trend_chart_via_js()` 失败时 | `trend_gmv` + `trend_stats` 失败 |
| `spiders/tiktok.py` | `visit_page_and_collect()` | `replay_info` 成功 |
| `spiders/base.py` | `start_crawl()` 开始 | `start_account()` |
| `spiders/base.py` | `start_crawl()` finally | `finish_account()` |
| `main.py` | `run_once()` | `start_batch()` / `finish_batch()` |
| `scheduler/task_scheduler.py` | `execute_crawl_task()` | `start_batch()` / `finish_batch()` |

---

## 规则六：监控 API 类型扩展流程

在 `monitor/registry.py` 的 `API_TYPE_REGISTRY` 中取消注释即可启用新的 API 类型。扩展步骤：

1. 取消 `registry.py` 中对应 api_type 的注释
2. 确认 `classifier.py` 中已有对应的分类规则（URL 匹配 / stats_types 判断）
3. 在爬虫代码合适位置添加 `monitor.record(batch_id, account_id, 'new_api_type', ...)` 调用
4. 更新本文件「规则五」的钩子调用点表格
