# live-platform dev 部署指南

本文面向 Zadig dev 环境。Apollo dev 配置已完成，服务启动时会固定读取：

```text
http://dev-apollo.tec-develop.com/configs/live-spider/dev/application
```

## 前置条件

| 项 | 要求 |
|----|------|
| Apollo | `live-spider / dev / application` 已配置完整 |
| Redis | `redisHost` / `redisPort` / `redisPassword` / `redisDb` 可从 Pod 访问 |
| MediaMTX | 与 live-platform 同机或同网络，API 与 RTMP 地址和 Apollo 配置一致 |
| 存储目录 | 宿主机存在 `/data/recordings` 和 `/data/live-platform/logs` |
| OSS / Kafka | Apollo 中的 OSS 与 Kafka 配置可用 |

## 构建与部署

### Zadig 部署

1. 选择 `services/live-platform` 对应服务。
2. 使用当前代码构建镜像。
3. 确认镜像内包含：
   - Python 3.12
   - FFmpeg（仅用于 `HTTP-FLV -> RTMP` relay）
   - Node.js / npm
   - `services/live-platform/utils/`
4. 部署到 dev 环境。
5. 查看容器日志，确认启动后没有 `ConfigError`。

### Docker Compose 本地服务器部署

```bash
sudo mkdir -p /data/recordings /data/live-platform/logs

cd services/live-platform
docker compose build
docker compose up -d
docker compose logs -f live-platform
```

容器启动顺序:MediaMTX 健康探针通过后才启动 live-platform(`depends_on.condition: service_healthy`)。当前 `docker-compose.yml` 不再注入业务环境变量；业务配置只从 Apollo 读取。

## Redis Seed 写入格式

外部服务需要提前写入监控房间 seed。

```bash
redis-cli SADD live:monitor:collections coll_1001

redis-cli HSET live:collection:coll_1001:config \
  collectionId coll_1001 \
  platform tiktok \
  roomUrl "https://www.tiktok.com/@demo/live" \
  enabled 1
```

字段说明：

| 字段 | 必填 | 说明 |
|------|------|------|
| `collectionId` | 是 | 主键，需与 Set 成员一致 |
| `platform` | 是 | `tiktok` / `shopee` / `lazada` |
| `roomUrl` | 是 | 直播间 URL |
| `enabled` | 是 | `1` 表示启用；`0` / `false` / `off` 表示禁用 |

## 运行时链路

1. `main.py` 启动时预加载 Apollo 配置(避免首次访问阻塞 event loop),然后启动 FastAPI、Scheduler、Upload worker。
2. Scheduler 按 `livePlatformDetectIntervalSeconds` 周期扫描 Redis seed。
3. `adapters.get_stream_info()` 调用本地 `utils/*Tool.py` 获取 `flv_url` 和 `roomId`。
4. 开播时，如果活跃录制数小于 `cutliveNumber`，先添加 MediaMTX path，再启动 FFmpeg relay。
5. FFmpeg relay 只把 HTTP-FLV 转推成 RTMP publisher；MediaMTX recorder 负责录制、切片和写入 `/data/recordings`。
6. 每轮检测都会写入 `live:collection:{collectionId}:status`。
7. MediaMTX 完成切片后调用 `/internal/segment-ready`。
8. Upload worker 先上传 OSS,再推送 Kafka(payload 含 `dataSource: live_crawler_{platform}`)。

## 关键日志

| 日志片段 | 含义 |
|----------|------|
| `live-platform 已启动` | 服务启动完成 |
| `房间检测完成` | Scheduler 已执行一轮 |
| `MediaMTX path 已添加` | MediaMTX 已接受录制 path 配置 |
| `启动 FFmpeg relay` | 已启动协议转换进程，输出目标是 MediaMTX RTMP，不是本地文件 |
| `录制已开始` | 状态机已进入 recording，等待 MediaMTX 切片回调刷新健康时间 |
| `收到切片回调` | MediaMTX 回调正常 |
| `切片处理完成` | OSS 上传与 Kafka 推送完成 |
| `Apollo 缺少必填配置` | Apollo 配置缺 key，需补配置后重启 |

MediaMTX 日志中的 `[recorder] recording ...` 才表示实际录制落盘开始。`runOnRecordSegmentComplete command launched` 只表示 MediaMTX 启动了回调命令；如果 live-platform 没有出现 `收到切片回调`，优先在 MediaMTX 容器内检查 `curl http://127.0.0.1:8080/health` 和手动 POST `/internal/segment-ready` 是否成功。

## 回滚

1. Zadig 回滚到上一版本镜像。
2. 如 Redis status 写入异常，可临时停止 `live-platform`，Redis seed 不需要删除。
3. 如果已启动 FFmpeg relay 或 MediaMTX path，回滚前确认旧 Pod 已停止，避免同一 collectionId 被重复转推和录制。

## 不在本轮范围

- 不实现 `POST /api/v1/tiktok/live-status/batch` HTTP 路由。
- 不做 Redis 不可用时的内存 fallback。
- 不从环境变量读取业务配置。
