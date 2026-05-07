# live-platform

> 合并 `live-monitor` 与 `live-stream` 的 Phase 1 新服务：房间检测、显式状态机、FFmpeg 协议转换、MediaMTX 录制回调、OSS 上传、Kafka 推送。

## 项目结构

```text
services/live-platform/
├── main.py                         # FastAPI 与调度器入口
├── api/
│   ├── internal.py                 # MediaMTX 内部回调接口
│   └── routes.py                   # 对外兼容接口
├── adapters/
│   ├── lazada.py                   # Lazada 取流适配
│   ├── shopee.py                   # Shopee 取流适配
│   └── tiktok.py                   # TikTok 取流适配
├── ffmpeg/
│   └── relay.py                    # FFmpeg relay 进程管理
├── orchestrator/
│   ├── mediamtx_client.py          # MediaMTX API 客户端
│   ├── scheduler.py                # 房间检测调度
│   └── state_machine.py            # 房间状态机
├── shared/
│   ├── config.py                   # 统一配置
│   ├── db.py                       # 房间仓储
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

```bash
cd services/live-platform
pip install -r requirements.txt
python main.py
```

## 核心环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LIVE_PLATFORM_PORT` | `8080` | API 端口 |
| `LIVE_DETECT_INTERVAL_SECONDS` | `60` | 房间检测间隔 |
| `LIVE_PLATFORM_ACCESS_TOKEN` | `AFDD0B4AD2EC172C586E2150770FBF9E` | 兼容接口鉴权 token |
| `LIVE_PLATFORM_SQLITE_PATH` | `data/live-platform.sqlite3` | 本地房间表 SQLite 路径 |
| `MEDIAMTX_API_BASE_URL` | `http://127.0.0.1:9997` | MediaMTX API |
| `MEDIAMTX_RTMP_BASE_URL` | `rtmp://127.0.0.1:1935/live` | FFmpeg 推给 MediaMTX 的 RTMP 前缀 |
| `SEGMENT_TIMEOUT_SECONDS` | `30` | 切片回调健康检查超时 |
| `OSS_*` | 空 | OSS 上传配置 |
| `KAFKA_BOOTSTRAP_SERVERS` | 空 | Kafka broker 列表，逗号分隔 |

## 常用命令

```bash
cd services/live-platform && pytest
cd services/live-platform && curl http://localhost:8080/health
```
