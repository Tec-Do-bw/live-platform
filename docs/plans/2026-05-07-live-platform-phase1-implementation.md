# Live Platform Phase 1 实施计划

> **开始日期：** 2026-05-07  
> **预计完成：** 2026-05-21（2 周）  
> **负责人：** XBW  
> **状态：** 代码实施完成，待真实 MediaMTX / 压测 / 生产验证

## 2026-05-07 执行记录

已在 `codex/live-platform-phase1` 分支完成仓库内可执行部分：

- 新建 `services/live-platform/` 服务骨架，包含 FastAPI 入口、配置、日志、SQLite 房间仓储、README 与 CLAUDE 约束文档。
- 实现显式房间状态机、健康检查、断流进入重连、资源清理、FFmpeg relay 进程管理与 MediaMTX API 客户端。
- 实现调度器、TikTok/Shopee/Lazada 取流适配入口、OSS worker、Kafka worker、上传编排、对外兼容 API 与内部切片回调 API。
- 补齐状态机、调度器、FFmpeg、上传编排、API 与端到端链路单测，已通过 `services/live-platform/.venv/bin/python -m pytest`，结果：`12 passed`。

仍需在真实环境执行：

- MediaMTX Docker Compose 部署、录制 hook 配置与 API/metrics 联通验证。
- 使用真实 OSS、Kafka、平台直播 URL 执行端到端录制验证。
- 80 路并发 24 小时压力测试、生产部署、3 天观察与旧服务下线。

---

## 总览

| 阶段 | 任务 | 时间 | 优先级 | 状态 |
|------|------|------|--------|------|
| 准备 | MediaMTX 部署与验证 | 1 天 | P0 | ⏳ 待真实环境执行 |
| 开发 | 搭建 live-platform 骨架 | 1 天 | P0 | ✅ 代码完成 |
| 开发 | 实现房间状态机 | 2 天 | P0 | ✅ 代码完成 |
| 开发 | 实现调度器与取流适配 | 2 天 | P0 | ✅ 代码完成 |
| 开发 | 实现 FFmpeg 协议转换 | 1 天 | P0 | ✅ 代码完成 |
| 开发 | 实现上传与 Kafka worker | 2 天 | P0 | ✅ 代码完成 |
| 开发 | 实现 API 与内部接口 | 1 天 | P1 | ✅ 代码完成 |
| 测试 | 单元测试与集成测试 | 2 天 | P0 | ✅ 本地通过 |
| 测试 | 端到端验证 | 1 天 | P0 | ⏳ 待真实环境执行 |
| 测试 | 80 路并发压力测试 | 1 天 | P0 | ⏳ 待真实环境执行 |
| 部署 | 生产环境部署与验证 | 1 天 | P0 | ⏳ 待真实环境执行 |

---

## Phase 0：准备工作（1 天）

> **部署方式已于 2026-05-10 由 Native systemd 调整为 Docker Compose + `network_mode: host` + bind mount。** 详见 `docs/designs/2026-05-10-mediamtx-deployment-adr.md`。

### 0.1 部署 MediaMTX（Docker Compose）

- [ ] **准备宿主机目录与文件系统**
  ```bash
  sudo mkdir -p /data/recordings /data/live-platform/db
  # 推荐 XFS + noatime，提升大文件顺序写性能
  sudo chown -R 1000:1000 /data/recordings /data/live-platform
  ```

- [ ] **准备 `docker-compose.yml`（位于 `services/live-platform/`）**
  - [ ] MediaMTX 与 live-platform 均使用 `network_mode: host`，消除 NAT/bridge 开销
  - [ ] `image: bluenviron/mediamtx:1.9.3-ffmpeg`（精确版本，禁用 `:latest`）
  - [ ] bind mount `/data/recordings:/data/recordings`、`./config/mediamtx.yml:/mediamtx.yml:ro`
  - [ ] `ulimits.nofile: 65536`、`restart: unless-stopped`、`logging.max-size: 50m`

- [ ] **准备 `config/mediamtx.yml`**
  - [ ] `api: yes, apiAddress: 127.0.0.1:9997`
  - [ ] `metrics: yes, metricsAddress: 127.0.0.1:9998`
  - [ ] `recordPath: /data/recordings/%path/%Y-%m-%d_%H-%M-%S-%f`
  - [ ] `recordSegmentDuration: 10s`（与健康检查超时 30s 对齐）
  - [ ] `writeQueueSize: 2048`（80 路并发防 write queue full）
  - [ ] `readTimeout: 30s` / `writeTimeout: 30s`
  - [ ] `runOnRecordSegmentComplete` 回调指向 `http://localhost:8080/internal/segment-ready`

- [ ] **启动服务**
  ```bash
  cd services/live-platform
  docker compose up -d mediamtx
  ```

- [ ] **验证 MediaMTX**
  - [ ] 容器状态：`docker compose ps`（`mediamtx` 应为 `running (healthy)`）
  - [ ] 日志：`docker compose logs --tail=100 mediamtx`
  - [ ] API：`curl http://localhost:9997/v3/paths/list`
  - [ ] Metrics：`curl http://localhost:9998/metrics`

- [ ] **开机自启**
  - [ ] 宿主机启用 Docker 服务：`sudo systemctl enable --now docker`
  - [ ] `restart: unless-stopped` 已配置，宿主机重启后容器自动拉起

### 0.2 准备开发环境

- [ ] **创建项目目录**
  ```bash
  mkdir -p services/live-platform/{orchestrator,ffmpeg,upload,adapters,api,shared,tests}
  ```

- [ ] **初始化依赖**
  - [ ] 创建 `requirements.txt`
  - [ ] 安装依赖：`pip install -r requirements.txt`

- [ ] **编写 Docker 构建与编排骨架**
  - [ ] `services/live-platform/Dockerfile`（基于 `python:3.12-slim`，分层缓存：先 `COPY requirements.txt` 再 `pip install`，最后 `COPY` 源码）
  - [ ] `services/live-platform/.dockerignore`（排除 `.venv/`、`__pycache__/`、`logs/`、`data/`、`tests/` 等）
  - [ ] `services/live-platform/docker-compose.yml`（MediaMTX + live-platform 两服务，均 `network_mode: host`）
  - [ ] `services/live-platform/config/mediamtx.yml`（MediaMTX 配置）
  - [ ] 本地自检：`docker compose config` 通过 + `docker compose build` 构建成功

---

## Phase 1：搭建骨架（1 天）

### 1.1 创建主入口

- [ ] **创建 `main.py`**
  ```python
  import asyncio
  from fastapi import FastAPI
  import uvicorn
  from apscheduler.schedulers.asyncio import AsyncIOScheduler
  
  from orchestrator.scheduler import detect_rooms
  from api.routes import router
  from api.internal import internal_router
  
  async def main():
      # 初始化调度器
      scheduler = AsyncIOScheduler()
      scheduler.add_job(detect_rooms, 'interval', seconds=60)
      scheduler.start()
      
      # 初始化 FastAPI
      app = FastAPI(title="Live Platform")
      app.include_router(router)
      app.include_router(internal_router, prefix="/internal")
      
      # 启动服务
      config = uvicorn.Config(app, host="0.0.0.0", port=8080)
      server = uvicorn.Server(config)
      await server.serve()
  
  if __name__ == "__main__":
      asyncio.run(main())
  ```

### 1.2 创建配置模块

- [ ] **创建 `shared/config.py`**
  - [ ] 定义 MediaMTX 配置
  - [ ] 定义数据库配置
  - [ ] 定义 OSS 配置
  - [ ] 定义 Kafka 配置

### 1.3 创建数据模型

- [ ] **创建 `shared/models.py`**
  - [ ] 定义 `Status` 枚举
  - [ ] 定义 `RoomState` dataclass
  - [ ] 定义 `SegmentTask` dataclass

### 1.4 创建日志模块

- [ ] **创建 `shared/logger.py`**
  - [ ] 配置日志格式
  - [ ] 配置日志输出（文件 + stdout）

---

## Phase 2：实现房间状态机（2 天）

### 2.1 实现状态机核心

- [ ] **创建 `orchestrator/state_machine.py`**
  - [ ] 实现 `RoomState` 类
  - [ ] 实现 `StateManager` 类
  - [ ] 实现状态转换方法：
    - [ ] `on_live_detected(room_id, flv_url)`
    - [ ] `on_recording_started(room_id)`
    - [ ] `on_segment_received(room_id)`
    - [ ] `on_stream_timeout(room_id)`
    - [ ] `on_reconnect_success(room_id)`
    - [ ] `on_reconnect_failed(room_id)`
    - [ ] `on_stream_ended(room_id)`

### 2.2 实现健康检查

- [ ] **在 `StateManager` 中实现健康检查**
  - [ ] 定期检查 `last_active` 超时
  - [ ] 超时房间自动进入 `reconnecting` 状态
  - [ ] 记录健康检查日志

### 2.3 编写单元测试

- [ ] **创建 `tests/test_state_machine.py`**
  - [ ] 测试状态转换逻辑
  - [ ] 测试超时检测
  - [ ] 测试重试逻辑

---

## Phase 3：实现调度器与取流适配（2 天）

### 3.1 实现调度器

- [ ] **创建 `orchestrator/scheduler.py`**
  - [ ] 实现 `detect_rooms()` 函数
  - [ ] 从数据库查询待监控房间
  - [ ] 遍历房间，检查状态
  - [ ] 对 `idle` 状态房间调用取流适配器
  - [ ] 检测到开播时推进状态机

### 3.2 实现取流适配器

- [ ] **创建 `adapters/tiktok.py`**
  - [ ] 从 `live-monitor` 迁移 `TiktokTool.getLiveStreamInfo()`
  - [ ] 返回 FLV URL 或 None

- [ ] **创建 `adapters/shopee.py`**
  - [ ] 从 `live-monitor` 迁移 `ShopeeTool.getLiveStreamInfo()`
  - [ ] 返回 FLV URL 或 None

- [ ] **创建 `adapters/lazada.py`**
  - [ ] 从 `live-monitor` 迁移 `LazadaTool.getLiveStreamInfo()`
  - [ ] 返回 FLV URL 或 None

### 3.3 编写单元测试

- [ ] **创建 `tests/test_scheduler.py`**
  - [ ] 测试房间检测逻辑
  - [ ] 测试取流适配器调用

- [ ] **创建 `tests/test_adapters.py`**
  - [ ] 测试 TikTok 适配器
  - [ ] 测试 Shopee 适配器
  - [ ] 测试 Lazada 适配器

---

## Phase 4：实现 FFmpeg 协议转换（1 天）

### 4.1 实现 FFmpeg relay

- [ ] **创建 `ffmpeg/relay.py`**
  - [ ] 实现 `start_ffmpeg_relay(flv_url, mediamtx_path)` 函数
  - [ ] 构建 FFmpeg 命令：`-i {flv_url} -c copy -f flv rtmp://localhost:1935/live/{path}`
  - [ ] 使用 `asyncio.create_subprocess_exec` 启动进程
  - [ ] 返回进程 PID

- [ ] **实现进程管理**
  - [ ] 实现 `stop_ffmpeg_relay(pid)` 函数
  - [ ] 实现 `is_ffmpeg_alive(pid)` 函数
  - [ ] 实现进程清理逻辑

### 4.2 集成到状态机

- [ ] **在 `state_machine.py` 中集成 FFmpeg**
  - [ ] `on_live_detected` 时启动 FFmpeg relay
  - [ ] `on_stream_timeout` 时杀掉 FFmpeg 进程
  - [ ] `on_stream_ended` 时清理 FFmpeg 进程

### 4.3 编写单元测试

- [ ] **创建 `tests/test_ffmpeg_relay.py`**
  - [ ] 测试 FFmpeg 启动
  - [ ] 测试进程管理

---

## Phase 5：实现 MediaMTX 客户端（1 天）

### 5.1 实现 MediaMTX API 客户端

- [ ] **创建 `orchestrator/mediamtx_client.py`**
  - [ ] 实现 `add_path(room_id, rtmp_source)` 方法
  - [ ] 实现 `remove_path(room_id)` 方法
  - [ ] 实现 `list_active_paths()` 方法
  - [ ] 实现 `get_path_info(room_id)` 方法

### 5.2 集成到状态机

- [ ] **在 `state_machine.py` 中集成 MediaMTX**
  - [ ] `on_live_detected` 时调用 `add_path`
  - [ ] `on_stream_ended` 时调用 `remove_path`

### 5.3 编写单元测试

- [ ] **创建 `tests/test_mediamtx_client.py`**
  - [ ] 测试 API 调用
  - [ ] 测试错误处理

---

## Phase 6：实现上传与 Kafka worker（2 天）

### 6.1 实现 OSS 上传 worker

- [ ] **创建 `upload/oss_worker.py`**
  - [ ] 从 `live-stream` 迁移 `AiyunOBSHelper`
  - [ ] 实现异步上传队列
  - [ ] 实现 `upload_segment(file_path)` 函数
  - [ ] 实现上传失败重试逻辑
  - [ ] 上传成功后删除本地文件

### 6.2 实现 Kafka 推送 worker

- [ ] **创建 `upload/kafka_worker.py`**
  - [ ] 从 `live-stream` 迁移 `KafkaHelper`
  - [ ] 实现 `send_segment_metadata(room_id, file_path, duration)` 函数
  - [ ] 实现推送失败重试逻辑

### 6.3 实现上传编排

- [ ] **创建 `upload/coordinator.py`**
  - [ ] 实现上传队列
  - [ ] 实现 worker 池
  - [ ] 实现上传 → Kafka 的串行编排

### 6.4 编写单元测试

- [ ] **创建 `tests/test_upload.py`**
  - [ ] 测试 OSS 上传
  - [ ] 测试 Kafka 推送
  - [ ] 测试上传编排

---

## Phase 7：实现 API 与内部接口（1 天）

### 7.1 实现对外 API

- [ ] **创建 `api/routes.py`**
  - [ ] 实现 `GET /health` — 健康检查
  - [ ] 实现 `POST /liveRoom/portInfo` — TikTok 直播间信息（保留兼容）
  - [ ] 实现 `POST /liveRoom/shopeeInfo` — Shopee 直播间信息（保留兼容）
  - [ ] 实现 `POST /liveRoom/lazadaInfo` — Lazada 直播间信息（保留兼容）
  - [ ] 实现 `GET /docs/doc` — 数据在线 API 调试页（保留）
  - [ ] 实现 `GET /docs/getConfig` — 获取调试配置（保留）

### 7.2 实现内部接口

- [ ] **创建 `api/internal.py`**
  - [ ] 实现 `POST /internal/segment-ready` — 接收 MediaMTX 切片回调
  - [ ] 回调处理逻辑：
    - [ ] 更新房间状态机 `last_active`
    - [ ] 推入上传队列

### 7.3 编写单元测试

- [ ] **创建 `tests/test_api.py`**
  - [ ] 测试对外 API
  - [ ] 测试内部接口

---

## Phase 8：集成测试（2 天）

### 8.1 端到端测试

- [ ] **创建 `tests/test_integration.py`**
  - [ ] 测试完整链路：
    1. 调度器检测到开播
    2. 启动 FFmpeg relay
    3. MediaMTX 开始录制
    4. 接收切片回调
    5. 上传到 OSS
    6. 推送 Kafka 消息
    7. 主播下播，清理资源

### 8.2 断流重连测试

- [ ] **模拟断流场景**
  - [ ] 手动杀掉 FFmpeg 进程
  - [ ] 验证状态机进入 `reconnecting`
  - [ ] 验证重新启动 FFmpeg
  - [ ] 验证录制恢复

### 8.3 异常场景测试

- [ ] **测试各种异常**
  - [ ] MediaMTX 服务挂掉
  - [ ] OSS 上传失败
  - [ ] Kafka 推送失败
  - [ ] 数据库连接失败
  - [ ] 验证飞书告警触发

---

## Phase 9：压力测试（1 天）

### 9.1 80 路并发测试

- [ ] **准备测试数据**
  - [ ] 在数据库中插入 80 个测试房间
  - [ ] 准备 80 个模拟直播流

- [ ] **启动压力测试**
  - [ ] 同时启动 80 路录制
  - [ ] 运行 24 小时

- [ ] **监控指标**
  - [ ] CPU 使用率（目标 < 80%）
  - [ ] 内存使用率（目标 < 20 GB）
  - [ ] 网络带宽（目标 < 500 Mbps）
  - [ ] 磁盘 I/O（目标 < 100 MB/s）
  - [ ] MediaMTX metrics（`mediamtx_paths_count` 应 = 80）

- [ ] **验证稳定性**
  - [ ] 无进程崩溃
  - [ ] 无内存泄漏
  - [ ] 无文件描述符耗尽
  - [ ] 断流重连成功率 > 95%

- [ ] **Native vs Docker 性能对比**
  - [ ] 基线：Native 部署下 80 路并发 2 小时的 CPU / 内存 / 磁盘 I/O / 网络带宽 / 切片回调延迟 / 上传成功率
  - [ ] 对比：Docker Compose（host 网络 + bind mount）部署下相同负载相同时长的同一组指标
  - [ ] 验收条件：Docker 相对 Native 各项指标劣化 < 5%，否则需定位根因后再推进生产部署
  - [ ] 结果回写到 `docs/designs/2026-05-10-mediamtx-deployment-adr.md` 的"下次复审"章节

---

## Phase 10：生产部署（1 天）

> 部署方式：Docker Compose + `network_mode: host` + bind mount。详见 `docs/designs/2026-05-10-mediamtx-deployment-adr.md`。

### 10.1 准备生产服务器

- [ ] **安装 Docker 与 Docker Compose**
  ```bash
  # 安装 Docker（如已安装则跳过）
  curl -fsSL https://get.docker.com | sh
  sudo systemctl enable --now docker
  ```

- [ ] **准备宿主机目录与文件系统**
  ```bash
  sudo mkdir -p /data/recordings /data/live-platform/db /data/live-platform/logs
  sudo chown -R 1000:1000 /data/recordings /data/live-platform
  # 推荐 XFS + noatime（如有独立数据盘）
  ```

- [ ] **拉取代码到生产服务器**
  ```bash
  git clone <repo-url> /opt/live-platform
  cd /opt/live-platform/services/live-platform
  ```

- [ ] **准备环境变量**
  ```bash
  cp .env.example .env
  # 编辑 .env，填入 OSS、Kafka、数据库等真实配置
  vim .env
  ```

### 10.2 构建与启动

- [ ] **构建 live-platform 镜像**
  ```bash
  cd /opt/live-platform/services/live-platform
  docker compose build live-platform
  ```

- [ ] **启动全部服务**
  ```bash
  docker compose up -d
  ```

- [ ] **确认容器状态**
  ```bash
  docker compose ps
  # mediamtx 和 live-platform 均应为 running (healthy)
  ```

### 10.3 验证部署

- [ ] **检查日志**
  ```bash
  docker compose logs --tail=100 mediamtx
  docker compose logs --tail=100 live-platform
  ```

- [ ] **测试核心接口**
  ```bash
  curl http://localhost:8080/health
  curl http://localhost:9997/v3/paths/list
  curl http://localhost:9998/metrics
  ```

### 10.4 灰度放量

- [ ] **灰度切流**
  - [ ] 10 路：观察 2 小时，确认切片回调、OSS 上传、Kafka 推送正常
  - [ ] 40 路：观察 4 小时，确认资源占用线性增长无异常
  - [ ] 80 路：观察 24 小时，确认全量稳定

### 10.5 观察运行

- [ ] **观察 3 天**
  - [ ] 每天检查日志：`docker compose logs --since 24h`
  - [ ] 监控断流率
  - [ ] 监控资源占用：`docker stats`
  - [ ] 验证开播检测延迟 < 60 秒
  - [ ] 验证断流重连成功率 > 95%
  - [ ] 检查磁盘空间：`df -h /data/recordings`

---

## Phase 11：下线旧服务（待 Phase 10 稳定后）

### 11.1 归档旧代码

- [ ] **归档 live-monitor**
  ```bash
  mv services/live-monitor docs/archive/live-monitor-deprecated
  ```

- [ ] **归档 live-stream**
  ```bash
  mv services/live-stream docs/archive/live-stream-deprecated
  ```

### 11.2 更新文档

- [ ] **更新根 `CLAUDE.md`**
  - [ ] 删除 live-monitor 和 live-stream 描述
  - [ ] 添加 live-platform 描述

- [ ] **更新根 `README.md`**
  - [ ] 更新架构图
  - [ ] 更新启动命令

- [ ] **创建 `services/live-platform/CLAUDE.md`**
  - [ ] 记录架构决策
  - [ ] 记录关键约束

- [ ] **创建 `services/live-platform/README.md`**
  - [ ] 项目结构
  - [ ] 启动命令
  - [ ] 配置说明

### 11.3 提交代码

- [ ] **创建 feature 分支**
  ```bash
  git checkout -b feature/live-platform-phase1
  ```

- [ ] **提交所有变更**
  ```bash
  git add services/live-platform
  git add docs/designs/2026-05-07-live-platform-phase1-mediamtx.md
  git add docs/plans/2026-05-07-live-platform-phase1-implementation.md
  git commit -m "feat: Phase 1 - 合并 live-monitor + live-stream，采用 MediaMTX 录制架构"
  ```

- [ ] **推送到远程**
  ```bash
  git push origin feature/live-platform-phase1
  ```

- [ ] **创建 Pull Request**
  - [ ] 标题：`Phase 1: 合并 live-monitor + live-stream，采用 MediaMTX 录制架构`
  - [ ] 描述：引用设计文档和实施计划

---

## 里程碑

| 日期 | 里程碑 | 交付物 |
|------|--------|--------|
| 2026-05-08 | MediaMTX 部署完成 | MediaMTX 服务运行，API 可用 |
| 2026-05-10 | 状态机与调度器完成 | 房间检测与状态管理可用 |
| 2026-05-13 | 录制链路打通 | FFmpeg + MediaMTX 录制可用 |
| 2026-05-15 | 上传链路打通 | OSS + Kafka 推送可用 |
| 2026-05-17 | 集成测试通过 | 端到端链路验证通过 |
| 2026-05-18 | 压力测试通过 | 80 路并发 24 小时稳定 |
| 2026-05-21 | 生产部署完成 | live-platform 上线，观察 3 天 |

---

## 回滚方案

如果 Phase 1 出现严重问题，按以下步骤回滚：

1. **立即回滚**
   ```bash
   # 停止 Docker 容器
   cd /opt/live-platform/services/live-platform
   docker compose down

   # 恢复旧服务
   git checkout main
   cd services/live-monitor && python main.py &
   cd services/live-stream && bash start.sh &
   ```

2. **验证**
   - 检查旧服务是否正常运行
   - 验证核心功能
   - 通知团队

3. **根因分析**
   ```bash
   # 收集 Docker 日志用于排查
   docker compose logs --since 1h > /tmp/live-platform-crash.log 2>&1
   ```

---

## 注意事项

1. **每个 Phase 完成后必须验证核心功能正常**
2. **压力测试必须通过才能部署生产**
3. **保留旧代码备份至少 1 个月**
4. **每次修改前先创建 git 分支**
5. **重要操作前先在测试环境验证**

---

**计划结束**
