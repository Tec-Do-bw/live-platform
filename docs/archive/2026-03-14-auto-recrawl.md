# 自动补采闭环 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现自动补采闭环（缺失检测 → 任务生成 → 执行补采 → 验证结果）+ 前端账号总览改版

**Architecture:** 任务队列驱动架构。新增 `recrawl_tasks` + `request_context` 两张 SQLite 表作为核心数据模型，`gap_detector` 检测缺失，`executor` 消费任务执行补采。前端从批次视图改为账号总览视角（跨批次聚合）。

**Tech Stack:** Python 3.12 / FastAPI / SQLite (WAL) / Vue3 + Element Plus / AdsPower API

**Spec:** `docs/superpowers/specs/2026-03-14-auto-recrawl-design.md`

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|------|------|
| `live_dp/monitor/recrawl/__init__.py` | 补采模块入口，暴露 `auto_detect_and_recrawl()` |
| `live_dp/monitor/recrawl/models.py` | `recrawl_tasks` + `request_context` 的 CRUD 操作 |
| `live_dp/monitor/recrawl/gap_detector.py` | 缺失检测器：对比 registry 期望 vs 实际记录 |
| `live_dp/monitor/recrawl/proxy.py` | AdsPower 代理 IP 获取 |
| `live_dp/monitor/recrawl/executor.py` | 补采执行器：消费 pending 任务，HTTP 请求 + 重试 |
| `live_dp/monitor/api/overview.py` | 账号总览 API（聚合查询） |
| `live_dp/monitor/api/recrawl_routes.py` | 补采任务 API（trigger + list） |
| `live_dp/tests/monitor/test_recrawl_models.py` | models 模块测试 |
| `live_dp/tests/monitor/test_gap_detector.py` | 缺失检测器测试 |
| `live_dp/tests/monitor/test_proxy.py` | 代理获取测试 |
| `live_dp/tests/monitor/test_executor.py` | 执行器测试 |
| `live_dp/tests/monitor/test_overview_api.py` | 总览 API 测试 |
| `live_dp/tests/monitor/test_recrawl_api.py` | 补采 API 测试 |
| `live_dp/monitor/frontend/src/views/AccountOverview.vue` | 账号总览页（新首页） |
| `live_dp/monitor/frontend/src/views/BatchHistory.vue` | 原 Dashboard 改名 |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `live_dp/monitor/db.py` | 新增 `recrawl_tasks` + `request_context` 建表 + 索引 |
| `live_dp/monitor/tracker.py` | 新增 `conn` 属性 + `save_request_context()` 方法 |
| `live_dp/monitor/server.py` | 注册 overview + recrawl 路由 |
| `live_dp/core/config_base.py` | 新增 `RECRAWL_CONFIG` |
| `live_dp/spiders/tiktok.py` | 在 `_handle_tiktok_live_list` 中持久化 trend_chart 上下文 |
| `live_dp/main.py` | `run_once()` 末尾集成自动补采调用 |
| `live_dp/monitor/frontend/src/api/index.js` | 新增 overview / recrawl API 调用 |
| `live_dp/monitor/frontend/src/router/index.js` | 路由调整（首页 → AccountOverview） |
| `live_dp/monitor/frontend/src/App.vue` | 导航栏调整 |
| `live_dp/monitor/frontend/src/views/AccountDetail.vue` | 补采按钮 + 任务面板 |

---

## Chunk 1: 数据库 + 配置 + 数据模型

### Task 1: 数据库 Schema 扩展

**Files:**
- Modify: `live_dp/monitor/db.py:27-98`
- Test: `live_dp/tests/monitor/test_db.py`

- [ ] **Step 1: 在 `init_db()` 中新增 `recrawl_tasks` 表 + 索引**

在 `live_dp/monitor/db.py` 的 `init_db()` 函数末尾（`conn.commit()` 之前）追加：

```python
        CREATE TABLE IF NOT EXISTS recrawl_tasks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id      TEXT NOT NULL,
            account_id    TEXT NOT NULL,
            group_name    TEXT DEFAULT '',
            room_id       TEXT DEFAULT '',
            target_date   TEXT DEFAULT '',
            api_type      TEXT NOT NULL,
            level         TEXT NOT NULL,
            source        TEXT NOT NULL,
            status        TEXT DEFAULT 'pending',
            retry_count   INTEGER DEFAULT 0,
            error_msg     TEXT DEFAULT '',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(batch_id, account_id, room_id, target_date, api_type)
        );
        CREATE INDEX IF NOT EXISTS idx_recrawl_status ON recrawl_tasks(status);
        CREATE INDEX IF NOT EXISTS idx_recrawl_account ON recrawl_tasks(account_id, status);

        CREATE TABLE IF NOT EXISTS request_context (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id       TEXT NOT NULL,
            context_type     TEXT NOT NULL,
            api_base_url     TEXT DEFAULT '',
            query_string     TEXT DEFAULT '',
            headers          TEXT DEFAULT '{}',
            cookies          TEXT DEFAULT '[]',
            payload_template TEXT DEFAULT '{}',
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, context_type)
        );
```

- [ ] **Step 2: 运行现有 DB 测试确认不破坏**

Run: `cd live_dp && python -m pytest tests/monitor/test_db.py -v`
Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add live_dp/monitor/db.py
git commit -m "feat(monitor): 新增 recrawl_tasks + request_context 表"
```

---

### Task 2: 补采配置

**Files:**
- Modify: `live_dp/core/config_base.py`

- [ ] **Step 1: 在 `config_base.py` 的 `ADSPOWER_CONFIG` 之后新增 `RECRAWL_CONFIG`**

```python
    # 补采配置
    RECRAWL_CONFIG: dict[str, Any] = {
        "enabled": True,              # 自动补采开关
        "max_retry": 3,               # 最大重试次数
        "retry_delays": [1, 3, 10],   # 重试间隔（秒）
        "request_interval": 2,        # 同账号请求间隔（秒）
        "max_concurrent": 2,          # 最大并发账号数
        "default_days": 3,            # 默认检测时间窗口（天）
    }
```

- [ ] **Step 2: 提交**

```bash
git add live_dp/core/config_base.py
git commit -m "feat(monitor): 新增 RECRAWL_CONFIG 补采配置"
```

---

### Task 3: 补采数据模型 (CRUD)

**Files:**
- Create: `live_dp/monitor/recrawl/__init__.py`
- Create: `live_dp/monitor/recrawl/models.py`
- Test: `live_dp/tests/monitor/test_recrawl_models.py`

- [ ] **Step 1: 创建模块目录和空 `__init__.py`**

```bash
mkdir -p live_dp/monitor/recrawl
```

`live_dp/monitor/recrawl/__init__.py`:
```python
"""补采闭环模块"""
```

- [ ] **Step 2: 编写 models 测试**

`live_dp/tests/monitor/test_recrawl_models.py`:

```python
"""补采任务数据模型测试"""

import pytest
from monitor.db import get_connection, init_db
from monitor.recrawl.models import (
    create_task_auto, create_task_manual, get_pending_tasks,
    update_task_status, get_tasks_by_account,
    save_request_context, get_request_context, cleanup_old_tasks,
)


@pytest.fixture
def conn():
    c = get_connection(':memory:')
    init_db(c)
    yield c
    c.close()


class TestRecrawlTasks:
    """补采任务 CRUD 测试"""

    def test_create_task_auto(self, conn):
        """自动补采创建任务"""
        task_id = create_task_auto(
            conn, batch_id='2026-03-14_14:30', account_id='acc1',
            group_name='新加坡团队', room_id='room1', target_date='',
            api_type='trend_gmv', level='room',
        )
        assert task_id is not None
        tasks = get_pending_tasks(conn)
        assert len(tasks) == 1
        assert tasks[0]['api_type'] == 'trend_gmv'
        assert tasks[0]['source'] == 'auto'

    def test_create_task_auto_duplicate_ignored(self, conn):
        """自动补采重复任务被忽略"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        tasks = get_pending_tasks(conn)
        assert len(tasks) == 1

    def test_create_task_manual_resets_failed(self, conn):
        """手动触发可重置已失败的任务"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        update_task_status(conn, 1, 'recrawl_failed', retry_count=3, error_msg='timeout')
        create_task_manual(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        tasks = get_pending_tasks(conn)
        assert len(tasks) == 1
        assert tasks[0]['status'] == 'pending'
        assert tasks[0]['retry_count'] == 0
        assert tasks[0]['source'] == 'manual'

    def test_create_task_manual_resets_success(self, conn):
        """手动触发可重置已成功的任务"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        update_task_status(conn, 1, 'success')
        create_task_manual(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        tasks = get_pending_tasks(conn)
        assert len(tasks) == 1

    def test_update_task_status(self, conn):
        """更新任务状态"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', '', '', 'live_list', 'account')
        update_task_status(conn, 1, 'running')
        tasks = get_tasks_by_account(conn, 'acc1')
        assert tasks[0]['status'] == 'running'

    def test_get_tasks_by_account_with_status_filter(self, conn):
        """按账号和状态筛选任务"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', '', '', 'live_list', 'account')
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        update_task_status(conn, 1, 'success')
        pending = get_tasks_by_account(conn, 'acc1', status='pending')
        assert len(pending) == 1
        assert pending[0]['api_type'] == 'trend_gmv'


class TestRequestContext:
    """请求上下文缓存测试"""

    def test_save_and_get_context(self, conn):
        """保存并读取请求上下文"""
        save_request_context(
            conn, account_id='acc1', context_type='trend_chart',
            api_base_url='https://shop.tiktok.com',
            query_string='aid=123&fp=abc',
            headers='{"Content-Type": "application/json"}',
            cookies='[{"name": "sessionid", "value": "xxx"}]',
        )
        ctx = get_request_context(conn, 'acc1', 'trend_chart')
        assert ctx is not None
        assert ctx['api_base_url'] == 'https://shop.tiktok.com'
        assert ctx['query_string'] == 'aid=123&fp=abc'

    def test_save_context_upsert(self, conn):
        """重复保存会更新而非报错"""
        save_request_context(conn, 'acc1', 'trend_chart', api_base_url='https://old.com')
        save_request_context(conn, 'acc1', 'trend_chart', api_base_url='https://new.com')
        ctx = get_request_context(conn, 'acc1', 'trend_chart')
        assert ctx['api_base_url'] == 'https://new.com'

    def test_get_context_not_found(self, conn):
        """未找到上下文返回 None"""
        ctx = get_request_context(conn, 'acc1', 'trend_chart')
        assert ctx is None


class TestCleanup:
    """数据清理测试"""

    def test_cleanup_old_tasks(self, conn):
        """清理旧任务"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', '', '', 'live_list', 'account')
        update_task_status(conn, 1, 'success')
        # 手动修改 updated_at 为 31 天前
        conn.execute(
            "UPDATE recrawl_tasks SET updated_at = datetime('now', '-31 days') WHERE id = 1"
        )
        conn.commit()
        deleted = cleanup_old_tasks(conn, days=30)
        assert deleted == 1
        assert len(get_tasks_by_account(conn, 'acc1')) == 0
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_recrawl_models.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 4: 实现 `models.py`**

`live_dp/monitor/recrawl/models.py`:

```python
"""补采任务数据模型 — recrawl_tasks 和 request_context 的 CRUD 操作"""

import sqlite3
from datetime import datetime


def create_task_auto(
    conn: sqlite3.Connection,
    batch_id: str, account_id: str, group_name: str,
    room_id: str, target_date: str, api_type: str, level: str,
) -> int | None:
    """创建自动补采任务（重复则忽略）"""
    try:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO recrawl_tasks
               (batch_id, account_id, group_name, room_id, target_date, api_type, level, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'auto')""",
            (batch_id, account_id, group_name, room_id, target_date, api_type, level),
        )
        conn.commit()
        return cursor.lastrowid if cursor.rowcount > 0 else None
    except Exception:
        return None


def create_task_manual(
    conn: sqlite3.Connection,
    batch_id: str, account_id: str, group_name: str,
    room_id: str, target_date: str, api_type: str, level: str,
) -> int:
    """创建或重置手动补采任务（无论当前状态均可重置）"""
    cursor = conn.execute(
        """INSERT INTO recrawl_tasks
           (batch_id, account_id, group_name, room_id, target_date, api_type, level, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'manual')
           ON CONFLICT(batch_id, account_id, room_id, target_date, api_type)
           DO UPDATE SET status='pending', retry_count=0, error_msg='',
                         source='manual', updated_at=CURRENT_TIMESTAMP""",
        (batch_id, account_id, group_name, room_id, target_date, api_type, level),
    )
    conn.commit()
    return cursor.lastrowid


def get_pending_tasks(conn: sqlite3.Connection, account_id: str | None = None) -> list[dict]:
    """获取 pending 状态的补采任务"""
    sql = "SELECT * FROM recrawl_tasks WHERE status = 'pending'"
    params: list = []
    if account_id:
        sql += " AND account_id = ?"
        params.append(account_id)
    sql += " ORDER BY created_at ASC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_tasks_by_account(
    conn: sqlite3.Connection, account_id: str, status: str | None = None,
) -> list[dict]:
    """获取指定账号的补采任务"""
    sql = "SELECT * FROM recrawl_tasks WHERE account_id = ?"
    params: list = [account_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def update_task_status(
    conn: sqlite3.Connection, task_id: int, status: str,
    retry_count: int | None = None, error_msg: str | None = None,
) -> None:
    """更新任务状态"""
    fields = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
    params: list = [status]
    if retry_count is not None:
        fields.append("retry_count = ?")
        params.append(retry_count)
    if error_msg is not None:
        fields.append("error_msg = ?")
        params.append(error_msg)
    params.append(task_id)
    conn.execute(f"UPDATE recrawl_tasks SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()


def save_request_context(
    conn: sqlite3.Connection, account_id: str, context_type: str,
    api_base_url: str = '', query_string: str = '',
    headers: str = '{}', cookies: str = '[]', payload_template: str = '{}',
) -> None:
    """保存或更新请求上下文（upsert）"""
    conn.execute(
        """INSERT INTO request_context
           (account_id, context_type, api_base_url, query_string, headers, cookies, payload_template)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(account_id, context_type)
           DO UPDATE SET api_base_url=excluded.api_base_url, query_string=excluded.query_string,
                         headers=excluded.headers, cookies=excluded.cookies,
                         payload_template=excluded.payload_template,
                         updated_at=CURRENT_TIMESTAMP""",
        (account_id, context_type, api_base_url, query_string, headers, cookies, payload_template),
    )
    conn.commit()


def get_request_context(
    conn: sqlite3.Connection, account_id: str, context_type: str,
) -> dict | None:
    """获取请求上下文"""
    row = conn.execute(
        "SELECT * FROM request_context WHERE account_id = ? AND context_type = ?",
        (account_id, context_type),
    ).fetchone()
    return dict(row) if row else None


def cleanup_old_tasks(conn: sqlite3.Connection, days: int = 30) -> int:
    """清理指定天数前的已完成/已失败任务"""
    cursor = conn.execute(
        """DELETE FROM recrawl_tasks
           WHERE status IN ('success', 'recrawl_failed')
             AND updated_at < datetime('now', ?)""",
        (f'-{days} days',),
    )
    conn.commit()
    return cursor.rowcount
```

- [ ] **Step 5: 运行测试**

Run: `cd live_dp && python -m pytest tests/monitor/test_recrawl_models.py -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add live_dp/monitor/recrawl/ live_dp/tests/monitor/test_recrawl_models.py
git commit -m "feat(monitor): 补采任务数据模型 CRUD + request_context 缓存"
```

---

## Chunk 2: 缺失检测器 + 代理获取

### Task 4: 缺失检测器

**Files:**
- Create: `live_dp/monitor/recrawl/gap_detector.py`
- Test: `live_dp/tests/monitor/test_gap_detector.py`

- [ ] **Step 1: 编写缺失检测器测试**

`live_dp/tests/monitor/test_gap_detector.py`:

```python
"""缺失检测器测试"""

import time
import pytest
from monitor.tracker import CollectionMonitor
from monitor.recrawl.gap_detector import detect_gaps


@pytest.fixture
def monitor():
    m = CollectionMonitor(db_path=':memory:')
    yield m


class TestGapDetector:

    def test_detect_missing_room_api(self, monitor):
        """检测直播间级 API 缺失"""
        conn = monitor.conn
        batch_id = '2026-03-14_14:30'
        monitor.start_batch(batch_id, 'once')
        monitor.start_account(batch_id, 'acc1', '新加坡团队')
        # 只记录 trend_gmv，缺少 trend_stats
        monitor.record_rooms(batch_id, 'acc1', [
            {'room_id': 'room1', 'live_start_ts': int(time.time()) - 3600,
             'live_end_ts': int(time.time()), 'duration': 3600},
        ])
        monitor.record(batch_id, 'acc1', 'trend_gmv', room_id='room1', status='success')
        monitor.finish_account(batch_id, 'acc1', 'success')
        monitor.finish_batch(batch_id)

        gaps = detect_gaps(conn, days=3)
        # 应该检测到 room1 缺少 trend_stats
        room_gaps = [g for g in gaps if g['level'] == 'room' and g['api_type'] == 'trend_stats']
        assert len(room_gaps) >= 1
        assert room_gaps[0]['room_id'] == 'room1'

    def test_no_gaps_when_all_collected(self, monitor):
        """全部采集成功时无缺失"""
        conn = monitor.conn
        batch_id = '2026-03-14_14:30'
        monitor.start_batch(batch_id, 'once')
        monitor.start_account(batch_id, 'acc1', '新加坡团队')
        monitor.record(batch_id, 'acc1', 'live_list', status='success')
        monitor.record(batch_id, 'acc1', 'replay_info', status='success')
        monitor.record_rooms(batch_id, 'acc1', [
            {'room_id': 'room1', 'live_start_ts': int(time.time()) - 3600,
             'live_end_ts': int(time.time()), 'duration': 3600},
        ])
        monitor.record(batch_id, 'acc1', 'trend_gmv', room_id='room1', status='success')
        monitor.record(batch_id, 'acc1', 'trend_stats', room_id='room1', status='success')
        monitor.finish_account(batch_id, 'acc1', 'success')
        monitor.finish_batch(batch_id)

        gaps = detect_gaps(conn, days=3)
        room_gaps = [g for g in gaps if g['level'] == 'room']
        account_gaps = [g for g in gaps if g['level'] == 'account']
        assert len(room_gaps) == 0
        assert len(account_gaps) == 0

    def test_cross_batch_aggregation(self, monitor):
        """跨批次聚合：批次1采到 trend_gmv，批次2不需要再补采"""
        conn = monitor.conn
        batch1 = '2026-03-14_08:00'
        monitor.start_batch(batch1, 'once')
        monitor.start_account(batch1, 'acc1', '新加坡团队')
        monitor.record_rooms(batch1, 'acc1', [
            {'room_id': 'room1', 'live_start_ts': int(time.time()) - 3600,
             'live_end_ts': int(time.time()), 'duration': 3600},
        ])
        monitor.record(batch1, 'acc1', 'trend_gmv', room_id='room1', status='success')
        monitor.record(batch1, 'acc1', 'trend_stats', room_id='room1', status='success')
        monitor.finish_account(batch1, 'acc1', 'success')
        monitor.finish_batch(batch1)

        batch2 = '2026-03-14_14:30'
        monitor.start_batch(batch2, 'once')
        monitor.start_account(batch2, 'acc1', '新加坡团队')
        monitor.record_rooms(batch2, 'acc1', [
            {'room_id': 'room1', 'live_start_ts': int(time.time()) - 3600,
             'live_end_ts': int(time.time()), 'duration': 3600},
        ])
        monitor.finish_account(batch2, 'acc1', 'success')
        monitor.finish_batch(batch2)

        gaps = detect_gaps(conn, days=3)
        room_gaps = [g for g in gaps if g['room_id'] == 'room1']
        assert len(room_gaps) == 0

    def test_detect_missing_daily_api(self, monitor):
        """检测日期级 API 缺失"""
        conn = monitor.conn
        batch_id = '2026-03-14_14:30'
        monitor.start_batch(batch_id, 'once')
        monitor.start_account(batch_id, 'acc1', '新加坡团队')
        # 记录 03-14 的 live_stats，但缺少 03-13
        monitor.record_daily_stats(batch_id, 'acc1', '2026-03-14', 'live_stats', 'success')
        monitor.finish_account(batch_id, 'acc1', 'success')
        monitor.finish_batch(batch_id)

        gaps = detect_gaps(conn, days=3)
        daily_gaps = [g for g in gaps if g['level'] == 'daily']
        # 应检测到缺失的日期级数据
        assert len(daily_gaps) >= 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_gap_detector.py -v`
Expected: FAIL

- [ ] **Step 3: 实现缺失检测器**

`live_dp/monitor/recrawl/gap_detector.py`:

```python
"""缺失检测器 — 对比 registry 期望 vs collection_records 实际记录，输出缺失清单"""

import time
import sqlite3
from datetime import datetime, timedelta
from monitor.registry import get_expected_account_types, get_expected_room_types, get_expected_daily_types


def detect_gaps(conn: sqlite3.Connection, days: int = 3) -> list[dict]:
    """检测时间窗口内的采集缺失

    Args:
        conn: 数据库连接
        days: 时间窗口（天数）

    Returns:
        缺失清单: [{account_id, room_id, target_date, api_type, level, batch_id, group_name}]
    """
    cutoff_ts = int(time.time()) - days * 86400
    gaps = []

    # 1. 获取时间窗口内所有账号（从 account_sessions）
    accounts = conn.execute(
        """SELECT DISTINCT account_id, group_name FROM account_sessions
           WHERE started_at >= datetime(?, 'unixepoch')
              OR batch_id IN (
                  SELECT batch_id FROM collection_batches
                  WHERE started_at >= datetime(?, 'unixepoch')
              )""",
        (cutoff_ts, cutoff_ts),
    ).fetchall()

    for account_row in accounts:
        account_id = account_row['account_id']
        group_name = account_row['group_name']

        # 获取该账号最新的 batch_id
        latest_batch = conn.execute(
            """SELECT batch_id FROM account_sessions
               WHERE account_id = ? ORDER BY started_at DESC LIMIT 1""",
            (account_id,),
        ).fetchone()
        batch_id = latest_batch['batch_id'] if latest_batch else ''

        # 2. 账号级缺失检测
        expected_account = get_expected_account_types()
        actual_account = set(
            r['api_type'] for r in conn.execute(
                """SELECT DISTINCT api_type FROM collection_records
                   WHERE account_id = ? AND room_id = '' AND status = 'success'
                     AND batch_id IN (
                         SELECT batch_id FROM collection_batches
                         WHERE started_at >= datetime(?, 'unixepoch')
                     )""",
                (account_id, cutoff_ts),
            ).fetchall()
        )
        for api_type in expected_account:
            if api_type not in actual_account:
                gaps.append({
                    'account_id': account_id, 'group_name': group_name,
                    'batch_id': batch_id, 'room_id': '', 'target_date': '',
                    'api_type': api_type, 'level': 'account',
                })

        # 3. 日期级缺失检测
        expected_daily = get_expected_daily_types()
        if expected_daily:
            # 生成时间窗口内的日期列表
            today = datetime.now().date()
            target_dates = [(today - timedelta(days=i)).isoformat() for i in range(days)]

            actual_daily = set()
            for r in conn.execute(
                """SELECT DISTINCT target_date, api_type FROM daily_collection_status
                   WHERE account_id = ? AND status = 'success'
                     AND target_date >= ?""",
                (account_id, target_dates[-1] if target_dates else ''),
            ).fetchall():
                actual_daily.add((r['target_date'], r['api_type']))

            for target_date in target_dates:
                for api_type in expected_daily:
                    if (target_date, api_type) not in actual_daily:
                        gaps.append({
                            'account_id': account_id, 'group_name': group_name,
                            'batch_id': batch_id, 'room_id': '', 'target_date': target_date,
                            'api_type': api_type, 'level': 'daily',
                        })

        # 4. 直播间级缺失检测
        rooms = conn.execute(
            """SELECT DISTINCT room_id, account_id FROM room_sessions
               WHERE account_id = ? AND start_time >= ?""",
            (account_id, cutoff_ts),
        ).fetchall()

        expected_room = get_expected_room_types()
        for room_row in rooms:
            room_id = room_row['room_id']
            actual_room = set(
                r['api_type'] for r in conn.execute(
                    """SELECT DISTINCT api_type FROM collection_records
                       WHERE account_id = ? AND room_id = ? AND status = 'success'""",
                    (account_id, room_id),
                ).fetchall()
            )
            for api_type in expected_room:
                if api_type not in actual_room:
                    gaps.append({
                        'account_id': account_id, 'group_name': group_name,
                        'batch_id': batch_id, 'room_id': room_id, 'target_date': '',
                        'api_type': api_type, 'level': 'room',
                    })

    return gaps
```

- [ ] **Step 4: 运行测试**

Run: `cd live_dp && python -m pytest tests/monitor/test_gap_detector.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add live_dp/monitor/recrawl/gap_detector.py live_dp/tests/monitor/test_gap_detector.py
git commit -m "feat(monitor): 缺失检测器 gap_detector"
```

---

### Task 5: AdsPower 代理获取

**Files:**
- Create: `live_dp/monitor/recrawl/proxy.py`
- Test: `live_dp/tests/monitor/test_proxy.py`

- [ ] **Step 1: 编写代理获取测试**

`live_dp/tests/monitor/test_proxy.py`:

```python
"""代理获取模块测试"""

from unittest.mock import patch, MagicMock
from monitor.recrawl.proxy import get_proxy_for_account, build_proxy_url


class TestBuildProxyUrl:

    def test_socks5_with_auth(self):
        config = {
            'proxy_soft': 'other', 'proxy_type': 'socks5',
            'proxy_host': '1.2.3.4', 'proxy_port': '1080',
            'proxy_user': 'user', 'proxy_password': 'pass',
        }
        url = build_proxy_url(config)
        assert url == 'socks5://user:pass@1.2.3.4:1080'

    def test_http_without_auth(self):
        config = {
            'proxy_soft': 'other', 'proxy_type': 'http',
            'proxy_host': '1.2.3.4', 'proxy_port': '8080',
        }
        url = build_proxy_url(config)
        assert url == 'http://1.2.3.4:8080'

    def test_no_proxy(self):
        config = {'proxy_soft': 'no_proxy'}
        url = build_proxy_url(config)
        assert url is None


class TestGetProxyForAccount:

    @patch('monitor.recrawl.proxy.requests.post')
    def test_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                'code': 0,
                'data': {
                    'list': [{
                        'profile_id': 'acc1',
                        'user_proxy_config': {
                            'proxy_soft': 'other', 'proxy_type': 'socks5',
                            'proxy_host': '1.2.3.4', 'proxy_port': '1080',
                            'proxy_user': 'user', 'proxy_password': 'pass',
                        },
                    }],
                },
            },
        )
        proxy = get_proxy_for_account('acc1')
        assert proxy == {'https': 'socks5://user:pass@1.2.3.4:1080', 'http': 'socks5://user:pass@1.2.3.4:1080'}

    @patch('monitor.recrawl.proxy.requests.post')
    def test_not_found(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {'code': 0, 'data': {'list': []}},
        )
        proxy = get_proxy_for_account('nonexistent')
        assert proxy is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_proxy.py -v`
Expected: FAIL

- [ ] **Step 3: 实现代理获取**

`live_dp/monitor/recrawl/proxy.py`:

```python
"""AdsPower 代理 IP 获取 — 通过 V2 API 查询环境的代理配置"""

import requests
from core.config import Settings
from utils.logger import logger


def build_proxy_url(proxy_config: dict) -> str | None:
    """将 AdsPower user_proxy_config 转为 requests 代理 URL"""
    if proxy_config.get('proxy_soft') == 'no_proxy':
        return None

    proxy_type = proxy_config.get('proxy_type', 'http')
    host = proxy_config.get('proxy_host', '')
    port = proxy_config.get('proxy_port', '')

    if not host or not port:
        return None

    user = proxy_config.get('proxy_user', '')
    password = proxy_config.get('proxy_password', '')

    if user and password:
        return f'{proxy_type}://{user}:{password}@{host}:{port}'
    return f'{proxy_type}://{host}:{port}'


def get_proxy_for_account(account_id: str, api_url: str | None = None) -> dict | None:
    """通过 AdsPower V2 API 获取账号对应的代理配置

    Returns:
        {'http': 'socks5://...', 'https': 'socks5://...'} 或 None
    """
    if api_url is None:
        api_url = Settings.ADSPOWER_CONFIG['api_url']

    try:
        resp = requests.post(
            f'{api_url}/api/v2/browser-profile/list',
            json={'profile_id': [account_id]},
            timeout=10,
        )
        data = resp.json()

        if data.get('code') != 0:
            logger.warning(f'AdsPower 查询代理失败: {data.get("msg")}')
            return None

        profiles = data.get('data', {}).get('list', [])
        if not profiles:
            logger.warning(f'未找到账号 {account_id} 的 AdsPower 环境')
            return None

        proxy_config = profiles[0].get('user_proxy_config', {})
        proxy_url = build_proxy_url(proxy_config)

        if proxy_url is None:
            logger.info(f'账号 {account_id} 未配置代理（no_proxy）')
            return None

        return {'http': proxy_url, 'https': proxy_url}

    except Exception as e:
        logger.error(f'获取账号 {account_id} 代理失败: {e}')
        return None
```

- [ ] **Step 4: 运行测试**

Run: `cd live_dp && python -m pytest tests/monitor/test_proxy.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add live_dp/monitor/recrawl/proxy.py live_dp/tests/monitor/test_proxy.py
git commit -m "feat(monitor): AdsPower 代理 IP 获取模块"
```

---

## Chunk 3: 补采执行器 + 请求上下文持久化

### Task 6: 补采执行器框架

**Files:**
- Create: `live_dp/monitor/recrawl/executor.py`

- [ ] **Step 1: 实现执行器框架**

`live_dp/monitor/recrawl/executor.py`:

```python
"""补采执行器 — 消费 pending 任务，通过 HTTP 请求补采缺失数据

注意：HTTP 请求的具体实现（cookies 获取、API 参数构造）为后续优化项。
当前版本搭建任务消费框架 + 重试逻辑，fetch_api_data 预留接口。
"""

import time
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

from core.config import Settings
from utils.logger import logger
from monitor.db import get_connection
from monitor.recrawl.models import (
    get_pending_tasks, update_task_status, get_request_context, cleanup_old_tasks,
)
from monitor.recrawl.proxy import get_proxy_for_account

# api_type → request_context 的 context_type 映射
CONTEXT_MAP = {
    'trend_gmv': 'trend_chart',
    'trend_stats': 'trend_chart',
    'live_stats': 'live_stats',
}


def execute_pending_tasks(conn: sqlite3.Connection) -> dict:
    """执行所有 pending 补采任务

    Returns:
        {'total': N, 'success': N, 'failed': N, 'skipped': N}
    """
    config = Settings.RECRAWL_CONFIG
    if not config.get('enabled', True):
        logger.info('自动补采已关闭，跳过执行')
        return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}

    # 清理旧任务
    cleanup_old_tasks(conn, days=30)

    tasks = get_pending_tasks(conn)
    if not tasks:
        logger.info('无 pending 补采任务')
        return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}

    logger.info(f'发现 {len(tasks)} 个 pending 补采任务')

    # 按账号分组
    account_tasks: dict[str, list[dict]] = defaultdict(list)
    for task in tasks:
        account_tasks[task['account_id']].append(task)

    stats = {'total': len(tasks), 'success': 0, 'failed': 0, 'skipped': 0}
    max_concurrent = config.get('max_concurrent', 2)

    def process_account(account_id: str, account_task_list: list[dict]) -> dict:
        """处理单个账号的所有补采任务（串行，独立数据库连接）"""
        result = {'success': 0, 'failed': 0, 'skipped': 0}

        # 每个线程使用独立的 SQLite 连接，避免多线程共享写入冲突
        thread_conn = get_connection()

        # 获取代理
        proxy = get_proxy_for_account(account_id)

        request_interval = config.get('request_interval', 2)

        for task in account_task_list:
            task_result = _execute_single_task(thread_conn, task, proxy, config)
            result[task_result] += 1
            time.sleep(request_interval)

        thread_conn.close()
        return result

    # 账号间并行执行
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(process_account, acc_id, task_list): acc_id
            for acc_id, task_list in account_tasks.items()
        }
        for future in futures:
            try:
                result = future.result()
                stats['success'] += result['success']
                stats['failed'] += result['failed']
                stats['skipped'] += result['skipped']
            except Exception as e:
                logger.error(f'账号补采线程异常: {e}')

    logger.info(
        f'补采执行完成: 总计 {stats["total"]}, '
        f'成功 {stats["success"]}, 失败 {stats["failed"]}, 跳过 {stats["skipped"]}'
    )
    return stats


def _execute_single_task(
    conn: sqlite3.Connection, task: dict, proxy: dict | None, config: dict,
) -> str:
    """执行单个补采任务

    Returns:
        'success' / 'failed' / 'skipped'
    """
    task_id = task['id']
    api_type = task['api_type']

    # 标记为 running
    update_task_status(conn, task_id, 'running')

    # 获取请求上下文
    context_type = CONTEXT_MAP.get(api_type, api_type)
    ctx = get_request_context(conn, task['account_id'], context_type)
    if ctx is None:
        logger.warning(f'补采任务 {task_id}: 无请求上下文 (account={task["account_id"]}, type={context_type})，跳过')
        update_task_status(conn, task_id, 'pending', error_msg='no_request_context')
        return 'skipped'

    # 重试循环
    max_retry = config.get('max_retry', 3)
    delays = config.get('retry_delays', [1, 3, 10])

    for attempt in range(max_retry):
        try:
            # TODO: 实际 HTTP 请求实现（后续优化）
            logger.info(
                f'补采任务 {task_id}: {api_type} (account={task["account_id"]}, '
                f'room={task["room_id"]}) — HTTP 请求待实现'
            )
            update_task_status(conn, task_id, 'pending', error_msg='http_not_implemented')
            return 'skipped'

        except Exception as e:
            error_msg = str(e)
            logger.warning(f'补采任务 {task_id} 第 {attempt + 1} 次失败: {error_msg}')
            update_task_status(
                conn, task_id, 'running',
                retry_count=attempt + 1, error_msg=error_msg,
            )
            if attempt < max_retry - 1:
                time.sleep(delays[attempt] if attempt < len(delays) else delays[-1])

    # 所有重试失败
    update_task_status(conn, task_id, 'recrawl_failed', retry_count=max_retry)
    return 'failed'
```

- [ ] **Step 2: 编写执行器测试**

`live_dp/tests/monitor/test_executor.py`:

```python
"""补采执行器测试"""

import pytest
from unittest.mock import patch
from monitor.db import get_connection, init_db
from monitor.recrawl.models import create_task_auto, save_request_context, get_pending_tasks
from monitor.recrawl.executor import execute_pending_tasks, _execute_single_task


@pytest.fixture
def conn():
    c = get_connection(':memory:')
    init_db(c)
    yield c
    c.close()


class TestExecutor:

    def test_empty_tasks(self, conn):
        """无 pending 任务时直接返回"""
        stats = execute_pending_tasks(conn)
        assert stats['total'] == 0

    @patch('monitor.recrawl.executor.Settings')
    def test_disabled_config(self, mock_settings, conn):
        """配置关闭时跳过执行"""
        mock_settings.RECRAWL_CONFIG = {'enabled': False}
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', '', '', 'live_list', 'account')
        stats = execute_pending_tasks(conn)
        assert stats['total'] == 0

    def test_skip_without_context(self, conn):
        """无请求上下文时任务被 skip"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        task = get_pending_tasks(conn)[0]
        config = {'max_retry': 3, 'retry_delays': [1, 3, 10]}
        result = _execute_single_task(conn, task, None, config)
        assert result == 'skipped'

    def test_skip_with_context_http_not_impl(self, conn):
        """有上下文但 HTTP 未实现时返回 skipped"""
        save_request_context(conn, 'acc1', 'trend_chart', api_base_url='https://shop.tiktok.com')
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        task = get_pending_tasks(conn)[0]
        config = {'max_retry': 3, 'retry_delays': [1, 3, 10]}
        result = _execute_single_task(conn, task, None, config)
        assert result == 'skipped'
```

- [ ] **Step 3: 运行测试**

Run: `cd live_dp && python -m pytest tests/monitor/test_executor.py -v`
Expected: 全部 PASS

```bash
git add live_dp/monitor/recrawl/executor.py
git commit -m "feat(monitor): 补采执行器框架（HTTP 请求待实现）"
```

---

### Task 7: 请求上下文持久化（爬虫集成）

**Files:**
- Modify: `live_dp/monitor/tracker.py`
- Modify: `live_dp/spiders/tiktok.py`

- [ ] **Step 1: 在 `tracker.py` 的 `CollectionMonitor` 中新增 `conn` 属性和 `save_request_context` 方法**

在 `CollectionMonitor` 类的 `__init__` 方法之后添加 `conn` 属性：

```python
    @property
    def conn(self) -> sqlite3.Connection:
        """暴露数据库连接供补采模块使用"""
        return self._conn
```

在 `CollectionMonitor` 类末尾添加 `save_request_context` 方法：

```python
    def save_request_context(
        self, account_id: str, context_type: str,
        api_base_url: str = '', query_string: str = '',
        headers: str = '{}', cookies: str = '[]',
        payload_template: str = '{}',
    ) -> None:
        """保存请求上下文到数据库，供补采模块复用"""
        try:
            from monitor.recrawl.models import save_request_context as _save
            _save(
                self.conn, account_id, context_type,
                api_base_url, query_string, headers, cookies, payload_template,
            )
        except Exception as e:
            logger.warning(f'保存请求上下文失败: {e}')
```

- [ ] **Step 2: 在 `tiktok.py:_handle_tiktok_live_list` 中持久化 trend_chart 上下文**

在 `tiktok.py` 的 `_handle_tiktok_live_list` 方法中，`self._api_query_string = parsed.query or ""` 赋值语句之后，添加：

```python
            # 采集监控：持久化 trend_chart 请求上下文，供补采模块复用
            if self.batch_id and headers:
                try:
                    import json as _json
                    from monitor import get_monitor
                    _filtered_headers = {k: v for k, v in headers.items() if not k.startswith(':')}
                    if not any(k.lower() == 'content-type' for k in _filtered_headers):
                        _filtered_headers['Content-Type'] = 'application/json'
                    get_monitor().save_request_context(
                        account_id=self.browser_id,
                        context_type='trend_chart',
                        api_base_url=self._api_base_url,
                        query_string=self._api_query_string,
                        headers=_json.dumps(_filtered_headers),
                    )
                except Exception:
                    pass  # 监控不阻塞采集
```

- [ ] **Step 3: 运行现有测试确认不破坏**

Run: `cd live_dp && python -m pytest tests/monitor/ -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add live_dp/monitor/tracker.py live_dp/spiders/tiktok.py
git commit -m "feat(monitor): 请求上下文持久化（trend_chart）"
```

---

### Task 8: 补采模块入口 + main.py 集成

**Files:**
- Modify: `live_dp/monitor/recrawl/__init__.py`
- Modify: `live_dp/main.py`

- [ ] **Step 1: 实现补采模块入口函数**

`live_dp/monitor/recrawl/__init__.py`:

```python
"""补采闭环模块

入口函数 auto_detect_and_recrawl() 在 main.py:run_once() 末尾调用。
"""

from utils.logger import logger


def auto_detect_and_recrawl(batch_id: str, mode: str = 'once', days: int = 3) -> None:
    """自动检测缺失并执行补采

    Args:
        batch_id: 当前批次 ID
        mode: 采集模式（full 模式不触发自动补采）
        days: 时间窗口（天数）
    """
    if mode == 'full':
        logger.info('全量采集模式，跳过自动补采')
        return

    try:
        from core.config import Settings
        config = Settings.RECRAWL_CONFIG
        if not config.get('enabled', True):
            logger.info('自动补采已关闭')
            return

        from monitor import get_monitor
        conn = get_monitor().conn

        # 1. 缺失检测
        from monitor.recrawl.gap_detector import detect_gaps
        gaps = detect_gaps(conn, days=days)
        if not gaps:
            logger.info('未检测到采集缺失，无需补采')
            return

        logger.info(f'检测到 {len(gaps)} 项采集缺失，生成补采任务')

        # 2. 生成补采任务
        from monitor.recrawl.models import create_task_auto
        created = 0
        for gap in gaps:
            result = create_task_auto(
                conn,
                batch_id=gap.get('batch_id', batch_id),
                account_id=gap['account_id'],
                group_name=gap.get('group_name', ''),
                room_id=gap.get('room_id', ''),
                target_date=gap.get('target_date', ''),
                api_type=gap['api_type'],
                level=gap['level'],
            )
            if result:
                created += 1

        logger.info(f'已创建 {created} 个补采任务（{len(gaps) - created} 个已存在）')

        # 3. 执行补采
        from monitor.recrawl.executor import execute_pending_tasks
        stats = execute_pending_tasks(conn)
        logger.info(f'补采执行结果: {stats}')

    except Exception as e:
        logger.error(f'自动补采异常: {e}')
```

- [ ] **Step 2: 在 `main.py:run_once()` 末尾集成**

在 `main.py` 的 `monitor.finish_batch(batch_id)` 之后添加：

```python
        # 自动补采闭环
        try:
            from monitor.recrawl import auto_detect_and_recrawl
            auto_detect_and_recrawl(batch_id, mode=mode, days=Settings.RECRAWL_CONFIG.get('default_days', 3))
        except Exception as e:
            logger.error(f'自动补采调用失败: {e}')
```

注意：需要找到 `finish_batch` 的确切位置，在其后添加。`mode` 参数从 `run_once` 函数的参数中获取（`full_collection` 为 True 时 mode='full'，否则 mode='once'）。

- [ ] **Step 3: 提交**

```bash
git add live_dp/monitor/recrawl/__init__.py live_dp/main.py
git commit -m "feat(monitor): 补采模块入口 + main.py 集成自动补采"
```

---

## Chunk 4: API 端点

### Task 9: 账号总览 API

**Files:**
- Create: `live_dp/monitor/api/overview.py`
- Test: `live_dp/tests/monitor/test_overview_api.py`
- Modify: `live_dp/monitor/server.py`

- [ ] **Step 1: 编写总览 API 测试**

`live_dp/tests/monitor/test_overview_api.py`:

```python
"""账号总览 API 测试"""

import time
import pytest
from fastapi.testclient import TestClient
from monitor.db import get_connection, init_db
from monitor.tracker import CollectionMonitor


@pytest.fixture
def app():
    from fastapi import FastAPI
    from monitor.api.overview import router, set_db_connection
    _app = FastAPI()
    _app.include_router(router)

    conn = get_connection(':memory:')
    init_db(conn)
    set_db_connection(conn)

    # 插入测试数据
    monitor = CollectionMonitor(conn)
    batch_id = '2026-03-14_14:30'
    monitor.start_batch(batch_id, 'once')
    monitor.start_account(batch_id, 'acc1', '新加坡团队-tiktok')
    monitor.record(batch_id, 'acc1', 'live_list', status='success')
    monitor.record(batch_id, 'acc1', 'replay_info', status='success')
    monitor.record_rooms(batch_id, 'acc1', [
        {'room_id': 'room1', 'live_start_ts': int(time.time()) - 3600,
         'live_end_ts': int(time.time()), 'duration': 3600},
    ])
    monitor.record(batch_id, 'acc1', 'trend_gmv', room_id='room1', status='success')
    # 缺少 trend_stats
    monitor.finish_account(batch_id, 'acc1', 'success')
    monitor.finish_batch(batch_id)

    yield _app
    conn.close()


@pytest.fixture
def client(app):
    return TestClient(app)


class TestOverviewAPI:

    def test_get_overview(self, client):
        resp = client.get('/api/overview?days=3')
        assert resp.status_code == 200
        data = resp.json()
        assert 'accounts' in data
        assert len(data['accounts']) >= 1
        acc = data['accounts'][0]
        assert acc['account_id'] == 'acc1'
        assert 'completeness' in acc
        assert acc['missing_count'] >= 1  # 缺少 trend_stats

    def test_get_account_detail(self, client):
        resp = client.get('/api/overview/acc1?days=3')
        assert resp.status_code == 200
        data = resp.json()
        assert 'account_level' in data
        assert 'room_level' in data
        assert 'completeness' in data
        # 检查 room1 缺少 trend_stats
        room = data['room_level'][0]
        assert room['room_id'] == 'room1'
        statuses = {a['api_type']: a['status'] for a in room['apis']}
        assert statuses['trend_gmv'] == 'success'
        assert statuses['trend_stats'] == 'missing'
```

- [ ] **Step 2: 实现总览 API**

`live_dp/monitor/api/overview.py`:

```python
"""账号总览 API — 跨批次聚合视角"""

import time
import sqlite3
from fastapi import APIRouter, Query
from monitor.db import get_connection
from monitor.registry import (
    get_expected_account_types, get_expected_daily_types, get_expected_room_types,
)

router = APIRouter(prefix='/api', tags=['overview'])

_conn: sqlite3.Connection | None = None


def set_db_connection(conn: sqlite3.Connection):
    global _conn
    _conn = conn


def _get_conn() -> sqlite3.Connection:
    return _conn or get_connection()


@router.get('/overview')
def get_overview(days: int = Query(default=3, ge=1, le=90)):
    """账号总览 — 返回时间窗口内所有账号的聚合完整率"""
    conn = _get_conn()
    cutoff_ts = int(time.time()) - days * 86400

    # 获取时间窗口内的所有账号
    accounts = conn.execute(
        """SELECT DISTINCT s.account_id, s.group_name,
                  MAX(s.started_at) as last_collected_at,
                  (SELECT batch_id FROM account_sessions
                   WHERE account_id = s.account_id ORDER BY started_at DESC LIMIT 1) as last_batch_id
           FROM account_sessions s
           JOIN collection_batches b ON s.batch_id = b.batch_id
           WHERE b.started_at >= datetime(?, 'unixepoch')
           GROUP BY s.account_id""",
        (cutoff_ts,),
    ).fetchall()

    expected_account = get_expected_account_types()
    expected_room = get_expected_room_types()
    result = []

    for acc in accounts:
        account_id = acc['account_id']

        # 统计直播间数
        rooms = conn.execute(
            "SELECT DISTINCT room_id FROM room_sessions WHERE account_id = ? AND start_time >= ?",
            (account_id, cutoff_ts),
        ).fetchall()
        total_rooms = len(rooms)

        # 期望总数
        expected_total = len(expected_account) + total_rooms * len(expected_room)

        # 实际成功数（跨批次聚合）
        actual_account = conn.execute(
            """SELECT COUNT(DISTINCT api_type) FROM collection_records
               WHERE account_id = ? AND room_id = '' AND status = 'success'
                 AND batch_id IN (SELECT batch_id FROM collection_batches WHERE started_at >= datetime(?, 'unixepoch'))""",
            (account_id, cutoff_ts),
        ).fetchone()[0]

        actual_room = 0
        for room in rooms:
            cnt = conn.execute(
                """SELECT COUNT(DISTINCT api_type) FROM collection_records
                   WHERE account_id = ? AND room_id = ? AND status = 'success'""",
                (account_id, room['room_id']),
            ).fetchone()[0]
            actual_room += cnt

        actual_total = actual_account + actual_room
        missing_count = max(0, expected_total - actual_total)
        completeness = round(actual_total / expected_total * 100, 1) if expected_total > 0 else 100.0

        result.append({
            'account_id': account_id,
            'account_name': account_id,  # 暂用 account_id，后续从 AdsPower 获取
            'group_name': acc['group_name'],
            'completeness': completeness,
            'total_rooms': total_rooms,
            'missing_count': missing_count,
            'last_batch_id': acc['last_batch_id'],
            'last_collected_at': acc['last_collected_at'],
        })

    # 按完整率升序排列（最不完整的在前）
    result.sort(key=lambda x: x['completeness'])

    from datetime import datetime, timedelta
    today = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    return {
        'accounts': result,
        'time_range': {'start': start, 'end': today},
        'days': days,
    }


@router.get('/overview/{account_id}')
def get_account_overview(account_id: str, days: int = Query(default=3, ge=1, le=90)):
    """账号聚合详情 — 三级数据状态（跨批次合并）"""
    conn = _get_conn()
    cutoff_ts = int(time.time()) - days * 86400

    expected_account_types = get_expected_account_types()
    expected_daily_types = get_expected_daily_types()
    expected_room_types = get_expected_room_types()

    # 1. 账号级
    account_level = []
    for api_type in expected_account_types:
        row = conn.execute(
            """SELECT batch_id FROM collection_records
               WHERE account_id = ? AND room_id = '' AND api_type = ? AND status = 'success'
               ORDER BY collected_at DESC LIMIT 1""",
            (account_id, api_type),
        ).fetchone()
        account_level.append({
            'api_type': api_type,
            'status': 'success' if row else 'missing',
            'last_batch': row['batch_id'] if row else None,
        })

    # 2. 日期级
    daily_level = []
    daily_records = conn.execute(
        """SELECT DISTINCT target_date, api_type, status FROM daily_collection_status
           WHERE account_id = ? AND target_date >= date(?, 'unixepoch')
           ORDER BY target_date DESC""",
        (account_id, cutoff_ts),
    ).fetchall()
    seen_dates = set()
    for r in daily_records:
        daily_level.append({
            'target_date': r['target_date'],
            'api_type': r['api_type'],
            'status': r['status'],
        })
        seen_dates.add(r['target_date'])

    # 3. 直播间级
    rooms = conn.execute(
        """SELECT DISTINCT rs.room_id,
                  COALESCE(MAX(rs.start_time), 0) as start_time
           FROM room_sessions rs
           WHERE rs.account_id = ? AND rs.start_time >= ?
           GROUP BY rs.room_id
           ORDER BY start_time DESC""",
        (account_id, cutoff_ts),
    ).fetchall()

    room_level = []
    for room in rooms:
        room_id = room['room_id']
        apis = []
        for api_type in expected_room_types:
            row = conn.execute(
                """SELECT 1 FROM collection_records
                   WHERE account_id = ? AND room_id = ? AND api_type = ? AND status = 'success'
                   LIMIT 1""",
                (account_id, room_id, api_type),
            ).fetchone()
            apis.append({
                'api_type': api_type,
                'status': 'success' if row else 'missing',
            })
        room_level.append({'room_id': room_id, 'apis': apis})

    # 计算完整率
    total = len(expected_account_types) + len(rooms) * len(expected_room_types)
    success = sum(1 for a in account_level if a['status'] == 'success')
    success += sum(1 for r in room_level for a in r['apis'] if a['status'] == 'success')
    completeness = round(success / total * 100, 1) if total > 0 else 100.0

    return {
        'account_level': account_level,
        'daily_level': daily_level,
        'room_level': room_level,
        'completeness': completeness,
    }
```

- [ ] **Step 3: 运行测试**

Run: `cd live_dp && python -m pytest tests/monitor/test_overview_api.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add live_dp/monitor/api/overview.py live_dp/tests/monitor/test_overview_api.py
git commit -m "feat(monitor): 账号总览 API（跨批次聚合）"
```

---

### Task 10: 补采任务 API

**Files:**
- Create: `live_dp/monitor/api/recrawl_routes.py`
- Test: `live_dp/tests/monitor/test_recrawl_api.py`

- [ ] **Step 1: 编写补采 API 测试**

`live_dp/tests/monitor/test_recrawl_api.py`:

```python
"""补采任务 API 测试"""

import pytest
from fastapi.testclient import TestClient
from monitor.db import get_connection, init_db


@pytest.fixture
def app():
    from fastapi import FastAPI
    from monitor.api.recrawl_routes import router, set_db_connection
    _app = FastAPI()
    _app.include_router(router)
    conn = get_connection(':memory:')
    init_db(conn)
    set_db_connection(conn)
    yield _app
    conn.close()


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRecrawlAPI:

    def test_trigger_manual_recrawl(self, client):
        resp = client.post('/api/recrawl/trigger', json={
            'account_id': 'acc1', 'level': 'room',
            'room_id': 'room1', 'api_type': 'trend_gmv',
            'target_date': '', 'batch_id': '2026-03-14_14:30',
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'created'

    def test_get_tasks(self, client):
        # 先创建一个任务
        client.post('/api/recrawl/trigger', json={
            'account_id': 'acc1', 'level': 'room',
            'room_id': 'room1', 'api_type': 'trend_gmv',
            'target_date': '', 'batch_id': '2026-03-14_14:30',
        })
        resp = client.get('/api/recrawl/tasks?account_id=acc1')
        assert resp.status_code == 200
        data = resp.json()
        assert len(data['tasks']) == 1
        assert data['tasks'][0]['api_type'] == 'trend_gmv'
```

- [ ] **Step 2: 实现补采 API**

`live_dp/monitor/api/recrawl_routes.py`:

```python
"""补采任务 API — 手动触发 + 任务列表查询"""

import sqlite3
from fastapi import APIRouter, Query
from pydantic import BaseModel
from monitor.db import get_connection
from monitor.recrawl.models import create_task_manual, get_tasks_by_account

router = APIRouter(prefix='/api', tags=['recrawl'])

_conn: sqlite3.Connection | None = None


def set_db_connection(conn: sqlite3.Connection):
    global _conn
    _conn = conn


def _get_conn() -> sqlite3.Connection:
    return _conn or get_connection()


class RecrawlTriggerRequest(BaseModel):
    account_id: str
    level: str
    room_id: str = ''
    api_type: str
    target_date: str = ''
    batch_id: str
    group_name: str = ''


@router.post('/recrawl/trigger')
def trigger_recrawl(req: RecrawlTriggerRequest):
    """手动触发补采任务"""
    conn = _get_conn()
    task_id = create_task_manual(
        conn, batch_id=req.batch_id, account_id=req.account_id,
        group_name=req.group_name, room_id=req.room_id,
        target_date=req.target_date, api_type=req.api_type, level=req.level,
    )
    return {'status': 'created', 'task_id': task_id}


@router.get('/recrawl/tasks')
def list_tasks(
    account_id: str = Query(default=None),
    status: str = Query(default=None),
):
    """查询补采任务列表"""
    conn = _get_conn()
    if account_id:
        tasks = get_tasks_by_account(conn, account_id, status=status)
    else:
        # 无 account_id 时返回所有任务（限制 100 条）
        sql = "SELECT * FROM recrawl_tasks"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT 100"
        rows = conn.execute(sql, params).fetchall()
        tasks = [dict(r) for r in rows]

    return {'tasks': tasks, 'total': len(tasks)}
```

- [ ] **Step 3: 运行测试**

Run: `cd live_dp && python -m pytest tests/monitor/test_recrawl_api.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 注册路由到 server.py（必须在 SPA fallback 之前）**

在 `live_dp/monitor/server.py` 第 24 行（`app.include_router(registry_router)` 之后、`FRONTEND_DIST` 判断之前）添加：

```python
from monitor.api.overview import router as overview_router
from monitor.api.recrawl_routes import router as recrawl_router

app.include_router(overview_router)
app.include_router(recrawl_router)
```

**注意**：新路由必须在 `/{full_path:path}` SPA fallback 通配路由之前注册，否则 API 请求会被 SPA 拦截。

- [ ] **Step 5: 提交**

```bash
git add live_dp/monitor/api/recrawl_routes.py live_dp/tests/monitor/test_recrawl_api.py live_dp/monitor/server.py
git commit -m "feat(monitor): 补采任务 API（手动触发 + 列表查询）+ 路由注册"
```

---

## Chunk 5: 前端改版

### Task 11: 前端 API 调用 + 路由调整

**Files:**
- Modify: `live_dp/monitor/frontend/src/api/index.js`
- Modify: `live_dp/monitor/frontend/src/router/index.js`

- [ ] **Step 1: 新增 API 调用函数**

在 `api/index.js` 末尾追加：

```javascript
// 账号总览
export const fetchOverview = (days = 3) => api.get('/overview', { params: { days } })
export const fetchAccountOverview = (accountId, days = 3) => api.get(`/overview/${accountId}`, { params: { days } })

// 补采
export const triggerRecrawl = (data) => api.post('/recrawl/trigger', data)
export const fetchRecrawlTasks = (params) => api.get('/recrawl/tasks', { params })
```

- [ ] **Step 2: 调整路由**

`live_dp/monitor/frontend/src/router/index.js`:

```javascript
import { createRouter, createWebHistory } from 'vue-router'
import AccountOverview from '../views/AccountOverview.vue'
import AccountDetail from '../views/AccountDetail.vue'
import BatchHistory from '../views/BatchHistory.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: AccountOverview },
    { path: '/account/:accountId', component: AccountDetail, props: true },
    { path: '/batches', component: BatchHistory },
  ]
})
```

- [ ] **Step 3: 提交**

```bash
git add live_dp/monitor/frontend/src/api/index.js live_dp/monitor/frontend/src/router/index.js
git commit -m "feat(monitor): 前端 API 调用 + 路由调整（账号总览为首页）"
```

---

### Task 12: Dashboard.vue → BatchHistory.vue

**Files:**
- Rename: `live_dp/monitor/frontend/src/views/Dashboard.vue` → `BatchHistory.vue`

- [ ] **Step 1: 使用 git mv 重命名 Dashboard.vue**

```bash
git mv live_dp/monitor/frontend/src/views/Dashboard.vue live_dp/monitor/frontend/src/views/BatchHistory.vue
```

- [ ] **Step 2: 提交**

```bash
git add live_dp/monitor/frontend/src/views/BatchHistory.vue
git commit -m "feat(monitor): Dashboard 降级为 BatchHistory（批次历史二级页面）"
```

---

### Task 13: 账号总览页 (AccountOverview.vue)

**Files:**
- Create: `live_dp/monitor/frontend/src/views/AccountOverview.vue`

- [ ] **Step 1: 创建 AccountOverview.vue**

使用 `@superpowers:frontend-design` skill 创建账号总览页。关键要素：
- 顶部：时间筛选器（近3天/7天/30天）+ 状态筛选器（全部/成功/部分/失败）
- 主体：卡片网格展示所有账号
- 每张卡片：账号名、分组名、环形完整率、直播间数、缺失数、一键补采按钮
- 导航链接到批次历史页
- 暗色系设计，与现有 UI 风格一致

API 调用：`fetchOverview(days)`

路由跳转：点击卡片 → `/account/${accountId}?days=${days}`

- [ ] **Step 2: 更新 App.vue 导航**

在 `App.vue` 的导航栏中新增：
- 「账号总览」指向 `/`
- 「批次历史」指向 `/batches`

- [ ] **Step 3: 构建测试**

Run: `cd live_dp/monitor/frontend && npm run build`
Expected: 构建成功

- [ ] **Step 4: 提交**

```bash
git add live_dp/monitor/frontend/src/views/AccountOverview.vue live_dp/monitor/frontend/src/App.vue
git commit -m "feat(monitor): 账号总览页（跨批次聚合首页）"
```

---

### Task 14: AccountDetail.vue 增强（补采按钮 + 任务面板）

**Files:**
- Modify: `live_dp/monitor/frontend/src/views/AccountDetail.vue`

- [ ] **Step 1: 在 AccountDetail.vue 中增强**

改动要点：
1. 从路由 query 中获取 `days` 参数，调用 `fetchAccountOverview(accountId, days)` 替代原 batch 绑定的详情 API
2. 每个数据项（账号级/日期级/直播间级）旁增加「补采」按钮
3. 补采按钮点击调用 `triggerRecrawl()`，传入对应的 `account_id, level, room_id, api_type, target_date, batch_id`
4. 页面底部新增补采任务面板，调用 `fetchRecrawlTasks({ account_id })` 展示状态
5. 按钮点击后 loading 状态 + 成功/失败 toast 反馈

- [ ] **Step 2: 构建测试**

Run: `cd live_dp/monitor/frontend && npm run build`
Expected: 构建成功

- [ ] **Step 3: 提交**

```bash
git add live_dp/monitor/frontend/src/views/AccountDetail.vue
git commit -m "feat(monitor): AccountDetail 增强（补采按钮 + 任务面板）"
```

---

## Chunk 6: 收尾

### Task 15: 更新 GitHub Issue + 运行全部测试

- [ ] **Step 1: 运行全部后端测试**

Run: `cd live_dp && python -m pytest tests/monitor/ -v`
Expected: 全部 PASS

- [ ] **Step 2: 构建前端**

Run: `cd live_dp/monitor/frontend && npm run build`
Expected: 构建成功

- [ ] **Step 3: 在 GitHub Issue #7 中补充说明**

```bash
gh issue comment 7 --body "补采执行器框架已搭建。HTTP 请求具体实现（cookies 获取、API 参数构造）为后续优化项，当前版本已预留接口（executor.py:fetch_api_data）。代理 IP 获取已实现，通过 AdsPower V2 API 读取 user_proxy_config。"
```

- [ ] **Step 4: 更新 memory-bank/architecture.md**

新增补采模块相关的文件说明和架构描述。

- [ ] **Step 5: 最终提交**

```bash
git add -A
git commit -m "docs: 更新架构文档，补充补采模块说明"
```
