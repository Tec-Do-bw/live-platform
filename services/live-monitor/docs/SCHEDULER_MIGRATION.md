# 定时调度任务迁移说明

## 迁移概述

已成功将 `webSoctket/` 下的定时调度功能迁移到 `liveSpider_Serverv2/`：

- `webSoctket/scheduler_manager.py` → `liveSpider_Serverv2/utils/scheduler_manager.py`
- `webSoctket/ALLSpider_Paidaxing.py` → `liveSpider_Serverv2/tasks/scheduler_tasks.py`
- 新建 `liveSpider_Serverv2/start_scheduler.py` 作为任务启动脚本

## 迁移的功能

### 1. 调度器管理 (scheduler_manager.py)

**功能：** 实现主备节点自动切换

- `SimpleSchedulerManager`: 调度器管理类
- `create_scheduler_manager()`: 便捷工厂函数

**特点：**
- ✅ 通过 HTTP `/health` 接口检查主节点健康状态
- ✅ 主节点总是执行任务
- ✅ 备节点只在主节点故障时执行（故障判定：连续3次请求失败）
- ✅ 支持自定义健康检查间隔

**配置说明：**

```python
# 节点信息（部署时修改）
NODE_ID = 'node1'      # 'node1' 或 'node2'
NODE_IP = '127.0.0.1'  # 节点IP地址

# 创建调度器
scheduler_manager = create_scheduler_manager(NODE_ID, NODE_IP)

# 包装任务函数
wrapped_task = scheduler_manager.wrap_task(task_func, "任务名称")
```

### 2. 定时任务 (scheduler_tasks.py)

**功能：** 包含所有数据采集任务

#### WebSocketClient 类

用于与插件进行 WebSocket 通信

```python
client = WebSocketClient(user_id="paidaxing")
await client.connect()
await client.send_message(target_user_id, message)
await client.close()
```

#### 采集任务

1. **GMV实时采集** (`mainSpider_gmv`)
   - 采集正在直播的直播间GMV数据
   - 调度频率：每5分钟执行一次
   - 通过WebSocket向插件发送采集任务

2. **T+1插件采集** (`mainSpider_T1`)
   - T+1数据与插件数据采集
   - 调度频率：每4小时执行一次
   - [TODO] 需要完整迁移相关函数

3. **基本信息采集** (`mainSpider_requests`)
   - 通过requests模拟请求采集基本信息
   - 调度频率：每天12点执行一次
   - [TODO] 需要完整迁移相关函数

### 3. 启动脚本 (start_scheduler.py)

统一的定时调度任务启动脚本

## 环境变量配置

```bash
# 节点标识
NODE_ID=node1          # 'node1' 或 'node2'
NODE_IP=127.0.0.1      # 节点IP地址

# 环境标识
ISTEST=1               # 0: 生产环境, 1: 测试环境
```

## 使用方式

### 方式1：直接运行启动脚本

```bash
cd liveSpider_Serverv2

# 方式1.1：使用默认配置
python start_scheduler.py

# 方式1.2：通过环境变量指定配置
NODE_ID=node1 NODE_IP=127.0.0.1 ISTEST=1 python start_scheduler.py

# 方式1.3：主机1配置
NODE_ID=node1 NODE_IP=47.237.6.199 ISTEST=0 python start_scheduler.py

# 方式1.4：主机2配置
NODE_ID=node2 NODE_IP=47.236.42.104 ISTEST=0 python start_scheduler.py
```

### 方式2：通过 systemd 服务启动（Linux/Mac）

创建 `/etc/systemd/system/live-spider-scheduler.service`：

```ini
[Unit]
Description=Live Spider Scheduler Service
After=network.target

[Service]
Type=simple
User=spider
WorkingDirectory=/path/to/liveSpider_Serverv2
Environment="NODE_ID=node1"
Environment="NODE_IP=127.0.0.1"
Environment="ISTEST=0"
ExecStart=/usr/bin/python3 start_scheduler.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl start live-spider-scheduler
sudo systemctl enable live-spider-scheduler
sudo systemctl status live-spider-scheduler
```

### 方式3：通过 Windows 批处理脚本启动

创建 `start_scheduler.bat`：

```batch
@echo off
cd D:\SpiderCode\livelab\liveSpider_Serverv2
set NODE_ID=node1
set NODE_IP=127.0.0.1
set ISTEST=1
python start_scheduler.py
pause
```

### 方式4：通过 Docker 启动

```bash
docker run -d \
  --name live-spider-scheduler \
  -e NODE_ID=node1 \
  -e NODE_IP=127.0.0.1 \
  -e ISTEST=1 \
  -v /path/to/liveSpider_Serverv2:/app \
  python:3.9 python /app/start_scheduler.py
```

## 日志查看

### 查看实时日志

```bash
# Linux/Mac - 查看最后100行日志
tail -f liveSpider_Serverv2/logs/2025-10-16.logs

# 搜索特定关键词
grep "GMV实时采集" liveSpider_Serverv2/logs/2025-10-16.logs

# 查看错误日志
grep "ERROR" liveSpider_Serverv2/logs/2025-10-16.logs
```

### 监控任务执行

调度器会在以下情况记录日志：

- ✅ 任务启动时：`[时间] 节点 {node_id} 执行任务: {task_name}`
- ✅ 任务完成时：`[调度器] 任务 {task_name} 执行完成`
- ❌ 任务失败时：`[调度器] 任务 {task_name} 执行失败: {error}`
- ⚠️ 主节点故障时：`[调度器] 主节点健康检查失败`
- ✅ 备节点接管时：`✅ [调度器] 主节点故障，备节点 {node_id} 接管任务执行`

## 主备切换机制

### 故障检测

备节点每隔 `check_interval` 秒（默认10秒）检查一次主节点健康状态

检查方式：
```
GET {primary_node_url}/health
```

### 故障判定

连续3次健康检查失败 = 主节点故障，备节点接管

### 恢复机制

- 当主节点恢复正常，备节点停止执行任务
- 主节点会立即接管所有任务
- 无缝切换，不会中断任务执行

## 端口配置

| 服务 | 迁移前端口 | 迁移后端口 |
|------|----------|----------|
| WebSocket API | 8081 | 8080 |
| 健康检查 | 8081/health | 8080/health |
| 定时任务 | 独立进程 | 独立进程 |

**注意：** 定时调度任务通过 WebSocket 与主应用通信

## 所需依赖

```bash
pip install schedule websockets pymysql
```

或在 `requirements.txt` 中添加：

```
schedule>=1.2.0
websockets>=10.0
pymysql>=1.0.2
```

## 迁移检查清单

- [x] 调度器管理器迁移 (`utils/scheduler_manager.py`)
- [x] 定时任务模块迁移 (`tasks/scheduler_tasks.py`)
- [x] 启动脚本创建 (`start_scheduler.py`)
- [ ] 完整T+1采集函数迁移
- [ ] 完整requests采集函数迁移
- [ ] 测试主备切换机制
- [ ] 测试定时任务执行
- [ ] 生产环境部署验证

## 常见问题

### Q1: 定时任务没有执行

**解决方案：**
1. 确保 `start_scheduler.py` 正在运行
2. 查看日志中是否有错误信息
3. 检查节点是否为主节点（主节点优先执行）
4. 验证数据库连接是否正常

### Q2: 备节点无法自动接管

**解决方案：**
1. 确保备节点能够访问主节点的 `/health` 接口
2. 检查防火墙是否允许8080端口访问
3. 查看日志中的健康检查结果
4. 确认主节点确实已停止运行

### Q3: WebSocket连接失败

**解决方案：**
1. 确保主应用服务器正在运行（8080端口）
2. 验证WebSocket URL是否正确
3. 检查防火墙是否允许WebSocket连接
4. 查看服务器日志中的错误信息

### Q4: 任务执行频率不对

**解决方案：**
1. 检查 `schedule.every()` 的配置
2. 确保系统时间正确
3. 查看日志中实际的执行时间
4. 验证任务队列中是否有堆积的任务

## 技术架构

```
┌─────────────────────────────────────┐
│     定时调度器 (start_scheduler.py) │
│  ┌────────────────────────────────┐ │
│  │ SimpleSchedulerManager         │ │
│  │ ├─ 主节点判断                 │ │
│  │ ├─ 健康检查                   │ │
│  │ └─ 任务包装                   │ │
│  └────────────────────────────────┘ │
│  ┌────────────────────────────────┐ │
│  │ 定时任务 (schedule library)    │ │
│  │ ├─ GMV采集 (5分钟)            │ │
│  │ ├─ T+1采集 (4小时)            │ │
│  │ └─ 基本信息采集 (每天12点)   │ │
│  └────────────────────────────────┘ │
│  ┌────────────────────────────────┐ │
│  │ WebSocketClient                │ │
│  │ └─ 连接主应用 (ws://127.0.0.1:8080) │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│    主应用 (liveSpider_Serverv2)     │
│  ┌────────────────────────────────┐ │
│  │ WebSocket 路由                 │ │
│  │ └─ /ws/{user_id}              │ │
│  │ └─ /health                    │ │
│  └────────────────────────────────┘ │
│  ┌────────────────────────────────┐ │
│  │ HTTP REST API                  │ │
│  │ └─ 其他功能路由               │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

## 后续改进计划

1. 📊 添加任务执行统计和监控面板
2. 📝 完整迁移T+1采集函数
3. 📝 完整迁移requests采集函数
4. 🔄 支持动态调整任务调度频率
5. 📈 添加性能监控和告警机制
6. 🗄️ 使用数据库存储任务执行历史

## 相关文件

- 调度器管理：`utils/scheduler_manager.py`
- 定时任务：`tasks/scheduler_tasks.py`
- 启动脚本：`start_scheduler.py`
- WebSocket 路由：`routes/websocket_routes.py`
- 主应用：`main.py`
