# 登录回调规格

> 浏览器登录监控服务的回调接口规范。由 `adspower-server` 服务在登录流程结束后主动 POST 给后端。
> 本文件为**唯一权威源**，各子服务的 CLAUDE.md / README.md 通过路径引用，不复制副本。

## 1. 概述

### 1.1 调用链路

```
前端 → 后端 → FastAPI（adspower-server）→ 登录监控 → 回调后端
```

### 1.2 回调时机

| 场景 | 触发点 | 回调状态 |
|------|--------|----------|
| 登录成功 | 检测到登录成功并验证店铺匹配 | `success` |
| 登录超时 | 超过配置的超时时间未完成登录 | `error` |
| 店铺不匹配 | 登录成功但店铺 ID 与预期不符 | `error` |
| 监听异常 | 登录监听过程发生异常 | `error` |
| API 关闭 | 调用关闭浏览器 API | `closed` |
| WebSocket 断开 | 前端 WebSocket 连接断开 | `closed` |
| 应用关闭 | 服务进程关闭 | `closed` |

## 2. 接口定义

```
POST {LOGIN_CALLBACK_URL}
Content-Type: application/json
accessToken: {LOGIN_CALLBACK_ACCESS_TOKEN}
```

### 2.1 配置项

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 回调地址 | `LOGIN_CALLBACK_URL` | - | 后端接收回调的 URL |
| 访问令牌 | `LOGIN_CALLBACK_ACCESS_TOKEN` | - | 请求头中的认证令牌 |
| 登录超时时间 | `LOGIN_TIMEOUT_SECONDS` | 900 | 登录超时（秒） |
| 成功后关闭延迟 | `LOGIN_SUCCESS_CLOSE_DELAY_SECONDS` | 5 | 成功后延迟关闭浏览器（秒） |
| 失败后关闭延迟 | `LOGIN_FAILED_CLOSE_DELAY_SECONDS` | 3 | 失败后延迟关闭浏览器（秒） |
| 超时后关闭延迟 | `LOGIN_TIMEOUT_CLOSE_DELAY_SECONDS` | 3 | 超时后延迟关闭浏览器（秒） |

### 2.2 请求 Payload

```json
{
    "login_status": "success|error|closed",
    "media": "shopee|tiktok|lazada",
    "validate_id": "123456",
    "collection_id": "profile_xxx",
    "reason": "timeout|shop_mismatch|api_close|...",
    "session_id": "session_xxx",
    "shop_id": 123456
}
```

### 2.3 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `login_status` | string | 是 | 登录状态：`success` / `error` / `closed` |
| `media` | string | 是 | 媒体类型：`shopee` / `tiktok` / `lazada` |
| `validate_id` | string | 是 | 预期的店铺 ID（用于校验） |
| `collection_id` | string | 是 | 浏览器环境 ID（AdsPower profile_id） |
| `reason` | string | 否 | 失败/关闭原因（见 §3） |
| `session_id` | string | 是 | 本次会话 ID |
| `shop_id` | int / null | 否 | 实际登录的店铺 ID（成功时返回） |

## 3. 状态与原因

### 3.1 login_status 三种值

| 值 | 含义 | 触发场景 |
|----|------|----------|
| `success` | 登录成功 | 检测到登录成功并验证店铺匹配 |
| `error` | 登录失败 | 超时、店铺不匹配、监听异常等 |
| `closed` | 主动关闭 | API 关闭、WebSocket 断开、应用关闭等（未完成登录流程） |

### 3.2 reason 字段详细说明

**error 类型**：

| reason | 含义 | 适用平台 |
|--------|------|----------|
| `timeout` | 登录超时 | 所有平台 |
| `shop_mismatch` | 店铺不匹配 | 所有平台 |
| `listen_error` | 监听异常 | 所有平台 |
| `credentials_missing` | JS Hook 未拦截到账密 | Lazada |
| `live_login_failed` | live 端口登录失败 | Lazada |
| `sellercenter_login_failed` | sellercenter 自动登录失败 | Lazada |
| `cookie_save_failed` | Cookie 持久化失败 | Lazada |

**closed 类型**：

| reason | 含义 |
|--------|------|
| `api_close` | API 主动关闭 |
| `ws_disconnect` | WebSocket 断开 |
| `app_shutdown` | 应用关闭 |

## 4. 回调示例

### 4.1 登录成功

```json
{
    "login_status": "success",
    "media": "shopee",
    "validate_id": "123456",
    "collection_id": "profile_abc123",
    "reason": "",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "shop_id": 123456
}
```

### 4.2 登录超时

```json
{
    "login_status": "error",
    "media": "tiktok",
    "validate_id": "789012",
    "collection_id": "profile_def456",
    "reason": "timeout",
    "session_id": "550e8400-e29b-41d4-a716-446655440001",
    "shop_id": null
}
```

### 4.3 店铺不匹配

```json
{
    "login_status": "error",
    "media": "shopee",
    "validate_id": "123456",
    "collection_id": "profile_ghi789",
    "reason": "shop_mismatch",
    "session_id": "550e8400-e29b-41d4-a716-446655440002",
    "shop_id": 654321
}
```

### 4.4 WebSocket 断开

```json
{
    "login_status": "closed",
    "media": "shopee",
    "validate_id": "123456",
    "collection_id": "profile_jkl012",
    "reason": "ws_disconnect",
    "session_id": "550e8400-e29b-41d4-a716-446655440003",
    "shop_id": null
}
```

## 5. 登录监听机制

### 5.1 Shopee

监听网络请求，匹配以下接口（任一返回的 shop_id 匹配 validate_id 即为成功）：

- `api/v2/login` — 获取登录后的 shop_id
- `subaccount/get_shop_list` — 获取子账号的店铺列表

### 5.2 TikTok

基于 Cookie 监听 `multi_sids`：

- Cookie 存在且包含 validate_id → 登录成功
- Cookie 存在但不包含 validate_id → 店铺不匹配
- 超时未出现 Cookie → 登录超时

### 5.3 Lazada（双端口流程）

Lazada 登录需要两个端口协同完成：

1. **live 端口（50325）**：用户在投屏页面输入账密，JS Hook 拦截并转发到 sellercenter 端口
2. **sellercenter 端口（50326）**：接收账密后自动填充并提交登录表单，登录成功后保存 Cookie

核心实现在 `adspower-server/app/services/login_monitor.py` 的 `_run_lazada` 方法中。

## 6. 回调优先级与去重

1. **登录结果回调优先**：登录成功/失败的回调优先于关闭回调
2. **首次触发原则**：每个 Session 只触发一次回调
3. **状态锁定**：一旦 `login_status` 被设置，后续关闭操作不再触发回调

Session 对象包含 `login_callback_sent` 标志位：首次回调成功后置 `true`，后续关闭操作检查此标志，已发送则跳过。

```python
if session.login_callback_sent:
    logger.info("Session 已发送过登录回调，跳过关闭回调")
    return
```

## 7. 触发点位置

### 7.1 登录监听触发（`app/services/login_monitor.py`）

```python
await self._callback_backend(session, status="success", reason="", shop_id=shop_id)
await self._callback_backend(session, status="error", reason="timeout", shop_id=None)
await self._callback_backend(session, status="error", reason="shop_mismatch", shop_id=shop_id)
await self._callback_backend(session, status="error", reason="listen_error", shop_id=None)
```

### 7.2 关闭触发

| 触发位置 | 文件 | reason |
|----------|------|--------|
| `/profile/close` API | `app/api/browser.py` | `api_close` |
| WebSocket 断开 | `app/api/websocket.py` | `ws_disconnect` |
| 应用关闭 | `app/main.py` | `app_shutdown` |

## 8. WebSocket 投屏

adspower-server 提供 WebSocket 投屏服务（`app/services/screencast.py`），通过 CDP 协议将浏览器画面实时推送到前端，用于远程监控登录过程。WebSocket 路径为 `/ws/remote/{session_id}`。

## 9. 后端接口实现建议

1. **幂等处理**：根据 `session_id` 去重
2. **状态机校验**：验证状态转换合法性
3. **异步处理**：回调接口快速响应，后续处理异步执行
4. **日志记录**：记录所有回调便于排查

推荐响应：

```json
{ "code": 0, "msg": "success" }
```

**错误处理**：本服务对 HTTP 4xx/5xx 与超时（10 秒）只记录日志，不重试。

## 10. 集成检查清单

- [ ] 提供回调接口 URL 与访问令牌
- [ ] 接口支持 POST + JSON + accessToken 请求头认证
- [ ] 能处理三种 login_status 与所有 reason 类型
- [ ] 接口实现幂等（基于 session_id）
- [ ] 接口响应时间 < 10 秒

## 附录：环境配置示例

```bash
# .env
LOGIN_CALLBACK_URL=https://api.example.com/callback/login
LOGIN_CALLBACK_ACCESS_TOKEN=your_access_token_here
LOGIN_TIMEOUT_SECONDS=900
LOGIN_SUCCESS_CLOSE_DELAY_SECONDS=5
LOGIN_FAILED_CLOSE_DELAY_SECONDS=3
LOGIN_TIMEOUT_CLOSE_DELAY_SECONDS=3
```
