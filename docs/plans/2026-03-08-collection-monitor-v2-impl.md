# 采集完整性监控系统 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 live_dp 爬虫构建采集完整性监控系统，含 SQLite 存储、CollectionMonitor 钩子、FastAPI REST API、Vue3 前端面板。

**Architecture:** 模块化嵌入式监控。独立 `monitor/` 模块封装数据库和监控逻辑，通过 CollectionMonitor 单例在爬虫关键路径埋钩子，实时记录采集状态到 SQLite。FastAPI 提供查询 API，Vue3 SPA 展示完整性矩阵和 GMV 数据。

**Tech Stack:** Python 3.12 / SQLite / FastAPI / Vue3 + Vite + Element Plus / pytest

**设计文档:** `docs/plans/2026-03-08-collection-monitor-v2-design.md`

---

## Task 1: 基础设施 — 数据库 + 注册表 + 测试框架

**Files:**
- Create: `live_dp/monitor/__init__.py`
- Create: `live_dp/monitor/db.py`
- Create: `live_dp/monitor/registry.py`
- Create: `live_dp/conftest.py`
- Create: `live_dp/tests/__init__.py`
- Create: `live_dp/tests/monitor/__init__.py`
- Create: `live_dp/tests/monitor/test_db.py`
- Create: `live_dp/tests/monitor/test_registry.py`
- Clean: `live_dp/monitor/__pycache__/` (旧缓存)

**Step 1: 清理旧缓存，创建目录结构**

```bash
cd live_dp
rm -rf monitor/__pycache__
mkdir -p tests/monitor
```

**Step 2: 创建 conftest.py（测试路径配置）**

```python
# live_dp/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
```

**Step 3: 创建 tests/__init__.py 和 tests/monitor/__init__.py**

两个空文件。

**Step 4: 创建 monitor/db.py**

```python
# live_dp/monitor/db.py
"""SQLite 数据库初始化与连接管理"""

import sqlite3
from pathlib import Path

DB_DIR = Path(__file__).parent / 'data'
DB_PATH = DB_DIR / 'monitor.db'


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """获取 SQLite 连接

    Args:
        db_path: 数据库路径，None 则使用默认路径，':memory:' 用于测试
    """
    if db_path == ':memory:':
        conn = sqlite3.connect(':memory:', check_same_thread=False)
    else:
        path = Path(db_path) if db_path else DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection):
    """初始化数据库表结构"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS collection_batches (
            batch_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            total_accounts INTEGER DEFAULT 0,
            success_accounts INTEGER DEFAULT 0,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS account_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            group_name TEXT DEFAULT '',
            total_rooms INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            UNIQUE(batch_id, account_id),
            FOREIGN KEY (batch_id) REFERENCES collection_batches(batch_id)
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_batch ON account_sessions(batch_id);

        CREATE TABLE IF NOT EXISTS collection_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            room_id TEXT DEFAULT '',
            api_type TEXT NOT NULL,
            status TEXT DEFAULT 'success',
            response_size INTEGER DEFAULT 0,
            extra_data TEXT DEFAULT '',
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(batch_id, account_id, room_id, api_type)
        );
        CREATE INDEX IF NOT EXISTS idx_records_batch ON collection_records(batch_id);
        CREATE INDEX IF NOT EXISTS idx_records_account ON collection_records(batch_id, account_id);
        CREATE INDEX IF NOT EXISTS idx_records_room ON collection_records(batch_id, account_id, room_id);
    """)
    conn.commit()
```

**Step 5: 创建 monitor/registry.py**

```python
# live_dp/monitor/registry.py
"""API 类型注册表 — 定义完整性监控的期望 API 列表

扩展方式：取消注释对应行即可，无需改数据库表结构。
"""

API_TYPE_REGISTRY: dict[str, list[str]] = {
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
    ],
}


def get_expected_account_types() -> list[str]:
    return list(API_TYPE_REGISTRY['account'])


def get_expected_room_types() -> list[str]:
    return list(API_TYPE_REGISTRY['room'])
```

**Step 6: 创建 monitor/__init__.py**

```python
# live_dp/monitor/__init__.py
"""采集完整性监控模块"""
```

**Step 7: 写测试 test_db.py**

```python
# live_dp/tests/monitor/test_db.py
from monitor.db import get_connection, init_db


def test_init_db_creates_tables():
    conn = get_connection(':memory:')
    init_db(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = [t['name'] for t in tables]
    assert 'collection_batches' in names
    assert 'account_sessions' in names
    assert 'collection_records' in names


def test_init_db_idempotent():
    conn = get_connection(':memory:')
    init_db(conn)
    init_db(conn)  # 再次调用不应报错
    count = conn.execute("SELECT COUNT(*) as c FROM collection_batches").fetchone()['c']
    assert count == 0
```

**Step 8: 写测试 test_registry.py**

```python
# live_dp/tests/monitor/test_registry.py
from monitor.registry import get_expected_account_types, get_expected_room_types


def test_account_types_includes_phase1():
    types = get_expected_account_types()
    assert 'live_list' in types
    assert 'replay_info' in types


def test_room_types_includes_phase1():
    types = get_expected_room_types()
    assert 'trend_gmv' in types
    assert 'trend_stats' in types
```

**Step 9: 运行测试**

```bash
cd live_dp && python -m pytest tests/monitor/test_db.py tests/monitor/test_registry.py -v
```

Expected: 4 passed

**Step 10: 提交**

```bash
git add monitor/db.py monitor/registry.py monitor/__init__.py conftest.py tests/
git commit -m "feat(monitor): 基础设施 — SQLite 数据库 + API 注册表 + 测试框架"
```

---

## Task 2: API 分类器

**Files:**
- Create: `live_dp/monitor/classifier.py`
- Create: `live_dp/tests/monitor/test_classifier.py`

**Step 1: 写测试 test_classifier.py**

```python
# live_dp/tests/monitor/test_classifier.py
import pytest
from monitor.classifier import classify_api, extract_stats_types


class TestExtractStatsTypes:
    def test_trend_chart_format(self):
        body = {"request": {"room_filter": {"room_id": "123"}, "stats_types": [3, 20]}}
        assert extract_stats_types(body) == [3, 20]

    def test_live_list_format(self):
        body = {"request": {"params": [{"stats_types": [10, 15, 11]}]}}
        assert extract_stats_types(body) == [10, 15, 11]

    def test_json_string_input(self):
        import json
        body = json.dumps({"request": {"stats_types": [52]}})
        assert extract_stats_types(body) == [52]

    def test_empty_input(self):
        assert extract_stats_types(None) == []
        assert extract_stats_types("") == []
        assert extract_stats_types({}) == []


class TestClassifyApi:
    def test_live_list(self):
        assert classify_api("https://shop.tiktok.com/api/v2/insights/creator/live/list?aid=123") == 'live_list'

    def test_replay_info(self):
        assert classify_api("https://webcast.tiktok.com/webcast/room/replay/info") == 'replay_info'

    def test_trend_chart_gmv_stats3(self):
        body = {"request": {"stats_types": [3], "granularity": 1}}
        assert classify_api("https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart", body) == 'trend_gmv'

    def test_trend_chart_gmv_stats52(self):
        body = {"request": {"stats_types": [52], "granularity": 15}}
        assert classify_api("https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart", body) == 'trend_gmv'

    def test_trend_chart_traffic(self):
        body = {"request": {"stats_types": [60, 61]}}
        assert classify_api("https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart", body) == 'trend_traffic'

    def test_trend_chart_stats(self):
        body = {"request": {"stats_types": [3, 20, 341, 21, 22]}}
        assert classify_api("https://shop.tiktok.com/api/v1/insights/creator/liveroom/recap/trend/chart", body) == 'trend_stats'

    def test_unknown_url(self):
        assert classify_api("https://example.com/other") is None

    def test_empty_url(self):
        assert classify_api("") is None
```

**Step 2: 运行测试，确认失败**

```bash
cd live_dp && python -m pytest tests/monitor/test_classifier.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'monitor.classifier'`

**Step 3: 创建 classifier.py**

```python
# live_dp/monitor/classifier.py
"""API 分类器 — 根据 URL + 请求参数判断 api_type

后续新增 API 类型时，在此文件添加匹配规则即可。
"""

import json


def extract_stats_types(request_body) -> list[int]:
    """从请求体中提取 stats_types 列表"""
    if not request_body:
        return []
    if isinstance(request_body, str):
        try:
            request_body = json.loads(request_body)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(request_body, dict):
        return []

    req = request_body.get('request', request_body)

    # trend/chart 格式：request.stats_types
    if 'stats_types' in req:
        return req['stats_types']

    # live/list 和 live/stats 格式：request.params[0].stats_types
    params = req.get('params', [])
    if params and isinstance(params, list):
        return params[0].get('stats_types', [])

    return []


def classify_api(url: str, request_body=None) -> str | None:
    """根据 URL + 请求参数判断 api_type

    Args:
        url: API URL
        request_body: 请求体（dict 或 JSON 字符串）

    Returns:
        api_type 字符串，无法识别返回 None
    """
    if not url:
        return None

    # 账号级 API — URL 直接匹配
    if 'live/list' in url:
        return 'live_list'
    if 'replay/info' in url:
        return 'replay_info'
    if 'account_info/get' in url:
        return 'account_info'

    # 直播间级 API — URL 直接匹配
    if 'recap/core/stats' in url:
        return 'room_core_stats'
    if 'recap/product/list' in url:
        return 'room_product_list'
    if 'workbench/live/detail/core/stats' in url:
        return 'room_traffic_conversion'
    if 'recap/viewer/source/stats' in url:
        return 'room_viewer_portrait'
    if 'detail/source/new' in url:
        return 'room_traffic_source'

    # trend/chart — 需要通过 stats_types 区分
    if 'recap/trend/chart' in url:
        stats_types = extract_stats_types(request_body)
        if 52 in stats_types:
            return 'trend_gmv'
        if 60 in stats_types or 61 in stats_types:
            return 'trend_traffic'
        if stats_types == [3]:
            return 'trend_gmv'
        return 'trend_stats'

    # live/stats — 需要通过 stats_types 区分
    if 'live/stats' in url:
        stats_types = extract_stats_types(request_body)
        if any(t in stats_types for t in [100, 101, 121]):
            return 'data_overview'
        return 'live_stats_7d'

    return None
```

**Step 4: 运行测试，确认通过**

```bash
cd live_dp && python -m pytest tests/monitor/test_classifier.py -v
```

Expected: 9 passed

**Step 5: 提交**

```bash
git add monitor/classifier.py tests/monitor/test_classifier.py
git commit -m "feat(monitor): API 分类器 — 根据 URL + stats_types 判断 api_type"
```

---

## Task 3: CollectionMonitor 核心

**Files:**
- Create: `live_dp/monitor/tracker.py`
- Create: `live_dp/tests/monitor/test_tracker.py`
- Modify: `live_dp/monitor/__init__.py`

**Step 1: 写测试 test_tracker.py**

```python
# live_dp/tests/monitor/test_tracker.py
import pytest
from monitor.tracker import CollectionMonitor


@pytest.fixture
def monitor():
    """每个测试使用独立的内存数据库"""
    return CollectionMonitor(db_path=':memory:')


class TestBatch:
    def test_start_and_finish_batch(self, monitor):
        monitor.start_batch('2026-03-08_20:00', 'once')
        monitor.start_account('2026-03-08_20:00', 'acc1')
        monitor.finish_account('2026-03-08_20:00', 'acc1', 'success')
        monitor.finish_batch('2026-03-08_20:00')

        row = monitor._conn.execute(
            "SELECT * FROM collection_batches WHERE batch_id=?", ('2026-03-08_20:00',)
        ).fetchone()
        assert row['mode'] == 'once'
        assert row['total_accounts'] == 1
        assert row['success_accounts'] == 1
        assert row['finished_at'] is not None


class TestAccount:
    def test_start_and_finish_account(self, monitor):
        monitor.start_batch('b1', 'once')
        monitor.start_account('b1', 'acc1', '美国团队-tiktok')
        monitor.finish_account('b1', 'acc1', 'partial')

        row = monitor._conn.execute(
            "SELECT * FROM account_sessions WHERE account_id='acc1'"
        ).fetchone()
        assert row['group_name'] == '美国团队-tiktok'
        assert row['status'] == 'partial'

    def test_finish_account_counts_rooms(self, monitor):
        monitor.start_batch('b1', 'once')
        monitor.start_account('b1', 'acc1')
        # 记录 2 个 room 的 trend 数据
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room1')
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room2')
        monitor.finish_account('b1', 'acc1')

        row = monitor._conn.execute(
            "SELECT total_rooms FROM account_sessions WHERE account_id='acc1'"
        ).fetchone()
        assert row['total_rooms'] == 2


class TestRecord:
    def test_record_account_level_api(self, monitor):
        monitor.start_batch('b1', 'once')
        monitor.record('b1', 'acc1', 'replay_info', status='success', response_size=1024)

        row = monitor._conn.execute(
            "SELECT * FROM collection_records WHERE api_type='replay_info'"
        ).fetchone()
        assert row['account_id'] == 'acc1'
        assert row['room_id'] == ''
        assert row['response_size'] == 1024

    def test_record_room_level_api(self, monitor):
        monitor.start_batch('b1', 'once')
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room123', status='success')

        row = monitor._conn.execute(
            "SELECT * FROM collection_records WHERE api_type='trend_gmv'"
        ).fetchone()
        assert row['room_id'] == 'room123'

    def test_record_with_extra_data(self, monitor):
        monitor.start_batch('b1', 'once')
        extra = {'revenue': '3651856', 'currency': 'IDR'}
        monitor.record('b1', 'acc1', 'live_list', extra_data=extra)

        import json
        row = monitor._conn.execute(
            "SELECT extra_data FROM collection_records WHERE api_type='live_list'"
        ).fetchone()
        data = json.loads(row['extra_data'])
        assert data['revenue'] == '3651856'

    def test_record_upsert(self, monitor):
        """重复记录应更新而非报错"""
        monitor.start_batch('b1', 'once')
        monitor.record('b1', 'acc1', 'live_list', status='failed')
        monitor.record('b1', 'acc1', 'live_list', status='success')

        rows = monitor._conn.execute(
            "SELECT * FROM collection_records WHERE api_type='live_list' AND account_id='acc1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]['status'] == 'success'


class TestRecordRooms:
    def test_record_rooms_stores_gmv(self, monitor):
        monitor.start_batch('b1', 'once')
        rooms = [
            {'room_id': 'r1', 'room_name': 'SALE', 'revenue': '1000', 'item_sold_cnt': 5},
            {'room_id': 'r2', 'room_name': 'LIVE', 'revenue': '2000', 'item_sold_cnt': 10},
        ]
        monitor.record_rooms('b1', 'acc1', rooms)

        import json
        row = monitor._conn.execute(
            "SELECT extra_data FROM collection_records WHERE api_type='live_list'"
        ).fetchone()
        data = json.loads(row['extra_data'])
        assert len(data['rooms']) == 2
        assert data['rooms'][0]['room_id'] == 'r1'
```

**Step 2: 运行测试，确认失败**

```bash
cd live_dp && python -m pytest tests/monitor/test_tracker.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'monitor.tracker'`

**Step 3: 创建 tracker.py**

```python
# live_dp/monitor/tracker.py
"""CollectionMonitor — 采集完整性监控器

通过钩子方法在爬虫关键路径记录采集状态到 SQLite。
"""

import json
from datetime import datetime

from monitor.db import get_connection, init_db
from monitor.registry import get_expected_account_types, get_expected_room_types


class CollectionMonitor:
    """采集完整性监控器"""

    def __init__(self, db_path: str | None = None):
        self._conn = get_connection(db_path)
        init_db(self._conn)

    def start_batch(self, batch_id: str, mode: str):
        """记录采集批次开始"""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO collection_batches (batch_id, mode, started_at) VALUES (?, ?, ?)",
                (batch_id, mode, datetime.now().isoformat())
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录批次开始失败: {e}')

    def finish_batch(self, batch_id: str):
        """记录采集批次结束，自动统计账号数"""
        try:
            row = self._conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success "
                "FROM account_sessions WHERE batch_id=?",
                (batch_id,)
            ).fetchone()
            total = row['total'] if row else 0
            success = row['success'] if row else 0

            self._conn.execute(
                "UPDATE collection_batches SET finished_at=?, total_accounts=?, success_accounts=? WHERE batch_id=?",
                (datetime.now().isoformat(), total, success, batch_id)
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录批次结束失败: {e}')

    def start_account(self, batch_id: str, account_id: str, group_name: str = ''):
        """记录账号采集开始"""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO account_sessions (batch_id, account_id, group_name, started_at) VALUES (?, ?, ?, ?)",
                (batch_id, account_id, group_name, datetime.now().isoformat())
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录账号开始失败: {e}')

    def finish_account(self, batch_id: str, account_id: str, status: str = 'success'):
        """记录账号采集结束，自动统计 room 数"""
        try:
            row = self._conn.execute(
                "SELECT COUNT(DISTINCT room_id) as cnt FROM collection_records "
                "WHERE batch_id=? AND account_id=? AND room_id != ''",
                (batch_id, account_id)
            ).fetchone()
            total_rooms = row['cnt'] if row else 0

            self._conn.execute(
                "UPDATE account_sessions SET status=?, total_rooms=?, finished_at=? "
                "WHERE batch_id=? AND account_id=?",
                (status, total_rooms, datetime.now().isoformat(), batch_id, account_id)
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录账号结束失败: {e}')

    def record(self, batch_id: str, account_id: str, api_type: str,
               room_id: str = '', status: str = 'success',
               response_size: int = 0, extra_data: dict | None = None):
        """通用记录方法 — 记录一次 API 采集结果"""
        try:
            extra_json = json.dumps(extra_data, ensure_ascii=False) if extra_data else ''
            self._conn.execute(
                "INSERT OR REPLACE INTO collection_records "
                "(batch_id, account_id, room_id, api_type, status, response_size, extra_data, collected_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (batch_id, account_id, room_id, api_type, status, response_size, extra_json,
                 datetime.now().isoformat())
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录采集数据失败: {e}')

    def record_rooms(self, batch_id: str, account_id: str, rooms_data: list[dict]):
        """记录 live/list 响应中的直播间列表（含 GMV 数据）"""
        try:
            extra = json.dumps({'rooms': rooms_data}, ensure_ascii=False)
            self._conn.execute(
                "INSERT OR REPLACE INTO collection_records "
                "(batch_id, account_id, room_id, api_type, status, response_size, extra_data, collected_at) "
                "VALUES (?, ?, '', 'live_list', 'success', ?, ?, ?)",
                (batch_id, account_id, len(extra), extra, datetime.now().isoformat())
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录直播间列表失败: {e}')

    @staticmethod
    def _log_error(msg: str):
        """静默日志，避免 import logger 在测试中报错"""
        try:
            from utils.logger import logger
            logger.error(msg)
        except ImportError:
            print(f'[MONITOR ERROR] {msg}')
```

**Step 4: 运行测试，确认通过**

```bash
cd live_dp && python -m pytest tests/monitor/test_tracker.py -v
```

Expected: 8 passed

**Step 5: 更新 monitor/__init__.py 导出单例**

```python
# live_dp/monitor/__init__.py
"""采集完整性监控模块"""

from monitor.tracker import CollectionMonitor

_monitor: CollectionMonitor | None = None


def get_monitor() -> CollectionMonitor:
    """获取 CollectionMonitor 全局单例"""
    global _monitor
    if _monitor is None:
        _monitor = CollectionMonitor()
    return _monitor
```

**Step 6: 运行全部测试**

```bash
cd live_dp && python -m pytest tests/monitor/ -v
```

Expected: 全部通过（13 tests）

**Step 7: 提交**

```bash
git add monitor/tracker.py monitor/__init__.py tests/monitor/test_tracker.py
git commit -m "feat(monitor): CollectionMonitor 核心 — 批次/账号/记录的 CRUD 方法"
```

---

## Task 4: 钩子集成 — 批次 + 账号级

**Files:**
- Modify: `live_dp/spiders/live_crawler.py:28,58` (添加 batch_id 参数透传)
- Modify: `live_dp/spiders/base.py:27,90-158` (添加 batch_id + monitor 钩子)
- Modify: `live_dp/main.py:25-47,70-237` (生成 batch_id + monitor 钩子)
- Modify: `live_dp/scheduler/task_scheduler.py:76-235` (同上)

**Step 1: 修改 live_crawler.py — 透传 batch_id**

在 `LiveCrawler.__new__` 中添加 `batch_id` 参数：

```python
# live_dp/spiders/live_crawler.py:28
# 修改前：
def __new__(cls, platform: str = 'tiktok', browser_id: str = None, full_collection: bool = False, group_name: str = ''):
# 修改后：
def __new__(cls, platform: str = 'tiktok', browser_id: str = None, full_collection: bool = False, group_name: str = '', batch_id: str = ''):
```

```python
# live_dp/spiders/live_crawler.py:58
# 修改前：
return crawler_class(browser_id=browser_id, full_collection=full_collection, group_name=group_name)
# 修改后：
return crawler_class(browser_id=browser_id, full_collection=full_collection, group_name=group_name, batch_id=batch_id)
```

**Step 2: 修改 base.py — 存储 batch_id + 在 start_crawl 中调用 monitor**

在 `BaseLiveCrawler.__init__` 中添加 `batch_id`：

```python
# live_dp/spiders/base.py:27
# 修改前：
def __init__(self, browser_id: str = None, full_collection: bool = False, group_name: str = ''):
# 修改后：
def __init__(self, browser_id: str = None, full_collection: bool = False, group_name: str = '', batch_id: str = ''):
```

在 `__init__` 方法体中 `self.timestamp = ...` 之后添加：

```python
        self.batch_id = batch_id
```

在 `start_crawl()` 方法中添加 monitor 钩子：

```python
# live_dp/spiders/base.py — start_crawl 方法
# 在方法开头（result = { ... } 之前）添加：
        from monitor import get_monitor
        monitor = get_monitor()
        if self.batch_id:
            monitor.start_account(self.batch_id, self.browser_id, self.group_name)

# 在 finally 块中（result['end_time'] = ... 之后）添加：
            if self.batch_id:
                status = 'success' if result.get('success') else ('login_failed' if not result.get('login_status', True) else 'failed')
                monitor.finish_account(self.batch_id, self.browser_id, status)
```

**Step 3: 修改 main.py — 生成 batch_id + monitor 钩子**

在文件顶部 import 区添加：

```python
from datetime import datetime as dt
from monitor import get_monitor
```

修改 `crawl_single_account` 函数签名和调用：

```python
# live_dp/main.py:25
# 修改前：
def crawl_single_account(platform: str, account, full_collection: bool) -> dict:
# 修改后：
def crawl_single_account(platform: str, account, full_collection: bool, batch_id: str = '') -> dict:

# 修改前（函数体内）：
        crawler = LiveCrawler(platform=platform, browser_id=user_id,
                              full_collection=full_collection, group_name=group_name)
# 修改后：
        crawler = LiveCrawler(platform=platform, browser_id=user_id,
                              full_collection=full_collection, group_name=group_name, batch_id=batch_id)
```

在 `run_once()` 函数开头添加 batch_id 生成和 monitor 钩子：

```python
# live_dp/main.py — run_once 函数
# 在 logger.info('='*60) 之前添加：
    mode = 'full' if full_collection else 'once'
    batch_id = dt.now().strftime('%Y-%m-%d_%H:%M')
    monitor = get_monitor()
    monitor.start_batch(batch_id, mode)

# 在并发模式 executor.submit 处传入 batch_id：
                    future = executor.submit(crawl_single_account, platform, account, full_collection, batch_id)

# 在串行模式 LiveCrawler 构造处传入 batch_id：
                    crawler = LiveCrawler(platform=platform, browser_id=user_id,
                                         full_collection=account_full_collection, group_name=group_name, batch_id=batch_id)

# 在函数末尾（最后的 logger.info 之后）添加：
    monitor.finish_batch(batch_id)
```

**Step 4: 修改 task_scheduler.py — 同上**

在文件顶部 import 区添加：

```python
from monitor import get_monitor
```

在 `execute_crawl_task()` 方法中：

```python
# live_dp/scheduler/task_scheduler.py — execute_crawl_task 方法
# 在 logger.info('开始执行定时采集任务') 之后添加：
        batch_id = datetime.now().strftime('%Y-%m-%d_%H:%M')
        monitor = get_monitor()
        monitor.start_batch(batch_id, 'scheduler')

# 在 LiveCrawler 构造处传入 batch_id：
                    crawler = LiveCrawler(platform=platform, browser_id=user_id,
                                         full_collection=account_full_collection, group_name=group_name, batch_id=batch_id)

# 在方法末尾（最后的告警代码之后）添加：
        monitor.finish_batch(batch_id)
```

**Step 5: 检查子类构造函数兼容**

确认 `TikTokLiveCrawler.__init__` 和 `MxTikTokLiveCrawler` 使用 `**kwargs` 透传，batch_id 会自动传递到 `BaseLiveCrawler.__init__`。

查看 `live_dp/spiders/tiktok.py:26`：

```python
def __init__(self, browser_id: str = None, full_collection: bool = False, **kwargs: Any) -> None:
    super().__init__(browser_id=browser_id, full_collection=full_collection, **kwargs)
```

batch_id 在 `**kwargs` 中，会传递到 base。无需改动。

**Step 6: 提交**

```bash
git add spiders/live_crawler.py spiders/base.py main.py scheduler/task_scheduler.py
git commit -m "feat(monitor): 钩子集成 — 批次 + 账号级监控（main/scheduler/base）"
```

---

## Task 5: 钩子集成 — TikTok 爬虫

**Files:**
- Modify: `live_dp/spiders/tiktok.py`

**Step 1: 在 _handle_tiktok_live_list 中记录 live_list + rooms**

在 `_handle_tiktok_live_list` 方法中，解析出 `room_id_list` 之后、开始遍历之前，添加 monitor 调用。

```python
# live_dp/spiders/tiktok.py — _handle_tiktok_live_list 方法
# 在 room_id_list = [] 之前添加 monitor 导入：
            from monitor import get_monitor
            monitor = get_monitor()

# 在 if room_id_list: 块内部、logger.info 之后添加 rooms 数据提取和记录：
            if room_id_list:
                mode_desc = '全部' if self.full_collection else '昨天的'
                logger.info(f'找到 {len(room_id_list)} 个{mode_desc}直播间，将通过 JS 注入获取趋势数据')

                # --- 新增：记录 live_list 及 rooms GMV 数据到 monitor ---
                if self.batch_id:
                    rooms_data = []
                    for stat in stats:
                        rid = stat.get('live_id')
                        if rid and str(rid) in [str(r) for r in room_id_list]:
                            revenue = stat.get('revenue', {})
                            rooms_data.append({
                                'room_id': str(rid),
                                'room_name': stat.get('live_name', ''),
                                'live_start_ts': stat.get('live_start_timestamp', 0),
                                'live_end_ts': stat.get('live_end_timestamp', 0),
                                'duration': stat.get('live_duration', 0),
                                'cover_url': stat.get('live_meta', {}).get('cover_url', ''),
                                'revenue': revenue.get('amount', '0'),
                                'currency_code': revenue.get('currency_code', ''),
                                'direct_revenue': stat.get('direct_revenue', {}).get('amount', '0'),
                                'item_sold_cnt': stat.get('item_sold_cnt', 0),
                                'view_cnt': stat.get('view_cnt', 0),
                                'ctr': stat.get('ctr', 0),
                                'c_o': stat.get('c_o', 0),
                            })
                    monitor.record_rooms(self.batch_id, self.browser_id, rooms_data)
                # --- 新增结束 ---
```

**Step 2: 在 _fetch_trend_chart_via_js 成功/失败时记录 trend 结果**

在 `_fetch_trend_chart_via_js` 方法中，成功返回之前和最终失败返回之前，添加 monitor 记录。

```python
# live_dp/spiders/tiktok.py — _fetch_trend_chart_via_js 方法
# 在成功分支（logger.info(f'room {room_id} 趋势数据获取成功') 之后，return 之前）添加：
                    if self.batch_id:
                        from monitor import get_monitor
                        m = get_monitor()
                        m.record(self.batch_id, self.browser_id, 'trend_gmv', room_id=room_id,
                                 status='success' if sent_count >= 1 else 'failed')
                        m.record(self.batch_id, self.browser_id, 'trend_stats', room_id=room_id,
                                 status='success' if sent_count >= 2 else 'failed')

# 在最终失败返回之前（方法末尾 return {'success': False, ...} 之前）添加：
        if self.batch_id:
            from monitor import get_monitor
            m = get_monitor()
            m.record(self.batch_id, self.browser_id, 'trend_gmv', room_id=room_id, status='failed')
            m.record(self.batch_id, self.browser_id, 'trend_stats', room_id=room_id, status='failed')
```

**Step 3: 在 visit_page_and_collect 中记录 replay_info**

在 `visit_page_and_collect` 方法中，处理 api_data_list 的循环内，当 URL 匹配 replay/info 时记录。

```python
# live_dp/spiders/tiktok.py — visit_page_and_collect 方法
# 在 self.handle_special_logic(...) 之后添加：
                    # 记录 replay/info 到 monitor
                    if self.batch_id and 'replay/info' in api_data['url']:
                        from monitor import get_monitor
                        get_monitor().record(
                            self.batch_id, self.browser_id, 'replay_info',
                            status='success', response_size=len(str(api_data.get('response', '')))
                        )
```

**Step 4: 提交**

```bash
git add spiders/tiktok.py
git commit -m "feat(monitor): TikTok 爬虫钩子 — live_list/replay/trend 采集记录"
```

---

## Task 6: FastAPI REST API

**Files:**
- Create: `live_dp/monitor/server.py`
- Create: `live_dp/monitor/api/__init__.py`
- Create: `live_dp/monitor/api/batches.py`
- Create: `live_dp/monitor/api/accounts.py`

**Step 1: 创建 api/__init__.py**

空文件。

**Step 2: 创建 api/batches.py**

```python
# live_dp/monitor/api/batches.py
"""批次相关 API 路由"""

from fastapi import APIRouter, Query
from monitor.db import get_connection, init_db
from monitor.registry import get_expected_account_types, get_expected_room_types

router = APIRouter(prefix="/api", tags=["batches"])

def _get_conn():
    conn = get_connection()
    init_db(conn)
    return conn


@router.get("/batches")
def list_batches(limit: int = Query(20, ge=1, le=100)):
    """获取采集批次列表"""
    conn = _get_conn()
    batches = conn.execute(
        "SELECT * FROM collection_batches ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()

    result = []
    expected_account = get_expected_account_types()
    expected_room = get_expected_room_types()

    for b in batches:
        batch_id = b['batch_id']

        # 计算完整率
        sessions = conn.execute(
            "SELECT account_id, total_rooms FROM account_sessions WHERE batch_id=?",
            (batch_id,)
        ).fetchall()

        total_expected = 0
        total_actual = 0
        for s in sessions:
            # 账号级
            total_expected += len(expected_account)
            account_records = conn.execute(
                "SELECT api_type FROM collection_records "
                "WHERE batch_id=? AND account_id=? AND room_id='' AND status='success'",
                (batch_id, s['account_id'])
            ).fetchall()
            actual_account = sum(1 for r in account_records if r['api_type'] in expected_account)
            total_actual += actual_account

            # 直播间级
            rooms = conn.execute(
                "SELECT DISTINCT room_id FROM collection_records "
                "WHERE batch_id=? AND account_id=? AND room_id != ''",
                (batch_id, s['account_id'])
            ).fetchall()
            for room in rooms:
                total_expected += len(expected_room)
                room_records = conn.execute(
                    "SELECT api_type FROM collection_records "
                    "WHERE batch_id=? AND account_id=? AND room_id=? AND status='success'",
                    (batch_id, s['account_id'], room['room_id'])
                ).fetchall()
                actual_room = sum(1 for r in room_records if r['api_type'] in expected_room)
                total_actual += actual_room

        completeness = round(total_actual / total_expected * 100, 1) if total_expected > 0 else 0

        result.append({
            'batch_id': batch_id,
            'mode': b['mode'],
            'total_accounts': b['total_accounts'],
            'success_accounts': b['success_accounts'],
            'completeness': completeness,
            'started_at': b['started_at'],
            'finished_at': b['finished_at'],
        })

    return {'batches': result}
```

**Step 3: 创建 api/accounts.py**

```python
# live_dp/monitor/api/accounts.py
"""账号 + 直播间相关 API 路由"""

import json
from fastapi import APIRouter, Query
from monitor.db import get_connection, init_db
from monitor.registry import get_expected_account_types, get_expected_room_types

router = APIRouter(prefix="/api", tags=["accounts"])

def _get_conn():
    conn = get_connection()
    init_db(conn)
    return conn


@router.get("/batches/{batch_id}/accounts")
def list_accounts(batch_id: str):
    """获取批次下的账号列表及采集状态"""
    conn = _get_conn()
    expected_account = get_expected_account_types()
    expected_room = get_expected_room_types()

    sessions = conn.execute(
        "SELECT * FROM account_sessions WHERE batch_id=? ORDER BY started_at",
        (batch_id,)
    ).fetchall()

    result = []
    for s in sessions:
        account_id = s['account_id']

        # 账号级 API 状态
        account_records = conn.execute(
            "SELECT api_type, status FROM collection_records "
            "WHERE batch_id=? AND account_id=? AND room_id=''",
            (batch_id, account_id)
        ).fetchall()
        api_status = {r['api_type']: r['status'] for r in account_records}

        # 直播间级统计
        rooms = conn.execute(
            "SELECT DISTINCT room_id FROM collection_records "
            "WHERE batch_id=? AND account_id=? AND room_id != ''",
            (batch_id, account_id)
        ).fetchall()
        room_success = 0
        for room in rooms:
            room_records = conn.execute(
                "SELECT api_type, status FROM collection_records "
                "WHERE batch_id=? AND account_id=? AND room_id=? AND status='success'",
                (batch_id, account_id, room['room_id'])
            ).fetchall()
            if all(any(r['api_type'] == t for r in room_records) for t in expected_room):
                room_success += 1

        result.append({
            'account_id': account_id,
            'group_name': s['group_name'],
            'total_rooms': s['total_rooms'],
            'room_success': room_success,
            'status': s['status'],
            'api_status': {t: api_status.get(t, 'missing') for t in expected_account},
            'started_at': s['started_at'],
            'finished_at': s['finished_at'],
        })

    return {'accounts': result, 'expected_account_types': expected_account, 'expected_room_types': expected_room}


@router.get("/accounts/{account_id}/rooms")
def list_rooms(account_id: str, batch_id: str = Query(...)):
    """获取账号下的直播间列表 + GMV + 采集状态"""
    conn = _get_conn()
    expected_room = get_expected_room_types()

    # 从 live_list 的 extra_data 中提取 rooms GMV 数据
    live_list_row = conn.execute(
        "SELECT extra_data FROM collection_records "
        "WHERE batch_id=? AND account_id=? AND api_type='live_list'",
        (batch_id, account_id)
    ).fetchone()

    rooms_gmv = {}
    if live_list_row and live_list_row['extra_data']:
        try:
            data = json.loads(live_list_row['extra_data'])
            for r in data.get('rooms', []):
                rooms_gmv[str(r.get('room_id', ''))] = r
        except (json.JSONDecodeError, TypeError):
            pass

    # 获取所有 room 的采集记录
    room_records = conn.execute(
        "SELECT room_id, api_type, status FROM collection_records "
        "WHERE batch_id=? AND account_id=? AND room_id != ''",
        (batch_id, account_id)
    ).fetchall()

    # 按 room_id 分组
    rooms_status: dict[str, dict[str, str]] = {}
    for r in room_records:
        rid = r['room_id']
        if rid not in rooms_status:
            rooms_status[rid] = {}
        rooms_status[rid][r['api_type']] = r['status']

    # 合并 GMV 数据 + 采集状态
    all_room_ids = set(rooms_gmv.keys()) | set(rooms_status.keys())
    result = []
    for rid in sorted(all_room_ids):
        gmv = rooms_gmv.get(rid, {})
        status = rooms_status.get(rid, {})
        result.append({
            'room_id': rid,
            'room_name': gmv.get('room_name', ''),
            'live_start_ts': gmv.get('live_start_ts', 0),
            'live_end_ts': gmv.get('live_end_ts', 0),
            'duration': gmv.get('duration', 0),
            'revenue': gmv.get('revenue', '0'),
            'currency_code': gmv.get('currency_code', ''),
            'item_sold_cnt': gmv.get('item_sold_cnt', 0),
            'view_cnt': gmv.get('view_cnt', 0),
            'api_status': {t: status.get(t, 'missing') for t in expected_room},
        })

    # 按开播时间倒序
    result.sort(key=lambda x: x['live_start_ts'], reverse=True)
    return {'rooms': result, 'expected_room_types': expected_room}
```

**Step 4: 创建 server.py**

```python
# live_dp/monitor/server.py
"""监控面板 FastAPI 服务入口

启动方式：cd live_dp && python -m monitor.server
"""

import sys
from pathlib import Path

# 确保 live_dp/ 在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from monitor.api.batches import router as batches_router
from monitor.api.accounts import router as accounts_router

app = FastAPI(title="采集完整性监控", version="1.0")

# 注册路由
app.include_router(batches_router)
app.include_router(accounts_router)

# 前端静态文件（构建后）
FRONTEND_DIST = Path(__file__).parent / 'frontend' / 'dist'
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback：所有非 API 路由返回 index.html"""
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8777)
```

**Step 5: 手动验证 API**

```bash
cd live_dp && pip install fastapi uvicorn -q
python -m monitor.server &
# 等待启动后测试
curl http://localhost:8777/api/batches
# Expected: {"batches":[]}
kill %1
```

**Step 6: 提交**

```bash
git add monitor/server.py monitor/api/
git commit -m "feat(monitor): FastAPI REST API — 批次/账号/直播间查询接口"
```

---

## Task 7: Vue3 前端

**Files:**
- Create: `live_dp/monitor/frontend/package.json`
- Create: `live_dp/monitor/frontend/vite.config.js`
- Create: `live_dp/monitor/frontend/index.html`
- Create: `live_dp/monitor/frontend/src/main.js`
- Create: `live_dp/monitor/frontend/src/App.vue`
- Create: `live_dp/monitor/frontend/src/router/index.js`
- Create: `live_dp/monitor/frontend/src/api/index.js`
- Create: `live_dp/monitor/frontend/src/views/Dashboard.vue`
- Create: `live_dp/monitor/frontend/src/views/AccountDetail.vue`

**Step 1: 创建 package.json**

```json
{
  "name": "monitor-frontend",
  "private": true,
  "version": "1.0.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.3.0",
    "element-plus": "^2.9.0",
    "axios": "^1.7.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "vite": "^5.0.0"
  }
}
```

**Step 2: 创建 vite.config.js**

```javascript
// live_dp/monitor/frontend/vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8777'
    }
  }
})
```

**Step 3: 创建 index.html**

```html
<!-- live_dp/monitor/frontend/index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>采集完整性监控</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

**Step 4: 创建 src/main.js**

```javascript
// live_dp/monitor/frontend/src/main.js
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

createApp(App).use(ElementPlus).use(router).mount('#app')
```

**Step 5: 创建 src/App.vue**

```vue
<!-- live_dp/monitor/frontend/src/App.vue -->
<template>
  <el-container style="min-height: 100vh">
    <el-header style="background: #545c64; display: flex; align-items: center">
      <h2 style="color: #fff; margin: 0">采集完整性监控</h2>
      <el-button style="margin-left: auto" type="primary" text @click="$router.push('/')">
        Dashboard
      </el-button>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>
```

**Step 6: 创建 src/router/index.js**

```javascript
// live_dp/monitor/frontend/src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import AccountDetail from '../views/AccountDetail.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/account/:accountId', component: AccountDetail, props: true },
  ]
})
```

**Step 7: 创建 src/api/index.js**

```javascript
// live_dp/monitor/frontend/src/api/index.js
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const fetchBatches = (limit = 20) => api.get('/batches', { params: { limit } })
export const fetchAccounts = (batchId) => api.get(`/batches/${batchId}/accounts`)
export const fetchRooms = (accountId, batchId) => api.get(`/accounts/${accountId}/rooms`, { params: { batch_id: batchId } })
```

**Step 8: 创建 src/views/Dashboard.vue**

```vue
<!-- live_dp/monitor/frontend/src/views/Dashboard.vue -->
<template>
  <div>
    <el-table :data="batches" stripe @row-click="toggleBatch" style="cursor: pointer">
      <el-table-column prop="batch_id" label="批次" width="180" />
      <el-table-column prop="mode" label="模式" width="100" />
      <el-table-column label="账号" width="120">
        <template #default="{ row }">
          {{ row.success_accounts }}/{{ row.total_accounts }}
        </template>
      </el-table-column>
      <el-table-column label="完整率" width="120">
        <template #default="{ row }">
          <el-tag :type="row.completeness >= 100 ? 'success' : row.completeness >= 50 ? 'warning' : 'danger'">
            {{ row.completeness }}%
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="started_at" label="开始时间" />
      <el-table-column prop="finished_at" label="结束时间" />
    </el-table>

    <!-- 展开的账号列表 -->
    <el-dialog v-model="showAccounts" :title="`批次 ${selectedBatch} 账号列表`" width="80%">
      <el-table :data="accounts" stripe>
        <el-table-column prop="account_id" label="账号ID" width="140" />
        <el-table-column prop="group_name" label="分组" width="160" />
        <el-table-column label="live_list" width="90" align="center">
          <template #default="{ row }">
            <el-icon :color="row.api_status.live_list === 'success' ? '#67C23A' : '#F56C6C'">
              <template v-if="row.api_status.live_list === 'success'">&#10004;</template>
              <template v-else>&#10008;</template>
            </el-icon>
          </template>
        </el-table-column>
        <el-table-column label="replay" width="90" align="center">
          <template #default="{ row }">
            <el-icon :color="row.api_status.replay_info === 'success' ? '#67C23A' : '#F56C6C'">
              <template v-if="row.api_status.replay_info === 'success'">&#10004;</template>
              <template v-else>&#10008;</template>
            </el-icon>
          </template>
        </el-table-column>
        <el-table-column label="trend" width="100" align="center">
          <template #default="{ row }">
            {{ row.room_success }}/{{ row.total_rooms }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'partial' ? 'warning' : 'danger'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button type="primary" link @click="goDetail(row.account_id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchBatches, fetchAccounts } from '../api'

const router = useRouter()
const batches = ref([])
const accounts = ref([])
const showAccounts = ref(false)
const selectedBatch = ref('')

onMounted(async () => {
  const res = await fetchBatches()
  batches.value = res.data.batches
})

async function toggleBatch(row) {
  selectedBatch.value = row.batch_id
  const res = await fetchAccounts(row.batch_id)
  accounts.value = res.data.accounts
  showAccounts.value = true
}

function goDetail(accountId) {
  showAccounts.value = false
  router.push({ path: `/account/${accountId}`, query: { batch_id: selectedBatch.value } })
}
</script>
```

**Step 9: 创建 src/views/AccountDetail.vue**

```vue
<!-- live_dp/monitor/frontend/src/views/AccountDetail.vue -->
<template>
  <div>
    <el-page-header @back="$router.push('/')" :title="'返回'" :content="`账号 ${accountId} 直播间详情`" />
    <el-table :data="rooms" stripe style="margin-top: 16px">
      <el-table-column prop="room_name" label="直播标题" min-width="200" show-overflow-tooltip />
      <el-table-column label="开播时间" width="170">
        <template #default="{ row }">
          {{ row.live_start_ts ? new Date(row.live_start_ts * 1000).toLocaleString() : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="时长" width="90">
        <template #default="{ row }">
          {{ row.duration ? Math.round(row.duration / 60) + '分' : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="GMV" width="140">
        <template #default="{ row }">
          {{ row.currency_code }} {{ Number(row.revenue).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column prop="item_sold_cnt" label="销量" width="80" />
      <el-table-column prop="view_cnt" label="观看" width="80" />
      <el-table-column v-for="t in expectedTypes" :key="t" :label="t" width="110" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.api_status[t] === 'success' ? 'success' : row.api_status[t] === 'failed' ? 'danger' : 'info'"
            size="small"
          >
            {{ row.api_status[t] || 'missing' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { fetchRooms } from '../api'

const props = defineProps({ accountId: String })
const route = useRoute()
const rooms = ref([])
const expectedTypes = ref([])

onMounted(async () => {
  const batchId = route.query.batch_id
  if (!batchId) return
  const res = await fetchRooms(props.accountId, batchId)
  rooms.value = res.data.rooms
  expectedTypes.value = res.data.expected_room_types
})
</script>
```

**Step 10: 安装依赖**

```bash
cd live_dp/monitor/frontend && npm install
```

**Step 11: 验证开发模式**

```bash
# 终端1：启动 FastAPI
cd live_dp && python -m monitor.server

# 终端2：启动 Vite dev server
cd live_dp/monitor/frontend && npm run dev
# 浏览器访问 http://localhost:5173
```

**Step 12: 提交**

```bash
cd live_dp
git add monitor/frontend/ -f
git commit -m "feat(monitor): Vue3 前端 — Dashboard + AccountDetail 页面"
```

---

## Task 8: 构建集成 + 文档更新

**Files:**
- Modify: `live_dp/monitor/frontend/` (build)
- Modify: `live_dp/requirements.txt`
- Modify: `memory-bank/architecture.md` (更新目录结构)

**Step 1: 构建前端**

```bash
cd live_dp/monitor/frontend && npm run build
# 产物在 dist/ 目录
```

**Step 2: 更新 requirements.txt**

在 `live_dp/requirements.txt` 末尾添加：

```
# 监控面板
fastapi>=0.115.0
uvicorn>=0.34.0
```

**Step 3: 验证完整流程**

```bash
cd live_dp
pip install fastapi uvicorn -q
python -m monitor.server
# 浏览器访问 http://localhost:8777
# 预期：看到空 Dashboard 页面（无数据）
```

**Step 4: 更新 architecture.md**

更新 `memory-bank/architecture.md` 中的目录结构和文件说明，添加 monitor 模块的完整文件列表。

**Step 5: 运行全部测试**

```bash
cd live_dp && python -m pytest tests/monitor/ -v
```

Expected: 全部通过

**Step 6: 提交**

```bash
git add monitor/frontend/dist/ requirements.txt memory-bank/architecture.md
git commit -m "feat(monitor): 构建前端 + 更新依赖和文档"
```

---

## 验证清单

- [ ] `python -m pytest tests/monitor/ -v` — 全部通过
- [ ] `python -m monitor.server` — FastAPI 启动无报错
- [ ] `curl http://localhost:8777/api/batches` — 返回 `{"batches":[]}`
- [ ] 浏览器访问 `http://localhost:8777` — 看到 Dashboard 页面
- [ ] 手动执行 `python main.py --mode once` 后再访问 — 能看到批次和账号数据
