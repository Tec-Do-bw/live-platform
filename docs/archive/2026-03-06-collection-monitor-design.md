# 采集监控系统 - 设计文档

**日期**: 2026-03-06
**版本**: V1 MVP
**状态**: 待确认

---

## 1. 概述

### 1.1 问题

live-dp 数据采集完整性无法自主监控。当前流程是后端/前端发现数据缺失后通知爬虫侧补采，被动且低效。

### 1.2 目标

建立嵌入式采集监控系统 + Web 面板，按 **账号 > 直播场次 > API接口** 三级维度，实时追踪 V1 核心指标的采集完整性。

### 1.3 非目标（MVP 不做）

- 不校验数据正确性，只校验"是否已采集"
- 不做自动补采（V2）
- 不做告警推送（V2）

---

## 2. 架构

```
live_dp 爬虫
    |
    +-- base.py: send_api_request()
    |       |
    |       +-- [钩子] 解析 api_url --> 写入 SQLite collection_records 表
    |
    +-- main.py / task_scheduler.py
            |
            +-- 采集完成后调用 MonitorReporter 生成完整性报告
                    |
                    +-- 写入 SQLite collection_batches 表

FastAPI 服务 (monitor/server.py)
    |
    +-- REST API: /api/batches, /api/accounts, /api/rooms, /api/room-detail
    |
    +-- 托管 Vue3 前端静态文件 (monitor/frontend/dist/)

Vue3 SPA (monitor/frontend/)
    |
    +-- 总览 Dashboard
    +-- 账号详情页
    +-- 直播间详情页
```

### 2.1 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 监控数据存储 | SQLite | 零部署依赖，单文件 |
| 后端 API | FastAPI | 和爬虫同为 Python 生态 |
| 前端 | Vue3 + Element Plus | 表格/树形组件丰富 |
| 部署 | 单进程 | FastAPI 托管静态文件 |

---

## 3. 数据模型

### 3.1 collection_batches - 采集批次表

```sql
CREATE TABLE collection_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT UNIQUE NOT NULL,       -- 格式: "2026-03-06_20:00"
    platform TEXT NOT NULL,              -- tiktok / shopee
    mode TEXT NOT NULL,                  -- scheduler / once / full
    total_accounts INTEGER DEFAULT 0,
    success_accounts INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 collection_records - 采集记录表

```sql
CREATE TABLE collection_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL,             -- 浏览器 browser_id
    group_name TEXT DEFAULT '',
    room_id TEXT DEFAULT '',              -- 账号级 API 为空字符串
    api_type TEXT NOT NULL,               -- 枚举见下方
    api_url TEXT NOT NULL,                -- 实际请求 URL
    status TEXT DEFAULT 'success',        -- success / failed / empty
    response_size INTEGER DEFAULT 0,      -- 响应体大小（字节）
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(batch_id, account_id, room_id, api_type)
);
CREATE INDEX idx_records_batch ON collection_records(batch_id);
CREATE INDEX idx_records_account ON collection_records(batch_id, account_id);
```

### 3.3 api_type 枚举定义

根据 V1 核心指标梳理，定义以下 api_type：

**账号级：**

| api_type | 对应 API | 区分方式 |
|----------|---------|---------|
| `live_list` | `/api/v2/insights/creator/live/list` | from_url 匹配 |
| `live_stats_7d` | `/api/v2/insights/creator/live/stats` | period=32 |
| `live_stats_yesterday` | `/api/v2/insights/creator/live/stats` | period=2, stats_types 含 11,115... |
| `data_overview` | `/api/v2/insights/creator/live/stats` | stats_types 含 100,101,121... |
| `account_info` | `/api/v1/streamer_desktop/account_info/get` | from_url 匹配 |

**直播间级（每个 room_id 都需要）：**

| api_type | 对应 API | 区分方式 |
|----------|---------|---------|
| `room_core_stats` | `/liveroom/recap/core/stats` | from_url 匹配 |
| `room_trend_gmv` | `/recap/trend/chart` | stats_types 含 52 |
| `room_product_list` | `/recap/product/list` | from_url 匹配 |
| `room_traffic_conversion` | `/workbench/live/detail/core/stats` | from_url 匹配 |
| `room_trend_traffic` | `/recap/trend/chart` | stats_types 含 60 或 61 |
| `room_viewer_portrait` | `/recap/viewer/source/stats` | from_url 匹配 |
| `room_trend_content` | `/recap/trend/chart` | stats_types 不含 52/60/61 |
| `room_traffic_source` | `/workbench/live/detail/source/new` | from_url 匹配 |
| `room_replay` | `webcast/room/replay/info` | from_url 匹配 |

---

## 4. 核心模块设计

### 4.1 CollectionMonitor（采集记录器）

位置: `live_dp/monitor/tracker.py`

```python
class CollectionMonitor:
    """嵌入爬虫的采集记录器"""

    def __init__(self, db_path: str, batch_id: str, platform: str):
        ...

    def classify_api(self, url: str, request_body: dict) -> str | None:
        """根据 URL 和请求参数判断 api_type，不在 V1 清单中返回 None"""
        ...

    def record(self, account_id: str, room_id: str,
               api_type: str, api_url: str,
               status: str, response_size: int):
        """记录一条采集结果"""
        ...

    def get_completeness(self, account_id: str) -> dict:
        """查询某账号的完整性报告"""
        ...
```

**集成点**: 在 `base.py` 的 `send_api_request()` 方法中，发送成功后调用 `monitor.record()`。

### 4.2 MonitorReporter（完整性报告器）

位置: `live_dp/monitor/reporter.py`

```python
class MonitorReporter:
    """采集完成后生成完整性报告"""

    def generate_batch_report(self, batch_id: str) -> dict:
        """生成批次完整性报告
        返回: {
            account_id: {
                account_apis: {api_type: True/False, ...},
                rooms: {
                    room_id: {api_type: True/False, ...},
                    ...
                }
            }
        }
        """
        ...
```

### 4.3 FastAPI 服务

位置: `live_dp/monitor/server.py`

```
GET  /api/batches                        -- 批次列表
GET  /api/batches/{batch_id}/summary     -- 批次完整性总览
GET  /api/batches/{batch_id}/accounts    -- 账号列表 + 完整率
GET  /api/accounts/{account_id}/rooms    -- 某账号的直播间列表
GET  /api/rooms/{batch_id}/{account_id}/{room_id}  -- 直播间详情 checklist
```

### 4.4 Vue3 前端

位置: `live_dp/monitor/frontend/`

3 个页面（参见 brainstorm 总结中的线框图）：
1. **总览 Dashboard** - 批次选择 + 账号列表 + 完整率筛选
2. **账号详情** - 账号级 API 状态 + 直播场次列表
3. **直播间详情** - V1 核心指标 Checklist

---

## 5. 新增目录结构

```
live_dp/
├── monitor/                    # [新增] 监控系统
│   ├── __init__.py
│   ├── db.py                   # SQLite 数据库初始化和连接
│   ├── tracker.py              # CollectionMonitor 采集记录器
│   ├── classifier.py           # API 分类器（URL+参数 -> api_type）
│   ├── reporter.py             # MonitorReporter 完整性报告
│   ├── server.py               # FastAPI 服务入口
│   ├── api/                    # FastAPI 路由
│   │   ├── __init__.py
│   │   ├── batches.py
│   │   ├── accounts.py
│   │   └── rooms.py
│   ├── frontend/               # Vue3 前端
│   │   ├── package.json
│   │   ├── src/
│   │   │   ├── App.vue
│   │   │   ├── views/
│   │   │   │   ├── Dashboard.vue
│   │   │   │   ├── AccountDetail.vue
│   │   │   │   └── RoomDetail.vue
│   │   │   └── router/
│   │   └── dist/               # 构建产物（由 FastAPI 托管）
│   └── data/
│       └── monitor.db          # SQLite 数据库文件
├── spiders/
│   └── base.py                 # [修改] 插入 monitor.record() 钩子
├── main.py                     # [修改] 初始化 batch_id 并传入 monitor
└── ...
```

---

## 6. 实施路线

### Phase 1: 基础设施（Day 1）

1. 创建 `monitor/` 目录和 SQLite 数据库初始化
2. 实现 `classifier.py`（API URL/参数 -> api_type 映射）
3. 实现 `tracker.py`（CollectionMonitor）

### Phase 2: 爬虫集成（Day 1-2）

4. 修改 `base.py`，在 `send_api_request` 中插入采集记录钩子
5. 修改 `main.py`，生成 batch_id 并初始化 monitor
6. 实现 `reporter.py`，采集完成后输出完整性报告到日志

### Phase 3: 后端 API（Day 2）

7. 实现 FastAPI 服务和 REST API 路由
8. 测试 API 数据返回

### Phase 4: 前端面板（Day 2-3）

9. Vue3 项目初始化 + Element Plus
10. 实现 Dashboard 页面
11. 实现账号详情页
12. 实现直播间详情页

### Phase 5: 联调与验证（Day 3）

13. 手动执行一次采集，验证数据写入
14. 前后端联调
15. 部署测试
