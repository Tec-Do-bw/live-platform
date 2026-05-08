# Live Platform 架构设计缺陷审计报告

> **审计日期：** 2026-05-03  
> **审计范围：** PRD v1.0、DDD 领域模型设计、四服务实际代码、跨服务集成  
> **审计方法：** 4 路并行 Agent 深度分析 + 交叉验证

---

## 执行摘要

| 维度 | Critical | Major | Minor |
|------|:--------:|:-----:|:-----:|
| PRD 与业务流程 | 3 | 6 | 6 |
| DDD 设计文档 | 3 | 5 | 4 |
| 代码与设计差距 | 2 | 3 | 3 |
| 跨服务集成 | 3 | 3 | 3 |
| **去重合并后** | **7** | **10** | **8** |

**核心结论：设计文档描述了一个理想化的 DDD 架构，但与实际代码存在巨大鸿沟。四个服务全部是事务脚本/贫血模型，没有聚合根、没有领域事件、没有仓储接口。DDD 设计文档缺少"AS-IS 分析"和"渐进式迁移路径"，直接落地风险极高。**

---

## 一、Critical 级别（7 项）

### C1. Context Map 严重失真，与实际依赖完全不符

**来源：** DDD 审计 + 集成审计

DDD 文档将四个上下文画成线性链（监控 → 录制 → 浏览器 → 采集），PRD 3.1 也沿用了这个拓扑。但实际代码中的依赖关系是：

```
派大星系统
  ├─ [MySQL 直连] → live-monitor ← [HTTP 轮询] ─ live-stream
  ├─ [HTTP 回调] ← adspower-server → [Cookie API] → live-crawler
  └─ [HTTP 回调] ← live-crawler
  
共享依赖：Apollo 配置中心、AdsPower 本地进程
```

关键错误：
- live-stream 与 adspower-server 之间**没有**直接依赖，但文档画了线
- live-monitor 与 live-crawler 通过 Apollo 和派大星数据库**隐式耦合**，文档未体现
- "Published Language" 和 "Shared Kernel" 在代码中均未实现

**影响：** 变更影响分析会遗漏关键依赖，上游修改破坏下游服务。

### C2. live-monitor 直连派大星 MySQL 数据库（Database Integration 反模式）

**来源：** 集成审计

`live-monitor/main.py` 通过 `pymysql` 直接查询派大星的 `live_streaming_room` 表：
```python
sql = "select room_id,room_url,allocation_status from live_streaming_room where local_status = 1"
```

这完全绕过了派大星的 API 层，违反了 DDD 中 Customer/Supplier 关系的定义。派大星的 schema 变更会直接破坏 live-monitor。

**影响：** 强耦合，数据库 schema 变更即崩溃。

### C3. 数据流架构图将并行管线误画为串行

**来源：** PRD 审计

PRD 7.1 将 live-stream 和 live-crawler 画成串行依赖，但实际上：
- live-stream 的触发条件是"开播检测到 flv_url"
- live-crawler 的触发条件是"定时任务 + 账号已登录"

两者是从 live-monitor 分叉的**两条并行管线**，没有上下游依赖。

**影响：** 误导开发团队理解系统架构，导致错误的依赖设计和排期。

### C4. 聚合根设计与实际代码严重脱节，缺少迁移路径

**来源：** DDD 审计 + 代码差距分析

DDD 文档设计了 4 个富领域模型聚合根，但实际代码中：

| 服务 | DDD 设计 | 实际代码 | 差距 |
|------|---------|---------|------|
| live-monitor | `LiveRoom` 聚合根 + 状态机 | 全局 `dict`，状态用 `"0"/"1"` | 5/5 极大 |
| live-stream | `StreamSession` 聚合根 | 全局 `dict` + 部分枚举 | 3/5 中等 |
| adspower-server | `BrowserSession` 聚合根 | 贫血 `Session` dataclass | 2/5 较小 |
| live-crawler | `CollectionSession` 聚合根 | `result` 字典 + 抽象基类 | 3/5 中等 |

文档没有"AS-IS 架构分析"和"渐进式迁移策略"，直接从事务脚本跳到富领域模型，跨度太大。

**影响：** 设计归设计、代码归代码的"两张皮"问题，团队无法落地。

### C5. 房间分配延迟 3+5=8 分钟，远超 PRD 承诺的 1 分钟

**来源：** 集成审计

- live-monitor 每 5 分钟检测一次直播状态
- live-stream 每 3 分钟轮询一次 `/get_roominfo`
- 最坏情况：直播开始后 8 分钟才开始录制

PRD 承诺"1 分钟内检测到开播"，但端到端延迟远超此值。

**影响：** 核心 SLA 无法达成，防摸鱼视频录制严重滞后。

### C6. 登出恢复和补采机制在 PRD 中完全缺失

**来源：** PRD 审计

PRD 没有覆盖两个关键业务场景：
- **登出恢复**：即时恢复路径（2 轮）、Fallback 恢复路径（3 轮）、Shopee 特殊规则（不触发即时恢复）
- **补采机制**：数据缺口检测、自动补采触发、Shopee 不支持 HTTP 补采的约束

这两个场景在 `.claude/references/` 中有详细规格文档，但 PRD 完全没有引用。

**影响：** 数据完整性的最后防线缺失，数据缺口无法修复。

### C7. DataCollection 聚合根忽略了双轨架构的本质差异

**来源：** DDD 审计

设计文档只有一个 `CollectionSession` 聚合根，但实际存在两条完全不同的采集路径：
- **浏览器采集**：`BaseLiveCrawler` → DrissionPage → API 拦截（TikTok/Shopee）
- **HTTP 采集**：`BaseHttpCrawler` → Downloader → 直接请求（Lazada）

两者的生命周期、错误处理、登录态管理完全不同，一个聚合根无法建模。

**影响：** `CollectionSession` 会变成"万能聚合根"，违反单一职责。

---

## 二、Major 级别（10 项）

### M1. live-monitor + live-stream 交互协议未定义

PRD 列出了 `/get_roominfo` 和 `/report_roominfo` 接口，但没有定义轮询频率、幂等性保证、超时处理、防重复分配机制。这是 P0 重构的核心问题。

### M2. 领域事件设计不完整，缺少关键跨上下文事件

缺少：`RoomAllocatedEvent`（触发录制）、`LoginStatusChangedEvent`（切换采集模式）、`StreamFailedEvent`（通知监控）、`CookieExpiredEvent`（触发重登录）。四个服务全部没有事件总线基础设施。

### M3. 监控系统缺少 live-stream 和 live-monitor 的数据整合

PRD 第 5 节的监控系统只覆盖 live-crawler 的采集完整性，完全没有流健康状态（断流率、重连次数）和房间状态（检测延迟、在线房间数）。

### M4. 仓储接口设计忽略了实际存储异构性

四个服务的存储方式完全不同：live-monitor 用内存 dict + MySQL，live-stream 纯内存，adspower-server 纯内存，live-crawler 用 SQLite + JSON 文件。统一的 Repository CRUD 接口不适用于内存存储的服务。

### M5. BrowserSession 聚合根过大，混合了三种不同平台的登录逻辑

`LoginMonitorService` 单文件 889 行，包含 Shopee 网络包监听、TikTok Cookie 轮询、Lazada JS Hook 注入三种完全不同的逻辑。应拆分为 `BrowserSession`（生命周期）+ `LoginSession`（登录流程，策略模式区分平台）。

### M6. Kafka 发送无容错，视频切片元数据可能丢失

live-stream 的 `KafkaHelper.sendToKafka()` 没有处理发送失败的回调。如果 Kafka 不可用，视频切片数据直接丢失，无本地 WAL 落盘。

### M7. 平台差异化规则未在 PRD 中体现

TikTok/Shopee/Lazada 在采集方式、登录流程、时区处理、补采支持、登出恢复上有显著差异，PRD 没有平台差异矩阵。

### M8. 与派大星系统的集成点定义不完整

登录回调 payload 格式、Kafka 消息格式、API 鉴权方式等均未在 PRD 中定义。adspower-server 和 live-crawler 各自独立实现了登录回调，payload 格式不一致。

### M9. 验收标准不可量化、不可测试

"断流重连成功率 > 90%" 没有定义测试方法和统计窗口；"监控系统能支撑日常运维" 无法作为验收依据。

### M10. StreamSession 聚合根缺少 OSS 上传和 Kafka 推送建模

DDD 文档只建模了 FFmpeg 推流状态，忽略了文件监控 → 大文件切割 → OSS 上传 → Kafka 推送的完整流水线。

---

## 三、Minor 级别（8 项）

| # | 缺陷 | 影响 |
|---|------|------|
| m1 | 非功能需求缺少容灾、降级、限流设计 | 单机部署无自动恢复 |
| m2 | `LiveInfo` 应为值对象而非实体 | 影响相等性判断 |
| m3 | `Platform` 应为枚举而非值对象 | 允许创建无效平台值 |
| m4 | 应用服务层存在领域逻辑泄漏 | 业务规则分散 |
| m5 | 缺少防腐层（Apollo/飞书/AdsPower API 各服务重复封装） | 外部 API 变更需改多处 |
| m6 | 风险评估遗漏反爬升级、Cookie 批量过期、单点故障等 | 风险应对不足 |
| m7 | 养号服务 P0 优先级偏高（应为 P1） | 资源分配不合理 |
| m8 | 实施路线图 3 周过于乐观（实际需 8-10 周） | 项目延期风险 |

---

## 四、代码现状 vs DDD 设计差距矩阵

| 维度 | live-monitor | live-stream | adspower-server | live-crawler |
|------|:-----------:|:-----------:|:---------------:|:------------:|
| 聚合根 | ❌ 无 | ⚠️ 有雏形 | ⚠️ 贫血模型 | ❌ 无 |
| 值对象 | ❌ 无 | ✅ StreamStatus | ⚠️ 概念存在 | ✅ CollectionMode |
| 领域事件 | ❌ 无 | ❌ 无 | ❌ 无 | ❌ 无 |
| 仓储接口 | ❌ 裸 SQL | ❌ 全局 dict | ⚠️ SessionManager | ❌ 直接 SQLite |
| 领域服务 | ❌ 无 | ❌ 无 | ⚠️ LoginMonitorService | ✅ collection_mode |
| 分层架构 | ❌ God Object | ❌ 单文件 | ✅ api/services/models | ⚠️ 半分层 |
| 测试覆盖 | ❌ 无 | ❌ 无 | ❌ 无 | ⚠️ monitor 模块 |
| **DDD 差距** | **5/5 极大** | **3/5 中等** | **2/5 较小** | **3/5 中等** |
| **重构工作量** | **3-4 周** | **1.5-2 周** | **1-1.5 周** | **2-2.5 周** |

---

## 五、安全与运维风险

| 风险 | 严重程度 | 位置 |
|------|---------|------|
| Access Token 硬编码且已过期（exp=2025-01-01） | 🔴 高 | 多个服务的 config 文件 |
| 代理凭证硬编码（200+ 代理 IP 明文） | 🔴 高 | live-monitor/main.py:1144 |
| 内存状态不持久化，重启丢失所有数据 | 🔴 高 | live-monitor, live-stream, adspower-server |
| Cookie 写入无并发控制 | 🟡 中 | adspower-server → live-crawler |
| Apollo 配置客户端三份不同实现 | 🟡 中 | 三个服务各自实现 |
| 无服务发现，IP 硬编码 | 🟡 中 | live-stream 主备节点 |

---

## 六、推荐行动计划

### Phase 0：文档修正（1-2 天）

1. 重画 Context Map 为网状拓扑，反映实际依赖
2. 修正 PRD 数据流为两条并行管线
3. 补充登出恢复、补采机制、平台差异矩阵到 PRD
4. DDD 文档增加"AS-IS 架构分析"章节

### Phase 1：P0 稳定性修复（2 周）

1. 修复房间分配延迟（改为事件驱动或缩短轮询间隔）
2. 修复 live-stream 断流问题（FFmpeg 参数优化）
3. Kafka 发送增加容错（本地 WAL + 重试）
4. 敏感信息迁移到环境变量/Apollo

### Phase 2：渐进式 DDD 重构（6-8 周）

按 DDD 差距从小到大的顺序重构：
1. **adspower-server**（1-1.5 周）— 差距最小，已有分层
2. **live-crawler**（2-2.5 周）— OOP 基础好
3. **live-stream**（1.5-2 周）— 已有枚举和配置类
4. **live-monitor**（3-4 周）— 差距最大，风险最高，最后做

采用 **Strangler Fig 模式**，逐步替换而非一次性重写。

### Phase 3：跨服务治理（持续）

1. 引入进程内事件总线 → 后续升级为 Kafka 事件
2. live-monitor 改为通过派大星 API 获取数据（去除数据库直连）
3. 抽取共享库（Apollo 客户端、登录回调、配置管理）
4. 统一监控系统整合三个数据源

---

**文档结束**
