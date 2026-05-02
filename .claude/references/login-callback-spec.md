# 登录回调规格

## login_status 三种值

| 值 | 含义 | 触发场景 |
|----|------|----------|
| `success` | 登录成功 | 检测到登录成功并验证店铺匹配 |
| `error` | 登录失败 | 超时、店铺不匹配、监听异常等 |
| `closed` | 主动关闭 | API关闭、WebSocket断开、应用关闭等（未完成登录流程） |

## reason 字段详细说明

### error 类型

| reason | 含义 | 适用平台 |
|--------|------|----------|
| `timeout` | 登录超时 | 所有平台 |
| `shop_mismatch` | 店铺不匹配 | 所有平台 |
| `listen_error` | 监听异常 | 所有平台 |
| `credentials_missing` | JS Hook 未拦截到账密 | Lazada |
| `live_login_failed` | live 端口登录失败 | Lazada |
| `sellercenter_login_failed` | sellercenter 自动登录失败 | Lazada |
| `cookie_save_failed` | Cookie 持久化失败 | Lazada |

### closed 类型

| reason | 含义 |
|--------|------|
| `api_close` | API 主动关闭 |
| `ws_disconnect` | WebSocket 断开 |
| `app_shutdown` | 应用关闭 |

## 回调 Payload 格式

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

## Lazada 双端口登录流程

Lazada 登录需要两个端口协同完成：

1. **live 端口（50325）**：用户在投屏页面输入账密，JS Hook 拦截并转发到 sellercenter 端口
2. **sellercenter 端口（50326）**：接收账密后自动填充并提交登录表单，登录成功后保存 Cookie

核心实现在 `adspower-server/app/services/login_monitor.py` 的 `_run_lazada` 方法中。

## WebSocket 投屏功能

adspower-server 提供 WebSocket 投屏服务（`app/services/screencast.py`），通过 CDP 协议将浏览器画面实时推送到前端，用于远程监控登录过程。
