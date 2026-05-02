# 架构说明

## 核心目录
- app/config.py：服务配置（AdsPower 地址、分组代理、登录页 URL、超时、回调地址、关闭延迟等）
- app/utils/logger.py：统一日志配置与日志输出
- app/models/request.py：请求模型（创建/关闭浏览器）
- app/models/response.py：响应模型与错误码常量
- app/services/adspower.py：AdsPower API 封装与异常定义（含 move_to_group 移动分组、query_group_by_name 查询分组、create_group 创建分组、get_or_create_group 获取或创建分组、list_browsers 查询环境列表V2、delete_browsers_batch 批量删除环境、cleanup_old_profiles 自动清理旧环境）
- app/services/session.py：Session 数据结构与生命周期管理（含 target_group_id 目标分组字段）
- app/services/screencast.py：CDP 投屏与输入事件转发
- app/services/login_monitor.py：登录监听、店铺校验、回调与延迟关闭（支持 api/v2/login 和 subaccount/get_shop_list 双接口监听，任一匹配即成功；登录成功后自动移动环境到目标分组）
- app/services/notification.py：飞书 Webhook 通知服务（静态代理缺失告警等）
- app/services/dynamic_proxy.py：动态代理获取服务（调用 kkoip API 获取 24 小时代理，含代理连通性验证）
- app/api/browser.py：HTTP 接口（创建/关闭浏览器）
- app/api/websocket.py：投屏 WebSocket 端点与消息处理
- app/main.py：FastAPI 应用入口、路由注册、异常处理、资源清理

## 测试与文档
- tests/test_html/index.html：投屏测试页面（创建、连接、输入、调试信息）
- requirements.txt：依赖列表
- README.md：使用说明
- todo.md：实施清单与进度

## 里程碑
- 阶段1投屏核心功能已完成（含完整流程与异常断连测试）
- 阶段2登录监听与店铺验证已完成（回调、超时与前端通知）
- 代码简化重构已完成（2026-01-21）
- 动态代理获取与飞书通知功能已完成（2026-01-22）
- 环境自动清理功能已完成（2026-01-23）

## 代码简化记录（2026-01-21）

### 简化内容
1. **app/config.py**：使用字典映射简化 `get_login_url` 函数
2. **app/services/adspower.py**：简化 `parse_proxy` 函数，使用更清晰的变量解构
3. **app/services/session.py**：
   - 提取 `_safe_cancel` 和 `_safe_call` 通用方法
   - 简化 `close` 方法中的重复逻辑
4. **app/services/screencast.py**：
   - 提取 `_get_key_code` 方法简化键盘事件处理
   - 添加中文注释提高可读性
5. **app/services/login_monitor.py**：
   - 提取 `_build_login_notification` 方法简化前端通知构建
   - 使用字典映射简化 `_schedule_close` 方法
   - 添加中文注释
6. **app/api/browser.py**：
   - 清理空的 try/except 块
   - 移除未使用的变量
   - 添加函数文档字符串
7. **app/api/websocket.py**：使用字典映射简化 `_handle_input_event` 函数
8. **app/main.py**：
   - 提取 `_cleanup_browser` 辅助函数
   - 添加中文注释和文档字符串

### 简化原则
- 保持所有功能不变
- 使用字典映射替代多个 if/elif 条件
- 提取重复代码为通用方法
- 添加中文注释提高可读性
- 移除无效代码和未使用变量
