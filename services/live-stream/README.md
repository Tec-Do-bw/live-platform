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
├── TT_client.py          # 单文件架构，包含全部业务逻辑（约 1280 行）
├── requirements.txt      # Python 依赖
├── start.sh              # 启动脚本
├── video/                # 运行时生成，按房间名分子目录存放 TS 切片
└── logs/                 # 运行时生成，按日期轮转
```

## 核心模块（均在 TT_client.py 内）

| 模块 | 类/函数 | 职责 |
|------|---------|------|
| FFmpeg 推流 | `FFmpegStreamManager` | 构建 FFmpeg 命令、启动进程、监控输出、健康检查、自动重连 |
| 视频处理 | `FileHelper` | TS 文件列表读取、长视频切割（>12s）、视频元信息解析、过时文件清理 |
| OSS 上传 | `AiyunOBSHelper` | 阿里云 OSS 上传，返回预签名 URL（180 天有效） |
| Kafka 推送 | `KafkaHelper` | 视频元数据推送到 Kafka（topic: `liveTs`） |
| 数据编排 | `MainHelper` | 串联文件处理 → OSS 上传 → Kafka 推送，含防重复处理机制 |
| 房间调度 | `get_room_info` / `start_get_room_scheduler` | 每 3 分钟轮询 live-monitor 获取房间、上报心跳 |
| 配置获取 | `fetch_apollo_config` | 从 Apollo 配置中心获取 Kafka/OSS 等配置 |
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

## 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `PRIMARY_NODE_URL` | 主节点地址 | `http://47.236.42.104:8080` |
| `BACKUP_NODE_URL` | 备用节点地址 | `http://47.237.6.199:8080` |
| `APOLLO_URL` | Apollo 配置中心地址 | 无默认值 |
| `APOLLOID` | Apollo 应用 ID | 硬编码为 `live-spider` |

## 相关文档

- 项目约束与设计决策（含 P0 断流约束、平台差异、跨服务交互规则）：`CLAUDE.md`
