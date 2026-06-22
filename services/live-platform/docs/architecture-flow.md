# live-platform 架构流程图

本文描述 `services/live-platform` 当前 dev 部署后的完整数据流。配置统一从 Apollo dev 读取；房间种子由 MySQL 同步到 Redis，开播状态统一落 Redis。录制链路中，FFmpeg 只做 `HTTP-FLV -> RTMP` relay，MediaMTX 负责 recorder、切片落盘和切片完成回调，后续由 OSS + Kafka 交付。

## 总览

```mermaid
flowchart LR
    subgraph deploy [部署与配置]
        zadig["Zadig dev 部署"]
        pod["live-platform 容器"]
        mediamtx["MediaMTX 容器"]
        apollo["Apollo dev<br/>live-spider / dev / application"]
    end

    subgraph redis_layer [Redis 状态中心]
        seed_set["live:monitor:collections<br/>Set(collectionId)"]
        room_config["live:collection:{id}:config<br/>platform / roomUrl / enabled"]
        room_status["live:collection:{id}:status<br/>isLive / roomId / flvUrl"]
    end

    subgraph detect [检测与状态机]
        scheduler["Scheduler<br/>detect_rooms"]
        adapter["adapters.get_stream_info"]
        tools["本地 utils Tool<br/>Tiktok / Shopee / Lazada"]
        upstream["平台直播页 / 上游接口"]
        state["StateManager<br/>collectionId 状态机"]
    end

    subgraph record [录制与交付]
        ffmpeg["FFmpeg relay<br/>HTTP-FLV -> RTMP publisher"]
        recorder["MediaMTX recorder"]
        disk["/data/recordings"]
        segment_api["POST /internal/segment-ready"]
        upload["UploadCoordinator"]
        oss["OSS"]
        kafka["Kafka topic"]
    end

    future["后续 live-monitor<br/>live-status/batch"]

    zadig --> pod
    zadig --> mediamtx
    apollo -->|启动加载配置| pod

    seed_set -->|读取 collectionId| scheduler
    scheduler -->|读取 seed 详情| room_config
    scheduler --> adapter
    adapter --> tools
    tools --> upstream
    scheduler -->|每轮写状态| room_status
    scheduler --> state

    state -->|add path| mediamtx
    state -->|未超过 cutliveNumber 时启动 relay| ffmpeg
    ffmpeg -->|publish RTMP| mediamtx
    mediamtx --> recorder
    recorder -->|录制切片| disk
    recorder -->|切片完成回调| segment_api
    segment_api --> state
    segment_api --> upload
    upload --> oss
    upload --> kafka

    future -.->|读取开播状态| room_status
```

图例：实线表示当前运行链路；虚线表示后续 `live-monitor` 接口复用的读取链路。FFmpeg relay 不写本地录制文件，只把平台 HTTP-FLV 流转推给 MediaMTX。Redis `config` 是房间 seed，Redis `status` 由 `live-platform` 每轮检测后写入。

## 启动与配置流

```mermaid
sequenceDiagram
    participant Zadig
    participant App as live-platform
    participant Apollo as Apollo dev
    participant Redis

    Zadig->>App: 部署容器
    App->>Apollo: GET /configs/live-spider/dev/application
    Apollo-->>App: 返回 Apollo 配置
    App->>App: 校验必填 key
    alt 缺 key 或格式错误
        App-->>Zadig: 启动失败，日志输出 ConfigError
    else 配置完整
        App->>Redis: 连接 Redis
        App->>App: 启动 FastAPI / Scheduler / Upload worker
    end
```

## 房间检测与 Redis 状态流

```mermaid
sequenceDiagram
    participant Scheduler
    participant Redis
    participant Adapter as get_stream_info
    participant State as StateManager
    participant MediaMTX
    participant FFmpeg

    Scheduler->>Redis: SMEMBERS live:monitor:collections
    loop 每个 collectionId
        Scheduler->>Redis: HGETALL live:collection:{collectionId}:config
        Redis-->>Scheduler: platform / roomUrl / enabled
        Scheduler->>Adapter: 按平台获取 stream_info
        Adapter-->>Scheduler: flv_url / roomId / 其他元数据
        Scheduler->>State: ensure_room(collectionId)
        alt flv_url 非空且非 error，且未超过 cutliveNumber
            Scheduler->>State: on_live_detected(collectionId, flv_url, roomId)
            State->>MediaMTX: 添加 path
            State->>FFmpeg: 启动 HTTP-FLV -> RTMP relay
            FFmpeg->>MediaMTX: publish RTMP
            MediaMTX->>MediaMTX: recorder 落盘切片
        else 未开播或容量已满
            Scheduler->>State: 保持或结束对应状态
        end
        Scheduler->>Redis: HSET live:collection:{collectionId}:status
    end
```

## 录制切片与上传流

```mermaid
sequenceDiagram
    participant MediaMTX
    participant API as /internal/segment-ready
    participant State as StateManager
    participant Upload as UploadCoordinator
    participant OSS
    participant Kafka

    MediaMTX->>API: POST path + filePath + duration
    API->>State: on_segment_received(path)
    State-->>API: 返回 collectionId 对应状态
    API->>Upload: enqueue(SegmentTask)
    Upload->>OSS: 上传切片文件
    OSS-->>Upload: signed videoUrl
    Upload->>Kafka: 推送 room_id / file / duration / videoUrl / dataSource
```

如果 MediaMTX 日志持续出现 `runOnRecordSegmentComplete command launched`，但 live-platform 日志没有 `POST /internal/segment-ready` 或 `收到切片回调`，说明 recorder 已经触发回调命令，但回调未成功进入 FastAPI。此时状态机的 `last_active` 不会刷新，会按 `segmentTimeoutSeconds` 进入重连。

## Redis Key

```text
live:monitor:collections
  Set: collectionId

live:collection:{collectionId}:config
  Hash:
    collectionId
    platform
    roomUrl
    enabled

live:collection:{collectionId}:status
  Hash:
    collectionId
    isLive
    roomId
    flvUrl
    platform
    roomUrl
    status
    mediamtxPath
    updatedAt
    lastLiveStart
    lastLiveEnd
    errorMessage
```

## ID 口径

| 名称 | 含义 | 来源 |
|------|------|------|
| `collectionId` | 账号/任务主键，Redis seed 和状态主键 | 外部 seed 写入 Redis |
| `roomId` | 平台真实直播间号 | `utils/*Tool.py` 返回的 `stream_info.roomId` |
| `mediamtxPath` | MediaMTX path，格式为 `{platform}-{collectionId}` | `StateManager` 生成 |

## 并发口径

`cutliveNumber` 映射为单个 `live-platform` 实例的最大活跃录制并发。容量满时，服务仍会检测房间并写 Redis 状态，但不会启动新的 MediaMTX path 或 FFmpeg relay。
