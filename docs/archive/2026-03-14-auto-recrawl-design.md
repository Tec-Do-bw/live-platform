# 自动补采闭环 设计文档

> **Issue**: #7 — feat(monitor): P1 — 自动补采闭环（爬虫根据监控系统自动补采）
> **分支**: `feature/auto-recrawl`
> **日期**: 2026-03-14

## 1. 背景与目标

当前采集系统具备完整性监控能力（P0 已完成），能检测到 API 采集缺失，但缺失后仍需人工手动补采。本功能实现自动补采闭环：

```
正常采集完成 → 缺失检测 → 生成补采任务 → 执行补采 → 验证结果 → 闭环
```

同时重构前端为**账号总览视角**（跨批次聚合），替代现有的批次割裂视图。

## 2. 核心决策

| 维度 | 决策 |
|------|------|
| 触发方式 | 混合：批次完成后自动补采 + 前端手动触发（三级粒度） |
| 手动触发粒度 | 账号级 / 日期级 / 直播间级，所有数据项均可触发（含已成功项） |
| 补采执行方式 | 独立 HTTP 请求模块（复用 AdsPower 代理 IP） |
| 重试策略 | 固定 3 次，间隔 1s → 3s → 10s，失败标记 `recrawl_failed` |
| 架构模式 | 任务队列驱动（`recrawl_tasks` 表，统一入口） |
| 前端首页 | 改为账号总览（跨批次聚合），批次视图降级为二级页面 |
| 时间范围 | 可选，默认近 3 天 |
| 缺失检测 | 时间窗口内跨批次聚合（任意批次成功即不算缺失） |

## 3. 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    前端 (Vue3)                       │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ 账号总览(首页) │  │  批次历史     │  │ 补采任务  │ │
│  │ 跨批次聚合    │  │ (二级页面)    │  │  状态面板 │ │
│  │ 手动补采按钮  │  │              │  │          │ │
│  └──────┬───────┘  └──────────────┘  └─────┬─────┘ │
│         │ POST /api/recrawl/*               │       │
└─────────┼───────────────────────────────────┼───────┘
          ▼                                   ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI 后端                        │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ 账号总览 API  │  │ 补采任务 API │  │ 缺失检测  │ │
│  │ (聚合查询)    │  │ (CRUD)      │  │    器     │ │
│  └──────────────┘  └──────┬───────┘  └─────┬─────┘ │
│                           │                │       │
│                    ┌──────▼────────────────▼─────┐ │
│                    │      补采执行器              │ │
│                    │  ┌─────────┐ ┌───────────┐  │ │
│                    │  │代理获取  │ │HTTP 请求   │  │ │
│                    │  │AdsPower │ │(带代理)    │  │ │
│                    │  └─────────┘ └───────────┘  │ │
│                    │  ┌─────────┐                │ │
│                    │  │补采验证器│                │ │
│                    │  └─────────┘                │ │
│                    └─────────────────────────────┘ │
│                                                     │
│  SQLite: collection_records + recrawl_tasks         │
│          + request_context                          │
└─────────────────────────────────────────────────────┘
```

### 数据流

```
批次完成 → 缺失检测器 → recrawl_tasks (source=auto)
                                ↓
前端手动触发 ──────────→ recrawl_tasks (source=manual)
                                ↓
                         补采执行器（消费 pending）
                                ↓
                    AdsPower 获取代理 → HTTP 请求
                                ↓
                         补采验证器 → 更新状态
```

## 4. 数据模型

### 4.1 recrawl_tasks（补采任务队列）

```sql
CREATE TABLE IF NOT EXISTS recrawl_tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id      TEXT NOT NULL,       -- 原始采集批次
    account_id    TEXT NOT NULL,       -- 账号 ID (browser_id)
    group_name    TEXT DEFAULT '',     -- AdsPower 分组名
    room_id       TEXT DEFAULT '',     -- 直播间 ID（账号级/日期级为空）
    target_date   TEXT DEFAULT '',     -- 目标日期（日期级补采，YYYY-MM-DD）
    api_type      TEXT NOT NULL,       -- 缺失的 API 类型
    level         TEXT NOT NULL,       -- 补采级别：account / daily / room
    source        TEXT NOT NULL,       -- 触发来源：auto / manual
    status        TEXT DEFAULT 'pending', -- pending → running → success / recrawl_failed
    retry_count   INTEGER DEFAULT 0,  -- 已重试次数（最大 3）
    error_msg     TEXT DEFAULT '',     -- 失败原因
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(batch_id, account_id, room_id, target_date, api_type)
);
```

**状态流转**：`pending` → `running` → `success` / `recrawl_failed`

**冲突处理策略**：
- **自动补采**：`INSERT OR IGNORE`，已存在的任务不重复创建
- **手动触发**：使用 `INSERT ... ON CONFLICT DO UPDATE SET status='pending', retry_count=0, source='manual', updated_at=CURRENT_TIMESTAMP`，无论任务当前状态（含已成功项），均可重置为 pending 重新执行

### 4.2 request_context（请求上下文缓存）

正常采集时持久化关键请求参数，供补采模块复用。

```sql
CREATE TABLE IF NOT EXISTS request_context (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id       TEXT NOT NULL,
    context_type     TEXT NOT NULL,       -- trend_chart / live_stats
    api_base_url     TEXT DEFAULT '',     -- API 基础 URL
    query_string     TEXT DEFAULT '',     -- URL 查询参数
    headers          TEXT DEFAULT '{}',   -- 请求头 JSON
    cookies          TEXT DEFAULT '[]',   -- cookies JSON
    payload_template TEXT DEFAULT '{}',   -- 请求体模板 JSON（live_stats 用）
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, context_type)
);
```

**写入时机**：
- `tiktok.py:_handle_tiktok_live_list` 提取到 headers / api_base_url / query_string 时 → `context_type='trend_chart'`
- `browserapi.py:_handle_live_stats_injection` 拦截到 live/stats 时 → `context_type='live_stats'`

**api_type → context_type 映射关系**：

| api_type | context_type | 说明 |
|----------|-------------|------|
| `trend_gmv` | `trend_chart` | 共用 trend/chart 端点，Body 中 stats_types 不同 |
| `trend_stats` | `trend_chart` | 同上 |
| `live_stats` | `live_stats` | 独立端点 |

补采执行器通过此映射查找对应的 `request_context` 记录。

## 5. 核心模块设计

### 5.1 缺失检测器 (`monitor/recrawl/gap_detector.py`)

**职责**：在时间窗口内，对比 registry 期望 API 与 collection_records 实际记录，输出缺失清单。

**逻辑**：
1. 从 `room_sessions` 获取时间窗口内的所有直播间（基于 `start_time` Unix 时间戳筛选，DISTINCT 去重跨批次重复）
2. 从 `collection_records` 获取所有成功记录（跨批次聚合，任意批次 status='success' 即视为已采集）
3. 从 `daily_collection_status` 获取日期级记录（同样跨批次聚合）
4. 对比 `API_TYPE_REGISTRY` 中的期望清单
5. 输出缺失列表：`[{account_id, room_id, target_date, api_type, level}]`

### 5.2 补采执行器 (`monitor/recrawl/executor.py`)

**职责**：消费 `recrawl_tasks` 表中的 pending 任务，执行 HTTP 请求补采。

**执行流程**：
```python
def execute_task(task):
    # 1. 获取代理 IP
    proxy = get_proxy_from_adspower(task.account_id)

    # 2. 读取请求上下文（通过 api_type → context_type 映射）
    CONTEXT_MAP = {'trend_gmv': 'trend_chart', 'trend_stats': 'trend_chart', 'live_stats': 'live_stats'}
    ctx = get_request_context(task.account_id, CONTEXT_MAP.get(task.api_type, task.api_type))

    # 3. 重试循环
    delays = [1, 3, 10]
    for attempt in range(3):
        try:
            data = fetch_api_data(
                api_type=task.api_type,
                room_id=task.room_id,
                target_date=task.target_date,
                proxy=proxy,
                headers=ctx.headers,
                cookies=ctx.cookies,
                base_url=ctx.api_base_url,
                query_string=ctx.query_string
            )
            send_to_data_server(data)

            if verify_collection(task):
                task.status = 'success'
                return
        except Exception as e:
            task.retry_count += 1
            task.error_msg = str(e)
            if attempt < 2:
                time.sleep(delays[attempt])

    task.status = 'recrawl_failed'
```

**安全措施**：
- 同账号补采任务**串行执行**，避免同 IP 并发
- 账号间可并行，最大并发数 2
- 请求间隔 ≥ 2 秒
- HTTP 请求带完整 headers 模拟浏览器
- 代理 IP 通过 AdsPower V2 API 获取 `user_proxy_config`

### 5.3 代理获取

```python
def get_proxy_from_adspower(account_id: str) -> dict:
    """通过 AdsPower API 获取账号对应的代理配置"""
    # POST /api/v2/browser-profile/list
    # body: { "profile_id": [account_id] }
    # 返回 user_proxy_config: { proxy_type, proxy_host, proxy_port, proxy_user, proxy_password }
    # 构造 requests 代理参数: { "https": "socks5://user:pass@host:port" }
```

### 5.4 补采验证器

补采执行后，检查 `collection_records` 中是否新增了成功记录。验证通过则更新任务状态为 `success`。

### 5.5 请求格式要求（关键）

补采 HTTP 请求必须完全复刻原始 JS 注入请求格式：

**trend/chart**（参考 `tiktok.py:_fetch_trend_chart_via_js`）：
- URL: `{api_base_url}/api/v1/insights/creator/liveroom/recap/trend/chart?{query_string}`
- Headers: 继承自 live/list 请求头（过滤 `:` 伪头部，补 Content-Type）
- Body GMV: `{"request": {"room_filter": {"room_id": "<id>", "query_online": true}, "stats_types": [3], "granularity": 1}}`
- Body Stats: `{"request": {"room_filter": {"room_id": "<id>", "query_online": true}, "stats_types": [3, 20, 341, 21, 22, 12, 16, 23, 50, 51, 40], "granularity": 1}}`

**live/stats**（参考 `browserapi.py:_handle_live_stats_injection`）：
- URL: 继承自原始 live/stats URL
- Headers: 继承自原始 packet.request.headers
- Body: 深拷贝原始 payload，替换 time_selector

## 6. API 端点

### 6.1 账号总览

```
GET /api/overview?days=3
```

返回时间窗口内所有账号的聚合完整率。`account_name` 从 AdsPower `list_browsers` API 的 `name` 字段获取（即 `account_sessions` 中暂无此字段，由 overview API 查询时从 AdsPower 补充，或在 `account_sessions` 表新增 `name` 列缓存）。

**完整率计算公式**：
```
completeness = 已采集成功数 / 期望总数 × 100
期望总数 = 账号级 API 数 + 时间窗口内日期数 × 日期级 API 数 + 时间窗口内直播间数 × 直播间级 API 数
已采集成功数 = 跨批次聚合后 status='success' 的去重记录数
```
三个层级（账号级、日期级、直播间级）统一纳入计算，不设权重。

```json
{
  "accounts": [
    {
      "account_id": "k175kd0t",
      "account_name": "...",
      "group_name": "新加坡团队-tiktok",
      "completeness": 95.0,
      "total_rooms": 12,
      "missing_count": 3,
      "last_batch_id": "2026-03-14_14:30",
      "last_collected_at": "2026-03-14T14:35:00"
    }
  ],
  "time_range": {"start": "2026-03-12", "end": "2026-03-14"},
  "days": 3
}
```

### 6.2 账号聚合详情

```
GET /api/overview/{account_id}?days=3
```

返回该账号三级聚合状态（跨批次合并，任意批次成功即为成功）。

```json
{
  "account_level": [
    {"api_type": "live_list", "status": "success", "last_batch": "..."},
    {"api_type": "replay_info", "status": "missing", "last_batch": null}
  ],
  "daily_level": [
    {"target_date": "2026-03-14", "api_type": "live_stats", "status": "success"},
    {"target_date": "2026-03-13", "api_type": "live_stats", "status": "missing"}
  ],
  "room_level": [
    {
      "room_id": "xxx", "room_name": "...",
      "apis": [
        {"api_type": "trend_gmv", "status": "success"},
        {"api_type": "trend_stats", "status": "missing"}
      ]
    }
  ],
  "completeness": 95.0
}
```

### 6.3 补采任务

```
POST /api/recrawl/trigger
```

手动触发补采：

```json
{
  "account_id": "k175kd0t",
  "level": "room",
  "room_id": "xxx",
  "api_type": "trend_gmv",
  "target_date": "",
  "batch_id": "2026-03-14_14:30"
}
```

```
GET /api/recrawl/tasks?account_id=xxx&status=pending
```

查询补采任务列表。

### 6.4 批次历史（保留原有）

```
GET /api/batches
GET /api/batches/{batch_id}/accounts
```

## 7. 前端改版

### 7.1 页面结构

| 页面 | 路由 | 说明 |
|------|------|------|
| 账号总览 (首页) | `/` | 跨批次聚合视角，时间筛选器，状态筛选，一键补采 |
| 账号详情 | `/account/:id` | 三级详情 + 每项补采按钮 + 底部补采任务面板 |
| 批次历史 | `/batches` | 原有批次视图（降级为二级页面） |

### 7.2 账号总览页

- 卡片网格展示所有账号
- 每张卡片：账号名、分组名、环形完整率、直播间数、缺失数、一键补采按钮
- 顶部时间筛选器：近 3 天（默认）/ 近 7 天 / 近 30 天 / 自定义
- 状态筛选：全部 / 成功 / 部分 / 失败

### 7.3 账号详情页增强

- 账号级 / 日期级 / 直播间级每个数据项都有补采按钮（无论成功失败）
- 缺失项高亮显示
- 底部补采任务面板：展示该账号的补采任务状态（来源、API 类型、目标、状态、重试次数）

## 8. 自动补采触发流程

```
main.py: run_once() 末尾
  │
  ▼
monitor.finish_batch(batch_id)
  │
  ▼
recrawl.auto_detect_and_create(batch_id, days=3)
  │
  ├─ 1. 缺失检测：对比 registry 期望 vs collection_records 实际
  │     （时间窗口内跨批次聚合，已在其他批次成功的不算缺失）
  │
  ├─ 2. 生成补采任务：写入 recrawl_tasks (source='auto', INSERT OR IGNORE)
  │     （UNIQUE 约束防止重复）
  │
  ├─ 3. 执行补采：使用 ThreadPoolExecutor 异步消费 pending 任务
  │     ├─ 获取 AdsPower 代理 IP
  │     ├─ 读取 request_context
  │     ├─ 同账号串行，账号间并行（最大并发 2）
  │     ├─ 请求间隔 ≥ 2 秒
  │     └─ 每个任务最多重试 3 次 (1s → 3s → 10s)
  │
  └─ 4. 验证 + 更新状态
        ├─ 成功：status='success'
        └─ 失败：retry_count 达上限 → status='recrawl_failed'
```

**执行模式**：补采在 `run_once()` 中**同步阻塞**执行（步骤 1-2 生成任务 + 步骤 3-4 执行任务）。虽然会延长采集周期，但保证补采在下次调度前完成。`--mode scheduler` 下由 APScheduler 控制间隔，补采执行时间在可控范围内。`--mode full` 下不触发自动补采（全量采集本身已覆盖所有数据）。

**并发实现**：使用 `concurrent.futures.ThreadPoolExecutor(max_workers=2)` 实现账号间并行，每个线程内串行处理该账号的任务。

## 9. 配置化

```python
# core/config_base.py
RECRAWL_CONFIG = {
    "enabled": True,              # 自动补采开关
    "max_retry": 3,               # 最大重试次数
    "retry_delays": [1, 3, 10],   # 重试间隔（秒）
    "request_interval": 2,        # 同账号请求间隔（秒）
    "max_concurrent": 2,          # 最大并发账号数
    "default_days": 3,            # 默认检测时间窗口（天）
}
```

## 10. 文件结构（新增）

```
live_dp/monitor/
├── recrawl/                     # 补采模块（新增）
│   ├── __init__.py
│   ├── gap_detector.py          # 缺失检测器
│   ├── executor.py              # 补采执行器
│   ├── proxy.py                 # AdsPower 代理获取
│   └── models.py                # 补采任务数据模型
├── api/
│   ├── overview.py              # 账号总览 API（新增）
│   ├── recrawl_routes.py        # 补采任务 API（新增）
│   ├── batches.py               # 原有
│   └── accounts.py              # 原有
├── db.py                        # 新增 recrawl_tasks + request_context 表
└── tracker.py                   # 新增 request_context 写入逻辑

live_dp/monitor/frontend/src/
├── views/
│   ├── AccountOverview.vue      # 账号总览页（新增，替代 Dashboard 为首页）
│   ├── AccountDetail.vue        # 增强：补采按钮 + 补采任务面板
│   └── BatchHistory.vue         # 由 Dashboard.vue 改名，降级为二级页面
├── api/
│   └── index.js                 # 新增 overview / recrawl API 调用
└── router/
    └── index.js                 # 路由调整
```

## 11. 错误处理与降级策略

| 异常场景 | 处理方式 |
|---------|---------|
| `request_context` 为空（首次运行/未写入） | 跳过该账号补采，日志告警，不标记 `recrawl_failed` |
| AdsPower 服务不可用 | 跳过整轮自动补采，日志告警 |
| 代理连接失败 | 计入重试次数，error_msg 记录 `proxy_error` |
| HTTP 401/403（session 过期） | 直接标记 `recrawl_failed`，error_msg 记录 `session_expired`，不做无意义重试 |
| HTTP 429（频率限制） | 延长等待间隔至 30 秒后重试 |
| HTTP 5xx（服务端错误） | 正常重试 |
| SQLite SQLITE_BUSY（并发写入冲突） | 现有 WAL 模式 + 5 秒 busy_timeout 已足够；补采写入使用独立连接，与爬虫主流程隔离 |

## 12. 数据清理策略

`recrawl_tasks` 表设置自动清理：30 天前的 `success` / `recrawl_failed` 状态任务在每次补采执行前自动删除。

## 13. 后续优化（记录到 GitHub Issue）

- HTTP 请求的具体实现（cookies 获取、API 参数构造）需要后续验证和优化
- 当前先搭建任务队列框架和前端交互，HTTP 请求实现预留接口
- 考虑 cookies 过期问题：补采请求可能因 session 过期而失败，后续可扩展为 JS 注入方式
