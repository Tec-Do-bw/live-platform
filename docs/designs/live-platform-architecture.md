# Live Platform 技术架构设计

> **版本：** v1.0  
> **日期：** 2026-05-05  
> **状态：** Draft  
> **作者：** XBW

---

## 1. 系统架构

### 1.1 DDD 限界上下文

```
┌─────────────────────────────────────────────────────────────────┐
│                        派大星系统 (外部)                          │
│  - 录入直播间地址                                                 │
│  - 发起登录授权                                                   │
│  - 消费 GMV 数据 (Kafka)                                         │
└────────────┬────────────────────────────────────────────────────┘
             │ API 调用
             ▼
┌─────────────────────────────────────────────────────────────────┐
│  直播间监控上下文 (live-monitor)  ★ 中心枢纽                      │
│  聚合根: LiveRoom                                                 │
│  职责:                                                            │
│  - 直播间状态管理 (待监控→监控中→开播→下播)                      │
│  - 开播检测 (1分钟内检测到)                                       │
│  - 房间分配 (通过 /get_roominfo 被动响应)                        │
│  - 主备高可用                                                     │
│  - Kafka 消息推送 (GMV/状态变更)                                  │
└──────────┬──────────────────────────────────────────────────────┘
           │                                    │
           │ 轮询 /get_roominfo (60s)           │ Kafka 消息
           │                                    │
           ▼                                    ▼
┌──────────────────────────┐         ┌──────────────────────────┐
│  视频流录制上下文         │         │  数据仓库 (外部)          │
│  (live-stream)           │         │  - 消费 Kafka 消息        │
│  聚合根: StreamSession   │         │  - 数据清洗计算           │
│  职责:                   │         └──────────────────────────┘
│  - FFmpeg 推流           │
│  - 断流重连              │
│  - 视频切割 (8s)         │
│  - OSS 上传              │
└──────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  浏览器管理上下文 (adspower-server)  ★ 独立服务                  │
│  聚合根: BrowserSession                                           │
│  职责:                                                            │
│  - AdsPower 浏览器生命周期管理                                    │
│  - CDP 投屏转发 (用户远程登录)                                    │
│  - 登录监控 (TikTok/Shopee/Lazada)                               │
│  - 登录回调通知 → live-crawler                                    │
└────────────┬────────────────────────────────────────────────────┘
             │ 双向依赖
             │ ↑ Cookie 获取 (live-crawler → adspower-server)
             │ ↓ 登录回调 (adspower-server → live-crawler)
             ▼
┌─────────────────────────────────────────────────────────────────┐
│  数据采集上下文 (live-crawler)                                    │
│  聚合根: CollectionSession                                        │
│  职责:                                                            │
│  - 双轨采集 (浏览器 TikTok/Shopee + HTTP Lazada)                 │
│  - GMV 数据采集 (5分钟实时采集)                                   │
│  - 数据上报 (Kafka)                                               │
│  - 采集完整性监控                                                 │
│  - 登出恢复 + 补采机制 (详见 4.4.4)                               │
│  - 养号服务 (Cookie 刷新)                                         │
└─────────────────────────────────────────────────────────────────┘
```

**关键交互说明：**
- live-stream 与 live-monitor 是**轮询依赖**（60s 间隔），非推送，存在延迟
- live-crawler 与 adspower-server 是**双向依赖**（Cookie 获取 + 登录回调）
- live-monitor 通过 Kafka 异步推送 GMV 和状态变更消息
- 四个上下文之间**无直接的串行依赖链**，是网状拓扑

### 1.2 技术架构分层

```
┌─────────────────────────────────────────────────────────────────┐
│  表现层 (Presentation Layer)                                     │
│  - FastAPI REST API                                              │
│  - WebSocket (投屏、实时推送)                                    │
│  - Vue3 监控面板                                                 │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  应用层 (Application Layer)                                      │
│  - Use Cases (业务流程编排)                                      │
│  - 定时任务调度 (APScheduler)                                    │
│  - 事件处理器 (Event Handlers)                                   │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  领域层 (Domain Layer)                                           │
│  - 聚合根 (LiveRoom, StreamSession, BrowserSession, ...)        │
│  - 领域服务 (LoginMonitor, StreamHealthChecker, ...)            │
│  - 领域事件 (LiveRoomDetectedEvent, ...)                        │
│  - 值对象 (Platform, StreamStatus, ...)                         │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  基础设施层 (Infrastructure Layer)                               │
│  - 数据库 (SQLite/MySQL)                                         │
│  - 消息队列 (Kafka)                                              │
│  - 对象存储 (OSS)                                                │
│  - 外部服务 (AdsPower API, FFmpeg)                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 数据流

### 2.1 端到端数据流

```
派大星系统录入直播间
    ↓
live-monitor 监控开播
    ↓
live-stream 拉取视频流 → OSS 存储 → Kafka 通知
    ↓
用户登录授权（adspower-server）
    ↓
live-crawler 采集 GMV 数据 → Kafka 推送
    ↓
数据仓库消费 Kafka → 清洗计算
    ↓
派大星系统展示数据
```

### 2.2 Kafka Topic 设计

| Topic | 生产者 | 消费者 | 说明 |
|-------|--------|--------|------|
| `liveTs` | live-stream | 数据仓库 | 视频切片上传通知 |
| `streamer_lazada_relate_data` | live-crawler | 数据仓库 | Lazada 采集数据 |
| `streamer_tiktok_relate_data` | live-crawler | 数据仓库 | TikTok 采集数据 |
| `streamer_shopee_relate_data` | live-crawler | 数据仓库 | Shopee 采集数据 |

---

## 3. 重构优先级

### 3.1 P0 - 核心稳定性（1-2周）

#### 1. 修复 live-stream 断流问题

**当前约束：**

| 参数 | 当前值 | 问题 | 建议值 |
|------|--------|------|--------|
| 最大重试次数 | 5 次 | 不够，直播流波动频繁 | 10 次 |
| 心跳检测间隔 | 30s | 太长，断流感知延迟 | 10s |
| 无数据超时 | 60s | 太长，断流后 60s 才触发重连 | 30s |
| 重试初始间隔 | 3s | 偏长，可缩短 | 1s |
| 稳定运行判定 | 60s 后重置重试计数 | 合理但阈值可调 | 保持 60s |

**优化方案：**
- 优化 FFmpeg 参数（重连、超时、缓冲）
- 增强重连机制（指数退避、健康检查）
- 添加流状态监控（心跳检测）

**验收标准：** 断流重连成功率 > 90%

#### 2. 优化 live-crawler 监控架构

**当前问题：** 监控通过 API 存储，架构冗余

**优化方案：**
```
# 当前架构（冗余）
live-crawler → 调用监控 API → 写入 monitor.db → 前端读库

# 优化后架构
live-crawler → 直接写入 monitor.db
                      ↓
                前端直接读库
```

**具体改动：**
- 移除 `monitor/api/` 中的写入接口（保留查询接口）
- `CollectionTracker` 直接操作 `monitor.db`
- `registry.py` 直接写入 `collection_events` 表
- `login_status_manager` 直接写入 `account_login_events` 表

**验收标准：** 监控系统响应时间 < 2s

### 3.2 P1 - 监控系统增强（1周）

#### 1. 实现数据采集监控 MVP（Phase 1）

**功能范围：**
- 国家 -> 平台 -> 账号三层视角
- 实时运行健康（最近 15/30/60 分钟）
- 今日报告就绪度
- 统一数据集模型

**技术实现：**
- 前端：Vue3 + Element Plus
- 后端：FastAPI 托管静态文件
- 数据：直接读取 `monitor.db`

**验收标准：**
- 首页能展示国家 -> 平台视角
- 能区分实时运行健康和报告就绪度
- 响应时间 < 2 秒

### 3.3 P2 - 架构优化（后续）

#### 1. live-crawler 改为纯 API + 养号服务

**当前问题：**
- 浏览器采集与养号服务耦合
- 浏览器依赖导致部署复杂

**优化方案：**
- 拆分为独立的养号服务
- 纯 HTTP API 采集（去除浏览器依赖）
- TikTok/Shopee 改用 HTTP 补采接口

#### 2. 完善监控系统（Phase 2/3）

**Phase 2：视频流录制监控**
- 推流健康度（断流次数、重连成功率）
- 视频切割上传成功率
- OSS 上传延迟
- 当前录制房间数

**Phase 3：直播间监控**
- 开播检测时效（1分钟内检测率）
- 房间分配成功率
- 主备切换状态
- WebSocket 连接数

**Phase 4：统一告警**
- 开播历史统计
- 告警通知（飞书）
- 异常自动诊断

---

## 4. 技术风险与应对

### 4.1 技术风险

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| FFmpeg 断流无法彻底解决 | 高 | 引入多源备份、智能缓冲 |
| AdsPower API 不稳定 | 中 | 增加重试机制、降级方案 |
| Kafka 消息堆积 | 中 | 监控消费延迟、扩容 |
| 监控数据库性能瓶颈 | 低 | SQLite → MySQL 迁移方案 |

### 4.2 外部依赖

| 依赖 | 提供方 | 风险 | 应对措施 |
|------|--------|------|---------|
| 派大星系统 API | 其他团队 | 接口变更需要同步 | 版本化 API，向后兼容 |
| AdsPower 服务 | 第三方 | 服务不稳定 | 本地缓存 + 重试机制 |
| 阿里云 OSS | 阿里云 | 费用、稳定性 | 监控用量，设置告警 |
| Kafka 集群 | 基础设施 | 容量、性能 | 监控消费延迟，预留扩容方案 |

---

## 5. 部署架构

### 5.1 当前部署方案

| 服务 | 部署方式 | 节点数 | 说明 |
|------|---------|--------|------|
| live-monitor | 单机部署 | 2（主备） | 主备高可用，通过 `/health` 检测 |
| live-stream | 单机部署 | 多节点 | Windows 多机部署，轮询 live-monitor |
| adspower-server | 单机部署 | 1 | 独立服务，管理浏览器环境 |
| live-crawler | 单机部署 | 1 | 定时任务 + 监控面板 |

### 5.2 扩展方案

**水平扩展：**
- live-stream：增加 Windows 节点，通过 IP 注册到 live-monitor
- live-crawler：多进程并发采集（`--workers N`）

**垂直扩展：**
- 监控数据库：SQLite → MySQL
- Kafka：增加分区数

---

## 6. 监控数据模型

### 6.1 核心表结构

#### account_sessions（采集执行记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| batch_id | TEXT | 批次 ID |
| account_id | TEXT | 账号 ID |
| platform | TEXT | 平台（tiktok/shopee/lazada） |
| country | TEXT | 国家 |
| status | TEXT | 状态（success/error/logout） |
| error_message | TEXT | 错误信息 |
| started_at | TIMESTAMP | 开始时间 |
| finished_at | TIMESTAMP | 结束时间 |

#### collection_events（数据集采集明细）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| batch_id | TEXT | 批次 ID |
| account_id | TEXT | 账号 ID |
| dataset_key | TEXT | 数据集标识 |
| status | TEXT | 状态（success/error） |
| created_at | TIMESTAMP | 创建时间 |

#### account_login_events（登录状态事件）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| account_id | TEXT | 账号 ID |
| event_type | TEXT | 事件类型（login/logout） |
| reason | TEXT | 登出原因 |
| mode_label | TEXT | 采集模式 |
| created_at | TIMESTAMP | 事件时间 |

### 6.2 统一数据集模型

| dataset_key | 用途 | 说明 |
|-------------|------|------|
| `realtime_account_snapshot` | 运行健康 | 实时账号级摘要 |
| `realtime_room_catalog` | 运行健康 | 实时直播间清单 |
| `realtime_room_core` | 运行健康 | 实时直播间核心详情 |
| `report_room_catalog` | 报告就绪 | 今日直播间清单 |
| `report_daily_summary` | 报告就绪 | 日级汇总 |
| `report_room_core` | 报告就绪 | 场次级核心指标 |

---

## 7. 技术债务

### 7.1 已知问题

| 问题 | 影响 | 优先级 | 计划 |
|------|------|--------|------|
| live-stream `online_room_list` 竞态风险 | 中 | P1 | 改用线程安全的数据结构 |
| live-monitor 与 live-stream 轮询延迟 | 中 | P2 | 改为推送模式（WebSocket） |
| live-crawler 浏览器依赖 | 高 | P2 | 改为纯 HTTP API |
| 监控 API 冗余层 | 低 | P0 | 已在重构计划中 |

### 7.2 待优化项

- live-stream 单文件架构（TT_client.py）拆分为模块
- live-monitor 全局字典改为数据库持久化
- 统一日志格式和日志收集
- 统一配置管理（Apollo 配置中心）

---

**文档结束**
