# Live Platform Phase 1:MediaMTX 录制架构

> **状态**:代码实施完成 ✅,待真实 MediaMTX / 压测 / 生产验证 ⏳
> **开始日期**:2026-05-07
> **预计完成**:2026-05-21(2 周)
> **负责人**:XBW + Claude
> **范围**:只合并 `live-monitor` + `live-stream`,`live-crawler` 不动
> **关联**:顶层架构精简方案见 [`2026-05-06-architecture-simplification.md`](2026-05-06-architecture-simplification.md);MediaMTX 部署方式见 [`../specs/2026-05-10-mediamtx-deployment-adr.md`](../specs/2026-05-10-mediamtx-deployment-adr.md)

---

## 0. 已完成的实施

已在 `codex/live-platform-phase1` 分支完成仓库内可执行部分:

- 新建 `services/live-platform/` 服务骨架,含 FastAPI 入口、配置、日志、SQLite 房间仓储、README 与 CLAUDE 约束文档
- 实现显式房间状态机、健康检查、断流重连、资源清理、FFmpeg relay 进程管理与 MediaMTX API 客户端
- 实现调度器、TikTok/Shopee/Lazada 取流适配入口、OSS worker、Kafka worker、上传编排、对外兼容 API、内部切片回调 API
- 状态机、调度器、FFmpeg、上传编排、API、端到端链路单测通过(`12 passed`)

仍需在真实环境执行:

- MediaMTX Docker Compose 部署、录制 hook 配置、API/metrics 联通验证
- 真实 OSS、Kafka、平台直播 URL 的端到端录制验证
- 80 路并发 24 小时压力测试、生产部署、3 天观察、旧服务下线

---

## 1. 背景与设计(原 design)

### 1.1 现有架构问题

```
live-monitor (5min 房间检测轮询)
     ↓ HTTP 轮询
live-stream (3min 录制状态轮询)
     ↓ FFmpeg subprocess
  录制文件
     ↓ 文件系统轮询(1s)
  OSS 上传
```

| 问题 | 影响 | 根因 |
|------|------|------|
| 开播检测延迟 8 分钟 | 用户体验差 | 两层轮询叠加(5min + 3min) |
| 断流重连成功率 < 90% | 数据丢失 | 参数保守 + 状态不一致 |
| 80 路并发线程暴涨 | 资源耗尽 | 每房间一线程 + 共享 dict 无锁 |
| 上传阻塞影响录制判断 | 雪崩风险 | 录制/上传/状态耦合在同一进程 |
| 状态不一致 | 排障困难 | monitor 和 stream 各维护一份 |
| 文件系统轮询开销 | CPU 浪费 | 每秒扫描目录判断文件就绪 |

### 1.2 新架构核心变化

- 录制底座从 FFmpeg 直接管理改为 **MediaMTX**
- Python 层从"录制管理器"降级为"编排器"
- 房间状态从"隐式推断"改为"显式状态机"
- 上传触发从"文件系统轮询"改为"MediaMTX 切片回调推送"
- 服务间 HTTP 轮询改为"单进程内函数调用"

### 1.3 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│  services/live-platform/                                     │
│                                                              │
│  ┌─────────────────┐      ┌──────────────────────────────┐ │
│  │  MediaMTX       │      │  Python Orchestrator         │ │
│  │  (录制底座)      │◄─────│  (编排层)                    │ │
│  │  拉流/录制/切片  │ API  │  状态机/调度/Upload/Kafka     │ │
│  └─────────────────┘      └──────────────────────────────┘ │
│         │ 切片回调(HTTP POST)        ▲                     │
│         └─────────────────────────────┘                     │
│                                                              │
│  ┌─────────────────┐      ┌──────────────────────────────┐ │
│  │  FFmpeg 进程池   │      │  streamlink / yt-dlp(备选)  │ │
│  │  (协议转换:FLV→RTMP) │   │                              │ │
│  └─────────────────┘      └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

| 组件 | 职责 | 不负责 |
|------|------|--------|
| MediaMTX | 拉流、录制、切片、协议处理、metrics | 业务逻辑、上传、Kafka |
| FFmpeg | HTTP-FLV → RTMP 协议转换(薄层) | 录制管理、切片、健康检查 |
| Python Orchestrator | 房间调度、状态机、API 编排、上传、Kafka | 媒体处理 |
| streamlink / yt-dlp | TikTok / Shopee URL 提取(备选) | 录制 |

### 1.4 目录结构

```
services/live-platform/
├── main.py                     # 进程入口
├── orchestrator/
│   ├── scheduler.py            # 房间检测调度(每 60s)
│   ├── state_machine.py        # 每房间显式状态机
│   └── mediamtx_client.py      # MediaMTX API 交互
├── ffmpeg/relay.py             # FFmpeg 协议转换管理
├── upload/
│   ├── oss_worker.py           # 独立上传 worker
│   ├── kafka_worker.py         # Kafka 推送 worker
│   └── coordinator.py          # 串行编排
├── adapters/{tiktok,shopee,lazada}.py  # 取流适配
├── api/{routes,internal}.py    # 对外 API + MediaMTX 回调
├── shared/{config,db,models,logger}.py
└── tests/
```

## 2. 房间状态机设计

### 2.1 状态转换图

```
┌───────┐  检测到开播   ┌──────────┐  FFmpeg+MediaMTX就绪  ┌───────────┐
│ idle  │ ──────────→ │ starting │ ──────────────────→ │ recording │
└───────┘              └──────────┘                      └───────────┘
    ↑                      │                                │    │
    │                 启动失败                          断流检测  正常下播
    │                      ↓                                ↓    │
    │                ┌──────────┐                    ┌─────────────┐
    │                │  failed  │                    │reconnecting │
    │                └──────────┘                    └─────────────┘
    │                      │                                │
    │                超过最大重试                      重连成功→recording
    │                      │                          重连失败→failed
    │                      ↓
    │                ┌──────────┐
    └─── 冷却结束 ←─ │ cooldown │
                     └──────────┘
```

### 2.2 状态转换表

| 当前状态 | 事件 | 下一状态 | 动作 |
|----------|------|----------|------|
| `idle` | 检测到开播 | `starting` | 获取 FLV URL,启动 FFmpeg + MediaMTX path |
| `starting` | path 就绪 | `recording` | 开始接收切片回调 |
| `starting` | 启动超时/失败 | `failed` | 清理资源,记录错误 |
| `recording` | 切片回调 | `recording` | 更新 last_active 时间戳 |
| `recording` | 无数据超时(30s) | `reconnecting` | 杀 FFmpeg,重新获取 URL |
| `recording` | 主播下播 | `idle` | 清理 path,上传剩余切片 |
| `reconnecting` | 新 URL 成功 | `starting` | 重启 FFmpeg |
| `reconnecting` | 重试耗尽 | `failed` | 清理资源,飞书告警 |
| `failed` | — | `cooldown` | 进入冷却期(避免雪崩) |
| `cooldown` | 冷却结束(60s) | `idle` | 重新进入调度池 |

### 2.3 与现有 TT_client.py 的本质区别

| 维度 | 现有 TT_client.py | 新状态机 |
|------|-------------------|----------|
| 状态存储 | 共享 dict 无锁 | 每房间独立 dataclass |
| 状态推断 | 靠目录文件是否存在 | 显式状态 + 时间戳 |
| 健康判断 | 扫描本地目录 | MediaMTX 切片回调 + metrics |
| 断流感知 | 心跳线程轮询 | `last_active` 超时检测 |
| 并发模型 | 每房间一线程 | asyncio 事件循环 + 进程池 |

## 3. MediaMTX 集成关键决策

### 3.1 切片回调驱动上传

```yaml
# config/mediamtx.yml
pathDefaults:
  record: yes
  recordFormat: fmp4
  recordPartDuration: 1s
  recordSegmentDuration: 10s
  recordPath: /data/recordings/%path/%Y-%m-%d_%H-%M-%S-%f
  runOnRecordSegmentComplete: >
    curl -X POST http://localhost:8080/internal/segment-ready
    -H "Content-Type: application/json"
    -d '{"path":"$MTX_PATH","file":"$MTX_SEGMENT_PATH","duration":"$MTX_SEGMENT_DURATION"}'
```

> **设计决策**:`recordSegmentDuration: 10s`(非 1h)。原因:
> 1. 切片回调是状态机健康信号(`last_active` 更新源),超时阈值 30s,回调频率必须高于超时频率
> 2. 与现有系统 8s 切片对齐,每切片一上传单元
> 3. 短切片降低断流时数据丢失窗口(最多丢 10s)

### 3.2 HTTP-FLV 拉流限制

**关键限制**:MediaMTX 不原生支持 HTTP-FLV 拉流。

**解决方案**:FFmpeg 做薄层协议转换 `FLV → RTMP push 到 MediaMTX`,只 `-c copy` 转封装。

```python
async def start_ffmpeg_relay(flv_url: str, mediamtx_path: str) -> int:
    rtmp_target = f"rtmp://localhost:1935/live/{mediamtx_path}"
    command = ["ffmpeg", "-i", flv_url, "-c", "copy", "-f", "flv", rtmp_target]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return process.pid
```

> **设计决策**:stdout/stderr 重定向到 DEVNULL 而非 PIPE。原因:长时间运行的 FFmpeg relay 会持续输出日志到 stderr,如果用 PIPE 但不消费,OS pipe buffer(64KB)满后 FFmpeg 阻塞,导致录制中断。如需排障改重定向到日志文件配合 logrotate。

### 3.3 部署方式

部署方式于 2026-05-10 由 "Native Linux + systemd" 调整为 **Docker Compose + `network_mode: host` + bind mount**,详见 [`../specs/2026-05-10-mediamtx-deployment-adr.md`](../specs/2026-05-10-mediamtx-deployment-adr.md)。

---

## 4. Phase 0:准备工作(1 天)

### 4.1 部署 MediaMTX(Docker Compose)

- [ ] **准备宿主机目录与文件系统**
  ```bash
  sudo mkdir -p /data/recordings /data/live-platform/db
  # 推荐 XFS + noatime
  sudo chown -R 1000:1000 /data/recordings /data/live-platform
  ```

- [ ] **`services/live-platform/docker-compose.yml`**
  - [ ] MediaMTX 与 live-platform 均 `network_mode: host`
  - [ ] `image: bluenviron/mediamtx:1.9.3-ffmpeg`(精确版本,禁 `:latest`)
  - [ ] bind mount `/data/recordings:/data/recordings`、`./config/mediamtx.yml:/mediamtx.yml:ro`
  - [ ] `ulimits.nofile: 65536`、`restart: unless-stopped`、`logging.max-size: 50m`

- [ ] **`config/mediamtx.yml`**
  - [ ] `api: yes, apiAddress: 127.0.0.1:9997`
  - [ ] `metrics: yes, metricsAddress: 127.0.0.1:9998`
  - [ ] `recordPath: /data/recordings/%path/%Y-%m-%d_%H-%M-%S-%f`
  - [ ] `recordSegmentDuration: 10s`(对齐健康检查超时 30s)
  - [ ] `writeQueueSize: 2048`(80 路并发防 write queue full)
  - [ ] `readTimeout: 30s` / `writeTimeout: 30s`
  - [ ] `runOnRecordSegmentComplete` 指向 `http://localhost:8080/internal/segment-ready`

- [ ] **启动并验证**
  ```bash
  cd services/live-platform
  docker compose up -d mediamtx
  docker compose ps                                    # running (healthy)
  docker compose logs --tail=100 mediamtx
  curl http://localhost:9997/v3/paths/list
  curl http://localhost:9998/metrics
  ```

- [ ] **开机自启**:`sudo systemctl enable --now docker`(已配置 `restart: unless-stopped`)

### 4.2 准备开发环境

- [ ] 创建项目目录:`mkdir -p services/live-platform/{orchestrator,ffmpeg,upload,adapters,api,shared,tests}`
- [ ] `requirements.txt` + `pip install -r requirements.txt`
- [ ] `Dockerfile`(基于 `python:3.12-slim`,分层缓存)、`.dockerignore`、`docker-compose.yml`(host 网络)、`config/mediamtx.yml`
- [ ] 自检:`docker compose config && docker compose build`

---

## 5. Phase 1:搭建骨架(1 天)✅ 代码完成

- [x] **1.1 主入口 `main.py`**:APScheduler + FastAPI + uvicorn,`detect_rooms` 60s 间隔,挂载 `routes` 与 `internal_router`(`/internal` 前缀)
- [x] **1.2 配置模块 `shared/config.py`**:MediaMTX / 数据库 / OSS / Kafka 配置
- [x] **1.3 数据模型 `shared/models.py`**:`Status` 枚举、`RoomState` dataclass、`SegmentTask` dataclass
- [x] **1.4 日志模块 `shared/logger.py`**:loguru,文件 + stdout 双输出

---

## 6. Phase 2:房间状态机(2 天)✅ 代码完成

- [x] **2.1 状态机核心 `orchestrator/state_machine.py`**:`RoomState` + `StateManager` + 状态转换方法(`on_live_detected`、`on_recording_started`、`on_segment_received`、`on_stream_timeout`、`on_reconnect_success`、`on_reconnect_failed`、`on_stream_ended`)
- [x] **2.2 健康检查**:`StateManager` 定期检查 `last_active` 超时,自动进入 `reconnecting`
- [x] **2.3 单元测试 `tests/test_state_machine.py`**:状态转换、超时检测、重试逻辑

---

## 7. Phase 3:调度器与取流适配(2 天)✅ 代码完成

- [x] **3.1 调度器 `orchestrator/scheduler.py`**:`detect_rooms()` 查询 DB → 遍历房间 → 对 `idle` 调用适配器 → 推进状态机
- [x] **3.2 取流适配器**:从 `live-monitor` 迁移
  - [x] `adapters/tiktok.py` ← `TiktokTool.getLiveStreamInfo()`
  - [x] `adapters/shopee.py` ← `ShopeeTool.getLiveStreamInfo()`
  - [x] `adapters/lazada.py` ← `LazadaTool.getLiveStreamInfo()`
- [x] **3.3 测试**:`tests/test_scheduler.py` + `tests/test_adapters.py`

---

## 8. Phase 4:FFmpeg 协议转换(1 天)✅ 代码完成

- [x] **4.1 `ffmpeg/relay.py`**:`start_ffmpeg_relay(flv_url, mediamtx_path)` / `stop_ffmpeg_relay(pid)` / `is_ffmpeg_alive(pid)`,asyncio 子进程
- [x] **4.2 集成状态机**:`on_live_detected` 启动 relay,`on_stream_timeout/ended` 杀进程
- [x] **4.3 测试 `tests/test_ffmpeg_relay.py`**:启动、进程管理

---

## 9. Phase 5:MediaMTX 客户端(1 天)✅ 代码完成

- [x] **5.1 `orchestrator/mediamtx_client.py`**:`add_path(room_id, rtmp_source)` / `remove_path(room_id)` / `list_active_paths()` / `get_path_info(room_id)`,httpx 异步客户端
- [x] **5.2 集成状态机**:`on_live_detected` → `add_path`,`on_stream_ended` → `remove_path`
- [x] **5.3 测试 `tests/test_mediamtx_client.py`**:API 调用、错误处理

---

## 10. Phase 6:上传与 Kafka worker(2 天)✅ 代码完成

- [x] **6.1 OSS 上传 worker `upload/oss_worker.py`**:从 `live-stream` 迁移 `AiyunOBSHelper`,异步上传队列、失败重试、上传成功后删本地文件
- [x] **6.2 Kafka 推送 worker `upload/kafka_worker.py`**:迁移 `KafkaHelper`,失败重试
- [x] **6.3 上传编排 `upload/coordinator.py`**:队列 + worker 池 + 上传 → Kafka 串行
- [x] **6.4 测试 `tests/test_upload.py`**:OSS、Kafka、编排

---

## 11. Phase 7:API 与内部接口(1 天)✅ 代码完成

- [x] **7.1 对外 API `api/routes.py`**:`GET /health`、`POST /liveRoom/{portInfo,shopeeInfo,lazadaInfo}`、`GET /docs/{doc,getConfig}`
- [x] **7.2 内部接口 `api/internal.py`**:`POST /internal/segment-ready`,接收 MediaMTX 切片回调 → 更新 `last_active` + 推上传队列
- [x] **7.3 测试 `tests/test_api.py`**

---

## 12. Phase 8:集成测试(2 天)✅ 本地通过 / ⏳ 真实环境待验证

- [x] **8.1 端到端 `tests/test_integration.py`**:调度器 → FFmpeg relay → MediaMTX 录制 → 切片回调 → OSS → Kafka → 主播下播清理
- [ ] **8.2 断流重连**:杀 FFmpeg → 验证状态机 `reconnecting` → 重启 → 录制恢复(真实环境)
- [ ] **8.3 异常场景**:MediaMTX 挂掉、OSS / Kafka 失败、DB 连接失败,验证飞书告警

---

## 13. Phase 9:压力测试(1 天)⏳ 真实环境待执行

- [ ] **9.1 准备数据**:DB 插入 80 个测试房间 + 80 个模拟流
- [ ] **9.2 启动测试**:同时启动 80 路录制,运行 24 小时
- [ ] **9.3 监控指标**(目标):
  - CPU < 80%、内存 < 20 GB、带宽 < 500 Mbps、磁盘 I/O < 100 MB/s
  - `mediamtx_paths_count` = 80
- [ ] **9.4 稳定性**:无进程崩溃、无内存泄漏、无 fd 耗尽、断流重连 > 95%
- [ ] **9.5 Native vs Docker 对比**:相同负载 2 小时,Docker 各项指标劣化 < 5%,结果回写 ADR 的"下次复审"

---

## 14. Phase 10:生产部署(1 天)⏳ 真实环境待执行

> 部署方式:Docker Compose + `network_mode: host` + bind mount。详见 [`../specs/2026-05-10-mediamtx-deployment-adr.md`](../specs/2026-05-10-mediamtx-deployment-adr.md)。

### 14.1 准备生产服务器

- [ ] 安装 Docker:`curl -fsSL https://get.docker.com | sh && sudo systemctl enable --now docker`
- [ ] 准备目录:`sudo mkdir -p /data/recordings /data/live-platform/{db,logs} && sudo chown -R 1000:1000 /data/recordings /data/live-platform`
- [ ] 拉代码:`git clone <repo> /opt/live-platform && cd /opt/live-platform/services/live-platform`
- [ ] 准备 `.env`:`cp .env.example .env && vim .env`(填 OSS / Kafka / DB 真实配置)

### 14.2 构建与启动

```bash
cd /opt/live-platform/services/live-platform
docker compose build live-platform
docker compose up -d
docker compose ps                                    # 两服务均 running (healthy)
```

### 14.3 验证部署

```bash
docker compose logs --tail=100 mediamtx
docker compose logs --tail=100 live-platform
curl http://localhost:8080/health
curl http://localhost:9997/v3/paths/list
curl http://localhost:9998/metrics
```

### 14.4 灰度放量

- [ ] 10 路 → 观察 2 小时,确认切片回调、OSS、Kafka 正常
- [ ] 40 路 → 观察 4 小时,资源占用线性增长无异常
- [ ] 80 路 → 观察 24 小时,全量稳定

### 14.5 观察 3 天

- [ ] 每天 `docker compose logs --since 24h`
- [ ] 监控断流率、`docker stats`、`df -h /data/recordings`
- [ ] 验证开播检测延迟 < 60s、断流重连成功率 > 95%

---

## 15. Phase 11:下线旧服务(待 Phase 10 稳定后)

- [ ] **11.1 归档旧代码**
  ```bash
  mv services/live-monitor docs/archive/live-monitor-deprecated
  mv services/live-stream  docs/archive/live-stream-deprecated
  ```

- [ ] **11.2 更新文档**
  - [ ] 根 `CLAUDE.md`:删除 live-monitor / live-stream 描述,添加 live-platform
  - [ ] 根 `README.md`:更新架构图、启动命令
  - [ ] 创建 `services/live-platform/CLAUDE.md` + `README.md`

- [ ] **11.3 提交代码**
  ```bash
  git checkout -b feature/live-platform-phase1
  git add services/live-platform docs/specs/2026-05-10-mediamtx-deployment-adr.md docs/plans/2026-05-07-live-platform-phase1.md
  git commit -m "feat: Phase 1 - 合并 live-monitor + live-stream,采用 MediaMTX 录制架构"
  git push origin feature/live-platform-phase1
  # 创建 PR:Phase 1: 合并 live-monitor + live-stream,采用 MediaMTX 录制架构
  ```

---

## 16. 里程碑

| 日期 | 里程碑 | 交付物 | 状态 |
|------|--------|--------|------|
| 2026-05-08 | MediaMTX 部署完成 | 服务运行,API 可用 | ⏳ |
| 2026-05-10 | 状态机与调度器完成 | 房间检测与状态管理 | ✅ |
| 2026-05-13 | 录制链路打通 | FFmpeg + MediaMTX 录制 | ✅(本地) |
| 2026-05-15 | 上传链路打通 | OSS + Kafka 推送 | ✅(本地) |
| 2026-05-17 | 集成测试通过 | 端到端验证 | ✅(本地) |
| 2026-05-18 | 压力测试通过 | 80 路并发 24h 稳定 | ⏳ |
| 2026-05-21 | 生产部署完成 | live-platform 上线 + 观察 3 天 | ⏳ |

---

## 17. 成功指标

| 指标 | 当前 | 目标 | 验证方式 |
|------|------|------|---------|
| 开播检测延迟 | 8 分钟 | 60 秒 | 端到端测试 |
| 断流重连成功率 | < 90% | > 95% | 监控日志统计 |
| 服务数 | 4 个 | 3 个 | 部署清单 |
| 80 路并发稳定性 | 未验证 | 24 小时无故障 | 压力测试 |
| 代码量 | ~32,000 行 | ~19,000 行 | `wc -l` |

---

## 18. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| MediaMTX 不支持 HTTP-FLV | 高 | FFmpeg 协议转换(已验证) |
| 80 路并发 write queue full | 中 | `writeQueueSize: 1024+` |
| 状态机 bug 卡死房间 | 中 | 超时自动清理 + 飞书告警 |
| 一次性切换风险 | 高 | 充分测试 + 灰度 + 回滚预案 |

---

## 19. 回滚方案

```bash
# 立即回滚
cd /opt/live-platform/services/live-platform
docker compose down
git checkout main
cd services/live-monitor && python main.py &
cd services/live-stream  && bash start.sh &

# 收集日志用于排查
docker compose logs --since 1h > /tmp/live-platform-crash.log 2>&1
```

回滚后:检查旧服务运行 → 验证核心功能 → 通知团队。

---

## 20. 注意事项

1. 每个 Phase 完成后必须验证核心功能正常
2. 压力测试通过才能部署生产
3. 保留旧代码备份至少 1 个月
4. 每次修改前先建 git 分支
5. 重要操作先在测试环境验证

---

**文档结束**
