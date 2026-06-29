# live-stream 直播流录制客户端

> 直播视频流录制客户端，部署在多台 Windows 机器上。从 live-monitor 获取房间分配，FFmpeg 拉流 → 切片 → OSS 上传 → Kafka 消息。

## 启动

```bash
pip install -r requirements.txt
python TT_client.py    # 默认端口 8080
bash start.sh          # 等价命令
```

## 项目结构

```
live-stream/
├── core/
│   └── apollo/                    # Apollo 客户端副本与 OpenAPI 写入能力
├── scripts/
│   └── seed_apollo_config.py      # 一次性写入 live-stream 点分 key 到 Apollo DEV/dev01
├── tests/
│   ├── test_config.py             # 配置门面测试
│   ├── test_ffmpeg_command.py     # FFmpeg 命令与 URL 候选测试
│   └── test_redis_room_source.py  # Redis 房间源测试
├── TT_client.py                   # 单文件架构，包含录制、切片、上传、Kafka 推送
├── config.py                      # Apollo 配置门面（点分 key、默认值、类型转换）
├── redis_room_source.py           # Redis 房间状态 / lease / recording 读取与写入
├── requirements.txt               # Python 依赖
├── start.sh                       # 启动脚本
├── video/                         # 运行时生成，按房间名分子目录存放 TS 切片
└── logs/                          # 运行时生成，按日期轮转
```

## 核心模块（均在 TT_client.py 内）

| 模块 | 类/函数 | 职责 |
|------|---------|------|
| FFmpeg 推流 | `FFmpegStreamManager` | 构建 FFmpeg 命令、启动进程、监控输出、健康检查、自动重连 |
| 视频处理 | `FileHelper` | TS 文件列表读取、长视频切割（>12s）、视频元信息解析、过时文件清理 |
| OSS 上传 | `AiyunOBSHelper` | 阿里云 OSS 上传，返回预签名 URL（180 天有效） |
| Kafka 推送 | `KafkaHelper` | 视频元数据推送到 Kafka（topic: `liveTs`） |
| Redis 房间源 | `RedisRoomSource` | Redis candidate/lease/recording 读取与写入 |
| 数据编排 | `MainHelper` | 串联文件处理 → OSS 上传 → Kafka 推送，含防重复处理机制 |
| 房间调度 | `get_room_info` / `start_get_room_scheduler` | 每 3 分钟轮询 live-monitor 获取房间、上报心跳 |
| 配置门面 | `config.py` + `core/apollo/` | 从 Apollo 读取点分 key，封装默认值、类型转换与热更新入口 |
| 主备容灾 | `request_with_fallback` | 请求主节点失败时自动切换备用节点 |

## 数据流

```
live-monitor /get_roominfo
        │
        ▼
  ProducerTask（每房间一个线程）
        │
        ├── FFmpegStreamManager.start_stream()
        │       │
        │       ▼
        │   FFmpeg 进程 → video/{roomName}/*.ts（8 秒切片）
        │
        └── upload_worker（后台线程，1 秒轮询）
                │
                ├── FileHelper.list_files_in_directory()  → 过滤就绪文件
                ├── FileHelper.cutBigFile()                → 长视频二次切割
                ├── AiyunOBSHelper.upload_file()           → 上传 OSS
                └── KafkaHelper.sendToKafka()              → 推送元数据
```

当 Apollo 配置 `live_stream.room_source=redis` 时，房间来源切换为 Redis：

- 读取 `live:monitor:collections` 和 `live:collection:{collectionId}:status`
- 通过 `live:collection:{collectionId}:lease` 认领录制
- 重连前重新读取 Redis 中的 `flvUrl`
- 保留 `online_room_list` 作为本地缓存，但不再作为跨服务所有权来源

## Apollo 引导环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `APOLLO_URL` | Apollo 配置中心地址 | `http://dev-apollo.tec-develop.com` |
| `APOLLOID` | Apollo 应用 ID | `live-spider` |
| `DEPLOY_ENV` | Apollo cluster | `dev01` |

业务配置（Kafka / OSS / Redis / 主备节点 / 房间源 / FFmpeg 参数）统一从 Apollo `application` namespace 读取：

- 通用 key：`redis.host` `redis.port` `redis.password` `redis.db`
- 通用 key：`kafka.servers` `kafka.topic`
- 通用 key：`oss.endpoint` `oss.bucket_name` `oss.access_key_id` `oss.access_key_secret`
- live-stream key：`live_stream.primary_node_url` `live_stream.backup_node_url`
- live-stream key：`live_stream.room_source` `live_stream.worker_id` `live_stream.lease_ttl_seconds`
- live-stream key：`live_stream.max_retries` `live_stream.retry_interval_seconds`
- live-stream key：`live_stream.retry_backoff` `live_stream.max_retry_interval_seconds`
- live-stream key：`live_stream.analyze_duration_us` `live_stream.probe_size_bytes`
- live-stream key：`live_stream.heartbeat_interval_seconds` `live_stream.no_data_timeout_seconds`

写入 Apollo DEV/dev01 的一次性脚本：`scripts/seed_apollo_config.py`

回滚方式：

```bash
在 Apollo 中把 `live_stream.room_source` 改回 `http`
```

## 相关文档

- 项目约束与设计决策（含 P0 断流约束、平台差异、跨服务交互规则）：`CLAUDE.md`
