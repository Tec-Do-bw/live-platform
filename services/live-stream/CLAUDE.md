# live-stream

> 通用编码规范见根目录 `CLAUDE.md`。以下仅记录 live-stream 特有规则。

## 项目定位

- 直播视频流录制客户端，部署在多台 Windows 机器上
- 从 live-monitor 获取房间分配，拉取直播流并切片上传
- 调用链路：live-monitor（房间分配）→ 本服务（FFmpeg 拉流 → 切片 → OSS 上传 → Kafka 消息）

## 目录结构

```
live-stream/
├── TT_client.py          # 单文件架构，包含全部业务逻辑
├── requirements.txt      # Python 依赖
├── start.sh              # 启动脚本
├── video/                # 运行时生成，按房间名分子目录存放 TS 切片
└── logs/                 # 运行时生成，按日期轮转的日志文件
```

## 运行命令

```bash
pip install -r requirements.txt
python TT_client.py                    # 启动服务（默认端口 8080）
bash start.sh                          # 等价于上面的命令
```

## 核心架构

### 模块划分（均在 TT_client.py 内）

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

### 数据流

```
live-monitor /get_roominfo
        │
        ▼
  ProducerTask（每房间一个线程）
        │
        ├── FFmpegStreamManager.start_stream()
        │       │
        │       ▼
        │   FFmpeg 进程 → video/{roomName}/*.ts（8秒切片）
        │
        └── upload_worker（后台线程，1秒轮询）
                │
                ├── FileHelper.list_files_in_directory()  → 过滤就绪文件
                ├── FileHelper.cutBigFile()                → 长视频二次切割
                ├── AiyunOBSHelper.upload_file()           → 上传 OSS
                └── KafkaHelper.sendToKafka()              → 推送元数据
```

### 平台差异

| 参数 | TikTok | Shopee |
|------|--------|--------|
| 读写超时 | 15s | 8s |
| 复用队列 | 1024 | 9999 |
| 视频元信息 | `parse_video_Info` | `parse_video_Info_shopee`（含 shop_id/nickname 等） |
| 平台判断 | 默认 | session 中含 `shop_id` |

## P0 断流问题：已知约束

当前 FFmpeg 推流存在断流问题，以下是已知约束和优化方向：

| 约束 | 当前值 | 问题 |
|------|--------|------|
| 最大重试次数 | 5 次 | 不够，直播流波动频繁 |
| 心跳检测间隔 | 30s | 太长，断流感知延迟 |
| 无数据超时 | 60s | 太长，断流后 60s 才触发重连 |
| 重试初始间隔 | 3s | 偏长，可缩短到 1s |
| 稳定运行判定 | 60s 后重置重试计数 | 合理但阈值可调 |

修改推流参数时注意：`build_ffmpeg_command` 中 TikTok 和 Shopee 使用不同超时配置，需分别调整。

## 与 live-monitor 的交互规则

| 接口 | 方向 | 用途 |
|------|------|------|
| `POST /get_roominfo` | stream → monitor | 获取待录制房间（携带本机 IP） |
| `POST /report_roominfo` | stream → monitor | 上报在线房间列表和状态，返回需释放的房间 |
| `GET /check_status` | monitor → stream | 健康检查（端口 8080） |

### 交互约束

- 轮询间隔 3 分钟，先上报再获取新房间
- 主备节点通过环境变量 `PRIMARY_NODE_URL` / `BACKUP_NODE_URL` 配置
- 房间释放由 monitor 在 `report_roominfo` 响应中指定 `released_rooms`
- 推流结束后必须从 `online_room_list` 移除房间，否则会导致心跳误报

## 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `PRIMARY_NODE_URL` | 主节点地址 | `http://47.236.42.104:8080` |
| `BACKUP_NODE_URL` | 备用节点地址 | `http://47.237.6.199:8080` |
| `APOLLO_URL` | Apollo 配置中心地址 | 无默认值 |
| `APOLLOID` | Apollo 应用 ID | 硬编码为 `live-spider` |

## 编码注意事项

- 单文件架构（TT_client.py ~1280 行），修改前通读相关模块
- 全局变量 `online_room_list` 和 `MainHelperObj` 在 `__main__` 中初始化，被多线程共享
- `online_room_list` 是普通 dict，多线程读写存在竞态风险（已知技术债）
- 文件就绪判断：修改时间超过 2 秒 + 排除最后一个文件（可能正在写入）
- 切割产物文件名格式：`xxx_NNNNN.MMMMM.ts`，需与原始切片区分
