# 采集模式与登出恢复机制

## 采集模式判断优先级

`core/collection_mode.py:resolve_collection_mode()` 按以下优先级判断：

1. **手动全量** (`--mode full`) - 最高优先级
2. **新账号全量** - 账号不在 `collection_tracker.json` 中
3. **登出恢复全量** - 检测到 `[login, logout]` 事件序列
4. **增量采集** - 默认模式

## 登录状态事件系统

基于 Event Sourcing 模式，事件表 `account_login_events`：

```sql
CREATE TABLE account_login_events (
    id INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- 'login' | 'logout'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 登出恢复机制

### 即时恢复路径（2 轮完成）

账号登出 → 业务通过 adspower-server 投屏登录 → 下一轮采集中 `send_login_callback("success")` 检测到 logout→login 状态切换，**当轮即时切换为全量采集**。

**实现要点**（所有 spider 子类自动继承）：
- `BaseLiveCrawler.send_login_callback` 在写入 login 事件前查询 `get_account_status()`
- 若当前为 logout 则设置 `self.full_collection = True` 和 `self._login_recovery = True`
- `main.py` / `task_scheduler.py` 在 `start_crawl()` 后检测 `result['login_recovery']`
- 补写 `full_recovery_started` / `full_recovery_succeeded` 事件

### Fallback 路径（3 轮完成）

若即时恢复未触发（如崩溃），下次调度 `resolve_collection_mode()` 读到 `[login, logout]` 序列触发恢复。

### 特殊规则：Shopee 不触发即时恢复

Shopee 的 `_auto_relogin()` 在每轮采集**开始前**检测 cookie 过期并自动重登录：

| 场景 | TikTok | Shopee |
|------|--------|--------|
| 登出检测时机 | 采集中途 | 采集开始前 |
| 上一轮数据 | 可能不完整 | 完整 |
| 自动重登录 | 无 | `_auto_relogin()` |
| 即时恢复 | 需要 | **不需要** |

**逻辑**：
- 上一轮 online → 本轮 `_auto_relogin()` 成功 → 正常增量（不触发全量）
- 上一轮 logout → 本轮 `resolve_collection_mode()` 检测 `[login, logout]` → 触发全量恢复
