## ADDED Requirements

### Requirement: 数据上报共享模块
`services/data_reporter.py` SHALL 提供 `send_api_request(message: dict, config: dict) -> bool` 函数，封装数据上报逻辑，包括：
- HTTP 请求发送到 livelabstar.com
- 失败重试机制
- 失败时落盘保存
- 登录事件写入

该函数 SHALL 与原 BaseLiveCrawler.send_api_request 行为完全一致。

#### Scenario: 上报成功
- **WHEN** 调用 send_api_request 且远端返回成功
- **THEN** 函数 SHALL 返回 True

#### Scenario: 上报失败后重试成功
- **WHEN** 首次请求失败但重试成功
- **THEN** 函数 SHALL 返回 True，重试次数不超过配置上限

#### Scenario: 上报最终失败
- **WHEN** 所有重试均失败
- **THEN** 函数 SHALL 将消息落盘保存，返回 False

### Requirement: 登录回调共享模块
`services/login_callback.py` SHALL 提供 `send_login_callback(account_id: str, platform: str, status: str, reason: str) -> bool` 函数，封装登录状态回调逻辑，包括：
- 发送登录状态到回调接口
- 登出恢复检测

该函数 SHALL 与原 BaseLiveCrawler.send_login_callback 行为完全一致。

**调用方说明**：
- 浏览器采集器（BaseLiveCrawler）调用（现有行为）
- HTTP 采集器（BaseHttpCrawler）不调用 — 不判断登录状态，不发送登录回调
- 养号服务调用（未来）— 负责 Cookie 管理和登录态判定

#### Scenario: 登录状态正常回调
- **WHEN** 调用 send_login_callback(status='login')
- **THEN** 函数 SHALL 发送登录状态到回调接口并返回 True

#### Scenario: 登出状态回调
- **WHEN** 调用 send_login_callback(status='logout', reason='cookie_expired')
- **THEN** 函数 SHALL 发送登出状态并触发登出恢复检测

### Requirement: BaseLiveCrawler 调用共享模块
修改后的 BaseLiveCrawler SHALL 调用 `services/data_reporter.py` 中的 `send_api_request` 函数，替代原有的内联实现。修改后的行为 MUST 与原实现完全一致。

BaseLiveCrawler 的 `send_login_callback` 保持原有实现不变（不抽取为共享模块），待后续统一迁移到共享模块。

#### Scenario: 浏览器采集数据上报无回归
- **WHEN** BaseLiveCrawler 调用共享模块的 send_api_request
- **THEN** 数据上报行为 SHALL 与修改前完全一致
