# live-platform

> 合并 `live-monitor` 与 `live-stream` 的 Phase 1 新服务：房间检测、显式状态机、FFmpeg 协议转换、MediaMTX 录制回调、OSS 上传、Kafka 推送。

## 项目结构

```text
services/live-platform/
├── main.py                         # FastAPI 与调度器入口
├── Dockerfile                      # live-platform 镜像构建（含 FFmpeg）
├── docker-compose.yml              # MediaMTX + live-platform 编排（host 网络）
├── .dockerignore
├── config/
│   └── mediamtx.yml                # MediaMTX 配置（bind mount 进容器）
├── docs/
│   ├── architecture-flow.md        # 整体架构流程图
│   ├── deployment-guide.md         # dev 部署指南
│   └── verification-checklist.md   # 部署后检验清单
├── api/
│   ├── internal.py                 # MediaMTX 内部回调接口
│   └── routes.py                   # 对外兼容接口
├── adapters/
│   ├── lazada.py                   # Lazada 取流适配
│   ├── shopee.py                   # Shopee 取流适配
│   └── tiktok.py                   # TikTok 取流适配
├── utils/
│   ├── TiktokTool.py               # TikTok 旧取流工具本地副本
│   ├── ShopeeTool.py               # Shopee 旧取流工具本地副本
│   ├── LazadaTool.py               # Lazada 旧取流工具本地副本
│   ├── api_response.py             # 兼容接口响应翻译层
│   └── downloader/                 # TikTok HTTP 下载器与代理策略
├── ffmpeg/
│   └── relay.py                    # FFmpeg relay 进程管理
├── orchestrator/
│   ├── mediamtx_client.py          # MediaMTX API 客户端
│   ├── scheduler.py                # 房间检测调度
│   └── state_machine.py            # 房间状态机
├── shared/
│   ├── apollo_config.py            # 固定 Apollo dev 配置读取
│   ├── config.py                   # Apollo-only 配置校验
│   ├── redis_store.py              # Redis 房间清单与状态仓储
│   ├── db.py                       # Redis 仓储兼容导出
│   ├── logger.py                   # 日志配置
│   └── models.py                   # 状态与任务模型
├── upload/
│   ├── coordinator.py              # 上传与 Kafka 编排
│   ├── kafka_worker.py             # Kafka 元数据推送
│   └── oss_worker.py               # OSS 上传 worker
├── tests/                          # 单元与集成测试
└── requirements.txt
```

## 启动

配套文档：

- [整体架构流程图](docs/architecture-flow.md)
- [dev 部署指南](docs/deployment-guide.md)
- [部署后检验清单](docs/verification-checklist.md)

### 推荐：Docker Compose（生产与联调）

依据 ADR `docs/specs/2026-05-10-mediamtx-deployment-adr.md`，Phase 1 统一使用 Docker Compose + `network_mode: host` + bind mount：

```bash
# 宿主机首次准备目录
sudo mkdir -p /data/recordings /data/live-platform/logs

cd services/live-platform
docker compose up -d
docker compose logs -f live-platform
```

### 本地直跑（仅限开发调试）

```bash
cd services/live-platform
pip install -r requirements.txt
python main.py
```

## Apollo 配置

服务只从 Apollo 读取业务配置，不读取环境变量、不使用业务默认值。Apollo bootstrap 固定在代码中：

| 项 | 值 |
|----|----|
| URL | `http://dev-apollo.tec-develop.com` |
| App ID | `live-spider` |
| Cluster | `dev` |
| Namespace | `application` |

必填 Apollo key：

| key | 说明 |
|-----|------|
| `livePlatformHost` / `livePlatformPort` | API 监听地址与端口 |
| `livePlatformDetectIntervalSeconds` | 房间检测间隔 |
| `livePlatformAccessToken` | 兼容接口鉴权 token |
| `mediaMtxApiBaseUrl` / `mediaMtxRtmpBaseUrl` / `mediaMtxRecordRoot` | MediaMTX API、RTMP 前缀、录制根目录 |
| `segmentTimeoutSeconds` | 切片回调健康检查超时 |
| `redisHost` / `redisPort` / `redisPassword` / `redisDb` | Redis 连接 |
| `endpoint` / `bucket_name` / `access_key_id` / `access_key_secret` | OSS 配置，沿用 live-stream 旧 key |
| `ossPrefix` / `ossSignedUrlTtlSeconds` | OSS 对象前缀与签名 URL TTL |
| `kafkaPro` | Kafka broker 列表，支持 `['host1:9092']` 字符串列表 |
| `kafkaAddress` | `kafkaPro` 缺失时的兼容 key |
| `topic_name` | Kafka topic |
| `cutliveNumber` | 单实例最大活跃录制并发 |
| `uploadWorkerCount` | 上传 worker 数 |
| `livePlatformLogDir` | 日志目录 |

## Redis 结构

房间种子由外部服务提前写入：

| Redis key | 类型 | 字段 |
|-----------|------|------|
| `live:monitor:collections` | Set | 成员为 `collectionId` |
| `live:collection:{collectionId}:config` | Hash | `collectionId`、`platform`、`roomUrl`、`enabled` |

状态由 `live-platform` 写入：

| Redis key | 类型 | 主要字段 |
|-----------|------|----------|
| `live:collection:{collectionId}:status` | Hash | `collectionId`、`isLive`、`roomId`、`flvUrl`、`platform`、`roomUrl`、`status`、`mediamtxPath`、`updatedAt` |

## 常用命令

```bash
cd services/live-platform && pytest
cd services/live-platform && curl http://localhost:8080/health
```
