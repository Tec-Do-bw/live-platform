# 设计文档：以直播场次为核心的采集完整性监控

> **Issue:** #6 — feat(monitor): P0 — 以直播场次为核心的采集完整性监控
> **日期:** 2026-03-14
> **状态:** 已确认（审查修订版 v3 — 补充日期级监控）

## 1. 目标

一眼看到每场直播、每天的关键数据是否采集齐全。后续新增指标只需注册即可自动出现在面板，前端无需改动。

## 2. 核心约束

- 本次监控三个层级的 API（使用**现有代码中的实际 api_type 名称**）：
  - **账号级**：`live_list`（直播间列表）、`replay_info`（直播回放列表）— 每个账号采集一次
  - **直播间级**：`trend_gmv`（GMV 趋势）、`trend_stats`（直播趋势统计）— 每个 room_id 采集一次
  - **日期级**：`live_stats`（`api/v2/insights/creator/live/stats`）— 按天采集，每个账号每天一条记录
- 直播场次列表从 live_list 响应中解析（room_id + 开播/结束时间戳）
- `live/stats` 的目标日期列表从 `browserapi._generate_daily_payloads()` 的逻辑推算
- 前端重构 AccountDetail 页，不新增页面
- 架构须支持指标注册制驱动，后续加指标只改 registry.py + classifier.py

> **API 名称映射：** Issue #6 原文中的 `live_stats`、`room_replay`、`room_trend_content` 是需求描述名，
> 对应到代码中的 api_type 分别是 `live_stats_7d`/`data_overview`、`replay_info`、`trend_stats`。
> 本设计以代码中的实际名称为准。

## 3. 三级监控架构

```
账号 (Account)
├── 账号级指标（一次性）
│   ├── live_list ✅/❌          — 直播间列表是否已采集
│   └── replay_info ✅/❌       — 直播回放是否已采集
│
├── 日期级指标（按天）
│   ├── 03-12  live_stats ✅     — 这一天的 live/stats 是否已采集
│   ├── 03-13  live_stats ✅
│   └── 03-14  live_stats ❌     — 缺失
│
└── 直播间级指标（按 room_id）
    ├── room_001
    │   ├── trend_gmv ✅
    │   └── trend_stats ✅
    └── room_002
        ├── trend_gmv ❌
        └── trend_stats ✅
```

## 4. 数据模型

### 4.1 新增表：`room_sessions`

```sql
CREATE TABLE IF NOT EXISTS room_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    room_id TEXT NOT NULL,
    start_time INTEGER DEFAULT 0,       -- 开播时间（Unix 时间戳）
    end_time INTEGER DEFAULT 0,         -- 结束时间（Unix 时间戳，0 表示正在直播）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(batch_id, account_id, room_id),
    FOREIGN KEY (batch_id) REFERENCES collection_batches(batch_id)
);
CREATE INDEX IF NOT EXISTS idx_rooms_batch_account ON room_sessions(batch_id, account_id);
```

### 4.2 新增表：`daily_collection_status`

```sql
CREATE TABLE IF NOT EXISTS daily_collection_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    target_date TEXT NOT NULL,           -- 目标日期，格式 'YYYY-MM-DD'
    api_type TEXT NOT NULL,              -- 如 'live_stats'
    status TEXT DEFAULT 'success',       -- success / failed / empty
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(batch_id, account_id, target_date, api_type),
    FOREIGN KEY (batch_id) REFERENCES collection_batches(batch_id)
);
CREATE INDEX IF NOT EXISTS idx_daily_batch_account ON daily_collection_status(batch_id, account_id);
```

**用途：** 存储按天采集的 `live/stats` 数据状态。`target_date` 表示这条数据对应哪一天（由 `_generate_daily_payloads` 中的 `target_date` 决定）。

### 4.3 现有表保持不变

- `collection_batches` — 采集批次表
- `account_sessions` — 账号采集会话表
- `collection_records` — 采集记录表（已有 room_id 字段，可关联 room_sessions）

### 4.4 完整性矩阵查询逻辑

**直播间级：**
```
room_sessions（应采集的 room 列表）
    LEFT JOIN collection_records（实际采集的记录）
    → 按 room_id 分组，对每个注册的 room 级 api_type 检查是否有记录
```

**日期级：**
```
预期日期列表（从 _generate_daily_payloads 逻辑推算）
    LEFT JOIN daily_collection_status（实际记录）
    → 按 target_date 分组，检查每天的 live_stats 是否有记录
```

## 5. Registry 改造

### 5.1 新数据结构 — 三层级

将 `API_TYPE_REGISTRY` 从两层扩展为三层（account / daily / room）：

```python
API_TYPE_REGISTRY: dict[str, list[dict]] = {
    # 账号级（每个账号采集一次）
    'account': [
        {'key': 'live_list', 'label': '直播间列表'},
        {'key': 'replay_info', 'label': '直播回放列表'},
    ],
    # 日期级（每个账号 × 每天一条）
    'daily': [
        {'key': 'live_stats', 'label': '关键指标(按天)'},
        # --- 后续可扩展 ---
        # {'key': 'data_overview', 'label': '数据概览(按天)'},
    ],
    # 直播间级（每个 room_id 都需要）
    'room': [
        {'key': 'trend_gmv', 'label': 'GMV趋势'},
        {'key': 'trend_stats', 'label': '直播趋势'},
    ],
}

def get_expected_account_types() -> list[str]:
    return [item['key'] for item in API_TYPE_REGISTRY['account']]

def get_expected_daily_types() -> list[str]:
    return [item['key'] for item in API_TYPE_REGISTRY['daily']]

def get_expected_room_types() -> list[str]:
    return [item['key'] for item in API_TYPE_REGISTRY['room']]

def get_registry_for_api() -> dict:
    return {
        'account_types': API_TYPE_REGISTRY['account'],
        'daily_types': API_TYPE_REGISTRY['daily'],
        'room_types': API_TYPE_REGISTRY['room'],
    }
```

### 5.2 Classifier 改造

`live/stats` 接口在 classifier.py 中已有规则（返回 `live_stats_7d` 或 `data_overview`）。
本次新增一个统一的分类：当 URL 包含 `live/stats` 时，除了返回细分 api_type，
tracker 端需要统一识别为 `live_stats` 日期级指标。

**实现方式：** 不改 classifier，在 tracker 的 `record_daily_stats()` 方法中直接硬编码 `api_type='live_stats'`，
因为调用点明确（browserapi.py 的 `_handle_live_stats_injection`），不需要通用分类。

## 6. 后端 API

### 6.1 新增：`GET /api/registry`

```json
{
  "account_types": [
    {"key": "live_list", "label": "直播间列表"},
    {"key": "replay_info", "label": "直播回放列表"}
  ],
  "daily_types": [
    {"key": "live_stats", "label": "关键指标(按天)"}
  ],
  "room_types": [
    {"key": "trend_gmv", "label": "GMV趋势"},
    {"key": "trend_stats", "label": "直播趋势"}
  ]
}
```

### 6.2 重构：`GET /api/batches/{batch_id}/accounts/{account_id}`

**路由说明：** 重构现有路由，将 `batch_id` 放入 URL path。旧路由标记废弃。

**响应示例：**

```json
{
  "account_id": "shop_abc123",
  "batch_id": "batch_20260314",
  "account_indicators": {
    "live_list": {"status": "success", "collected_at": "2026-03-14T10:00:00"},
    "replay_info": {"status": "success", "collected_at": "2026-03-14T10:01:00"}
  },
  "daily_stats": [
    {"target_date": "2026-03-12", "live_stats": {"status": "success"}},
    {"target_date": "2026-03-13", "live_stats": {"status": "success"}},
    {"target_date": "2026-03-14", "live_stats": {"status": null}}
  ],
  "rooms": [
    {
      "room_id": "748350001",
      "start_time": 1710403200,
      "end_time": 1710417600,
      "indicators": {
        "trend_gmv": {"status": "success"},
        "trend_stats": {"status": "success"}
      },
      "completeness": 1.0
    },
    {
      "room_id": "748350002",
      "start_time": 1710338400,
      "end_time": 1710349200,
      "indicators": {
        "trend_gmv": {"status": null},
        "trend_stats": {"status": "success"}
      },
      "completeness": 0.5
    }
  ],
  "overall_completeness": 0.75
}
```

### 6.3 完整率计算规则

- **单个 room 完整率** = 已采集的 room 级指标数 / 注册的 room 级指标总数
- **overall_completeness** = 所有 room 完整率的平均值
- **边界情况**：当 room_sessions 为空，`overall_completeness = 1.0`
- **daily_stats 不参与 overall_completeness 计算**（它是独立维度，前端单独展示）

## 7. Tracker 改造

### 7.1 `record_rooms()` 重构

**关键：** `live_list` 有双重角色 — 既是账号级指标，又是 room_sessions 数据来源。

```python
def record_rooms(self, batch_id: str, account_id: str, rooms_data: list[dict]):
    """记录 live_list 响应，解析直播场次写入 room_sessions

    即使 rooms_data 为空列表，也记录 live_list 的采集状态为 success。
    """
    # 1. 记录 live_list API 本身的采集状态
    # 注意：response_size 此处表示房间数量（非字节数）
    self.record(batch_id=batch_id, account_id=account_id,
                api_type='live_list', status='success',
                response_size=len(rooms_data))

    # 2. 解析每个 room，写入 room_sessions
    for room in rooms_data:
        self._insert_room_session(
            batch_id, account_id,
            room_id=room['room_id'],
            start_time=room.get('live_start_ts', 0),
            end_time=room.get('live_end_ts', 0),
        )
```

### 7.2 新增：`record_daily_stats()` 方法

```python
def record_daily_stats(self, batch_id: str, account_id: str,
                       target_date: str, api_type: str = 'live_stats',
                       status: str = 'success'):
    """记录按天采集的指标状态

    Args:
        batch_id: 批次 ID
        account_id: 账号 ID
        target_date: 目标日期，格式 'YYYY-MM-DD'
        api_type: 日期级 api_type，默认 'live_stats'
        status: 采集状态（success / failed / empty）
    """
    try:
        conn = get_connection()
        conn.execute(
            '''INSERT OR REPLACE INTO daily_collection_status
               (batch_id, account_id, target_date, api_type, status)
               VALUES (?, ?, ?, ?, ?)''',
            (batch_id, account_id, target_date, api_type, status)
        )
        conn.commit()
    except Exception as e:
        self._log_error(f'记录日期级采集状态失败: {e}')
```

### 7.3 钩子集成点：`browserapi._handle_live_stats_injection()`

在 `_handle_live_stats_injection()` 中，每成功获取一个日期的 live/stats 数据后，调用 `record_daily_stats()`：

```python
# 在 browserapi.py _handle_live_stats_injection 中
# 每个日期请求成功后，需要通知监控系统
# 但 browserapi 不直接依赖 monitor，改为由 tiktok.py 在采集完成后记录

# 方案：tiktok.py 已有 batch_id 和 account_id，
# 在 visit_page_and_collect 处理 live/stats 数据后，
# 解析每条响应对应的 target_date，调用 monitor.record_daily_stats()
```

**具体集成方式：** 由于 `browserapi.py` 不持有 `batch_id`，日期级记录应在 `tiktok.py` 中完成：
1. `get_listened_data()` 返回的 `collected_data` 中包含 live/stats 的多条数据
2. `tiktok.py` 在 `visit_page_and_collect()` 处理这些数据时，从 request body 中解析出 `target_date`
3. 对每个 target_date 调用 `monitor.record_daily_stats(batch_id, account_id, target_date)`

### 7.4 从请求体解析 target_date

`_generate_daily_payloads()` 生成的 payload 中有 `time_selector.start_timestamp` 和 `time_selector.end_timestamp`，
`target_date` = `start_timestamp + 1天`（因为 start 是 D-1 的 UTC 00:00，end 是 D+1 的 UTC 00:00，实际 target 是 D）。

```python
def extract_target_date(request_body: dict) -> str | None:
    """从 live/stats 请求体中提取目标日期"""
    try:
        params = request_body.get('request', {}).get('params', [])
        if not params:
            return None
        time_selector = params[0].get('time_selector', {})
        start_ts = time_selector.get('start_timestamp', 0)
        if not start_ts:
            return None
        # target_date = start + 1天（start 是 D-1 的 UTC 00:00）
        from datetime import datetime, timedelta, timezone
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        target_dt = start_dt + timedelta(days=1)
        return target_dt.strftime('%Y-%m-%d')
    except Exception:
        return None
```

### 7.5 崩溃处理

- room_sessions 写入后崩溃 → 面板显示 ❌（正确行为）
- daily_collection_status 部分日期写入后崩溃 → 缺失的日期显示 ❌（正确行为）

## 8. 前端重构

### 8.1 AccountDetail 页面结构

```
┌─────────────────────────────────────────────────────────┐
│ 账号：shop_abc123          批次：batch_20260314         │
│ 整体完整率：75%  ████████░░░░                           │
├─────────────────────────────────────────────────────────┤
│ 账号级指标                                              │
│  live_list ✅  |  replay_info ✅                        │
├─────────────────────────────────────────────────────────┤
│ 日期级指标（live/stats 按天采集状态）                     │
│ ┌───────────┬────────────┬────────────┬────────────┐    │
│ │           │  03-12     │  03-13     │  03-14     │    │
│ ├───────────┼────────────┼────────────┼────────────┤    │
│ │ live_stats│    ✅      │    ✅      │    ❌      │    │
│ └───────────┴────────────┴────────────┴────────────┘    │
├─────────────────────────────────────────────────────────┤
│ 直播场次列表                                            │
│ ┌──────────┬────────────┬──────────┬──────────┬──────┐  │
│ │ 直播间ID │  开播时间   │ GMV趋势  │直播趋势  │完整率│  │
│ ├──────────┼────────────┼──────────┼──────────┼──────┤  │
│ │ 74835001 │ 03-14 14:00│    ✅    │    ✅    │ 100% │  │
│ │ 74835002 │ 03-13 20:00│    ❌    │    ✅    │  50% │  │
│ │ 74835003 │ 03-12 10:00│    ❌    │    ❌    │   0% │  │
│ └──────────┴────────────┴──────────┴──────────┴──────┘  │
└─────────────────────────────────────────────────────────┘
```

### 8.2 关键设计点

1. **列头动态渲染**：前端从 `/api/registry` 获取 `daily_types` 和 `room_types`，分别渲染日期级和直播间级表格
2. **状态标记**：`success` → ✅ 绿色，`null` → ❌ 红色，`failed`/`empty` → ⚠️ 黄色
3. **日期级表格**：列头为日期（从 API 返回的 `daily_stats` 中提取），行为日期级 api_type
4. **暗色主题**：沿用现有控制台风格

## 9. 可扩展性保证

后续新增指标的三种场景：

| 场景 | 改动 | 示例 |
|------|------|------|
| 新增直播间级指标 | registry + classifier | 商品列表、流量转化 |
| 新增日期级指标 | registry + classifier + tracker 钩子 | data_overview 按天 |
| 新增账号级指标 | registry + classifier + tracker 钩子 | account_info |

**前端均无需改动** — 根据 registry 动态渲染。

## 10. 改动范围汇总

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `monitor/db.py` | 修改 | 新增 `room_sessions` + `daily_collection_status` 建表语句 |
| `monitor/tracker.py` | 修改 | `record_rooms()` 写入 room_sessions；新增 `record_daily_stats()`、`_insert_room_session()`、`extract_target_date()` |
| `monitor/registry.py` | 修改 | 三层级注册表（account/daily/room），新增 `get_expected_daily_types()`、`get_registry_for_api()` |
| `monitor/api/accounts.py` | 重构 | 返回 account_indicators + daily_stats + rooms 三级数据 |
| `monitor/api/registry_routes.py` | 新增 | `/api/registry` 接口（避免与 `monitor/registry.py` 同名混淆）|
| `monitor/server.py` | 修改 | 注册 registry_routes 路由 |
| `spiders/tiktok.py` | 修改 | 处理 live/stats 数据时调用 `monitor.record_daily_stats()` |
| `monitor/frontend/src/api/index.js` | 修改 | 新增 `fetchRegistry()` 调用 |
| `monitor/frontend/src/views/AccountDetail.vue` | 重构 | 三段式布局：账号级 + 日期级 + 直播间级 |
| `tests/monitor/` | 新增/修改 | room_sessions + daily_collection_status + registry 测试 |
| `scripts/mock_monitor_data.py` | 修改 | 添加模拟数据 |
