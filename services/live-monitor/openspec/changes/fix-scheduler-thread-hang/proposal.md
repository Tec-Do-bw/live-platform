# Change: 修复定时调度器线程挂起问题

## Why

`start_select_info_scheduler` 启动的定时调度器线程在执行 `check_live_status` 时会因为以下原因挂起/崩溃：
1. **阻塞式队列获取**：`getPageinfo_selenium` 中 `self.tabItemQ.get()` 没有超时参数，当浏览器标签页资源耗尽时会**无限阻塞**
2. **SSL 代理错误**：代理配置问题导致 `SSL: WRONG_VERSION_NUMBER` 错误，触发降级到 selenium 方式，进而触发阻塞
3. **无监控机制**：线程设置为 `daemon=True` 但没有健康检查和自动恢复机制

## 问题日志分析

```
2025-12-03 16:37:02 | INFO | main.py:733 - 待检查直播间数量为：113
# 此后无 "=== 本轮检测完成" 日志
# 16:42:02 应触发的下一轮任务也未执行
getLiveStreamInfo_requests11111111:e--> HTTPSConnectionPool(host='www.tiktok.com', port=443): 
Max retries exceeded with url: /@dettolwmcofficial/live 
(Caused by SSLError(SSLError(1, '[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1010)')))
使用自动化获取直播地址 https://www.tiktok.com/@dettolwmcofficial/live
```

## What Changes

### 1. 队列获取添加超时机制 (核心修复)
- `TiktokTool.getPageinfo_selenium` 中 `tabItemQ.get()` 添加 `timeout` 参数
- 超时后优雅返回 `None`，避免无限阻塞

### 2. 调度器线程健康监控
- 添加调度器线程存活检查机制
- 线程死亡后自动重启
- 添加飞书告警通知

### 3. 单次任务执行超时保护
- 为 `check_live_status` 整体执行设置超时时间（如5分钟）
- 超时后强制结束当前轮次，进入下一轮

### 4. 日志增强
- 关键节点添加日志（队列获取、任务开始/结束）
- 方便问题排查

## Impact

- **受影响代码**:
  - `main.py`: `start_select_info_scheduler`, `check_live_status`, `check_single_room`
  - `utils/TiktokTool.py`: `getPageinfo_selenium`, `getLiveStreamInfo_requests`
- **风险**: 低 - 仅增加超时和监控逻辑，不改变核心业务流程
- **兼容性**: 完全向后兼容

## 技术方案

### 方案 A: 队列超时 + 线程监控（推荐）
```python
# TiktokTool.py - 添加超时
tabItems = self.tabItemQ.get(timeout=30)  # 30秒超时

# main.py - 线程监控
scheduler_thread = threading.Thread(target=scheduler, daemon=True)
# 每5分钟检查线程存活，死亡则重启
```

### 方案 B: 使用 APScheduler 替代手动调度
- 使用成熟的调度框架，内置任务超时和重试机制
- 改动较大，暂不采用

## 验证方法

1. 部署后持续运行24小时观察
2. 确认每5分钟有 "[定时任务] 节点 node1 开始执行..." 日志
3. 确认每轮都有 "=== 本轮检测完成" 日志
4. 模拟 SSL 错误场景验证降级处理正常

