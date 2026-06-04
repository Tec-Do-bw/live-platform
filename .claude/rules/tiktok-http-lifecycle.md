---
paths:
  - "services/live-crawler/crawlers/http/tiktok/adapter.py"
  - "services/live-crawler/crawlers/http/tiktok/collector.py"
  - "services/live-crawler/cookie_keeper/tiktok_refresher.py"
  - "services/live-crawler/monitor/api/tiktok_refresh_routes.py"
  - "services/live-crawler/jobs/refresh_tiktok_credentials.py"
  - "services/adspower-server/app/services/login_monitor.py"
  - "services/adspower-server/app/services/adspower.py"
---

# TikTok HTTP 三链路生命周期

> TikTok 已 HTTP 化（plan: `docs/plans/2026-05-28-tiktok-http-refactor.md`）。
> 登录、养号、采集拆成三块独立链路，通过 `account_credentials` 表 + 登录回调解耦。
> **完整流程图（含行号）见 [`.claude/docs/tiktok-flow-diagrams.md`](../docs/tiktok-flow-diagrams.md)，本 rule 不复制图，只记跨链路契约与不变量。**

## 核心不变量：登录态判定一律走 HTTP `account_info`

三链路对"账号是否在线"的判断**必须**复用同一个口径——`collector.fetch_account_info`（curl_cffi 直连 `/api/v1/streamer_desktop/account_info/get`，判 `code==0 && data.user_id`）。

| 链路 | 判定位置 | 不允许 |
|------|---------|--------|
| 养号刷新 | `tiktok_refresher._check_login_by_api` 复用 `fetch_account_info` | ❌ 仅凭 cookie 存在性判活 |
| HTTP 采集 | `adapter.setup_session` → `fetch_account_info` | ❌ 跳过验证直接采集 |
| 登录投屏 | `login_monitor._check_tiktok_login_by_api`（注入 JS fetch 同一端点） | ❌ 仅凭 `multi_sids` 命中即判成功 |

**为什么**：cookie 还在不代表登录态有效（可能被风控/异地踢出）。只有真实请求 `account_info` 拿到 `user_id` 才算在线。`_check_sessionid_cookie`（查 sessionid 存在+未过期）**只是 HTTP 调用异常时的降级兜底**，不能作为主判据。

## 登录回调语义（HTTP 链路 = 二态）

HTTP 链路用 live-crawler 的 `services/login_callback.py:send_login_callback`，与浏览器侧 adspower-server 的三态（`success/error/closed`）**不同**：

- `login_status` 只有 **`success` / `logout`** 两态
- 返回 `{callback_sent: bool, login_recovery: bool}`
- `login_recovery=True` 表示检测到 logout→login 切换（详见 [[logout-recovery-flow]]）
- 回调契约字段定义见 [[login-callback-spec]]

**发回调的三条铁律**（养号刷新 + HTTP 采集共用）：

1. **在线** → `save_credentials` 写库 + `send_login_callback("success")`
2. **明确登出**（`account_info` 返回 `code≠0`，reason 非空） → `send_login_callback("logout", reason=...)`，且 **不写脏凭据**
3. **状态未知**（HTTP 调用异常/网络错误，reason 为空） → **不发任何回调**，避免污染登录态（下次刷新/采集自然恢复）

> ⚠️ 第 3 条是高频踩坑点：拦截超时、浏览器崩溃、网络抖动都属"状态未知"，绝不能误判成 logout 发回调，否则会触发不必要的登出恢复全量。

## 三链路衔接

```
链路一 登录投屏(人工)  ──登录成功自动触发──►  链路二 养号刷新凭据  ──写──►  account_credentials 表
                                                  ▲                              │
每日 cron 03:00 ──────────兜底───────────────────┘                              │读
                                                                                 ▼
                              链路三 HTTP 采集 ◄────────────────────────────────┘
                                  │凭据失效 logout 回调
                                  ▼
                            下一轮登出恢复全量
```

### 链路一 → 链路二（登录成功触发刷新）

- `login_monitor._schedule_tiktok_credential_refresh`：登录 success 后 `create_task` 异步调度，**不阻塞** ws 推送与业务回调
- 开关 `TIKTOK_REFRESH_ON_LOGIN`：关闭时登录成功不触发刷新
- **profile 冲突防护**：投屏浏览器与养号浏览器共用同一 AdsPower profile，必须等投屏浏览器 `check_browser_active` 返回 Inactive 才触发刷新；轮询最长 15min，超时则 `stop_browser` 强制关 + 二次确认，仍活跃则放弃（由 cron 兜底）
- 触发方式：httpx POST `{MONITOR_API_URL}/api/refresh_tiktok_credential`，带 `X-API-Token`（复用 `COOKIE_API_CONFIG.token`），timeout=180s，payload 仅 `{account_id}`

### 链路二 接口侧（`tiktok_refresh_routes.py`）

- `X-API-Token` 校验失败 → 403；`account_id` 为空 → 400
- 刷新是阻塞操作（开浏览器 15-30s），**必须** `run_in_threadpool` 执行，避免卡住事件循环
- `group_name`/`proxy` 不信任外部传入，由 `_load_profile_context` 从 AdsPower profile 查权威值

### 链路二 → 链路三（凭据落库）

- `save_credentials` 写 `account_credentials`，`region` 从 query_string 三层提取（`carrier_region` → `region` → `store_region`，取大写）
- `ext_json` 含 `query_string`/`creator_id`/`user_agent`，供 HTTP 采集复用设备指纹

### 链路三（采集读凭据）

- 工厂路由判 `credentials.crawler_mode=='http'` 或 `PLATFORM_CONFIG.tiktok.crawler_type=='http'`（**非环境变量**）
- `setup_session` 验证结果（`login_result`/`cred`/`session`）注入 `collect_tiktok`，account_info 由 adapter 单独上报一次，生成器内不重复请求
- 时间窗/时区按 region 走 `collector.TIKTOK_REGION_PROFILES`，详见 [[tiktok-collection-time]]
- 采集模式（增量/全量）判定见 [[collection-mode-rules]]

## 禁止事项

- ❌ 不得用 cookie 存在性替代 `account_info` 判活（降级兜底除外）
- ❌ 状态未知时不得发 logout 回调
- ❌ 不得跳过 `run_in_threadpool` 在事件循环里同步开浏览器
- ❌ 不得信任外部传入的 `group_name`/`proxy`，须从 AdsPower profile 取权威值
- ❌ 不得在投屏浏览器仍活跃时触发养号刷新（profile 冲突）
