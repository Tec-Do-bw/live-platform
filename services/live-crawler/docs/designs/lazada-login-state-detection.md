# Lazada 登录态判断与关键 Cookie

## 接口分组与 Cookie 依赖

根据实际测试结果，Lazada 采集接口分为三组，每组依赖不同的关键 Cookie：

| 接口组 | Base URL | 关键 Cookie | 签名要求 | 失效表现 |
|--------|----------|------------|---------|---------|
| **数据洞察** (1.4~1.5, 2.x) | `sellercenter.lazada.{domain}/ba/sycm/lazada/faas/` | `JSID` | 无 | 返回 HTML/text（非 JSON） |
| **营销中心** (1.1~1.3) | `acs-m.lazada.{domain}/h5/mtop.lazada.live.data.seller.*` | `JSID` + `_m_h5_tk` + `_m_h5_tk_enc` | mtop 签名 | `FAIL_SYS_TOKEN_ILLEGAL` 或 `FAIL_SYS_TOKEN_EXOIRED` |
| **LazLive** (3.1~3.2) | `acs-m.lazada.{domain}/h5/mtop.lazada.live.*` | `lzd_sid` + `_m_h5_tk` + `_m_h5_tk_enc` | mtop 签名 | `FAIL_SYS_TOKEN_ILLEGAL` 或 `FAIL_SYS_SESSION_EXPIRED` |

## 关键 Cookie 说明

### 1. `JSID` - Sellercenter 会话 Cookie
- **类型**: Session Cookie（无明确过期时间）
- **域**: `.lazada.{domain}`
- **作用**: Sellercenter 主站登录凭证
- **影响范围**: 数据洞察接口 + 营销中心接口
- **失效时机**: 服务端 session 过期（时间不固定，可能几小时到几天）

### 2. `lzd_sid` - LazLive 会话 Cookie
- **类型**: Session Cookie（无明确过期时间）
- **域**: `.lazada.{domain}`
- **作用**: LazLive 直播后台登录凭证
- **影响范围**: LazLive 接口
- **失效时机**: 服务端 session 过期（时间不固定）

### 3. `_m_h5_tk` + `_m_h5_tk_enc` - mtop 签名 Token
- **类型**: 有明确过期时间的 Cookie（通常 7 天）
- **域**: `.lazada.{domain}`
- **作用**: mtop 网关签名计算
- **影响范围**: 营销中心接口 + LazLive 接口（所有 mtop 接口）
- **失效时机**: 
  - 到达过期时间（Cookie 中的 Expires 字段）
  - 服务端提前清理（可能比 Expires 早）

## 登录态探测接口

### 方案一：分组探测（推荐）

**探测 Sellercenter 登录态**：
```
接口: GET /ba/sycm/lazada/faas/dashboard/key/overviewV2.json
参数: dateRange=YYYY-MM-DD|YYYY-MM-DD&dateType=day
关键 Cookie: JSID
判断逻辑:
  - 有效: HTTP 200 + JSON 格式 + code == 0
  - 登出: HTTP 200 + HTML/text 格式（非 JSON）
```

**探测营销中心接口可用性**：
```
接口: GET /h5/mtop.lazada.live.data.seller.metrics/1.0/
参数: 需要 mtop 签名（jsv, appKey, t, sign, data 等）
关键 Cookie: JSID + _m_h5_tk + _m_h5_tk_enc
判断逻辑:
  - 有效: ret 包含 "SUCCESS"
  - Token 过期: ret 包含 "FAIL_SYS_TOKEN_EXOIRED" → 从响应头 Set-Cookie 更新 token
  - 账号登出: ret 包含 "FAIL_SYS_TOKEN_ILLEGAL"（且响应头无 Set-Cookie）
```

**探测 LazLive 登录态**：
```
接口: POST /h5/mtop.lazada.live.querylivesbystatus/1.0/
参数: 需要 mtop 签名
关键 Cookie: lzd_sid + _m_h5_tk + _m_h5_tk_enc
判断逻辑:
  - 有效: ret 包含 "SUCCESS"
  - Token 过期: ret 包含 "FAIL_SYS_TOKEN_EXOIRED" → 从响应头 Set-Cookie 更新 token
  - 账号登出: ret 包含 "FAIL_SYS_SESSION_EXPIRED"（且响应头无 Set-Cookie）
```

### 方案二：最小化探测

如果只关心"账号是否可用"，可以只测试两个接口：

1. **Sellercenter 端**：测试数据洞察接口（只需 `JSID`）
2. **LazLive 端**：测试 LazLive 接口（需要 `lzd_sid` + `_m_h5_tk`）

## 登录态失效的常见原因

### 1. Session Cookie 过期（`JSID` / `lzd_sid`）
- **现象**: 几小时后请求失败
- **原因**: 服务端 session 超时清理
- **解决**: 重新登录对应端口

### 2. mtop Token 过期（`_m_h5_tk`）

**重要：Token 过期不等于账号登出**

当收到 `FAIL_SYS_TOKEN_EXOIRED::令牌过期` 时：
- **不代表账号登出**，只是 mtop token 过期了
- **服务器会自动返回新 token**：响应头中包含 `Set-Cookie: _m_h5_tk=...` 和 `Set-Cookie: _m_h5_tk_enc=...`
- **处理方式**：直接从响应头提取新 token 并更新到 cookie 存储，然后重试请求即可

**响应头示例**：
```python
# 当请求返回 FAIL_SYS_TOKEN_EXOIRED 时，响应头会包含：
response.cookies
# <RequestsCookieJar[
#   Cookie(name='_m_h5_tk', value='93550f2e83a90f7ca43a95ab3e3de430_1776761236311', 
#          domain='.lazada.co.th', expires=1777358476, ...),
#   Cookie(name='_m_h5_tk_enc', value='92a320eaf59e43538ac598cf2b0910a5',
#          domain='.lazada.co.th', expires=1777358476, ...)
# ]>
```

**实现逻辑**：
```python
response = requests.get(url, cookies=cookies, ...)
data = response.json()

if "FAIL_SYS_TOKEN_EXOIRED" in data.get("ret", []):
    # 从响应头提取新 token
    new_m_h5_tk = response.cookies.get('_m_h5_tk')
    new_m_h5_tk_enc = response.cookies.get('_m_h5_tk_enc')
    
    if new_m_h5_tk and new_m_h5_tk_enc:
        # 更新 cookie 存储
        cookies['_m_h5_tk'] = new_m_h5_tk
        cookies['_m_h5_tk_enc'] = new_m_h5_tk_enc
        save_cookies(account_id, cookies)  # 持久化到数据库
        
        # 重新计算签名并重试请求
        return retry_request_with_new_token(cookies)
    else:
        # 响应头没有新 token，说明是真正的账号登出
        return handle_logout()
```

**其他失效场景**：
- **现象**: 到达 Cookie Expires 时间后失效
- **原因**: Cookie 本身过期（通常 7 天）
- **解决**: 需要访问主站页面触发 token 刷新，或通过上述自动更新机制获取新 token

### 3. 两端登录态独立
- Sellercenter 登出不影响 LazLive
- LazLive 登出不影响 Sellercenter
- 但 `_m_h5_tk` 是共享的，一旦过期，两端的 mtop 接口都会失效

## 如何判断账号真正登出

**关键原则：不能仅通过 `_m_h5_tk` 过期来判断登出**

### Sellercenter 端登出判断

| 失效类型 | 响应特征 | 是否登出 | 处理方式 |
|---------|---------|---------|---------|
| **数据洞察接口** | 返回 HTML/text（非 JSON） | ✅ 是 | 需要重新登录 |
| **营销中心接口** | `FAIL_SYS_TOKEN_EXOIRED` + 响应头有 `Set-Cookie` | ❌ 否 | 更新 token 后重试 |
| **营销中心接口** | `FAIL_SYS_TOKEN_ILLEGAL` + 响应头无 `Set-Cookie` | ✅ 是 | 需要重新登录 |

### LazLive 端登出判断

| 失效类型 | 响应特征 | 是否登出 | 处理方式 |
|---------|---------|---------|---------|
| **LazLive 接口** | `FAIL_SYS_TOKEN_EXOIRED` + 响应头有 `Set-Cookie` | ❌ 否 | 更新 token 后重试 |
| **LazLive 接口** | `FAIL_SYS_SESSION_EXPIRED` + 响应头无 `Set-Cookie` | ✅ 是 | 需要重新登录 |
| **LazLive 接口** | `FAIL_SYS_TOKEN_ILLEGAL` + 响应头无 `Set-Cookie` | ✅ 是 | 需要重新登录 |

### 判断逻辑伪代码

```python
def is_account_logged_out(response, endpoint_type: str) -> bool:
    """
    判断账号是否真正登出
    
    Args:
        response: HTTP 响应对象
        endpoint_type: 'sellercenter_ba' | 'marketing_center' | 'lazlive'
    
    Returns:
        True: 账号已登出，需要重新登录
        False: 仅 token 过期或请求正常
    """
    # 数据洞察接口：返回非 JSON 即为登出
    if endpoint_type == 'sellercenter_ba':
        try:
            response.json()
            return False  # 能解析 JSON，说明未登出
        except:
            return True   # 返回 HTML，说明已登出
    
    # mtop 接口（营销中心 / LazLive）
    data = response.json()
    ret = data.get("ret", [])
    
    # 如果返回 SUCCESS，肯定没登出
    if any("SUCCESS" in r for r in ret):
        return False
    
    # 如果返回 TOKEN_EXOIRED，检查响应头是否有新 token
    if any("FAIL_SYS_TOKEN_EXOIRED" in r for r in ret):
        has_new_token = (
            response.cookies.get('_m_h5_tk') is not None and
            response.cookies.get('_m_h5_tk_enc') is not None
        )
        return not has_new_token  # 有新 token = 未登出，无新 token = 已登出
    
    # 其他失败情况（TOKEN_ILLEGAL / SESSION_EXPIRED）
    if any("FAIL_SYS" in r for r in ret):
        return True  # 真正的登出
    
    return False
```

## Cookie 刷新机制

### 哪些接口会刷新 Cookie？

根据 HTTP 响应头中的 `Set-Cookie` 判断：

- **刷新 `JSID`**: 访问 Sellercenter 主站页面（如首页、Dashboard）
- **刷新 `lzd_sid`**: 访问 LazLive 主站页面（如直播间列表页）
- **刷新 `_m_h5_tk`**: 访问任一主站页面（Sellercenter 或 LazLive）

**注意**: API 接口通常不会刷新 Cookie，只有页面级请求才会返回 `Set-Cookie`。

## 实现建议

### 采集前预检
```python
def check_lazada_login_state(cookies: dict) -> dict:
    """
    返回: {
        'sellercenter': bool,  # 数据洞察接口是否可用
        'marketing': bool,     # 营销中心接口是否可用
        'lazlive': bool,       # LazLive 接口是否可用
    }
    """
    # 1. 测试 Sellercenter（只需 JSID）
    # 2. 测试营销中心（需要 JSID + _m_h5_tk）
    # 3. 测试 LazLive（需要 lzd_sid + _m_h5_tk）
```

### Cookie 续命策略
```python
def refresh_cookies(account_id: str):
    """
    定期访问主站页面，触发 Cookie 刷新
    """
    # 1. 用 AdsPower 打开浏览器
    # 2. 访问 sellercenter 首页（刷新 JSID + _m_h5_tk）
    # 3. 访问 live 首页（刷新 lzd_sid + _m_h5_tk）
    # 4. 提取新 Cookie 保存到数据库
```

## 测试脚本

测试脚本位置：`live_dp/tests/crawlers/http/lazda_cookie_activity.py`

使用方式：
```bash
# 测试所有三组接口
python lazda_cookie_activity.py

# 单独测试营销中心接口
python lazda_cookie_activity.py marketing

# 监控 session 过期时间（每 30 分钟检查一次）
python lazda_cookie_activity.py monitor 30 24

# 探测哪些接口会刷新 cookie
python lazda_cookie_activity.py discover
```
