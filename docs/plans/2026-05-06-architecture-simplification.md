# Live Platform 架构极简化(Phase 1~5)

> **状态**:进行中(Phase 1 ~ 5 实施)
> **开始日期**:2026-05-06
> **预计完成**:2026-06-03(4 周)
> **负责人**:XBW
> **关联**:Phase 3 的 live-platform 服务搭建详见 [`2026-05-07-live-platform-phase1.md`](2026-05-07-live-platform-phase1.md)

---

## 一、背景与目标(原 design)

### 1.1 当前问题

- 4 个独立服务(live-monitor、live-stream、adspower-server、live-crawler)
- 32,000 行 Python 代码 + 3,600 行前端
- live-monitor 有 39 个 API 端点,其中 22 个与监控无关
- 开播检测延迟 5+3=8 分钟(目标 1 分钟)
- 主备 HA 机制在 225 账号规模下过度设计

### 1.2 第一性原理分析

剥掉所有抽象层、DDD 术语、微服务架构,这个系统做的事情是:

> **一个定时轮询器,检查直播间是否在线,如果在线就录视频、抓数据,推给 Kafka。**

用户的根本需求:

> **"我今天的 GMV 数据全了吗?没全的帮我补上。"**

### 1.3 服务必要性评估

| 服务 | 当前理由 | 真实分析 | 结论 |
|------|---------|---------|------|
| live-monitor | "中心枢纽" | 历史遗留。本质是带 HTTP API 的房间状态字典 + CMS + 激活码 + AI 聊天 | **可合并** |
| live-stream | "视频流录制" | 1 个文件 1,281 行,轮询 live-monitor 拿房间,跑 FFmpeg | **可合并** |
| adspower-server | "浏览器管理" | 依赖第三方桌面应用 AdsPower,登录需要独立环境 | **必须独立** |
| live-crawler | "数据采集" | 采集逻辑复杂,但监控面板过度设计 | **可合并** |

**结论:2 个核心服务足够 + 1 个独立浏览器服务。**

### 1.4 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│  live-platform(单 Python 进程)                             │
│  ├── 房间检测器(每 60 秒)                                  │
│  ├── FFmpeg / MediaMTX 录制(详见 phase1 plan)             │
│  ├── OSS 上传器(后台任务)                                  │
│  ├── GMV 采集器(定时任务)                                  │
│  ├── 完整性检查 + 飞书告警(每日 18:00)                     │
│  └── FastAPI(/liveRoom/info, /health, /docs/doc)           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  adspower-server(独立服务,依赖 AdsPower 桌面应用)          │
│  └── 浏览器登录管理 + WebSocket 投屏                         │
└─────────────────────────────────────────────────────────────┘
```

### 1.5 预期收益

| 指标 | 当前 | 目标 |
|------|------|------|
| 开播检测延迟 | 8 分钟 | 60 秒 |
| 代码量 | 32,000 行 | 10,000 行 |
| 服务数 | 4 个 | 2 个 |
| API 端点数 | 39 个 | 4 个核心 |
| 部署机器 | 8 台(每台 30 路) | 1 台(16 核 32G) |
| 断流重连成功率 | < 90% | > 95% |

---

## 二、删除清单(原 design)

### 2.1 立即删除(无风险)

| 删除项 | 位置 | 行数 | 理由 |
|--------|------|------|------|
| docs 路由非核心页面与后台 | `live-monitor/routes/docs.py` | ~900 | 保留 `/docs/doc` 调试页与 `/docs/getConfig`;删除 AI 聊天、登录后台、版本历史、数据需求表单、离线任务、在线改配置 |
| 激活码系统 | `live-monitor/routes/activation.py` | 372 | 直播监控不需要 |
| 主备 HA 机制 | `live-monitor/main.py` | ~200 | systemd 重启 < 5s,比 HA 切换更快 |
| Vue 监控面板 | `live-crawler/monitor/frontend/` | 3,600 | 用飞书日报替代 |
| 未挂载的路由 | `live-monitor/routes/websocket_routes.py` | ~100 | 已注释的死代码 |

**总计删除:~5,200 行(16% 代码量)**

### 2.2 合并对比

| 维度 | 当前 | 优化后 |
|------|------|--------|
| 服务数 | 4 个独立服务 | 2 个核心 + 1 个独立(adspower) |
| API 端点 | 39 个(live-monitor) | 4 个核心 |
| 配置文件 | 4 套 | 1 套 |
| 日志系统 | 4 套 | 1 套 |
| 部署机器 | 8 台 | 1 台(16 核 32G) |

---

## 三、机器配置(原 design)

峰值 80 路 FFmpeg(`-c:v copy -c:a copy` 流拷贝):

| 资源 | 计算 | 需求 |
|------|------|------|
| CPU | 80 路 × 0.2 核/路 | 16 核 |
| 内存 | 80 路 × 100 MB/路 + 系统开销 | 32 GB |
| 网络下行 | 80 路 × 3 Mbps | 240 Mbps |
| 网络上行(OSS) | 80 路 × 3 Mbps | 240 Mbps |
| 磁盘 I/O | 80 路 × 3 Mbps | 30 MB/s(NVMe SSD) |
| 磁盘容量 | 临时存储 + 日志 | 1 TB |

**推荐配置**:阿里云 ECS `ecs.c7.4xlarge`(16 核 32 GB + 1 TB NVMe SSD ESSD PL1 + 双千兆网卡)

---

## 四、Phase 1:修复 FFmpeg 断流(P0,1 周)

**时间**:2026-05-06 ~ 2026-05-12
**目标**:断流重连成功率 > 95%

### 任务清单

- [ ] **1.1 修改 FFmpeg 重连参数**
  - [ ] 打开 `services/live-stream/TT_client.py`,定位 `FFmpegStreamManager` 配置段
  - [ ] 修改:
    ```python
    heartbeat_interval = 10        # 30s → 10s
    no_data_timeout = 15           # 60s → 15s
    max_retries = 15               # 5 → 15
    retry_initial_interval = 1     # 3s → 1s
    stable_threshold = 30          # 60s → 30s
    ```
  - [ ] 提交:`git commit -m "优化 FFmpeg 断流重连参数"`

- [ ] **1.2 部署生产**
  - [ ] `systemctl stop live-stream`
  - [ ] `git pull origin main`
  - [ ] `systemctl start live-stream`
  - [ ] `tail -f logs/ffmpeg_stream_*.log`

- [ ] **1.3 监控断流(3 天)**
  - [ ] 每天检查断流日志、统计重连成功率、记录异常
  - [ ] 验收:重连成功率 > 95%

- [ ] **1.4 调优(如需要)**
  - [ ] 未达标继续调参,考虑增加重试或缩短超时

---

## 五、Phase 2:删除非核心代码(P1,2 天)

**时间**:2026-05-13 ~ 2026-05-14
**目标**:删除 1,400 行非核心代码

### 任务清单

- [ ] **2.1 精简 docs 路由(保留数据在线 API 调试页)**
  - [ ] `services/live-monitor/routes/docs.py` 仅保留 `GET /docs/doc` 与 `GET /docs/getConfig`
  - [ ] 删除 `login`、`chat`、`offlineTask`、`configGenerator`、`versionHistory`、`dataNeedForm`、`updateConfig` 等
  - [ ] 保留 `main.py` 中的 docs 路由注册
  - [ ] 提交:`git commit -m "精简 docs 路由,保留数据在线 API 调试页"`

- [ ] **2.2 删除激活码系统(372 行)**
  - [ ] 备份:`cp services/live-monitor/routes/activation.py docs/archive/`
  - [ ] 删除:`rm services/live-monitor/routes/activation.py`
  - [ ] 从 `main.py` 移除路由注册
  - [ ] 提交:`git commit -m "删除激活码系统"`

- [ ] **2.3 删除主备 HA 机制(~200 行)**
  - [ ] `services/live-monitor/main.py` 删除函数:`sync_room_dict_to_backup()`、`sync_offline_scripts_to_backup()`、`check_primary_health()`
  - [ ] 删除路由:`POST /sync_room_dict`、`POST /sync_offline_scripts`、`POST /sync_log`
  - [ ] 删除 APScheduler 中的同步任务
  - [ ] 提交:`git commit -m "删除主备 HA 机制"`

- [ ] **2.4 删除未挂载的路由(~100 行)**
  - [ ] 删除 `services/live-monitor/routes/websocket_routes.py` line 149 附近已注释代码
  - [ ] 提交:`git commit -m "清理未挂载的死代码"`

- [ ] **2.5 测试核心功能**
  - [ ] `cd services/live-monitor && pytest tests/`
  - [ ] 验证调试页:`curl http://localhost:8080/docs/getConfig`
  - [ ] 手动打开 `/docs/doc` 调试 `portInfo` / `shopeeInfo` / `lazadaInfo`
  - [ ] 测试核心端点:
    ```bash
    curl -X POST http://localhost:8080/liveRoom/portInfo \
      -H "Content-Type: application/json" \
      -d '{"room_url": "https://www.tiktok.com/@xxx/live"}'
    curl http://localhost:8080/health
    curl -X POST http://localhost:8080/get_roominfo \
      -H "Content-Type: application/json" \
      -d '{"client_ip": "192.168.1.100"}'
    ```

- [ ] **2.6 部署验证**
  - [ ] 部署生产环境,观察 1 天无异常

---

## 六、Phase 3:合并服务(P2,1 周)

**时间**:2026-05-15 ~ 2026-05-21
**目标**:合并 live-monitor + live-stream + live-crawler 监控,消除 HTTP 轮询

> **实际执行已升级为 MediaMTX 录制架构**,详见独立 plan [`2026-05-07-live-platform-phase1.md`](2026-05-07-live-platform-phase1.md)。
>
> 以下任务清单是早期 FFmpeg 直管方案,**phase1 plan 已用 MediaMTX 重写**;本节保留作为决策演进记录。

### 任务清单

- [ ] **3.1 创建新项目结构**
  ```bash
  mkdir -p services/live-platform/{api,tasks,ffmpeg,crawler,monitor,data}
  mkdir -p services/live-platform/tests
  ```

- [ ] **3.2 创建主入口 `services/live-platform/main.py`**(基础框架:APScheduler + FastAPI + uvicorn)

- [ ] **3.3 迁移房间检测**:从 `live-monitor/main.py` 复制 `select_Info()`、`check_live_status()` → `tasks/room_detector.py:detect_rooms()`,加入 `scheduler.add_job(detect_rooms, 'interval', seconds=60)`

- [ ] **3.4 迁移 FFmpeg 管理**(已被 MediaMTX 方案覆盖):从 `live-stream/TT_client.py` 复制 `FFmpegStreamManager` → `ffmpeg/manager.py`

- [ ] **3.5 迁移 OSS 上传**(已被 MediaMTX 切片回调方案覆盖):从 `live-stream/TT_client.py` 复制 → `tasks/oss_uploader.py`

- [ ] **3.6 迁移 GMV 采集**:从 `live-crawler/main.py` 复制 → `crawler/gmv_crawler.py`,加入 `scheduler.add_job(crawl_gmv, 'interval', minutes=5)`

- [ ] **3.7 迁移 API 路由**:`api/routes.py` 实现 `POST /liveRoom/portInfo`、`POST /liveRoom/shopeeInfo`、`POST /liveRoom/lazadaInfo`、`GET /health`

- [ ] **3.8 配置整合**:`services/live-platform/config.py` 合并三服务配置,使用环境变量

- [ ] **3.9 数据库迁移**:确认 SQLite 位置 `services/live-platform/data/monitor.db`,迁移表结构

- [ ] **3.10 编写测试**:单元测试 + 集成测试 + 端到端测试

- [ ] **3.11 压力测试**:模拟 80 路并发,验证 24 小时稳定性,CPU < 80% / 内存 < 20 GB / 带宽 < 500 Mbps

- [ ] **3.12 灰度发布**:测试环境部署 → 双写验证 → 逐步切流 → 观察 3 天 → 全量切换

- [ ] **3.13 下线旧服务**
  - [ ] `systemctl stop live-monitor && systemctl stop live-stream`
  - [ ] `mv services/live-monitor docs/archive/` 等
  - [ ] 提交:`git commit -m "合并服务完成,下线 live-monitor 和 live-stream"`

---

## 七、Phase 4:监控简化(P3,5-6 天)

**时间**:2026-05-29 ~ 2026-06-12
**目标**:日志驱动的日报 Agent 替代 SQLite + Vue 监控面板

> 原方案(SQLite 聚合 + Vue 前端 + 实时告警)已废弃。新方案拆为 4A / 4B 两步执行,详见各自 plan:
>
> - [Phase 4A: 日报 Agent](./2026-05-28-phase4a-daily-report-agent.md) — 新增日志驱动的日报功能,不破坏现有系统(2 天)
> - [Phase 4B: 删除 SQLite/补采/前端](../archive/2026-05-28-phase4b-remove-sqlite-recrawl-frontend.md) — 已执行(2026-05-28)

### 验收要点(由 4A/4B 各自 plan 详列)

- [ ] 4A 完成: 飞书每天 10:00 收到日报卡片,含完整度/异常/问题账号/趋势对比
- [x] 4B 完成: SQLite 监控面板、补采系统、监控前端移除,采集主流程无回归

---

## 八、Phase 5:验收与文档收尾(1 周)

**时间**:2026-05-25 ~ 2026-06-03

### 任务清单

- [ ] **5.1 验收测试**
  - [ ] 开播检测延迟 < 60 秒
  - [ ] 断流重连成功率 > 95%
  - [ ] 代码量 < 10,000 行
  - [ ] 服务数 = 2 个核心 + 1 个独立(adspower)
  - [ ] API 端点数 < 5 个
  - [ ] 部署机器数 = 1 台

- [ ] **5.2 更新文档**
  - [ ] 根 `CLAUDE.md`:删除已废弃服务描述
  - [ ] 根 `README.md`:更新架构图与启动命令
  - [ ] 创建 `services/live-platform/CLAUDE.md` 与 `README.md`
  - [ ] 更新 `.claude/rules/` 中的交互规则

- [ ] **5.3 清理代码**
  - [ ] 删除未使用的依赖、配置、注释代码
  - [ ] `black services/live-platform/`

- [ ] **5.4 性能基线**:记录 CPU(峰值/平均)/ 内存 / 带宽 / 磁盘 I/O

- [ ] **5.5 监控告警**:systemd 自动重启 + 磁盘空间(< 20%)/ CPU(> 90%)/ 进程存活告警(飞书)

- [ ] **5.6 备份策略**:每日数据库备份 + 日志轮转 + 仓库备份

- [ ] **5.7 运维文档**:部署文档 + 故障排查 + 回滚方案

---

## 九、里程碑

| 日期 | 里程碑 | 交付物 |
|------|--------|--------|
| 2026-05-12 | Phase 1 完成 | FFmpeg 断流修复,重连成功率 > 95% |
| 2026-05-14 | Phase 2 完成 | 删除 1,400 行非核心代码 |
| 2026-05-21 | Phase 3 完成 | 服务合并,开播检测 < 60 秒 |
| 2026-05-24 | Phase 4 完成 | 飞书日报上线 |
| 2026-06-03 | 项目完成 | 全部验收通过,文档齐全 |

---

## 十、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 单点故障(一台机器) | 高 | systemd 自动重启 + 飞书告警 + 每日备份 |
| FFmpeg 进程泄漏 | 中 | 定期检查僵尸进程 + 自动清理 |
| 磁盘空间不足 | 中 | 监控磁盘使用率 + 自动清理旧文件 |
| 迁移期间数据丢失 | 低 | 灰度发布 + 双写验证 |
| Phase 3 风险最高 | 高 | 必须灰度发布,保留旧代码备份 ≥ 1 个月 |

---

## 十一、回滚方案

```bash
# 立即回滚
systemctl stop live-platform
systemctl start live-monitor
systemctl start live-stream
git revert <commit-hash>

# 数据恢复
cp backup/monitor.db.backup services/live-monitor/data/monitor.db
```

回滚后:检查旧服务运行 → 验证核心功能 → 通知团队。

---

## 十二、注意事项

1. 每个 Phase 完成后必须验证核心功能正常
2. Phase 3(合并服务)风险最高,必须灰度发布
3. 保留旧代码备份至少 1 个月
4. 每次修改前先创建 git 分支
5. 重要操作前先在测试环境验证

---

## 十三、附录:删除的端点清单

### 13.1 live-monitor 删除的端点

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

### 13.2 保留的核心端点

- `POST /liveRoom/portInfo` — 获取 TikTok 直播间信息
- `POST /liveRoom/shopeeInfo` — 获取 Shopee 直播间信息
- `POST /liveRoom/lazadaInfo` — 获取 Lazada 直播间信息
- `GET /health` — 健康检查
- `GET /docs/doc` + `GET /docs/getConfig` — 数据在线 API 调试页

---

**文档结束**
