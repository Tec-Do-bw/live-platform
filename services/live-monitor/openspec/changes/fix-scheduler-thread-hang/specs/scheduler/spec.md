## ADDED Requirements

### Requirement: 队列获取超时机制
系统在从浏览器标签页队列获取资源时 SHALL 设置合理的超时时间（默认30秒），防止无限阻塞。

#### Scenario: 队列获取成功
- **WHEN** 从 tabItemQ 队列获取浏览器标签页资源
- **AND** 队列中有可用资源
- **THEN** 应在超时时间内返回资源对象

#### Scenario: 队列获取超时
- **WHEN** 从 tabItemQ 队列获取浏览器标签页资源
- **AND** 队列在30秒内无可用资源
- **THEN** 应抛出 queue.Empty 异常并被捕获
- **AND** 函数返回 None
- **AND** 记录超时警告日志

### Requirement: 线程池任务超时保护
系统在执行直播间检测任务时 SHALL 为每个任务设置超时时间，防止单个任务阻塞整个线程池。

#### Scenario: 单个房间检测超时
- **WHEN** 线程池执行 check_single_room 任务
- **AND** 任务执行时间超过60秒
- **THEN** 任务应被标记为超时失败
- **AND** 记录超时错误日志
- **AND** 不影响其他任务执行

### Requirement: 调度器线程健康监控
系统 SHALL 持续监控定时调度器线程的运行状态，并在线程异常时自动恢复。

#### Scenario: 调度器线程正常运行
- **WHEN** 调度器线程正常运行
- **THEN** 监控线程应每30秒确认调度器存活
- **AND** 不触发任何告警

#### Scenario: 调度器线程死亡
- **WHEN** 调度器线程因异常而终止
- **THEN** 监控线程应在30秒内检测到
- **AND** 自动重启调度器线程
- **AND** 发送飞书告警通知
- **AND** 记录重启日志

### Requirement: 调度器健康检查 API
系统 SHALL 提供 HTTP 端点用于查询调度器线程状态。

#### Scenario: 查询调度器状态
- **WHEN** 客户端请求 GET /scheduler/health
- **THEN** 返回 JSON 响应包含:
  - `is_alive`: 线程是否存活
  - `last_execution_time`: 最后一次任务执行时间
  - `execution_count`: 总执行次数
  - `restart_count`: 重启次数

## MODIFIED Requirements

### Requirement: 定时任务异常处理增强
定时任务执行时 SHALL 捕获所有可能的异常，确保循环不会因单次失败而终止。

#### Scenario: SSL 连接错误
- **WHEN** 检测直播间时发生 SSL 错误
- **THEN** 记录错误日志
- **AND** 跳过当前房间继续处理其他房间
- **AND** 不触发 selenium 降级（如果队列资源不足）

#### Scenario: 单轮任务超时
- **WHEN** 单轮 check_live_status 执行时间超过4分钟
- **THEN** 强制结束当前轮次
- **AND** 记录超时警告日志
- **AND** 正常进入5分钟等待，准备下一轮

