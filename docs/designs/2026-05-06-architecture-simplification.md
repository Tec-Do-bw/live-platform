# Live Platform 架构极简化方案

> **作者：** Elon Musk 第一性原理审视  
> **日期：** 2026-05-06  
> **状态：** 待实施  
> **目标：** 从 4 服务 32,000 行代码简化到 2 服务 10,000 行代码

---

## 执行摘要

**当前问题：**
- 4 个独立服务（live-monitor、live-stream、adspower-server、live-crawler）
- 32,000 行 Python 代码 + 3,600 行前端
- live-monitor 有 39 个 API 端点，其中 22 个与监控无关
- 开播检测延迟 5+3=8 分钟（目标 1 分钟）
- 主备 HA 机制在 225 账号规模下过度设计

**核心发现：**
- 峰值并发 ≤ 80 路直播流
- FFmpeg 使用 `-c copy` 模式（流拷贝，CPU 占用极低）
- 一台 16 核 32G 机器可承载全部负载
- 服务间 HTTP 轮询是架构遗留，非技术必要

**解决方案：**
- 合并 live-monitor + live-stream + live-crawler 监控 → **live-platform**（单进程）
- 保留 adspower-server 独立（依赖第三方桌面应用）
- 删除 1,400 行非核心代码（精简 docs 后台、激活码、HA）
- 用飞书日报替代 Vue 监控面板（3,600 行 → 30 行）

**预期收益：**
- 代码量减少 75%（32,000 → 8,000 行）
- 开播检测延迟降至 60 秒（达标）
- 部署从 8 台机器降至 1 台
- 单人维护成本降低 60%

---

## 第一性原理分析

### 系统的物理本质

剥掉所有抽象层、DDD 术语、微服务架构，这个系统做的事情是：

> **一个定时轮询器，检查直播间是否在线，如果在线就录视频、抓数据，推给 Kafka。**

用户的根本需求：

> **"我今天的 GMV 数据全了吗？没全的帮我补上。"**

### 为什么需要 4 个服务？

| 服务 | 当前理由 | 真实分析 | 结论 |
|------|---------|---------|------|
| live-monitor | "中心枢纽" | 历史遗留。本质是带 HTTP API 的房间状态字典 + CMS + 激活码 + AI 聊天 | **可合并** |
| live-stream | "视频流录制" | 1 个文件 1,281 行，轮询 live-monitor 拿房间，跑 FFmpeg | **可合并** |
| adspower-server | "浏览器管理" | 依赖第三方桌面应用 AdsPower，登录需要独立环境 | **必须独立** |
| live-crawler | "数据采集" | 采集逻辑复杂，但监控面板过度设计 | **可合并** |

**结论：2 个服务足够。**

---

## 目标架构

### 服务拓扑

```
┌─────────────────────────────────────────────────────────────┐
│  live-platform（单 Python 进程）                             │
│  ├── 房间检测器（每 60 秒）                                  │
│  ├── FFmpeg 管理器（subprocess 启停）                        │
│  ├── OSS 上传器（后台线程）                                  │
│  ├── GMV 采集器（定时任务）                                  │
│  ├── 完整性检查 + 飞书告警（每日 18:00）                     │
│  └── FastAPI（2 个端点：/liveRoom/info, /health）           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  adspower-server（独立服务）                                 │
│  └── 浏览器登录管理 + WebSocket 投屏                         │
└─────────────────────────────────────────────────────────────┘
```

### 核心流程（单进程内）

```
每 60 秒：
  ├── 查询数据库 → 获取待监控房间列表
  ├── HTTP 检查 TikTok/Shopee API → 判断是否在线
  └── 在线？
      ├── YES → subprocess.Popen(['ffmpeg', ...])
      │         ├── 写入 .ts 文件
      │         ├── OSS 上传器检测到完成文件 → 上传
      │         └── 发送 Kafka 消息
      └── NO → 跳过

每 5 分钟：
  └── GMV 采集任务（原 live-crawler 逻辑）

每天 18:00：
  └── 检查完整性 → 生成报告 → 飞书推送
```

**延迟分析：**
- 当前：数据库轮询（5 分钟）+ live-stream 轮询（3 分钟）= **8 分钟**
- 优化后：检测到在线（60 秒）+ 立即启动 FFmpeg = **60 秒** ✅

---

## 删除清单

### 立即删除（无风险）

| 删除项 | 位置 | 行数 | 理由 |
|--------|------|------|------|
| docs 路由中的非核心页面与后台能力 | `live-monitor/routes/docs.py` | ~900 | 保留 `/docs/doc` 调试页及其依赖的 `/docs/getConfig`，删除 AI 聊天、登录后台、版本历史、数据需求表单、离线任务、在线改配置等非核心能力 |
| 激活码系统 | `live-monitor/routes/activation.py` | 372 | 直播监控不需要激活码 |
| 主备 HA 机制 | `live-monitor/main.py` | ~200 | systemd 重启 < 5 秒，比 HA 切换（30 秒）更快 |
| Vue 监控面板 | `live-crawler/monitor/frontend/` | 3,600 | 用飞书日报替代（30 行） |
| 未挂载的路由 | `live-monitor/routes/websocket_routes.py` | ~100 | 已注释掉的死代码 |

**总计删除：~5,200 行（16% 代码量）**

### 合并重构

| 合并项 | 当前 | 优化后 |
|--------|------|--------|
| 服务数 | 4 个独立服务 | 2 个服务 |
| API 端点 | 39 个（live-monitor） | 2 个核心端点 |
| 配置文件 | 4 套 | 1 套 |
| 日志系统 | 4 套 | 1 套 |
| 部署机器 | 8 台（每台 30 路） | 1 台（16 核 32G） |

---

## 机器配置

### 资源需求计算

峰值 80 路 FFmpeg（`-c:v copy -c:a copy` 流拷贝模式）：

| 资源 | 计算 | 需求 |
|------|------|------|
| CPU | 80 路 × 0.2 核/路 | 16 核 |
| 内存 | 80 路 × 100 MB/路 + 系统开销 | 32 GB |
| 网络（下行） | 80 路 × 3 Mbps/路 | 240 Mbps |
| 网络（上行 OSS） | 80 路 × 3 Mbps/路 | 240 Mbps |
| 磁盘 I/O | 80 路 × 3 Mbps/路 | 30 MB/s（NVMe SSD） |
| 磁盘容量 | 临时存储 + 日志 | 1 TB |

### 推荐配置

**阿里云 ECS：**
- 实例规格：ecs.c7.4xlarge
- CPU：16 核（Intel Xeon 或 AMD EPYC）
- 内存：32 GB
- 网络：双千兆网卡（或 10 Gbps）
- 磁盘：1 TB NVMe SSD（ESSD PL1）

---

## 实施计划

### Phase 1：修复 FFmpeg 断流（P0）

**时间：** 1 周  
**目标：** 解决唯一影响用户的 P0 问题

**修改参数：**

```python
# services/live-stream/TT_client.py

# 当前值 → 优化值
心跳检测间隔: 30s → 10s
无数据超时: 60s → 15s
最大重试次数: 5 → 15
重试初始间隔: 3s → 1s
稳定运行判定: 60s → 30s
```

**验证：**
- 部署到生产环境
- 观察 3 天断流率
- 目标：断流重连成功率 > 95%

---

### Phase 2：删除非核心代码（P1）

**时间：** 2 天  
**目标：** 减少认知负荷，降低维护成本

**删除清单：**

```bash
# 1. 精简 docs 路由
# 在 services/live-monitor/routes/docs.py 中仅保留：
#   - GET /docs/doc
#   - GET /docs/getConfig
# 删除 login/chat/offlineTask/configGenerator/versionHistory/
# dataNeedForm/updateConfig 等非核心页面与后台能力

# 2. 删除激活码系统
rm services/live-monitor/routes/activation.py

# 3. 删除 HA 相关代码
# 在 services/live-monitor/main.py 中删除：
#   - sync_room_dict()
#   - sync_offline_scripts()
#   - 主备切换逻辑

# 4. 删除未挂载的路由
# 在 services/live-monitor/routes/websocket_routes.py 中删除已注释代码
```

**验证：**
- 运行测试：`pytest services/live-monitor/tests/`
- 确认调试页仍可用：
  - `/docs/doc` 可正常打开
  - `/docs/getConfig` 可返回 `portInfo`、`shopeeInfo`、`lazadaInfo` 的调试配置
- 确认核心链路不受影响：
  - `/liveRoom/portInfo` 正常返回
  - `/get_roominfo` 正常分配房间
  - `/report_roominfo` 正常接收心跳

---

### Phase 3：合并服务（P2）

**时间：** 1 周  
**目标：** 消除服务间 HTTP 轮询，达成 1 分钟检测目标

**步骤：**

1. **创建新项目结构**

```bash
mkdir -p services/live-platform/{api,tasks,ffmpeg,crawler,monitor}
```

2. **迁移代码**

```python
# services/live-platform/main.py
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
import uvicorn

from tasks.room_detector import detect_rooms
from tasks.gmv_crawler import crawl_gmv
from tasks.completeness_checker import check_completeness
from tasks.oss_uploader import upload_segments

async def main():
    scheduler = AsyncIOScheduler()
    
    # 定时任务
    scheduler.add_job(detect_rooms, 'interval', seconds=60)
    scheduler.add_job(crawl_gmv, 'interval', minutes=5)
    scheduler.add_job(check_completeness, 'cron', hour=18)
    
    # 后台任务
    asyncio.create_task(upload_segments())
    
    # FastAPI
    app = FastAPI()
    from api.routes import router
    app.include_router(router)
    
    scheduler.start()
    config = uvicorn.Config(app, host="0.0.0.0", port=8080)
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
```

3. **重构房间检测 + FFmpeg 启动**

```python
# services/live-platform/tasks/room_detector.py
import subprocess
from ffmpeg.manager import FFmpegManager

active_rooms = {}  # {room_id: {"process": ..., "start_time": ...}}

async def detect_rooms():
    """每 60 秒检测一次"""
    rooms = await db.query("SELECT * FROM live_streaming_room WHERE local_status=1")
    
    for room in rooms:
        if room.id not in active_rooms:
            # 检查是否在线
            live_info = await check_live_status(room.url)
            
            if live_info and live_info.get("flv_url"):
                # 立即启动 FFmpeg（不需要等轮询）
                start_recording(room.id, live_info)

def start_recording(room_id: str, live_info: dict):
    """启动 FFmpeg 子进程"""
    command = FFmpegManager.build_command(
        live_info["flv_url"],
        f"output/{room_id}.ts"
    )
    process = subprocess.Popen(command)
    active_rooms[room_id] = {
        "process": process,
        "start_time": time.time(),
        "live_info": live_info
    }
    logger.info(f"[{room_id}] FFmpeg 已启动")
```

**验证：**
- 端到端测试：录入直播间 → 60 秒内检测到 → FFmpeg 启动
- 压力测试：模拟 80 路并发
- 监控资源占用：CPU < 80%，内存 < 20 GB

---

### Phase 4：监控简化（P3）

**时间：** 3 天  
**目标：** 用 30 行 Python 替代 3,600 行 Vue 前端

**删除前端：**

```bash
rm -rf services/live-crawler/monitor/frontend
```

**创建飞书日报脚本：**

```python
# scripts/daily_completeness_report.py
import sqlite3
from datetime import date
from feishu_webhook import send_message

def generate_report():
    db = sqlite3.connect("services/live-platform/data/monitor.db")
    today = date.today()
    
    # 查询今日缺失数据
    missing = db.execute("""
        SELECT account_id, platform, error_message
        FROM account_sessions
        WHERE date = ? AND status != 'success'
    """, (today,)).fetchall()
    
    if not missing:
        message = f"✅ {today} 数据采集完整，无缺失"
    else:
        message = f"⚠️ {today} 数据缺失 {len(missing)} 条\n\n"
        for account_id, platform, error in missing:
            message += f"- {account_id} ({platform}): {error}\n"
    
    send_message(message)

if __name__ == "__main__":
    generate_report()
```

**添加到 cron：**

```bash
crontab -e
# 每天 18:00 执行
0 18 * * * cd /path/to/live-platform && python scripts/daily_completeness_report.py
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 单点故障（一台机器） | 高 | systemd 自动重启 + 飞书告警 + 每日备份 |
| FFmpeg 进程泄漏 | 中 | 定期检查僵尸进程 + 自动清理 |
| 磁盘空间不足 | 中 | 监控磁盘使用率 + 自动清理旧文件 |
| 迁移期间数据丢失 | 低 | 灰度发布 + 双写验证 |

---

## 成功指标

| 指标 | 当前 | 目标 | 验证方式 |
|------|------|------|---------|
| 开播检测延迟 | 8 分钟 | 60 秒 | 端到端测试 |
| 代码量 | 32,000 行 | 10,000 行 | `find . -name "*.py" \| xargs wc -l` |
| 服务数 | 4 个 | 2 个 | 部署清单 |
| API 端点数 | 39 个 | 4 个 | OpenAPI 文档 |
| 部署机器数 | 8 台 | 1 台 | 基础设施清单 |
| 断流重连成功率 | < 90% | > 95% | 监控日志统计 |

---

## 附录：删除的功能清单

### live-monitor 删除的端点

| 端点 | 用途 | 删除理由 |
|------|------|---------|
| `/docs/login` | CMS 登录 | 与监控无关 |
| `/docs/chat` | AI 聊天 | 与监控无关 |
| `/docs/offlineTask` | 离线任务管理 | 与监控无关 |
| `/docs/configGenerator` | 配置生成器 | 与监控无关 |
| `/docs/versionHistory` | 版本历史 | 与监控无关 |
| `/docs/dataNeedForm` | 数据需求表单 | 与监控无关 |
| `/adsmeta/api/activation/*` | 激活码系统 | 与监控无关 |
| `/sync_room_dict` | 主备同步 | 删除 HA 机制 |
| `/sync_offline_scripts` | 主备同步 | 删除 HA 机制 |
| `/sync_log` | 主备同步 | 删除 HA 机制 |

**保留的核心端点：**
- `/liveRoom/portInfo` - 获取 TikTok 直播间信息
- `/liveRoom/shopeeInfo` - 获取 Shopee 直播间信息
- `/liveRoom/lazadaInfo` - 获取 Lazada 直播间信息
- `/health` - 健康检查

---

**文档结束**
