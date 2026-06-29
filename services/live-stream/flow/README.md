# Redis 桥接架构流程图

## 流程图说明

本图展示了 live-platform 在 commit 0e85ab1 之后的 Redis 桥接架构，重点突出：

### 1. **核心改动：Redis 成为桥梁**
- **旧模式**：live-stream 通过 HTTP 轮询 live-monitor 的内存字典
- **新模式**：live-stream 直接从 Redis 读取，live-monitor 负责写入

### 2. **Redis 5 类键**（图中 Redis 桥接层）
- `collections` (Set)：房间 ID 集合
- `config` (Hash)：房间配置（无 TTL）
- `status` (Hash)：**实时状态，含 flvUrl**（TTL 900s）⭐
- `lease` (String)：录制租约（TTL 360s）
- `recording` (Hash)：录制状态（TTL 360s）

### 3. **关键创新：断流时刷新 flvUrl**（绿色高亮）
FFmpeg 断流后触发 `on_retry_refresh()` 回调：
1. **重新读取 Redis status**（不是用内存缓存）
2. 检查 `flvUrl` 是否变化
3. 如果变化 → 用新 URL 重连
4. 如果未变化 → 轮换备用 play_urls
5. 如果离线/过期 → 停止录制，释放租约

这解决了之前"一直用过期 URL 重试直到耗尽 12 次"的问题。

### 4. **数据流向**（箭头）
- **实线箭头**：主要数据流
- **虚线箭头**：控制流（续租、心跳、释放）

### 5. **颜色标注**
- 🟨 **黄色高亮（status）**：存储 flvUrl 的关键 Hash
- 🟩 **绿色高亮（Refresh）**：断流刷新逻辑
- 🔵 **蓝色高亮（CheckURL）**：URL 变化判断

---

## 配置迁移指南

### 环境变量配置

```bash
# 核心开关：选择房间源模式
LIVE_STREAM_ROOM_SOURCE=redis  # 旧值: http

# Redis 连接配置（二选一）
# 方式1：直接配置
REDIS_HOST=10.225.17.67
REDIS_PORT=6379
REDIS_PASSWORD=your_password
REDIS_DB=0

# 方式2：通过 Apollo 自动获取（推荐）
APOLLO_URL=http://10.225.17.67:30080
ISTEST=0  # 0=生产, 1=测试

# 可选：调优参数
STREAM_LEASE_TTL_SECONDS=360        # 租约时长
STREAM_MAX_RETRIES=12                # 最大重试次数
STREAM_HEARTBEAT_INTERVAL_SECONDS=10 # 心跳间隔
STREAM_NO_DATA_TIMEOUT_SECONDS=25    # 无数据超时
STREAM_RETRY_INTERVAL_SECONDS=1      # 重试初始间隔
```

### 迁移步骤

#### 阶段 1：验证 Redis 连接
```bash
# 测试 Redis 连接
redis-cli -h <REDIS_HOST> -p <REDIS_PORT> -a <REDIS_PASSWORD>
> PING
PONG

# 检查 live-monitor 是否写入了数据
> SMEMBERS live:monitor:collections
> HGETALL live:collection:<某个ID>:config
> HGETALL live:collection:<某个ID>:status
```

#### 阶段 2：灰度切换单台 live-stream
```bash
# 1. 停止旧进程
kill <old_pid>

# 2. 设置环境变量
export LIVE_STREAM_ROOM_SOURCE=redis
export REDIS_HOST=10.225.17.67
export REDIS_PORT=6379

# 3. 启动新进程
python TT_client.py

# 4. 观察日志
tail -f logs/ffmpeg_stream_*.log
# 查找关键日志：
# - "使用 Redis 房间源"
# - "成功抢占租约"
# - "直播源已刷新，使用新的FLV URL重连"
```

#### 阶段 3：验证断流刷新机制
```bash
# 人工模拟断流场景
# 1. 找一个正在录制的房间
# 2. 在 Redis 中手动修改 flvUrl
redis-cli HSET live:collection:<ID>:status flvUrl "https://new-cdn-url/live.flv"

# 3. 等待 FFmpeg 自然断流或手动 kill FFmpeg 子进程（不是 TT_client.py）
# 4. 观察日志是否出现：
#    "[room_id] 直播源已刷新，使用新的FLV URL重连"
```

#### 阶段 4：全量切换
确认灰度节点稳定运行 24 小时后，逐台切换其余 live-stream 节点。

---

## 故障排查

### 问题 1：抢占租约失败
**现象**：日志显示 "租约已被占用"
**原因**：另一台 worker 已持有该房间的租约
**解决**：正常行为，说明负载均衡生效；如需强制接管，手动删除租约：
```bash
redis-cli DEL live:collection:<ID>:lease
```

### 问题 2：断流后仍用旧 URL
**现象**：日志未显示 "直播源已刷新"
**排查**：
1. 检查 `LIVE_STREAM_ROOM_SOURCE` 是否为 `redis`
2. 检查 Redis status 中的 `flvUrl` 是否已更新
3. 检查 `expiresAt` 是否过期

### 问题 3：频繁抢占/释放租约
**现象**：同一房间在多个 worker 间跳动
**原因**：心跳续租失败或 TTL 过短
**解决**：
```bash
# 增加租约 TTL
export STREAM_LEASE_TTL_SECONDS=600
```

---

## 监控指标

### Redis 健康
```bash
# 监控键数量
redis-cli DBSIZE

# 监控内存使用
redis-cli INFO memory

# 监控慢查询
redis-cli SLOWLOG GET 10
```

### live-stream 健康
- 租约持有数：`redis-cli KEYS "live:collection:*:lease" | wc -l`
- 录制中房间数：`redis-cli KEYS "live:collection:*:recording" | wc -l`
- 断流重连次数：grep "直播源已刷新" logs/*.log | wc -l

---

## 性能对比

| 指标 | HTTP 模式 | Redis 模式 |
|------|----------|-----------|
| 房间分配延迟 | 3 分钟（轮询间隔） | < 1 秒（实时） |
| 断流恢复时间 | 12+ 次重试（≈ 2 分钟） | 1-2 次重试（≈ 10 秒） |
| flvUrl 刷新 | 下次轮询（3 分钟） | 断流立即刷新 |
| 跨节点状态同步 | 依赖 HTTP 心跳 | Redis 自动同步 |
| 单点故障风险 | live-monitor 挂掉全失效 | Redis 持久化 + 主备 |

---

## 相关文档

- 完整设计文档：`docs/archive/live-monitor-stream-redis-bridge.md`
- live-monitor CLAUDE.md：`services/live-monitor/CLAUDE.md`
- live-stream CLAUDE.md：`services/live-stream/CLAUDE.md`
- Redis 桥接代码：`services/live-stream/redis_room_source.py`
