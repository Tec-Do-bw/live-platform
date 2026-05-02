# 直播场次级采集完整性监控 实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现三级监控体系（账号级 + 日期级 + 直播间级），让面板一眼看到每场直播、每天的关键数据是否采集齐全。

**Architecture:** 新增 `room_sessions` 和 `daily_collection_status` 两张表存储直播场次和日期级采集状态。改造 `registry.py` 为三层注册表（account/daily/room），重构 `AccountDetail` API 返回三级数据。前端根据 registry 动态渲染表格列头，后续新增指标只需注册即可。

**Tech Stack:** Python 3.12 / FastAPI / SQLite / Vue3 + Element Plus / pytest

**Spec:** `docs/superpowers/specs/2026-03-14-room-level-completeness-monitor-design.md`

---

## Chunk 1: 后端数据层 + Registry 改造

### Task 1: 新增 room_sessions 和 daily_collection_status 表

**Files:**
- Modify: `live_dp/monitor/db.py:27-70` (init_db 函数)
- Test: `live_dp/tests/monitor/test_db.py`

- [ ] **Step 1: 写失败测试 — 验证新表存在**

```python
# tests/monitor/test_db.py — 追加测试

def test_init_db_creates_room_sessions_table():
    """room_sessions 表应被创建"""
    from monitor.db import get_connection, init_db
    conn = get_connection(':memory:')
    init_db(conn)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='room_sessions'"
    ).fetchone()
    assert row is not None


def test_init_db_creates_daily_collection_status_table():
    """daily_collection_status 表应被创建"""
    from monitor.db import get_connection, init_db
    conn = get_connection(':memory:')
    init_db(conn)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_collection_status'"
    ).fetchone()
    assert row is not None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_db.py::test_init_db_creates_room_sessions_table tests/monitor/test_db.py::test_init_db_creates_daily_collection_status_table -v`
Expected: FAIL — 表不存在

- [ ] **Step 3: 在 db.py 的 init_db 中添加建表语句**

在 `live_dp/monitor/db.py` 的 `init_db()` 函数中，`conn.commit()` 之前追加两张新表的 SQL：

```python
        CREATE TABLE IF NOT EXISTS room_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            room_id TEXT NOT NULL,
            start_time INTEGER DEFAULT 0,
            end_time INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(batch_id, account_id, room_id),
            FOREIGN KEY (batch_id) REFERENCES collection_batches(batch_id)
        );
        CREATE INDEX IF NOT EXISTS idx_rooms_batch_account
            ON room_sessions(batch_id, account_id);

        CREATE TABLE IF NOT EXISTS daily_collection_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            target_date TEXT NOT NULL,
            api_type TEXT NOT NULL,
            status TEXT DEFAULT 'success',
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(batch_id, account_id, target_date, api_type),
            FOREIGN KEY (batch_id) REFERENCES collection_batches(batch_id)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_batch_account
            ON daily_collection_status(batch_id, account_id);
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd live_dp && python -m pytest tests/monitor/test_db.py -v`
Expected: 全部 PASS（包括原有的 2 个测试 + 新增 2 个测试）

- [ ] **Step 5: 提交**

```bash
cd live_dp
git add monitor/db.py tests/monitor/test_db.py
git commit -m "feat(monitor): 新增 room_sessions 和 daily_collection_status 表"
```

---

### Task 2: 改造 Registry 为三层注册表

**Files:**
- Modify: `live_dp/monitor/registry.py`
- Modify: `live_dp/tests/monitor/test_registry.py`

- [ ] **Step 1: 写失败测试 — 验证三层结构和新函数**

```python
# tests/monitor/test_registry.py — 追加测试

from monitor.registry import (
    get_expected_account_types,
    get_expected_room_types,
    get_expected_daily_types,
    get_registry_for_api,
    API_TYPE_REGISTRY,
)


def test_daily_types_includes_live_stats():
    """日期级注册表应包含 live_stats"""
    types = get_expected_daily_types()
    assert 'live_stats' in types


def test_registry_has_three_levels():
    """注册表应包含 account / daily / room 三层"""
    assert 'account' in API_TYPE_REGISTRY
    assert 'daily' in API_TYPE_REGISTRY
    assert 'room' in API_TYPE_REGISTRY


def test_get_registry_for_api_returns_all_levels():
    """get_registry_for_api 应返回三层数据供前端使用"""
    result = get_registry_for_api()
    assert 'account_types' in result
    assert 'daily_types' in result
    assert 'room_types' in result
    # 每项包含 key 和 label
    for item in result['account_types']:
        assert 'key' in item
        assert 'label' in item
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_registry.py -v`
Expected: FAIL — `get_expected_daily_types` 和 `get_registry_for_api` 不存在

- [ ] **Step 3: 改造 registry.py**

将 `API_TYPE_REGISTRY` 从 `dict[str, list[str]]` 改为 `dict[str, list[dict]]` 三层结构：

```python
"""API 类型注册表 — 定义完整性监控的期望 API 列表

扩展方式：在对应层级中添加 {'key': '...', 'label': '...'} 即可。
前端通过 /api/registry 获取注册表，动态渲染列头，无需改前端代码。
"""

API_TYPE_REGISTRY: dict[str, list[dict]] = {
    # 账号级（每个账号采集一次）
    'account': [
        {'key': 'live_list', 'label': '直播间列表'},
        {'key': 'replay_info', 'label': '直播回放列表'},
    ],
    # 日期级（每个账号 × 每天一条）
    'daily': [
        {'key': 'live_stats', 'label': '关键指标(按天)'},
    ],
    # 直播间级（每个 room_id 都需要）
    'room': [
        {'key': 'trend_gmv', 'label': 'GMV趋势'},
        {'key': 'trend_stats', 'label': '直播趋势'},
    ],
}


def get_expected_account_types() -> list[str]:
    """返回账号级期望 api_type 列表"""
    return [item['key'] for item in API_TYPE_REGISTRY['account']]


def get_expected_daily_types() -> list[str]:
    """返回日期级期望 api_type 列表"""
    return [item['key'] for item in API_TYPE_REGISTRY['daily']]


def get_expected_room_types() -> list[str]:
    """返回直播间级期望 api_type 列表"""
    return [item['key'] for item in API_TYPE_REGISTRY['room']]


def get_registry_for_api() -> dict:
    """返回完整注册表供前端 /api/registry 使用"""
    return {
        'account_types': API_TYPE_REGISTRY['account'],
        'daily_types': API_TYPE_REGISTRY['daily'],
        'room_types': API_TYPE_REGISTRY['room'],
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd live_dp && python -m pytest tests/monitor/test_registry.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 运行全部监控测试确认无回归**

Run: `cd live_dp && python -m pytest tests/monitor/ -v`
Expected: 全部 PASS（注意：accounts.py 中的 `get_expected_account_types()` / `get_expected_room_types()` 返回值类型不变，仍为 `list[str]`，不会回归）

- [ ] **Step 6: 提交**

```bash
cd live_dp
git add monitor/registry.py tests/monitor/test_registry.py
git commit -m "feat(monitor): 改造 Registry 为三层注册表（account/daily/room）"
```

---

### Task 3: Tracker 新增 _insert_room_session + record_daily_stats + extract_target_date

**Files:**
- Modify: `live_dp/monitor/tracker.py`
- Modify: `live_dp/tests/monitor/test_tracker.py`

- [ ] **Step 1: 写失败测试 — _insert_room_session**

```python
# tests/monitor/test_tracker.py — 追加到文件末尾

class TestInsertRoomSession:
    def test_insert_room_session_basic(self, monitor):
        """_insert_room_session 应写入 room_sessions 表"""
        monitor.start_batch('b1', 'once')
        monitor._insert_room_session('b1', 'acc1', 'room1', 1710403200, 1710417600)

        row = monitor._conn.execute(
            "SELECT * FROM room_sessions WHERE room_id='room1'"
        ).fetchone()
        assert row is not None
        assert row['batch_id'] == 'b1'
        assert row['account_id'] == 'acc1'
        assert row['start_time'] == 1710403200
        assert row['end_time'] == 1710417600

    def test_insert_room_session_duplicate_ignored(self, monitor):
        """重复写入同一 room 应不报错（UNIQUE 约束用 INSERT OR IGNORE）"""
        monitor.start_batch('b1', 'once')
        monitor._insert_room_session('b1', 'acc1', 'room1', 100, 200)
        monitor._insert_room_session('b1', 'acc1', 'room1', 100, 200)

        rows = monitor._conn.execute(
            "SELECT * FROM room_sessions WHERE room_id='room1'"
        ).fetchall()
        assert len(rows) == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py::TestInsertRoomSession -v`
Expected: FAIL — `_insert_room_session` 不存在

- [ ] **Step 3: 实现 _insert_room_session**

在 `tracker.py` 的 `CollectionMonitor` 类中添加：

```python
    def _insert_room_session(self, batch_id: str, account_id: str,
                             room_id: str, start_time: int = 0,
                             end_time: int = 0):
        """写入直播场次到 room_sessions 表"""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO room_sessions "
                "(batch_id, account_id, room_id, start_time, end_time) "
                "VALUES (?, ?, ?, ?, ?)",
                (batch_id, account_id, room_id, start_time, end_time)
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'写入直播场次失败: {e}')
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py::TestInsertRoomSession -v`
Expected: PASS

- [ ] **Step 5: 写失败测试 — record_rooms 改造（写入 room_sessions）**

```python
class TestRecordRoomsV2:
    def test_record_rooms_writes_room_sessions(self, monitor):
        """record_rooms 应同时写入 room_sessions 表"""
        monitor.start_batch('b1', 'once')
        rooms = [
            {'room_id': 'r1', 'room_name': 'SALE', 'live_start_ts': 1000, 'live_end_ts': 2000},
            {'room_id': 'r2', 'room_name': 'LIVE', 'live_start_ts': 3000, 'live_end_ts': 4000},
        ]
        monitor.record_rooms('b1', 'acc1', rooms)

        sessions = monitor._conn.execute(
            "SELECT * FROM room_sessions WHERE batch_id='b1' ORDER BY room_id"
        ).fetchall()
        assert len(sessions) == 2
        assert sessions[0]['room_id'] == 'r1'
        assert sessions[0]['start_time'] == 1000
        assert sessions[1]['room_id'] == 'r2'
        assert sessions[1]['start_time'] == 3000

    def test_record_rooms_still_records_live_list(self, monitor):
        """record_rooms 改造后仍应记录 live_list 的 collection_record"""
        monitor.start_batch('b1', 'once')
        rooms = [{'room_id': 'r1', 'room_name': 'X'}]
        monitor.record_rooms('b1', 'acc1', rooms)

        row = monitor._conn.execute(
            "SELECT * FROM collection_records WHERE api_type='live_list'"
        ).fetchone()
        assert row is not None
        assert row['status'] == 'success'

    def test_record_rooms_empty_list(self, monitor):
        """空 rooms_data 仍应记录 live_list 成功状态"""
        monitor.start_batch('b1', 'once')
        monitor.record_rooms('b1', 'acc1', [])

        row = monitor._conn.execute(
            "SELECT * FROM collection_records WHERE api_type='live_list'"
        ).fetchone()
        assert row is not None
        assert row['status'] == 'success'

        sessions = monitor._conn.execute(
            "SELECT * FROM room_sessions WHERE batch_id='b1'"
        ).fetchall()
        assert len(sessions) == 0
```

- [ ] **Step 6: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py::TestRecordRoomsV2 -v`
Expected: FAIL — record_rooms 不写 room_sessions

- [ ] **Step 7: 改造 record_rooms 方法**

替换 `tracker.py` 中的 `record_rooms` 方法：

```python
    def record_rooms(self, batch_id: str, account_id: str, rooms_data: list[dict]):
        """记录 live_list 响应，解析直播场次写入 room_sessions

        即使 rooms_data 为空列表，也记录 live_list 的采集状态为 success。
        """
        # 1. 记录 live_list API 本身的采集状态
        self.record(batch_id=batch_id, account_id=account_id,
                    api_type='live_list', status='success',
                    response_size=len(rooms_data),
                    extra_data={'rooms': rooms_data})

        # 2. 解析每个 room，写入 room_sessions
        for room in rooms_data:
            self._insert_room_session(
                batch_id, account_id,
                room_id=str(room.get('room_id', '')),
                start_time=room.get('live_start_ts', 0),
                end_time=room.get('live_end_ts', 0),
            )
```

- [ ] **Step 8: 运行测试确认通过**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py::TestRecordRoomsV2 tests/monitor/test_tracker.py::TestRecordRooms -v`
Expected: 全部 PASS（新旧测试都通过）

- [ ] **Step 9: 写失败测试 — record_daily_stats**

```python
class TestRecordDailyStats:
    def test_record_daily_stats_basic(self, monitor):
        """record_daily_stats 应写入 daily_collection_status 表"""
        monitor.start_batch('b1', 'once')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'success')

        row = monitor._conn.execute(
            "SELECT * FROM daily_collection_status "
            "WHERE batch_id='b1' AND target_date='2026-03-12'"
        ).fetchone()
        assert row is not None
        assert row['api_type'] == 'live_stats'
        assert row['status'] == 'success'

    def test_record_daily_stats_upsert(self, monitor):
        """重复写入应更新状态"""
        monitor.start_batch('b1', 'once')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'failed')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'success')

        rows = monitor._conn.execute(
            "SELECT * FROM daily_collection_status "
            "WHERE batch_id='b1' AND target_date='2026-03-12'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]['status'] == 'success'

    def test_record_daily_stats_multiple_dates(self, monitor):
        """应支持同一账号多天记录"""
        monitor.start_batch('b1', 'once')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-13')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-14')

        rows = monitor._conn.execute(
            "SELECT * FROM daily_collection_status WHERE batch_id='b1' ORDER BY target_date"
        ).fetchall()
        assert len(rows) == 3
```

- [ ] **Step 10: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py::TestRecordDailyStats -v`
Expected: FAIL — `record_daily_stats` 不存在

- [ ] **Step 11: 实现 record_daily_stats**

在 `tracker.py` 的 `CollectionMonitor` 类中添加：

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
            self._conn.execute(
                "INSERT OR REPLACE INTO daily_collection_status "
                "(batch_id, account_id, target_date, api_type, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (batch_id, account_id, target_date, api_type, status)
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录日期级采集状态失败: {e}')
```

- [ ] **Step 12: 运行测试确认通过**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py::TestRecordDailyStats -v`
Expected: PASS

- [ ] **Step 13: 写失败测试 — extract_target_date**

```python
from monitor.tracker import extract_target_date


class TestExtractTargetDate:
    def test_extract_from_valid_request_body(self):
        """从标准 live/stats 请求体中提取 target_date"""
        body = {
            'request': {
                'params': [{
                    'time_selector': {
                        'start_timestamp': 1710201600,  # 2024-03-12 00:00:00 UTC
                        'end_timestamp': 1710374400,    # 2024-03-14 00:00:00 UTC
                    }
                }]
            }
        }
        result = extract_target_date(body)
        assert result == '2024-03-13'  # start + 1 天

    def test_extract_returns_none_for_empty_body(self):
        """空请求体应返回 None"""
        assert extract_target_date({}) is None

    def test_extract_returns_none_for_missing_params(self):
        """缺少 params 应返回 None"""
        body = {'request': {}}
        assert extract_target_date(body) is None

    def test_extract_returns_none_for_zero_timestamp(self):
        """timestamp 为 0 应返回 None"""
        body = {
            'request': {
                'params': [{
                    'time_selector': {'start_timestamp': 0}
                }]
            }
        }
        assert extract_target_date(body) is None
```

- [ ] **Step 14: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py::TestExtractTargetDate -v`
Expected: FAIL — `extract_target_date` 不存在

- [ ] **Step 15: 实现 extract_target_date**

先在 `tracker.py` 顶部扩展已有的 datetime import：

```python
# 将 tracker.py 第 7 行的
from datetime import datetime
# 改为
from datetime import datetime, timedelta, timezone
```

然后在 `tracker.py` 中添加模块级函数（放在 `CollectionMonitor` 类之前或之后均可）：

```python
def extract_target_date(request_body: dict) -> str | None:
    """从 live/stats 请求体中提取目标日期

    payload 结构：request.params[0].time_selector.start_timestamp
    target_date = start + 1天（因为 start 是 D-1 的 UTC 00:00）
    """
    try:
        params = request_body.get('request', {}).get('params', [])
        if not params:
            return None
        time_selector = params[0].get('time_selector', {})
        start_ts = time_selector.get('start_timestamp', 0)
        if not start_ts:
            return None
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        target_dt = start_dt + timedelta(days=1)
        return target_dt.strftime('%Y-%m-%d')
    except Exception:
        return None
```

- [ ] **Step 16: 运行测试确认通过**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py::TestExtractTargetDate -v`
Expected: PASS

- [ ] **Step 17: 运行全部 tracker 测试确认无回归**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py -v`
Expected: 全部 PASS

- [ ] **Step 18: 提交**

```bash
cd live_dp
git add monitor/tracker.py tests/monitor/test_tracker.py
git commit -m "feat(monitor): Tracker 新增 room_sessions 写入、日期级记录、target_date 解析"
```

---

## Chunk 2: 后端 API 层

### Task 4: 新增 /api/registry 路由

**Files:**
- Create: `live_dp/monitor/api/registry_routes.py`
- Modify: `live_dp/monitor/server.py:15-22`
- Create: `live_dp/tests/monitor/test_api_registry.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/monitor/test_api_registry.py

from fastapi.testclient import TestClient
from monitor.server import app


client = TestClient(app)


def test_registry_endpoint_returns_three_levels():
    """/api/registry 应返回 account_types / daily_types / room_types"""
    resp = client.get('/api/registry')
    assert resp.status_code == 200
    data = resp.json()
    assert 'account_types' in data
    assert 'daily_types' in data
    assert 'room_types' in data


def test_registry_endpoint_items_have_key_and_label():
    """每项应包含 key 和 label"""
    resp = client.get('/api/registry')
    data = resp.json()
    for item in data['account_types']:
        assert 'key' in item
        assert 'label' in item
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_api_registry.py -v`
Expected: FAIL — 404（路由不存在）

- [ ] **Step 3: 创建 registry_routes.py**

```python
"""注册表 API 路由 — 提供前端所需的 API 类型注册信息"""

from fastapi import APIRouter
from monitor.registry import get_registry_for_api

router = APIRouter(prefix="/api", tags=["registry"])


@router.get("/registry")
def get_registry():
    """返回三层 API 类型注册表，供前端动态渲染列头"""
    return get_registry_for_api()
```

- [ ] **Step 4: 在 server.py 中注册路由**

在 `server.py` 的 import 区域添加：
```python
from monitor.api.registry_routes import router as registry_router
```

在路由注册区域添加：
```python
app.include_router(registry_router)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd live_dp && python -m pytest tests/monitor/test_api_registry.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
cd live_dp
git add monitor/api/registry_routes.py monitor/server.py tests/monitor/test_api_registry.py
git commit -m "feat(monitor): 新增 /api/registry 路由，返回三层注册表"
```

---

### Task 5: 重构 AccountDetail API — 返回三级数据

**Files:**
- Modify: `live_dp/monitor/api/accounts.py`
- Create: `live_dp/tests/monitor/test_api_account_detail.py`

- [ ] **Step 1: 写失败测试 — 新路由返回三级数据**

```python
# tests/monitor/test_api_account_detail.py

import json
import pytest
from fastapi.testclient import TestClient
from monitor.server import app
from monitor.tracker import CollectionMonitor
from monitor.db import get_connection, init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_data(monkeypatch):
    """为每个测试注入内存数据库中的测试数据"""
    conn = get_connection(':memory:')
    init_db(conn)

    # 让 accounts.py 中的 _get_conn() 使用测试连接
    monkeypatch.setattr('monitor.api.accounts._get_conn', lambda: conn)

    # 使用内存数据库创建 monitor 实例
    monitor = CollectionMonitor(db_path=':memory:')
    # 替换其连接为已初始化的测试连接
    monitor._conn = conn

    # 准备测试数据
    monitor.start_batch('b1', 'once')
    monitor.start_account('b1', 'acc1', '印尼团队-tiktok')

    # live_list + room_sessions
    monitor.record_rooms('b1', 'acc1', [
        {'room_id': 'r1', 'room_name': 'SALE', 'live_start_ts': 1000, 'live_end_ts': 2000},
        {'room_id': 'r2', 'room_name': 'LIVE', 'live_start_ts': 3000, 'live_end_ts': 4000},
    ])
    monitor.record('b1', 'acc1', 'replay_info', status='success')

    # room 级记录
    monitor.record('b1', 'acc1', 'trend_gmv', room_id='r1', status='success')
    monitor.record('b1', 'acc1', 'trend_stats', room_id='r1', status='success')
    monitor.record('b1', 'acc1', 'trend_gmv', room_id='r2', status='success')
    # r2 的 trend_stats 缺失

    # 日期级记录
    monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'success')
    monitor.record_daily_stats('b1', 'acc1', '2026-03-13', 'live_stats', 'success')
    # 2026-03-14 缺失

    monitor.finish_account('b1', 'acc1', 'success')
    monitor.finish_batch('b1')

    return conn


def test_account_detail_has_three_sections():
    """账号详情 API 应返回 account_indicators + daily_stats + rooms"""
    resp = client.get('/api/batches/b1/accounts/acc1')
    assert resp.status_code == 200
    data = resp.json()
    assert 'account_indicators' in data
    assert 'daily_stats' in data
    assert 'rooms' in data


def test_account_detail_account_indicators():
    """account_indicators 应包含账号级 API 状态"""
    resp = client.get('/api/batches/b1/accounts/acc1')
    data = resp.json()
    indicators = data['account_indicators']
    assert indicators['live_list']['status'] == 'success'
    assert indicators['replay_info']['status'] == 'success'


def test_account_detail_daily_stats():
    """daily_stats 应包含日期级采集状态"""
    resp = client.get('/api/batches/b1/accounts/acc1')
    data = resp.json()
    daily = data['daily_stats']
    assert len(daily) >= 2
    # 检查已采集的日期
    dates = {d['target_date']: d for d in daily}
    assert dates['2026-03-12']['live_stats']['status'] == 'success'
    assert dates['2026-03-13']['live_stats']['status'] == 'success'


def test_account_detail_rooms():
    """rooms 应包含直播间级指标和完整率"""
    resp = client.get('/api/batches/b1/accounts/acc1')
    data = resp.json()
    rooms = data['rooms']
    assert len(rooms) == 2

    # 找到 r1（完整）和 r2（不完整）
    rooms_map = {r['room_id']: r for r in rooms}
    assert rooms_map['r1']['indicators']['trend_gmv']['status'] == 'success'
    assert rooms_map['r1']['indicators']['trend_stats']['status'] == 'success'
    assert rooms_map['r1']['completeness'] == 1.0

    assert rooms_map['r2']['indicators']['trend_gmv']['status'] == 'success'
    assert rooms_map['r2']['indicators']['trend_stats']['status'] is None
    assert rooms_map['r2']['completeness'] == 0.5


def test_account_detail_overall_completeness():
    """overall_completeness 应为所有 room 完整率的平均值"""
    resp = client.get('/api/batches/b1/accounts/acc1')
    data = resp.json()
    # r1 = 1.0, r2 = 0.5 → average = 0.75
    assert data['overall_completeness'] == 0.75
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd live_dp && python -m pytest tests/monitor/test_api_account_detail.py -v`
Expected: FAIL — 路由不存在（当前只有 `/api/accounts/{account_id}/rooms`，没有 `/api/batches/{batch_id}/accounts/{account_id}`）

- [ ] **Step 3: 在 accounts.py 中新增账号详情路由**

在 `accounts.py` 中添加新路由。同时更新 import（文件顶部已有 `import json`，只需扩展 registry import）：

```python
from monitor.registry import (
    get_expected_account_types,
    get_expected_room_types,
    get_expected_daily_types,
)
```

新增路由函数：

```python
@router.get("/batches/{batch_id}/accounts/{account_id}")
def get_account_detail(batch_id: str, account_id: str):
    """获取账号的三级采集详情：账号级 + 日期级 + 直播间级"""
    conn = _get_conn()
    expected_account = get_expected_account_types()
    expected_daily = get_expected_daily_types()
    expected_room = get_expected_room_types()

    # 1. 账号级指标
    account_records = conn.execute(
        "SELECT api_type, status, collected_at FROM collection_records "
        "WHERE batch_id=? AND account_id=? AND room_id=''",
        (batch_id, account_id)
    ).fetchall()
    api_map = {r['api_type']: {'status': r['status'], 'collected_at': r['collected_at']}
               for r in account_records}
    account_indicators = {
        t: api_map.get(t, {'status': None, 'collected_at': None})
        for t in expected_account
    }

    # 2. 日期级指标
    daily_records = conn.execute(
        "SELECT target_date, api_type, status FROM daily_collection_status "
        "WHERE batch_id=? AND account_id=? ORDER BY target_date",
        (batch_id, account_id)
    ).fetchall()
    # 按日期分组
    daily_map: dict[str, dict[str, dict]] = {}
    for r in daily_records:
        date = r['target_date']
        if date not in daily_map:
            daily_map[date] = {}
        daily_map[date][r['api_type']] = {'status': r['status']}
    daily_stats = []
    for date in sorted(daily_map.keys()):
        entry = {'target_date': date}
        for t in expected_daily:
            entry[t] = daily_map[date].get(t, {'status': None})
        daily_stats.append(entry)

    # 3. 直播间级指标（从 room_sessions 获取应采列表）
    room_sessions = conn.execute(
        "SELECT room_id, start_time, end_time FROM room_sessions "
        "WHERE batch_id=? AND account_id=? ORDER BY start_time DESC",
        (batch_id, account_id)
    ).fetchall()

    room_records = conn.execute(
        "SELECT room_id, api_type, status FROM collection_records "
        "WHERE batch_id=? AND account_id=? AND room_id != ''",
        (batch_id, account_id)
    ).fetchall()
    # 按 room_id 分组
    room_api_map: dict[str, dict[str, str]] = {}
    for r in room_records:
        rid = r['room_id']
        if rid not in room_api_map:
            room_api_map[rid] = {}
        room_api_map[rid][r['api_type']] = r['status']

    # 从 live_list 的 extra_data 中提取 GMV 数据
    live_list_row = conn.execute(
        "SELECT extra_data FROM collection_records "
        "WHERE batch_id=? AND account_id=? AND api_type='live_list'",
        (batch_id, account_id)
    ).fetchone()
    rooms_gmv: dict[str, dict] = {}
    if live_list_row and live_list_row['extra_data']:
        try:
            data = json.loads(live_list_row['extra_data'])
            for r in data.get('rooms', []):
                rooms_gmv[str(r.get('room_id', ''))] = r
        except (json.JSONDecodeError, TypeError):
            pass

    rooms = []
    completeness_list = []
    for rs in room_sessions:
        rid = rs['room_id']
        apis = room_api_map.get(rid, {})
        gmv = rooms_gmv.get(rid, {})
        indicators = {}
        hit = 0
        for t in expected_room:
            status = apis.get(t)
            indicators[t] = {'status': status}
            if status == 'success':
                hit += 1
        comp = hit / len(expected_room) if expected_room else 1.0
        completeness_list.append(comp)
        rooms.append({
            'room_id': rid,
            'start_time': rs['start_time'],
            'end_time': rs['end_time'],
            'room_name': gmv.get('room_name', ''),
            'revenue': gmv.get('revenue', '0'),
            'currency_code': gmv.get('currency_code', ''),
            'item_sold_cnt': gmv.get('item_sold_cnt', 0),
            'view_cnt': gmv.get('view_cnt', 0),
            'indicators': indicators,
            'completeness': comp,
        })

    # 4. 总完整率
    overall = sum(completeness_list) / len(completeness_list) if completeness_list else 1.0

    return {
        'account_id': account_id,
        'batch_id': batch_id,
        'account_indicators': account_indicators,
        'daily_stats': daily_stats,
        'rooms': rooms,
        'overall_completeness': overall,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd live_dp && python -m pytest tests/monitor/test_api_account_detail.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 运行全部监控测试确认无回归**

Run: `cd live_dp && python -m pytest tests/monitor/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
cd live_dp
git add monitor/api/accounts.py tests/monitor/test_api_account_detail.py
git commit -m "feat(monitor): 新增账号详情 API，返回三级采集状态"
```

---

## Chunk 3: 前端重构 + Mock 数据 + 爬虫集成

### Task 6: 前端 API 层 — 新增 fetchRegistry / fetchAccountDetail

**Files:**
- Modify: `live_dp/monitor/frontend/src/api/index.js`

- [ ] **Step 1: 添加两个新 API 调用**

```javascript
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const fetchBatches = (limit = 20) => api.get('/batches', { params: { limit } })
export const fetchAccounts = (batchId) => api.get(`/batches/${batchId}/accounts`)
export const fetchRooms = (accountId, batchId) => api.get(`/accounts/${accountId}/rooms`, { params: { batch_id: batchId } })
export const fetchRegistry = () => api.get('/registry')
export const fetchAccountDetail = (batchId, accountId) => api.get(`/batches/${batchId}/accounts/${accountId}`)
```

- [ ] **Step 2: 提交**

```bash
cd live_dp
git add monitor/frontend/src/api/index.js
git commit -m "feat(monitor): 前端新增 fetchRegistry / fetchAccountDetail API"
```

---

### Task 7: 重构 AccountDetail.vue — 三段式布局

**Files:**
- Modify: `live_dp/monitor/frontend/src/views/AccountDetail.vue`

- [ ] **Step 1: 重写 AccountDetail.vue**

完整替换 `AccountDetail.vue` 为三段式布局（账号级 + 日期级 + 直播间级）。

关键改动：
1. 从 `fetchAccountDetail(batchId, accountId)` 获取三级数据（替代原来的 `fetchRooms`）
2. 从 `fetchRegistry()` 获取列头定义
3. 新增「账号级指标」section — 水平排列 tag 式状态
4. 新增「日期级指标」section — 日期 × api_type 矩阵表格
5. 改造「直播场次」section — 使用 room_sessions 数据 + indicators 矩阵

```vue
<template>
  <div class="account-detail">
    <!-- 顶部导航 -->
    <div class="detail-header">
      <button class="back-btn" @click="$router.push('/')">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        <span>返回总览</span>
      </button>
      <div class="detail-title">
        <span class="title-label">ACCOUNT</span>
        <h2 class="title-id">{{ accountId }}</h2>
      </div>
    </div>

    <!-- 数据概览卡片 -->
    <div class="overview-strip" v-if="detail">
      <div class="ov-card">
        <span class="ov-val">{{ detail.rooms.length }}</span>
        <span class="ov-label">直播场次</span>
      </div>
      <div class="ov-card">
        <span class="ov-val" :style="{ color: completenessColor }">
          {{ Math.round(detail.overall_completeness * 100) }}%
        </span>
        <span class="ov-label">直播间完整率</span>
      </div>
      <div class="ov-card">
        <span class="ov-val">{{ totalGMV }}</span>
        <span class="ov-label">总 GMV</span>
      </div>
    </div>

    <!-- 账号级指标 -->
    <div class="section" v-if="detail">
      <h3 class="section-title">账号级指标</h3>
      <div class="indicator-row">
        <div
          v-for="t in (registry.account_types || [])"
          :key="t.key"
          class="indicator-tag"
          :class="'tag-' + getStatus(detail.account_indicators[t.key])"
        >
          <svg v-if="getStatus(detail.account_indicators[t.key]) === 'success'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3">
            <path d="M20 6L9 17l-5-5"/>
          </svg>
          <svg v-else-if="getStatus(detail.account_indicators[t.key]) === 'failed' || getStatus(detail.account_indicators[t.key]) === 'empty'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3">
            <path d="M12 9v4M12 17h.01"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
          <span class="tag-label">{{ t.label }}</span>
        </div>
      </div>
    </div>

    <!-- 日期级指标 -->
    <div class="section" v-if="detail && detail.daily_stats.length">
      <h3 class="section-title">日期级指标（按天采集状态）</h3>
      <div class="daily-table-wrap">
        <table class="daily-table">
          <thead>
            <tr>
              <th></th>
              <th v-for="day in detail.daily_stats" :key="day.target_date">
                {{ formatDate(day.target_date) }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in (registry.daily_types || [])" :key="t.key">
              <td class="daily-label">{{ t.label }}</td>
              <td
                v-for="day in detail.daily_stats"
                :key="day.target_date"
                class="daily-cell"
                :class="'cell-' + getStatus(day[t.key])"
              >
                <svg v-if="getStatus(day[t.key]) === 'success'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3">
                  <path d="M20 6L9 17l-5-5"/>
                </svg>
                <svg v-else-if="getStatus(day[t.key]) === 'failed' || getStatus(day[t.key]) === 'empty'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3">
                  <path d="M12 9v4M12 17h.01"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3">
                  <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 直播场次列表 -->
    <div class="section" v-if="detail">
      <div class="section-header">
        <h3 class="section-title">直播场次列表</h3>
        <div class="type-legend">
          <span class="legend-item" v-for="t in (registry.room_types || [])" :key="t.key">{{ t.label }}</span>
        </div>
      </div>

      <div class="room-list">
        <div
          v-for="(room, idx) in detail.rooms"
          :key="room.room_id"
          class="room-row"
          :style="{ animationDelay: idx * 40 + 'ms' }"
        >
          <div class="room-info">
            <div class="room-title-line">
              <span class="room-name" :title="room.room_name">{{ room.room_name || '未命名直播' }}</span>
              <span class="room-id">{{ room.room_id }}</span>
              <span class="room-completeness" :style="{ color: roomCompColor(room.completeness) }">
                {{ Math.round(room.completeness * 100) }}%
              </span>
            </div>
            <div class="room-meta">
              <span class="meta-item">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
                </svg>
                {{ formatTimestamp(room.start_time) }}
              </span>
              <span class="meta-item" v-if="room.end_time">
                {{ formatDuration(room.start_time, room.end_time) }}
              </span>
              <span class="meta-item gmv" v-if="Number(room.revenue)">
                {{ room.currency_code }} {{ Number(room.revenue).toLocaleString() }}
              </span>
              <span class="meta-item" v-if="room.item_sold_cnt">
                {{ room.item_sold_cnt }} 单
              </span>
              <span class="meta-item" v-if="room.view_cnt">
                {{ room.view_cnt }} 观看
              </span>
            </div>
          </div>

          <div class="api-matrix">
            <div
              v-for="t in (registry.room_types || [])"
              :key="t.key"
              class="api-cell"
              :class="'cell-' + getStatus(room.indicators[t.key])"
              :title="t.label + ': ' + getStatus(room.indicators[t.key])"
            >
              <svg v-if="getStatus(room.indicators[t.key]) === 'success'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              <svg v-else-if="getStatus(room.indicators[t.key]) === 'failed'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3">
                <path d="M5 12h14"/>
              </svg>
            </div>
          </div>
        </div>
      </div>

      <div v-if="detail.rooms.length === 0 && !loading" class="empty-rooms">
        <p>该批次下无直播间数据</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { fetchAccountDetail, fetchRegistry } from '../api'

const props = defineProps({ accountId: String })
const route = useRoute()
const detail = ref(null)
const registry = ref({})
const loading = ref(true)

onMounted(async () => {
  const batchId = route.query.batch_id
  if (!batchId) { loading.value = false; return }
  try {
    const [detailRes, registryRes] = await Promise.all([
      fetchAccountDetail(batchId, props.accountId),
      fetchRegistry(),
    ])
    detail.value = detailRes.data
    registry.value = registryRes.data
  } finally {
    loading.value = false
  }
})

const completenessColor = computed(() => {
  if (!detail.value) return ''
  const pct = detail.value.overall_completeness * 100
  if (pct >= 90) return 'var(--accent-green)'
  if (pct >= 50) return 'var(--accent-amber)'
  return 'var(--accent-red)'
})

function roomCompColor(comp) {
  const pct = comp * 100
  if (pct >= 90) return 'var(--accent-green)'
  if (pct >= 50) return 'var(--accent-amber)'
  return 'var(--accent-red)'
}

const totalGMV = computed(() => {
  if (!detail.value || !detail.value.rooms.length) return '-'
  const currencies = {}
  for (const r of detail.value.rooms) {
    const code = r.currency_code || 'USD'
    currencies[code] = (currencies[code] || 0) + Number(r.revenue || 0)
  }
  const parts = Object.entries(currencies)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => `${k} ${v.toLocaleString()}`)
  return parts.join(' / ') || '-'
})

function getStatus(indicator) {
  if (!indicator || indicator.status === null || indicator.status === undefined) return 'missing'
  return indicator.status
}

function formatDate(dateStr) {
  // 'YYYY-MM-DD' → 'MM-DD'
  return dateStr ? dateStr.slice(5) : ''
}

function formatTimestamp(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
  })
}

function formatDuration(start, end) {
  if (!start || !end) return ''
  const minutes = Math.round((end - start) / 60)
  if (minutes < 60) return `${minutes}分钟`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${h}时${m}分`
}
</script>
```

样式部分保留原有的暗色主题样式，新增：

```css
/* 保留原有 header / overview-strip / room-list 等样式 */
/* 新增以下样式 */

.section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

/* 账号级指标标签 */
.indicator-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.indicator-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
}

.tag-success {
  background: rgba(16, 185, 129, 0.12);
  color: var(--accent-green);
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.tag-failed, .tag-empty {
  background: rgba(245, 158, 11, 0.12);
  color: var(--accent-amber);
  border: 1px solid rgba(245, 158, 11, 0.2);
}

.tag-missing {
  background: rgba(100, 116, 139, 0.08);
  color: var(--text-muted);
  border: 1px solid var(--border-color);
}

.tag-icon {
  font-weight: 700;
}

.tag-label {
  font-family: var(--font-mono);
  font-size: 12px;
}

/* 日期级表格 */
.daily-table-wrap {
  overflow-x: auto;
}

.daily-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.daily-table th, .daily-table td {
  padding: 10px 16px;
  text-align: center;
  border-bottom: 1px solid var(--border-color);
}

.daily-table th {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 600;
  letter-spacing: 0.5px;
}

.daily-label {
  text-align: left !important;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.daily-cell {
  font-weight: 700;
  font-size: 14px;
}

.daily-cell.cell-success { color: var(--accent-green); }
.daily-cell.cell-failed, .daily-cell.cell-empty { color: var(--accent-amber); }
.daily-cell.cell-missing { color: var(--text-muted); opacity: 0.4; }

/* room completeness */
.room-completeness {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 700;
}
```

- [ ] **Step 2: 构建前端验证无语法错误**

Run: `cd live_dp/monitor/frontend && npm run build`
Expected: 构建成功

- [ ] **Step 3: 提交**

```bash
cd live_dp
git add monitor/frontend/src/views/AccountDetail.vue
git commit -m "feat(monitor): 重构 AccountDetail 为三段式布局（账号+日期+直播间）"
```

---

### Task 8: 更新 Mock 数据脚本

**Files:**
- Modify: `live_dp/scripts/mock_monitor_data.py`

- [ ] **Step 1: 在 mock 脚本中添加 room_sessions 和 daily_stats 数据**

在 `mock_monitor_data.py` 的每个批次中，调用 `record_daily_stats` 注入日期级数据。`record_rooms` 改造后已自动写入 `room_sessions`，无需额外修改 room 数据。

追加的代码：

```python
# 在批次 1 的账号 1 数据后面添加日期级数据
monitor.record_daily_stats(BATCH_1, 'k16w3t5d', '2026-03-12', 'live_stats', 'success')
monitor.record_daily_stats(BATCH_1, 'k16w3t5d', '2026-03-13', 'live_stats', 'success')
monitor.record_daily_stats(BATCH_1, 'k16w3t5d', '2026-03-14', 'live_stats', 'failed')

# 账号 2 的日期级数据
monitor.record_daily_stats(BATCH_1, 'k1926s53', '2026-03-12', 'live_stats', 'success')
monitor.record_daily_stats(BATCH_1, 'k1926s53', '2026-03-13', 'live_stats', 'success')
monitor.record_daily_stats(BATCH_1, 'k1926s53', '2026-03-14', 'live_stats', 'empty')  # 测试 empty 状态

# 批次 2 的日期级数据
monitor.record_daily_stats(BATCH_2, 'k16w3t5d', '2026-03-07', 'live_stats', 'success')
monitor.record_daily_stats(BATCH_2, 'k16w3t5d', '2026-03-08', 'live_stats', 'success')
```

- [ ] **Step 2: 运行脚本验证无报错**

Run: `cd live_dp && python scripts/mock_monitor_data.py`
Expected: 输出「模拟数据注入完成!」

- [ ] **Step 3: 提交**

```bash
cd live_dp
git add scripts/mock_monitor_data.py
git commit -m "feat(monitor): Mock 数据新增日期级采集状态"
```

---

### Task 9: 爬虫集成 — tiktok.py 记录日期级 live/stats 采集

**Files:**
- Modify: `live_dp/spiders/tiktok.py`

> **注意：** 此任务涉及修改爬虫主流程代码。实现时需确保：
> 1. 所有 monitor 调用包裹在 try/except 中
> 2. 使用 lazy import（`from monitor import get_monitor`）
> 3. 监控失败不阻塞采集流程

- [ ] **Step 1: 确认 tiktok.py 中 live/stats 数据的处理位置**

已确认：`_handle_live_stats_injection()` 将 live/stats 注入数据直接 append 到 `collected_data` 列表中（通过引用传递）。这些数据在 `get_listened_data()` 返回后，会出现在 `visit_page_and_collect()` 的 `api_data_list` 循环中。每个 `api_data` 包含 `url`、`method`、`request`（请求体 dict）、`response` 四个 key。

- [ ] **Step 2: 在 tiktok.py 中添加日期级记录逻辑**

在 `visit_page_and_collect` 方法的主处理循环中（现有 `replay/info` 监控钩子附近，约 line 251），添加 live/stats 日期级记录：

```python
# 采集监控：记录 live/stats 日期级采集状态
if self.batch_id and 'live/stats' in api_data.get('url', ''):
    try:
        from monitor import get_monitor
        from monitor.tracker import extract_target_date
        # 注意：api_data 的请求体 key 是 'request'（不是 'request_body'）
        request_body = api_data.get('request', {})
        if isinstance(request_body, str):
            import json
            request_body = json.loads(request_body)
        target_date = extract_target_date(request_body)
        if target_date:
            get_monitor().record_daily_stats(
                self.batch_id, self.browser_id,
                target_date, 'live_stats', 'success'
            )
    except Exception:
        pass  # 监控不阻塞采集
```

> **注意：** `api_data['request']` 对于 live/stats 注入数据是 dict（由 `_generate_daily_payloads` 生成的 payload），
> 但对于正常网络拦截的数据可能是 JSON 字符串。需要兼容两种情况。

- [ ] **Step 3: 验证改动不影响现有测试**

Run: `cd live_dp && python -m pytest tests/monitor/ -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
cd live_dp
git add spiders/tiktok.py
git commit -m "feat(monitor): tiktok.py 集成日期级 live/stats 采集记录"
```

---

## 变更影响总结

| 文件 | 改动类型 | 影响范围 |
|------|---------|---------|
| `monitor/db.py` | 修改 | 新增 2 张表，不影响现有 3 张表 |
| `monitor/registry.py` | 修改 | 数据结构从 `list[str]` 改为 `list[dict]`，但返回函数签名不变 |
| `monitor/tracker.py` | 修改 | 新增 3 个方法 + 改造 `record_rooms`（向后兼容） |
| `monitor/api/accounts.py` | 修改 | 新增路由，不影响现有路由 |
| `monitor/api/registry_routes.py` | 新增 | 全新文件 |
| `monitor/server.py` | 修改 | 注册新路由，1 行改动 |
| `monitor/frontend/src/api/index.js` | 修改 | 新增 2 个 API 函数 |
| `monitor/frontend/src/views/AccountDetail.vue` | 重构 | 三段式布局替换 |
| `spiders/tiktok.py` | 修改 | 新增约 10 行监控钩子 |
| `scripts/mock_monitor_data.py` | 修改 | 新增日期级测试数据 |
| `tests/monitor/` | 新增/修改 | 4 个测试文件覆盖新功能 |

**回归风险控制：**
- `get_expected_account_types()` / `get_expected_room_types()` 返回值类型不变（仍为 `list[str]`）
- `record_rooms()` 改造后保持向后兼容（仍写 `collection_records`，额外写 `room_sessions`）
- 现有前端路由（`/api/batches/{batch_id}/accounts`）不变，只新增路由
