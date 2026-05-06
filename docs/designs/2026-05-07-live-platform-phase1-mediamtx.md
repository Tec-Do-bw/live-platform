# Live Platform Phase 1 设计方案：MediaMTX 录制架构

> **作者：** XBW + Claude  
> **日期：** 2026-05-07  
> **状态：** 待实施  
> **目标：** 新建 `services/live-platform/`，合并 live-monitor + live-stream，采用 MediaMTX 录制底座

---

## 执行摘要

**Phase 1 范围：** 只合并 `live-monitor` + `live-stream`，`live-crawler` 完全不动。

**核心变化：**
- 录制底座从 FFmpeg 直接管理改为 **MediaMTX**
- Python 层从"录制管理器"降级为"编排器"
- 房间状态从"隐式推断"改为"显式状态机"
- 上传触发从"文件系统轮询"改为"MediaMTX 回调推送"
- 服务间 HTTP 轮询改为"单进程内函数调用"

**预期收益：**
- 开播检测延迟从 8 分钟降至 60 秒
- 断流重连成功率从 < 90% 提升至 > 95%
- 服务数从 4 个降至 3 个
- 80 路并发录制架构可靠性提升
- 代码量减少约 40%（删除轮询、状态同步、文件扫描逻辑）

---

## 一、当前问题分析

### 1.1 现有架构的核心问题

**服务拓扑：**
```
live-monitor (房间检测，5 分钟轮询)
     ↓ HTTP 轮询
live-stream (录制管理，3 分钟轮询)
     ↓ FFmpeg subprocess
  录制文件
     ↓ 文件系统轮询（1 秒）
  OSS 上传
```

**问题清单：**

| 问题 | 影响 | 根因 |
|------|------|------|
| 开播检测延迟 8 分钟 | 用户体验差 | 两层轮询叠加（5min + 3min） |
| 断流重连成功率 < 90% | 数据丢失 | 参数保守 + 状态不一致 |
| 80 路并发时线程暴涨 | 资源耗尽 | 每房间一个线程 + 共享 dict 无锁 |
| 上传阻塞影响录制判断 | 雪崩风险 | 录制/上传/状态耦合在同一进程 |
| 状态不一致 | 排障困难 | monitor 和 stream 各维护一份状态 |
| 文件系统轮询开销 | CPU 浪费 | 每秒扫描目录判断文件是否就绪 |

### 1.2 为什么不能"小修小补"

现有 `services/live-stream/TT_client.py` (1281 行) 的问题不是参数能救的，是架构模型本身：

- **每房间一个线程**：80 路 = 80 个线程 + 80 个上传线程 = 160 线程
- **共享 dict 状态**：`online_room_list` 无锁保护，多线程竞态
- **本地目录扫描做健康判断**：靠文件副作用推断状态
- **录制、上传、状态、调度全部耦合**：一个模块出问题全链路受影响

这类架构一旦上 80 路，常见死法：
- 线程暴涨，状态不同步
- 房间释放与实际 FFmpeg 生命周期错位
- 上传阻塞影响录制判断
- 断流恢复雪崩

---

## 二、新架构设计

### 2.1 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│  services/live-platform/                                     │
│                                                              │
│  ┌─────────────────┐      ┌──────────────────────────────┐ │
│  │  MediaMTX       │      │  Python Orchestrator         │ │
│  │  (录制底座)      │◄─────│  (编排层)                    │ │
│  │                 │ API  │                              │ │
│  │  - 拉流录制     │      │  - 房间状态机                │ │
│  │  - 协议处理     │      │  - 任务调度                  │ │
│  │  - 切片回调     │      │  - MediaMTX API 调用         │ │
│  │  - 指标暴露     │      │  - OSS 上传 worker           │ │
│  └─────────────────┘      │  - Kafka 推送 worker         │ │
│         │                  │  - 健康检查 + 飞书告警       │ │
│         │ 切片回调          └──────────────────────────────┘ │
│         │ (HTTP POST)                  ▲                    │
│         └──────────────────────────────┘                    │
│                                                              │
│  ┌─────────────────┐      ┌──────────────────────────────┐ │
│  │  FFmpeg 进程池   │      │  streamlink / yt-dlp         │ │
│  │  (协议转换)      │      │  (取流适配，签名变化时降级)   │ │
│  └─────────────────┘      └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**职责划分：**

| 组件 | 职责 | 不负责 |
|------|------|--------|
| MediaMTX | 拉流、录制、切片、协议处理、指标暴露 | 业务逻辑、上传、Kafka |
| FFmpeg | HTTP-FLV → RTMP 协议转换（薄层） | 录制管理、切片、健康检查 |
| Python Orchestrator | 房间调度、状态机、API 编排、上传、Kafka | 媒体处理 |
| streamlink/yt-dlp | TikTok/Shopee URL 提取（备选） | 录制 |

### 2.2 目录结构

```
services/live-platform/
├── main.py                     # 进程入口
├── orchestrator/
│   ├── scheduler.py            # 房间检测调度（每 60s）
│   ├── state_machine.py        # 每房间显式状态机
│   └── mediamtx_client.py      # MediaMTX API 交互
├── ffmpeg/
│   └── relay.py                # FFmpeg 协议转换管理
├── upload/
│   ├── oss_worker.py           # 独立上传 worker
│   └── kafka_worker.py         # Kafka 推送 worker
├── adapters/
│   ├── tiktok.py               # TikTok 取流适配
│   ├── shopee.py               # Shopee 取流适配
│   └── lazada.py               # Lazada 取流适配
├── api/
│   ├── routes.py               # 对外接口
│   └── internal.py             # 内部接口（接收 MediaMTX 回调）
├── shared/
│   ├── config.py               # 统一配置
│   ├── db.py                   # 数据库访问
│   ├── models.py               # 数据模型
│   └── logger.py               # 日志
├── tests/
│   ├── test_state_machine.py
│   ├── test_scheduler.py
│   └── test_integration.py
└── README.md
```

---

## 三、房间状态机设计

### 3.1 状态定义

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

### 3.2 状态转换表

| 当前状态 | 事件 | 下一状态 | 动作 |
|----------|------|----------|------|
| `idle` | 调度器检测到开播 | `starting` | 获取 FLV URL，启动 FFmpeg 转换 + MediaMTX path |
| `starting` | MediaMTX path 就绪 | `recording` | 开始接收切片回调 |
| `starting` | 启动超时/失败 | `failed` | 清理资源，记录错误 |
| `recording` | 切片回调到达 | `recording` | 更新 last_active 时间戳 |
| `recording` | 无数据超时（30s） | `reconnecting` | 杀掉 FFmpeg，重新获取 URL |
| `recording` | 主播正常下播 | `idle` | 清理 MediaMTX path，上传剩余切片 |
| `reconnecting` | 新 URL 获取成功 | `starting` | 重新启动 FFmpeg 转换 |
| `reconnecting` | 重试次数耗尽 | `failed` | 清理资源，飞书告警 |
| `failed` | — | `cooldown` | 进入冷却期（避免雪崩） |
| `cooldown` | 冷却结束（60s） | `idle` | 重新进入调度池 |

### 3.3 状态机核心属性

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class Status(Enum):
    IDLE = "idle"
    STARTING = "starting"
    RECORDING = "recording"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    COOLDOWN = "cooldown"

@dataclass
class RoomState:
    room_id: str
    platform: str              # tiktok / shopee / lazada
    room_url: str
    status: Status
    flv_url: Optional[str] = None
    mediamtx_path: Optional[str] = None  # MediaMTX 中的 path 名称
    ffmpeg_pid: Optional[int] = None     # 协议转换进程 PID
    retry_count: int = 0
    max_retries: int = 15
    last_active: float = 0     # 最后一次收到切片回调的时间
    started_at: float = 0
    error_message: str = ""
    
    def is_healthy(self, timeout: int = 30) -> bool:
        """判断录制是否健康（基于切片回调时间，需 > recordSegmentDuration）"""
        if self.status != Status.RECORDING:
            return True
        return time.time() - self.last_active < timeout
```

### 3.4 与现有方案的本质区别

| 维度 | 现有 TT_client.py | 新状态机 |
|------|-------------------|----------|
| 状态存储 | 共享 dict，无锁 | 每房间独立 dataclass |
| 状态推断 | 靠目录文件是否存在 | 显式状态 + 时间戳 |
| 健康判断 | 扫描本地目录 | MediaMTX 切片回调 + metrics |
| 断流感知 | 心跳线程轮询 | `last_active` 超时检测 |
| 并发模型 | 每房间一个线程 | asyncio 事件循环 + 进程池 |

---

## 四、房间管理架构（消除跨服务轮询）

### 4.1 现有问题

```
当前：live-monitor 管房间状态 ←HTTP 轮询→ live-stream 管录制
     （两个进程，两套状态，靠 API 同步）
```

导致：
- 状态不一致（monitor 认为在录，stream 实际已断）
- 延迟叠加（monitor 轮询 5min + stream 轮询 3min = 8min）
- 排障困难（状态分散在两个服务）

### 4.2 新设计：单进程内闭环

```
┌─────────────────────────────────────────────────────────────┐
│  live-platform 单进程                                        │
│                                                              │
│  ┌──────────────┐     直接函数调用      ┌────────────────┐  │
│  │  Scheduler   │ ──────────────────→  │  State Machine │  │
│  │  (每60s检测)  │                      │  (房间状态机)   │  │
│  └──────────────┘                      └────────────────┘  │
│         │                                      │            │
│         │ 查询 DB                    控制 MediaMTX + FFmpeg  │
│         ↓                                      ↓            │
│  ┌──────────────┐                      ┌────────────────┐  │
│  │   SQLite     │                      │  MediaMTX API  │  │
│  │  (房间表)    │                      │  + FFmpeg 进程  │  │
│  └──────────────┘                      └────────────────┘  │
│                                                │            │
│                              切片回调（HTTP 内部接口）        │
│                                                ↓            │
│                                        ┌────────────────┐  │
│                                        │ Upload Workers │  │
│                                        │ (OSS + Kafka)  │  │
│                                        └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 核心流程（无跨服务调用）

```python
# orchestrator/scheduler.py
async def detect_rooms():
    """每 60 秒执行一次，单进程内直接操作状态机"""
    rooms = await db.query(
        "SELECT * FROM live_streaming_room WHERE local_status=1"
    )
    
    for room in rooms:
        state = state_manager.get(room.id)
        
        if state.status == Status.IDLE:
            # 直接调用取流适配器（不再 HTTP 调用另一个服务）
            flv_url = await adapters.get_stream_url(
                room.platform, room.url
            )
            
            if flv_url:
                # 直接推进状态机（不再等另一个服务轮询）
                await state_manager.transition(
                    room.id, 
                    Event.LIVE_DETECTED, 
                    flv_url=flv_url
                )
```

---

## 五、MediaMTX 集成设计

### 5.1 MediaMTX 切片回调能力

MediaMTX 提供 `runOnRecordSegmentComplete` hook，每个切片写入完成时触发：

```yaml
# /etc/mediamtx.yml
pathDefaults:
  record: yes
  recordFormat: fmp4
  recordPartDuration: 1s
  recordSegmentDuration: 10s   # 每 10 秒生成一个切片文件，触发一次回调
  recordPath: /data/recordings/%path/%Y-%m-%d_%H-%M-%S-%f
  runOnRecordSegmentComplete: >
    curl -X POST http://localhost:8080/internal/segment-ready
    -H "Content-Type: application/json"
    -d '{"path":"$MTX_PATH","file":"$MTX_SEGMENT_PATH","duration":"$MTX_SEGMENT_DURATION"}'
```

> **设计决策：** `recordSegmentDuration` 设为 `10s` 而非 `1h`。原因：
> 1. 切片回调是房间状态机的健康信号（`last_active` 更新来源），超时阈值为 30s，因此回调频率必须高于超时频率。
> 2. 与现有系统 8s 切片对齐，每个切片文件即为一个上传单元。
> 3. 短切片降低断流时的数据丢失窗口（最多丢 10s）。

回调传递的变量：
- `$MTX_PATH` — 房间/流名称
- `$MTX_SEGMENT_PATH` — 切片文件完整路径
- `$MTX_SEGMENT_DURATION` — 切片时长

**上传链路变成：**
```
MediaMTX 录制完一个切片
  → 触发 runOnRecordSegmentComplete
    → 调用 Python orchestrator 的内部接口
      → OSS upload worker 拿到文件路径，上传
        → Kafka worker 推送元数据
```

不再需要"文件系统轮询扫描"，彻底解耦。

### 5.2 HTTP-FLV 拉流限制与解决方案

**关键限制：** MediaMTX 不原生支持 HTTP-FLV 拉流。

TikTok/Shopee 直播流通常是 FLV over HTTP，MediaMTX 不能直接拉。

**解决方案：** 用 FFmpeg 做薄薄一层协议转换：

```
Python 获取 FLV URL 
  → 启动 FFmpeg 做协议转换（FLV → RTMP push 到 MediaMTX）
    → MediaMTX 负责录制/切片/回调
```

FFmpeg 在这里的角色从"录制管理器"降级为"协议转换器"，只做 `-c copy` 转封装。

```python
# ffmpeg/relay.py
async def start_ffmpeg_relay(
    flv_url: str, 
    mediamtx_path: str
) -> int:
    """启动 FFmpeg 协议转换进程"""
    rtmp_target = f"rtmp://localhost:1935/live/{mediamtx_path}"
    
    command = [
        "ffmpeg",
        "-i", flv_url,
        "-c", "copy",  # 流拷贝，无转码
        "-f", "flv",
        rtmp_target
    ]
    
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    return process.pid
```

> **设计决策：** FFmpeg 的 stdout/stderr 重定向到 DEVNULL 而非 PIPE。原因：
> 长时间运行的 FFmpeg relay 会持续输出日志到 stderr，如果用 PIPE 但不消费，
> OS pipe buffer（通常 64KB）满后 FFmpeg 进程会阻塞，导致录制中断。
> 如需 FFmpeg 日志用于排障，可改为重定向到日志文件并配合 logrotate。

### 5.3 MediaMTX API 集成

```python
# orchestrator/mediamtx_client.py
import httpx

class MediaMTXClient:
    def __init__(self, base_url: str = "http://localhost:9997"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=10.0)
    
    async def add_path(self, room_id: str, rtmp_source: str):
        """动态添加录制路径"""
        path_name = f"room_{room_id}"
        payload = {
            "source": rtmp_source,
            "record": True
        }
        resp = await self.client.post(
            f"{self.base_url}/v3/config/paths/add/{path_name}",
            json=payload
        )
        resp.raise_for_status()
        return path_name
    
    async def remove_path(self, room_id: str):
        """移除路径（停止录制）"""
        path_name = f"room_{room_id}"
        resp = await self.client.delete(
            f"{self.base_url}/v3/config/paths/delete/{path_name}"
        )
        resp.raise_for_status()
    
    async def list_active_paths(self) -> list[dict]:
        """列出所有活跃路径"""
        resp = await self.client.get(
            f"{self.base_url}/v3/paths/list"
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
```

---

## 六、MediaMTX 部署方案

### 6.1 推荐方案：systemd 服务 + 裸机二进制

**选型理由：**

| 考虑维度 | 判断 |
|----------|------|
| 性能 | 80 路流拷贝对 CPU 敏感，裸机 0 虚拟化开销 |
| 运维复杂度 | systemd 原生进程守护、自动重启、日志管理 |
| 通信便捷性 | Python 通过 `localhost:9997` 直连，无需端口映射 |
| 配置灵活性 | 支持热重载，无需重启 |
| 升级便捷性 | 内置 `--upgrade` 一键升级 |
| 资源占用 | 预估 2-4 核 CPU + 2-4 GB 内存（80 路） |

### 6.2 部署架构图

```
┌─────────────────────────────────────────────────────────────┐
│  阿里云 ECS (16 核 32G, Linux)                               │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  systemd 进程守护                                     │  │
│  │                                                       │  │
│  │  ┌─────────────────┐      ┌──────────────────────┐  │  │
│  │  │  MediaMTX       │      │  live-platform       │  │  │
│  │  │  (录制底座)      │◄─────│  (Python orchestrator)│  │  │
│  │  │                 │ API  │                      │  │  │
│  │  │  - 端口 9997    │      │  - 端口 8080         │  │  │
│  │  │  - 端口 9998    │      │  - FastAPI           │  │  │
│  │  │    (metrics)    │      │  - asyncio           │  │  │
│  │  └─────────────────┘      └──────────────────────┘  │  │
│  │         │                           ▲                │  │
│  │         │ 切片回调                   │                │  │
│  │         │ (HTTP POST)               │                │  │
│  │         └───────────────────────────┘                │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 systemd 服务配置

```ini
# /etc/systemd/system/mediamtx.service
[Unit]
Description=MediaMTX Live Media Server
After=network.target

[Service]
Type=simple
User=mediamtx
ExecStart=/usr/local/bin/mediamtx /etc/mediamtx.yml
Restart=always
RestartSec=5

# 资源限制
LimitNOFILE=65536
LimitNPROC=4096

# 性能优化
Nice=-10

[Install]
WantedBy=multi-user.target
```

### 6.4 资源占用预估

| 资源 | 预估值（80 路流拷贝） |
|------|---------------------|
| CPU | 2-4 核 |
| 内存 | 2-4 GB |
| 网络带宽 | 160 Mbps（假设每路 2 Mbps） |
| 磁盘 I/O | 20 MB/s |
| 文件描述符 | 需设置 65536 |

**16 核 32G 配置完全足够**，主要瓶颈在网络带宽和磁盘 I/O。

---

## 七、成功指标

| 指标 | 当前 | 目标 | 验证方式 |
|------|------|------|---------|
| 开播检测延迟 | 8 分钟 | 60 秒 | 端到端测试 |
| 断流重连成功率 | < 90% | > 95% | 监控日志统计 |
| 服务数 | 4 个 | 3 个 | 部署清单 |
| 80 路并发稳定性 | 未验证 | 24 小时无故障 | 压力测试 |
| 代码量 | ~32,000 行 | ~19,000 行 | `find . -name "*.py" \| xargs wc -l` |

---

## 八、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| MediaMTX 不支持 HTTP-FLV | 高 | 用 FFmpeg 做协议转换（已验证可行） |
| 80 路并发时 write queue full | 中 | 调整 `writeQueueSize: 1024` |
| 状态机 bug 导致房间卡死 | 中 | 增加超时自动清理 + 飞书告警 |
| 一次性切换风险 | 高 | 充分测试 + 回滚预案 |

---

**文档结束**
