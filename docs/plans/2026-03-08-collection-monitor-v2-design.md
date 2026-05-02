# 采集完整性监控系统 V2 设计文档

**日期**: 2026-03-08
**作者**: XBW + Claude
**状态**: 已确认

---

## 1. 背景

live_dp 数据采集完整性无法自主监控，依赖人工反馈。V1 核心指标包含 14+ 种 API 类型（5 个账号级 + 9 个直播间级），当前 Phase 1 仅启用其中 3 种（live/list、replay/info、trend/chart x2），后续将逐步放开。

## 2. 目标

- 按 账号 > 直播场次 > API 三级维度监控采集完整性
- 支持 Web 面板查看
- 设计上支持 API 类型的渐进式扩展，新增 API 类型无需改数据库表结构

## 3. 方案

**方案 B：模块化嵌入式监控**

- 独立 `monitor/` 模块，CollectionMonitor 类封装所有钩子逻辑
- SQLite 存储，FastAPI REST API，Vue3 前端面板
- 仅覆盖 TikTok 平台

## 4. 数据模型（SQLite）

### 4.1 collection_batches — 采集批次

```sql
CREATE TABLE collection_batches (
    batch_id TEXT PRIMARY KEY,          -- 格式: "2026-03-08_20:00"
    mode TEXT NOT NULL,                 -- scheduler / once / full
    total_accounts INTEGER DEFAULT 0,
    success_accounts INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 account_sessions — 账号采集会话

```sql
CREATE TABLE account_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    account_id TEXT NOT NULL,            -- browser_id
    group_name TEXT DEFAULT '',
    total_rooms INTEGER DEFAULT 0,       -- live/list 中发现的直播间数
    status TEXT DEFAULT 'running',       -- running / success / partial / failed / login_failed
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    UNIQUE(batch_id, account_id),
    FOREIGN KEY (batch_id) REFERENCES collection_batches(batch_id)
);
CREATE INDEX idx_sessions_batch ON account_sessions(batch_id);
```

### 4.3 collection_records — 采集记录（核心表）

```sql
CREATE TABLE collection_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    room_id TEXT DEFAULT '',             -- 账号级 API 为空
    api_type TEXT NOT NULL,              -- 枚举字符串: live_list / trend_gmv / ...
    status TEXT DEFAULT 'success',       -- success / failed / empty
    response_size INTEGER DEFAULT 0,
    extra_data TEXT DEFAULT '',           -- JSON，存 GMV 等附加信息
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(batch_id, account_id, room_id, api_type)
);
CREATE INDEX idx_records_batch ON collection_records(batch_id);
CREATE INDEX idx_records_account ON collection_records(batch_id, account_id);
CREATE INDEX idx_records_room ON collection_records(batch_id, account_id, room_id);
```

## 5. API 类型注册表

```python
API_TYPE_REGISTRY = {
    # 账号级（每个账号采集一次）
    'account': [
        'live_list',           # Phase 1
        'replay_info',         # Phase 1
        # --- 后续逐步放开 ---
        # 'live_stats_7d',
        # 'live_stats_yesterday',
        # 'data_overview',
        # 'account_info',
    ],
    # 直播间级（每个 room_id 都需要）
    'room': [
        'trend_gmv',           # Phase 1
        'trend_stats',         # Phase 1
        # --- 后续逐步放开 ---
        # 'room_core_stats',
        # 'room_product_list',
        # 'room_traffic_conversion',
        # 'room_trend_traffic',
        # 'room_viewer_portrait',
        # 'room_trend_content',
        # 'room_traffic_source',
    ]
}
```

**扩展流程（新增 API 类型）：**
1. 在 `API_TYPE_REGISTRY` 取消注释对应行
2. 在 `config_base.py` 的 `listen_urls` 取消注释对应 URL
3. 在爬虫代码相应位置加一行 `monitor.record(api_type, ...)`
4. 无需改数据库表结构

## 6. API 分类器

```python
def classify_api(url: str, request_body: dict) -> str | None:
    """根据 URL + 请求参数判断 api_type"""
    if 'live/list' in url:          return 'live_list'
    if 'replay/info' in url:        return 'replay_info'
    if 'trend/chart' in url:
        stats_types = extract_stats_types(request_body)
        if stats_types == [3]:      return 'trend_gmv'
        if 52 in stats_types:       return 'trend_gmv'
        if 60 in stats_types:       return 'trend_traffic'
        return 'trend_stats'
    if 'core/stats' in url:         return 'room_core_stats'
    if 'product/list' in url:       return 'room_product_list'
    if 'detail/core/stats' in url:  return 'room_traffic_conversion'
    if 'viewer/source' in url:      return 'room_viewer_portrait'
    if 'source/new' in url:         return 'room_traffic_source'
    if 'account_info' in url:       return 'account_info'
    return None
```

## 7. CollectionMonitor 钩子设计

```python
class CollectionMonitor:
    """采集完整性监控器"""

    def start_batch(self, batch_id, mode): ...
    def finish_batch(self, batch_id): ...

    def start_account(self, batch_id, account_id, group_name): ...
    def finish_account(self, batch_id, account_id, status): ...

    def record_rooms(self, batch_id, account_id, rooms_data): ...
        # 从 live/list 响应中提取 room 列表，批量写入 room 基础信息到 extra_data

    def record(self, batch_id, account_id, api_type, room_id='',
               status='success', response_size=0, extra_data=None): ...
        # 通用记录方法，一行搞定任何 API 类型
```

### 钩子位置

| 钩子 | 位置 | 调用 |
|------|------|------|
| 批次开始/结束 | `main.py` 或 `task_scheduler.py` | `monitor.start_batch()` / `finish_batch()` |
| 账号开始/结束 | `base.py start_crawl()` | `monitor.start_account()` / `finish_account()` |
| live/list 解析 | `tiktok.py _handle_tiktok_live_list()` | `monitor.record('live_list', ...)` + `monitor.record_rooms(...)` |
| replay/info | `tiktok.py visit_page_and_collect()` | `monitor.record('replay_info', ...)` |
| trend/chart | `tiktok.py _fetch_trend_chart_via_js()` | `monitor.record('trend_gmv'/'trend_stats', room_id=..., ...)` |

## 8. FastAPI REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/batches` | 批次列表 + 完整性汇总（完整率百分比） |
| GET | `/api/batches/{batch_id}/accounts` | 批次下账号列表 + 各 API 状态 |
| GET | `/api/accounts/{account_id}/rooms?batch_id=` | 账号下直播间列表 + GMV + 各 API 采集状态 |

### 完整性计算

```
账号完整率 = (已采集的 account API 数 + 所有 room 已采集的 room API 数)
           / (expected account API 数 + total_rooms * expected room API 数)
批次完整率 = 所有账号完整率的平均值
```

## 9. Vue3 前端

### 页面 1：Dashboard 总览
- 批次列表表格：批次ID、模式、账号数、完整率、时间
- 点击批次 → 展开账号列表
- 账号行：账号ID、分组、live_list/replay 状态图标、trend 完成比例（如 3/5）、整体状态

### 页面 2：账号直播间详情
- 直播间表格：标题、开播时间、时长、GMV、销量、观看数
- 每行末尾：trend_gmv / trend_stats 状态标记
- 颜色编码：绿色=成功、红色=失败、灰色=未采集

### 技术选型
- Vue3 + Vite + Element Plus
- axios 调用 FastAPI API
- FastAPI 托管前端 dist/ 静态文件

## 10. 模块结构

```
live_dp/monitor/
├── __init__.py          # 导出 CollectionMonitor 单例
├── db.py                # SQLite 初始化 + 连接管理
├── tracker.py           # CollectionMonitor 类
├── classifier.py        # API 分类器
├── registry.py          # API_TYPE_REGISTRY 配置
├── server.py            # FastAPI 服务入口
├── api/
│   ├── __init__.py
│   ├── batches.py       # 批次路由
│   └── accounts.py      # 账号 + 直播间路由
├── frontend/            # Vue3 SPA
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.vue
│       ├── main.js
│       ├── router/index.js
│       ├── views/
│       │   ├── Dashboard.vue
│       │   └── AccountDetail.vue
│       └── api/index.js
└── data/
    └── monitor.db       # SQLite 数据库文件
```

## 11. live/list 响应中可提取的 GMV 数据

存入 `collection_records.extra_data` JSON（api_type=live_list 时），供前端展示：

```json
{
  "rooms": [
    {
      "room_id": "7613870140707048210",
      "room_name": "EARLY RAMADHAN SALE!",
      "live_start_ts": 1772742319,
      "live_end_ts": 1772815517,
      "duration": 73198,
      "cover_url": "https://...",
      "revenue": "3651856",
      "currency_code": "IDR",
      "direct_revenue": "3284068",
      "item_sold_cnt": 30,
      "view_cnt": 2222,
      "ctr": 0.141314,
      "c_o": 0.085987
    }
  ]
}
```
