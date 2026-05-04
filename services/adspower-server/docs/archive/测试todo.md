# AdsPower 登录转发投屏服务 - 测试待办清单

> 目标：给测试同学的手工/半自动测试清单，覆盖 API、投屏 WebSocket、登录监控、回调、代理与资源清理等核心流程。
> 适用范围：D:\SpiderCode\dev\adspower-server（当前代码版本）

---

## 1. 环境与准备（P0）
- [ ] AdsPower 本地服务可用（默认 `http://localhost:50325`），可创建/启动/关闭浏览器环境。
- [ ] 后端服务可启动：`python -m app.main`，默认端口 `8000`。
- [ ] 必要依赖安装完成：`pip install -r requirements.txt`。
- [ ] `tests/test_html/index.html` 可访问（注意其中的 API 地址是否需要改为当前测试环境）。
- [ ] 外部依赖可用（按需）：
  - [ ] 动态代理 API（`DYNAMIC_PROXY_API_URL`）可访问。
  - [ ] Feishu Webhook（`FEISHU_WEBHOOK_URL`）可用（建议使用测试群/测试 webhook）。
  - [ ] 回调地址（`LOGIN_CALLBACK_URL`）可用（建议使用测试接收器）。

## 2. 冒烟测试（P0）
- [ ] 访问 `http://47.237.6.199:8080/docs` 可打开 Swagger 文档。
- [ ] 使用 `tests/test_html/index.html` 执行“创建 → 连接 → 投屏显示 → 关闭”完整流程成功。

## 3. API 接口测试（P0/P1）
### 3.1 创建浏览器 `/api/browser/profile/create`
- [ ] **必填参数校验**：缺失 `country/media/validate_id` 返回 422 且 code = `-2`（参数错误）。
- [ ] **正常创建**：使用支持组合（见“测试数据”），返回 `code=0`，含 `session_id`、`ws_url`、`debug_port`、`collection_id`。
- [ ] **collection_id 复用**：传入已有 `collection_id`，应直接启动对应环境（不新建 profile）。
- [ ] **不支持组合**：`TH/shopee` 或 `VN/shopee` 触发动态代理流程；若动态代理失败应返回 `code=-3`。
- [ ] **AdsPower 不可用**：停掉 AdsPower 后请求创建，返回 `code=-4`。

### 3.2 关闭浏览器 `/api/browser/profile/close`
- [ ] **正常关闭**：传 `session_id` 关闭成功，`code=0`。
- [ ] **无效 session_id**：返回 `code=-6`。
- [ ] **重复关闭**：再次关闭同一 session，返回 `code=0` 或 `code=-6`，不应崩溃。

## 4. WebSocket 投屏与交互（P0）
- [ ] 使用 `ws://{host}:{port}/ws/remote/{session_id}` 可建立连接。
- [ ] 收到 `frame` 消息并可渲染（base64 jpeg）。
- [ ] `ping` → `pong` 往返正常，延迟显示正常。
- [ ] **输入事件**：鼠标点击/移动、键盘输入、中文输入均可在远端页面生效。
- [ ] **frameAck**：前端 ACK 后无异常日志；不 ACK 时服务端 3 秒后自动 ACK 不崩溃。
- [ ] **非法 session_id**：连接应被拒绝（关闭代码 1008）。

## 5. 登录监控与结果回调（P0/P1）
### 5.1 Shopee 登录流程
- [ ] validate_id 与真实店铺一致：登录成功，前端收到 `login_success`。
- [ ] validate_id 不一致：前端收到 `login_failed` + `reason=shop_mismatch`。
- [ ] 登录超时：前端收到 `login_timeout`。

### 5.2 TikTok 登录流程（cookie 监听）
- [ ] `multi_sids` 包含 validate_id：登录成功。
- [ ] `multi_sids` 不包含 validate_id：登录失败（shop_mismatch）。
- [ ] 登录超时：超时后触发回调与关闭流程。

### 5.3 回调与延迟关闭
- [ ] 回调请求发送成功（检查回调服务收到字段：login_status/media/validate_id/collection_id/session_id/shop_id）。
- [ ] 登录成功/失败/超时分别触发不同延迟关闭时间（5s/3s/3s 默认）。
- [ ] 回调失败不影响主流程（只记日志）。

## 6. 代理、分组与通知（P1）
- [ ] **静态代理配置**：支持组合创建成功且 proxy 生效。
- [ ] **动态代理**：静态配置不存在时，能够调用动态代理并通过验证（ipify）。
- [ ] **Feishu 通知**：动态代理触发时应发送通知。
- [ ] **分组移动**：登录成功后环境移动到 `{COUNTRY}团队-{media}` 分组（AdsPower 中验证）。

## 7. 资源清理与稳定性（P0/P1）
- [ ] 前端 WebSocket 断开时自动清理 session 和 AdsPower 环境。
- [ ] 服务进程退出时（shutdown event）清理所有活跃 session。
- [ ] 异常场景（AdsPower 返回错误、CDP 断开）不会导致服务崩溃。
- [ ] 日志中无明显异常堆栈，`logs/app.log` 正常写入。

## 8. 多会话与压力（P1/P2）
- [ ] 同时创建 3~5 个 session，投屏与输入互不影响。
- [ ] 长时间投屏（30+分钟）无内存明显增长、无断连。

## 9. 配置与边界（P2）
- [ ] 环境变量覆盖生效（`SERVER_PORT/LOGIN_TIMEOUT_SECONDS` 等）。
- [ ] `validate_id` 为大整数（字符串）仍可正确比较，不丢精度。
- [ ] `PROFILE_CLEANUP_THRESHOLD/COUNT` 调低后可触发自动清理旧环境。

---

## 测试数据参考
**静态支持组合**（来自配置）：
- TH / tiktok
- VN / tiktok
- MY / shopee
- ID / shopee
- MY / tiktok
- ID / tiktok

**不支持组合（用于动态代理/错误测试）**：
- TH / shopee
- VN / shopee
- 任意不存在组合（如 US / shopee）

---

## 测试记录（供填写）
- 测试环境地址：
- AdsPower 版本/状态：
- 测试账号/店铺：
- 回调接收地址：
- 主要问题与日志摘要：
