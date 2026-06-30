---
paths:
  - "services/live-crawler/crawlers/browser/base.py"
  - "services/live-crawler/crawlers/http/tiktok/adapter.py"
  - "services/live-crawler/scheduler/task_scheduler.py"
  - "services/live-crawler/monitor/login_status_manager.py"
  - "services/live-crawler/services/login_callback.py"
  - "services/live-crawler/main.py"
  - "services/live-crawler/core/collection_mode.py"
---

# 登出恢复流程详解

## 背景

账号登出后需要重新登录并恢复数据采集。系统设计了两条恢复路径：即时恢复（2 轮完成）和 Fallback 恢复（3 轮完成），确保登出账号能可靠恢复。

## 即时恢复路径（2 轮）

### 时序图
```
轮次 1: 账号登出
  └─ send_login_callback("error", reason="timeout")
  └─ 写入 logout 事件

[业务通过 adspower-server 投屏登录]

轮次 2: 下一轮采集
  └─ send_login_callback("success") 检测到 logout→login 切换
  └─ 当轮即时设置 full_collection=True
  └─ 执行全量采集
  └─ 写入 full_recovery_started / full_recovery_succeeded 事件
```

### 实现要点

1. **BaseLiveCrawler.send_login_callback**（浏览器版）
   - 在写入 login 事件前调用 `get_account_status()`
   - 若当前状态为 logout，设置 `self.full_collection = True` 和 `self._login_recovery = True`

   **TikTok HTTP 版**（`crawlers/http/tiktok/adapter.py`）：`setup_session` 验证通过后调 `send_login_callback("success")`，读返回的 `callback.get("login_recovery")`，为真则 `self._login_recovery = True` + `self.full_collection = True`（adapter.py:87-89）。判活与回调契约见 [[tiktok-http-lifecycle]]。

2. **main.py / task_scheduler.py**
   - 在 `start_crawl()` 后检测 `result['login_recovery']`
   - 补写 `full_recovery_started` / `full_recovery_succeeded` 事件

3. **recovery_events.py**
   - `mode_label` 守卫同时接受 `'登出恢复全量'` 和 `'登出即时恢复全量'`

## Fallback 恢复路径（3 轮）

### 时序图
```
轮次 1: 账号登出
  └─ 写入 logout 事件

[业务通过 adspower-server 投屏登录]

轮次 2: 下一轮采集
  └─ 即时恢复未触发（如进程崩溃）
  └─ 写入 login 事件

轮次 3: 再下一轮采集
  └─ resolve_collection_mode() 读到 [login, logout] 序列
  └─ 返回 (True, '登出恢复全量')
  └─ 执行全量采集
```

### 触发条件

- 即时恢复未触发（进程崩溃、异常退出等）
- `account_login_events` 表中最近 2 条记录为 `[login, logout]`

## 登录状态事件系统

基于 Event Sourcing 模式，所有登录状态变更记录到 `account_login_events` 表：

| 字段 | 说明 |
|------|------|
| `event_type` | `login` / `logout` |
| `reason` | 登出原因（timeout / shop_mismatch 等） |
| `mode_label` | 采集模式（增量 / 登出恢复全量 / 登出即时恢复全量） |
| `created_at` | 事件时间戳 |

## 注意事项

- 所有 spider 子类自动继承即时恢复逻辑（在 `BaseLiveCrawler` 中实现）
- Shopee 平台例外：登出恢复不触发即时全量（详见 `shopee-special-rules.md`）
- 恢复事件必须在主进程中写入，不能在子进程中操作
