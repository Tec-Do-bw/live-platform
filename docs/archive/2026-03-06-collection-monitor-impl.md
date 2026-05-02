# Collection Monitor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an embedded collection monitoring system that tracks API collection completeness per account/room, with a FastAPI backend and Vue3 dashboard.

**Architecture:** Hook into `BaseLiveCrawler.send_api_request()` to record every API call to SQLite. After each batch completes, generate a completeness matrix. Serve results via FastAPI REST API + Vue3 SPA.

**Tech Stack:** Python 3.12 / FastAPI / SQLite / Vue3 / Element Plus / Vite

---

## Phase 1: Foundation (Tasks 1-3)

### Task 1: SQLite Database Module

**Files:**
- Create: `live_dp/monitor/__init__.py`
- Create: `live_dp/monitor/db.py`
- Create: `live_dp/monitor/data/` (directory, gitignored)
- Test: `live_dp/tests/monitor/test_db.py`

**Step 1: Create directory structure**

```bash
cd live_dp
mkdir -p monitor/data monitor/api tests/monitor
touch monitor/__init__.py monitor/api/__init__.py tests/__init__.py tests/monitor/__init__.py
```

Add to `.gitignore`:
```
monitor/data/*.db
```

**Step 2: Write the failing test**

```python
# live_dp/tests/monitor/test_db.py
import sqlite3
import tempfile
import os
import pytest

from monitor.db import init_db, get_connection


def test_init_db_creates_tables():
    """init_db should create collection_batches and collection_records tables."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_monitor.db")
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "collection_batches" in tables
        assert "collection_records" in tables


def test_init_db_idempotent():
    """Calling init_db twice should not raise."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_monitor.db")
        init_db(db_path)
        init_db(db_path)  # Should not raise


def test_get_connection_returns_working_connection():
    """get_connection should return a usable sqlite3 connection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_monitor.db")
        init_db(db_path)
        conn = get_connection(db_path)
        cursor = conn.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1
        conn.close()
```

**Step 3: Run test to verify it fails**

Run: `cd live_dp && python -m pytest tests/monitor/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'monitor.db'`

**Step 4: Implement db.py**

```python
# live_dp/monitor/db.py
"""SQLite database initialization and connection for collection monitor."""

import sqlite3
from pathlib import Path

_DEFAULT_DB_PATH = Path(__file__).parent / "data" / "monitor.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT UNIQUE NOT NULL,
    platform TEXT NOT NULL,
    mode TEXT NOT NULL,
    total_accounts INTEGER DEFAULT 0,
    success_accounts INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL,
    group_name TEXT DEFAULT '',
    room_id TEXT DEFAULT '',
    api_type TEXT NOT NULL,
    api_url TEXT NOT NULL,
    status TEXT DEFAULT 'success',
    response_size INTEGER DEFAULT 0,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(batch_id, account_id, room_id, api_type)
);

CREATE INDEX IF NOT EXISTS idx_records_batch ON collection_records(batch_id);
CREATE INDEX IF NOT EXISTS idx_records_account ON collection_records(batch_id, account_id);
"""


def init_db(db_path: str | None = None) -> None:
    """Initialize the SQLite database with the monitoring schema.

    Args:
        db_path: Path to the SQLite database file. Defaults to monitor/data/monitor.db.
    """
    path = Path(db_path) if db_path else _DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    conn.close()


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode enabled.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        sqlite3.Connection configured with row_factory and WAL mode.
    """
    path = str(db_path) if db_path else str(_DEFAULT_DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
```

**Step 5: Run test to verify it passes**

Run: `cd live_dp && python -m pytest tests/monitor/test_db.py -v`
Expected: 3 PASSED

**Step 6: Commit**

```bash
git add live_dp/monitor/ live_dp/tests/
git commit -m "feat(monitor): add SQLite database module with schema init"
```

---

### Task 2: API Classifier

**Files:**
- Create: `live_dp/monitor/classifier.py`
- Test: `live_dp/tests/monitor/test_classifier.py`

**Step 1: Write the failing tests**

```python
# live_dp/tests/monitor/test_classifier.py
import json
import pytest

from monitor.classifier import classify_api, ACCOUNT_API_TYPES, ROOM_API_TYPES


class TestClassifyApiByUrl:
    """Test URL-only matching rules."""

    def test_live_list(self):
        url = "https://shop.tiktok.com/api/v2/insights/creator/live/list?page=1"
        assert classify_api(url, None) == "live_list"

    def test_account_info(self):
        url = "https://shop.tiktok.com/api/v1/streamer_desktop/account_info/get"
        assert classify_api(url, None) == "account_info"

    def test_room_core_stats(self):
        url = "https://shop.tiktok.com/liveroom/recap/core/stats?room_id=123"
        assert classify_api(url, None) == "room_core_stats"

    def test_room_product_list(self):
        url = "https://shop.tiktok.com/recap/product/list?room_id=123"
        assert classify_api(url, None) == "room_product_list"

    def test_room_traffic_conversion(self):
        url = "https://shop.tiktok.com/workbench/live/detail/core/stats"
        assert classify_api(url, None) == "room_traffic_conversion"

    def test_room_viewer_portrait(self):
        url = "https://shop.tiktok.com/recap/viewer/source/stats"
        assert classify_api(url, None) == "room_viewer_portrait"

    def test_room_traffic_source(self):
        url = "https://shop.tiktok.com/workbench/live/detail/source/new"
        assert classify_api(url, None) == "room_traffic_source"

    def test_room_replay(self):
        url = "https://livecenter.tiktok.com/webcast/room/replay/info"
        assert classify_api(url, None) == "room_replay"

    def test_unknown_url(self):
        url = "https://shop.tiktok.com/some/other/api"
        assert classify_api(url, None) is None


class TestClassifyApiByParams:
    """Test parameter-based matching for /live/stats and /trend/chart."""

    def test_live_stats_7d(self):
        url = "https://shop.tiktok.com/api/v2/insights/creator/live/stats"
        body = json.dumps({"params": [{"period": 32}]})
        assert classify_api(url, body) == "live_stats_7d"

    def test_live_stats_yesterday(self):
        url = "https://shop.tiktok.com/api/v2/insights/creator/live/stats"
        body = json.dumps({"params": [{"period": 2, "stats_types": [11, 115]}]})
        assert classify_api(url, body) == "live_stats_yesterday"

    def test_data_overview(self):
        url = "https://shop.tiktok.com/api/v2/insights/creator/live/stats"
        body = json.dumps({"params": [{"stats_types": [100, 101, 121]}]})
        assert classify_api(url, body) == "data_overview"

    def test_room_trend_gmv(self):
        url = "https://shop.tiktok.com/recap/trend/chart"
        body = json.dumps({"params": [{"stats_types": [52]}]})
        assert classify_api(url, body) == "room_trend_gmv"

    def test_room_trend_traffic(self):
        url = "https://shop.tiktok.com/recap/trend/chart"
        body = json.dumps({"params": [{"stats_types": [60, 61]}]})
        assert classify_api(url, body) == "room_trend_traffic"

    def test_room_trend_content(self):
        url = "https://shop.tiktok.com/recap/trend/chart"
        body = json.dumps({"params": [{"stats_types": [1, 2, 3]}]})
        assert classify_api(url, body) == "room_trend_content"


class TestApiTypeSets:
    """Verify the exported type sets are correct."""

    def test_account_api_count(self):
        assert len(ACCOUNT_API_TYPES) == 5

    def test_room_api_count(self):
        assert len(ROOM_API_TYPES) == 9
```

**Step 2: Run test to verify it fails**

Run: `cd live_dp && python -m pytest tests/monitor/test_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement classifier.py**

```python
# live_dp/monitor/classifier.py
"""API classifier: maps URL + request body to api_type for V1 core metrics."""

import json
from urllib.parse import urlparse

# V1 core api_type definitions
ACCOUNT_API_TYPES = frozenset({
    "live_list",
    "live_stats_7d",
    "live_stats_yesterday",
    "data_overview",
    "account_info",
})

ROOM_API_TYPES = frozenset({
    "room_core_stats",
    "room_trend_gmv",
    "room_product_list",
    "room_traffic_conversion",
    "room_trend_traffic",
    "room_viewer_portrait",
    "room_trend_content",
    "room_traffic_source",
    "room_replay",
})

ALL_API_TYPES = ACCOUNT_API_TYPES | ROOM_API_TYPES

# URL path -> api_type (exact path match, no param disambiguation needed)
_URL_RULES: list[tuple[str, str]] = [
    ("/api/v2/insights/creator/live/list", "live_list"),
    ("/api/v1/streamer_desktop/account_info/get", "account_info"),
    ("/liveroom/recap/core/stats", "room_core_stats"),
    ("/recap/product/list", "room_product_list"),
    ("/workbench/live/detail/core/stats", "room_traffic_conversion"),
    ("/recap/viewer/source/stats", "room_viewer_portrait"),
    ("/workbench/live/detail/source/new", "room_traffic_source"),
    ("webcast/room/replay/info", "room_replay"),
]

# Stats type sets for /live/stats disambiguation
_DATA_OVERVIEW_TYPES = {100, 101, 121}
# Stats type sets for /trend/chart disambiguation
_GMV_TYPES = {52}
_TRAFFIC_TYPES = {60, 61}


def _parse_body(body: str | None) -> dict | None:
    """Safely parse JSON request body string."""
    if not body:
        return None
    try:
        return json.loads(body) if isinstance(body, str) else body
    except (json.JSONDecodeError, TypeError):
        return None


def _get_stats_types(parsed: dict) -> set[int]:
    """Extract stats_types set from parsed request body."""
    params = parsed.get("params", [])
    if not params or not isinstance(params, list):
        return set()
    first = params[0] if isinstance(params[0], dict) else {}
    return set(first.get("stats_types", []))


def _get_period(parsed: dict) -> int | None:
    """Extract period from parsed request body."""
    params = parsed.get("params", [])
    if not params or not isinstance(params, list):
        return None
    first = params[0] if isinstance(params[0], dict) else {}
    return first.get("period")


def _classify_live_stats(body: str | None) -> str | None:
    """Classify /api/v2/insights/creator/live/stats by request params."""
    parsed = _parse_body(body)
    if not parsed:
        return None

    period = _get_period(parsed)
    stats_types = _get_stats_types(parsed)

    # period=32 -> live_stats_7d
    if period == 32:
        return "live_stats_7d"

    # stats_types contains data_overview indicators -> data_overview
    if stats_types & _DATA_OVERVIEW_TYPES:
        return "data_overview"

    # period=2 -> live_stats_yesterday
    if period == 2:
        return "live_stats_yesterday"

    return None


def _classify_trend_chart(body: str | None) -> str | None:
    """Classify /recap/trend/chart by stats_types in request body."""
    parsed = _parse_body(body)
    if not parsed:
        return "room_trend_content"  # fallback

    stats_types = _get_stats_types(parsed)

    if stats_types & _GMV_TYPES:
        return "room_trend_gmv"
    if stats_types & _TRAFFIC_TYPES:
        return "room_trend_traffic"
    return "room_trend_content"


def classify_api(url: str, body: str | None) -> str | None:
    """Classify an API request into a V1 api_type.

    Args:
        url: The full API URL (fromUrl).
        body: The JSON-encoded request body string (extra field), or None.

    Returns:
        The api_type string if matched, None if not a V1 monitored API.
    """
    # Extract path from URL
    parsed_url = urlparse(url)
    path = parsed_url.path

    # Check URL-only rules first
    for pattern, api_type in _URL_RULES:
        if pattern in url:
            return api_type

    # Parameter-based rules
    if "/api/v2/insights/creator/live/stats" in url:
        return _classify_live_stats(body)

    if "/recap/trend/chart" in url:
        return _classify_trend_chart(body)

    return None
```

**Step 4: Run test to verify it passes**

Run: `cd live_dp && python -m pytest tests/monitor/test_classifier.py -v`
Expected: 15 PASSED

**Step 5: Commit**

```bash
git add live_dp/monitor/classifier.py live_dp/tests/monitor/test_classifier.py
git commit -m "feat(monitor): add API classifier for V1 core metrics"
```

---

### Task 3: Collection Tracker (Monitor Core)

**Files:**
- Create: `live_dp/monitor/tracker.py`
- Test: `live_dp/tests/monitor/test_tracker.py`

**Step 1: Write the failing tests**

```python
# live_dp/tests/monitor/test_tracker.py
import tempfile
import os
import pytest

from monitor.db import init_db
from monitor.tracker import CollectionMonitor


@pytest.fixture
def monitor(tmp_path):
    """Create a CollectionMonitor with a temp database."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return CollectionMonitor(db_path=db_path, batch_id="2026-03-06_20:00", platform="tiktok")


class TestCollectionMonitor:

    def test_record_success(self, monitor):
        monitor.record(
            account_id="browser_001",
            room_id="",
            api_type="live_list",
            api_url="https://example.com/api/v2/insights/creator/live/list",
            status="success",
            response_size=1024,
        )
        # Query to verify
        from monitor.db import get_connection
        conn = get_connection(monitor.db_path)
        row = conn.execute(
            "SELECT * FROM collection_records WHERE account_id = ?", ("browser_001",)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["api_type"] == "live_list"
        assert row["status"] == "success"

    def test_record_upsert_on_duplicate(self, monitor):
        """Second record with same key should update (INSERT OR REPLACE)."""
        monitor.record("browser_001", "", "live_list", "https://ex.com/a", "failed", 0)
        monitor.record("browser_001", "", "live_list", "https://ex.com/a", "success", 512)

        from monitor.db import get_connection
        conn = get_connection(monitor.db_path)
        rows = conn.execute(
            "SELECT * FROM collection_records WHERE account_id = ? AND api_type = ?",
            ("browser_001", "live_list"),
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["status"] == "success"

    def test_record_with_room_id(self, monitor):
        monitor.record("browser_001", "room_123", "room_core_stats", "https://ex.com", "success", 2048)

        from monitor.db import get_connection
        conn = get_connection(monitor.db_path)
        row = conn.execute(
            "SELECT * FROM collection_records WHERE room_id = ?", ("room_123",)
        ).fetchone()
        conn.close()
        assert row["api_type"] == "room_core_stats"
        assert row["room_id"] == "room_123"

    def test_record_does_not_raise_on_error(self, monitor):
        """record() should not raise even with bad data (non-blocking)."""
        # This should not raise - it logs the error internally
        monitor.record("browser_001", "", "live_list", "https://ex.com", "success", 0)
        # Duplicate with same unique key but we already tested upsert above
        # Test with None values that might cause issues
        monitor.record("browser_001", "", "live_list", None, "success", 0)

    def test_start_batch(self, monitor):
        monitor.start_batch(mode="once", total_accounts=5)

        from monitor.db import get_connection
        conn = get_connection(monitor.db_path)
        row = conn.execute(
            "SELECT * FROM collection_batches WHERE batch_id = ?",
            ("2026-03-06_20:00",),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["platform"] == "tiktok"
        assert row["mode"] == "once"
        assert row["total_accounts"] == 5

    def test_finish_batch(self, monitor):
        monitor.start_batch(mode="once", total_accounts=3)
        monitor.finish_batch(success_accounts=2)

        from monitor.db import get_connection
        conn = get_connection(monitor.db_path)
        row = conn.execute(
            "SELECT * FROM collection_batches WHERE batch_id = ?",
            ("2026-03-06_20:00",),
        ).fetchone()
        conn.close()
        assert row["success_accounts"] == 2
        assert row["finished_at"] is not None
```

**Step 2: Run test to verify it fails**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement tracker.py**

```python
# live_dp/monitor/tracker.py
"""CollectionMonitor: records API collection events to SQLite."""

import sqlite3
from datetime import datetime

from monitor.db import get_connection


class CollectionMonitor:
    """Embedded collection recorder that hooks into the crawler pipeline.

    Usage:
        monitor = CollectionMonitor(db_path, batch_id, platform)
        monitor.start_batch(mode="once", total_accounts=10)
        # ... during crawling:
        monitor.record(account_id, room_id, api_type, api_url, status, response_size)
        # ... after crawling:
        monitor.finish_batch(success_accounts=8)
    """

    def __init__(self, db_path: str, batch_id: str, platform: str):
        self.db_path = db_path
        self.batch_id = batch_id
        self.platform = platform

    def record(
        self,
        account_id: str,
        room_id: str,
        api_type: str,
        api_url: str,
        status: str,
        response_size: int,
        group_name: str = "",
    ) -> None:
        """Record a single API collection event. Non-blocking: exceptions are swallowed."""
        try:
            conn = get_connection(self.db_path)
            conn.execute(
                """INSERT OR REPLACE INTO collection_records
                   (batch_id, platform, account_id, group_name, room_id,
                    api_type, api_url, status, response_size, collected_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.batch_id,
                    self.platform,
                    account_id,
                    group_name,
                    room_id,
                    api_type,
                    str(api_url) if api_url else "",
                    status,
                    response_size,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # Non-blocking: do not interfere with crawling

    def start_batch(self, mode: str, total_accounts: int) -> None:
        """Record the start of a collection batch."""
        try:
            conn = get_connection(self.db_path)
            conn.execute(
                """INSERT OR IGNORE INTO collection_batches
                   (batch_id, platform, mode, total_accounts, started_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    self.batch_id,
                    self.platform,
                    mode,
                    total_accounts,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def finish_batch(self, success_accounts: int) -> None:
        """Record the end of a collection batch."""
        try:
            conn = get_connection(self.db_path)
            conn.execute(
                """UPDATE collection_batches
                   SET success_accounts = ?, finished_at = ?
                   WHERE batch_id = ?""",
                (success_accounts, datetime.now().isoformat(), self.batch_id),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
```

**Step 4: Run test to verify it passes**

Run: `cd live_dp && python -m pytest tests/monitor/test_tracker.py -v`
Expected: 6 PASSED

**Step 5: Commit**

```bash
git add live_dp/monitor/tracker.py live_dp/tests/monitor/test_tracker.py
git commit -m "feat(monitor): add CollectionMonitor tracker with batch lifecycle"
```

---

## Phase 2: Crawler Integration (Tasks 4-6)

> **验证策略：Task 4-5 不写单元测试，改为编码后通过实际采集验证 monitor.db 数据写入。Task 6 保留 TDD。**

### Task 4: Hook into send_api_request

**Files:**
- Modify: `live_dp/spiders/base.py:27-57` (add monitor attribute to `__init__`)
- Modify: `live_dp/spiders/base.py:204-295` (add monitor hook after send)

**Context:** `send_api_request` receives a `message` dict with:
- `message["fromUrl"]` = the API URL
- `message["extra"]` = JSON-encoded request body (or None)
- `message["request"]["response"]` = response body string

The hook must:
1. Call `classify_api(fromUrl, extra)` to get `api_type`
2. If `api_type` is not None, call `monitor.record()`
3. Extract `room_id` from URL query params if present

**Step 1: Add monitor attribute to BaseLiveCrawler.__init__**

In `live_dp/spiders/base.py`, add to `__init__` (after line 57):

```python
# Monitor (injected externally, defaults to None = monitoring disabled)
self.monitor = None
```

**Step 2: Add monitor hook to send_api_request**

In `live_dp/spiders/base.py`, add at the **beginning** of `send_api_request` method (after the docstring, before the `if not Settings.DATA_SERVER_CONFIG.get("enabled")` check):

```python
# --- Monitor hook: record API collection ---
self._monitor_record(message)
```

Then add a new private method to `BaseLiveCrawler`:

```python
def _monitor_record(self, message: Dict[str, Any]) -> None:
    """Record API call to monitor if monitoring is enabled. Non-blocking."""
    if not self.monitor:
        return
    try:
        from monitor.classifier import classify_api
        from urllib.parse import urlparse, parse_qs

        from_url = message.get("fromUrl", "")
        extra = message.get("extra")
        api_type = classify_api(from_url, extra)

        if api_type is None:
            return

        # Extract room_id from URL query params (roomId or room_id)
        parsed = urlparse(from_url)
        qs = parse_qs(parsed.query)
        room_id = qs.get("roomId", qs.get("room_id", [""]))[0]

        # Determine status based on response size
        response_str = message.get("request", {}).get("response", "")
        response_size = len(response_str) if response_str else 0
        status = "empty" if response_size < 50 else "success"

        self.monitor.record(
            account_id=self.browser_id,
            room_id=room_id,
            api_type=api_type,
            api_url=from_url,
            status=status,
            response_size=response_size,
            group_name=self.group_name,
        )
    except Exception:
        pass  # Non-blocking
```

**Step 3: Verify import syntax**

```bash
cd live_dp && python -c "from spiders.base import BaseLiveCrawler; print('OK')"
```
Expected: `OK`（不报 SyntaxError 即可，不需要跑 pytest）

**Step 4: Commit**

```bash
git add live_dp/spiders/base.py
git commit -m "feat(monitor): hook monitor recording into send_api_request"
```

---

### Task 5: Inject Monitor into Crawl Pipeline

**Files:**
- Modify: `live_dp/main.py:70-237` (inject monitor in `run_once`)
- Modify: `live_dp/scheduler/task_scheduler.py:76-235` (inject monitor in `execute_crawl_task`)

**Context:** We need to:
1. Generate `batch_id` = `datetime.now().strftime("%Y-%m-%d_%H:%M")`
2. Create `CollectionMonitor` instance
3. Call `monitor.start_batch()` before crawling
4. Assign `crawler.monitor = monitor` after creating each crawler
5. Call `monitor.finish_batch()` after all accounts done

**Step 1: Modify run_once() in main.py**

At the top of `run_once()`, after line 81 (`logger.info`), add:

```python
# Initialize collection monitor
from datetime import datetime as _dt
from monitor.db import init_db
from monitor.tracker import CollectionMonitor
from pathlib import Path as _Path

_monitor_db = str(_Path(__file__).parent / "monitor" / "data" / "monitor.db")
init_db(_monitor_db)
_batch_id = _dt.now().strftime("%Y-%m-%d_%H:%M")
_mode = "full" if full_collection else "once"
```

After the platform loop starts and `accounts` is resolved (before the crawling loop), add:

```python
# Create monitor for this platform
monitor = CollectionMonitor(db_path=_monitor_db, batch_id=_batch_id, platform=platform)
monitor.start_batch(mode=_mode, total_accounts=len(accounts))
```

In the serial crawling loop, after `crawler = LiveCrawler(...)` (line ~194), add:

```python
crawler.monitor = monitor
```

In the concurrent mode's `crawl_single_account`, the monitor cannot be pickled across processes. For now, skip monitor injection in concurrent mode (add a comment: `# TODO: monitor not supported in concurrent mode yet`).

After the platform results are tallied (after line ~224), add:

```python
monitor.finish_batch(success_accounts=platform_success)
```

**Step 2: Modify execute_crawl_task() in task_scheduler.py**

Same pattern. At the top of `execute_crawl_task()`, after line 81:

```python
# Initialize collection monitor
from datetime import datetime as _dt
from monitor.db import init_db
from monitor.tracker import CollectionMonitor
from pathlib import Path as _Path

_monitor_db = str(_Path(__file__).resolve().parent.parent / "monitor" / "data" / "monitor.db")
init_db(_monitor_db)
_batch_id = _dt.now().strftime("%Y-%m-%d_%H:%M")
```

Inside the platform loop, after accounts are resolved, before the crawling loop:

```python
monitor = CollectionMonitor(db_path=_monitor_db, batch_id=_batch_id, platform=platform)
monitor.start_batch(mode="scheduler", total_accounts=len(accounts))
```

After `crawler = LiveCrawler(...)` (line ~168):

```python
crawler.monitor = monitor
```

After the platform result tally:

```python
monitor.finish_batch(success_accounts=platform_success)
```

**Step 3: Verify import syntax**

```bash
cd live_dp && python -c "import main; print('main OK')"
cd live_dp && python -c "from scheduler.task_scheduler import TaskScheduler; print('scheduler OK')"
```
Expected: 两个都输出 OK（不报 SyntaxError / ImportError）

**Step 4: Commit**

```bash
git add live_dp/main.py live_dp/scheduler/task_scheduler.py
git commit -m "feat(monitor): inject CollectionMonitor into crawl pipeline"
```

**Step 5: 端到端验证（与 Task 13 合并执行）**

Task 4+5 的真正验证在 Task 13（手动采集验证）中完成：
- 执行一次实际采集（或 seed 脚本）
- 检查 `monitor/data/monitor.db` 中 `collection_batches` 和 `collection_records` 表是否有数据
- 验证 `api_type` 分类是否正确

---

### Task 6: Completeness Reporter

**Files:**
- Create: `live_dp/monitor/reporter.py`
- Test: `live_dp/tests/monitor/test_reporter.py`

**Step 1: Write the failing tests**

```python
# live_dp/tests/monitor/test_reporter.py
import pytest

from monitor.db import init_db, get_connection
from monitor.tracker import CollectionMonitor
from monitor.reporter import MonitorReporter
from monitor.classifier import ACCOUNT_API_TYPES, ROOM_API_TYPES


@pytest.fixture
def setup_db(tmp_path):
    """Create a DB with some test records."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    monitor = CollectionMonitor(db_path=db_path, batch_id="2026-03-06_20:00", platform="tiktok")
    monitor.start_batch(mode="once", total_accounts=1)

    # Record all 5 account-level APIs for account_001
    for api_type in ACCOUNT_API_TYPES:
        monitor.record("account_001", "", api_type, f"https://ex.com/{api_type}", "success", 1000)

    # Record 7 of 9 room-level APIs for room_A (missing room_replay, room_traffic_source)
    for api_type in list(ROOM_API_TYPES)[:7]:
        monitor.record("account_001", "room_A", api_type, f"https://ex.com/{api_type}", "success", 500)

    monitor.finish_batch(success_accounts=1)

    return db_path


def test_generate_batch_report(setup_db):
    reporter = MonitorReporter(db_path=setup_db)
    report = reporter.generate_batch_report("2026-03-06_20:00")

    assert "account_001" in report
    acct = report["account_001"]

    # All 5 account APIs should be True
    for api_type in ACCOUNT_API_TYPES:
        assert acct["account_apis"][api_type] is True

    # room_A should have some True, some False
    assert "room_A" in acct["rooms"]
    room = acct["rooms"]["room_A"]
    assert sum(1 for v in room.values() if v) == 7
    assert sum(1 for v in room.values() if not v) == 2


def test_account_completeness_rate(setup_db):
    reporter = MonitorReporter(db_path=setup_db)
    report = reporter.generate_batch_report("2026-03-06_20:00")

    acct = report["account_001"]
    # 5 account APIs + 7 room APIs = 12 collected out of 5 + 9 = 14 total
    total = len(ACCOUNT_API_TYPES) + len(ROOM_API_TYPES)
    collected = sum(1 for v in acct["account_apis"].values() if v) + \
                sum(1 for v in acct["rooms"]["room_A"].values() if v)
    assert collected == 12
    assert total == 14


def test_empty_batch(setup_db):
    reporter = MonitorReporter(db_path=setup_db)
    report = reporter.generate_batch_report("nonexistent_batch")
    assert report == {}
```

**Step 2: Run test to verify it fails**

Run: `cd live_dp && python -m pytest tests/monitor/test_reporter.py -v`
Expected: FAIL

**Step 3: Implement reporter.py**

```python
# live_dp/monitor/reporter.py
"""MonitorReporter: generates completeness reports from collection records."""

from monitor.db import get_connection
from monitor.classifier import ACCOUNT_API_TYPES, ROOM_API_TYPES


class MonitorReporter:
    """Generates completeness matrix for a batch."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def generate_batch_report(self, batch_id: str) -> dict:
        """Generate completeness report for a batch.

        Returns:
            {
                account_id: {
                    "account_apis": {api_type: True/False, ...},
                    "rooms": {
                        room_id: {api_type: True/False, ...},
                        ...
                    }
                }
            }
        """
        conn = get_connection(self.db_path)
        rows = conn.execute(
            "SELECT account_id, room_id, api_type, status FROM collection_records WHERE batch_id = ?",
            (batch_id,),
        ).fetchall()
        conn.close()

        if not rows:
            return {}

        # Build a lookup: (account_id, room_id, api_type) -> status
        collected = {}
        accounts = set()
        rooms_by_account: dict[str, set[str]] = {}

        for row in rows:
            account_id = row["account_id"]
            room_id = row["room_id"]
            api_type = row["api_type"]
            status = row["status"]

            accounts.add(account_id)
            collected[(account_id, room_id, api_type)] = status

            if room_id:
                rooms_by_account.setdefault(account_id, set()).add(room_id)

        # Build report
        report = {}
        for account_id in sorted(accounts):
            acct_report = {
                "account_apis": {},
                "rooms": {},
            }

            # Account-level completeness
            for api_type in ACCOUNT_API_TYPES:
                status = collected.get((account_id, "", api_type))
                acct_report["account_apis"][api_type] = status is not None and status != "failed"

            # Room-level completeness
            for room_id in sorted(rooms_by_account.get(account_id, [])):
                room_report = {}
                for api_type in ROOM_API_TYPES:
                    status = collected.get((account_id, room_id, api_type))
                    room_report[api_type] = status is not None and status != "failed"
                acct_report["rooms"][room_id] = room_report

            report[account_id] = acct_report

        return report
```

**Step 4: Run test to verify it passes**

Run: `cd live_dp && python -m pytest tests/monitor/test_reporter.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add live_dp/monitor/reporter.py live_dp/tests/monitor/test_reporter.py
git commit -m "feat(monitor): add MonitorReporter for completeness matrix"
```

---

## Phase 3: Backend API (Tasks 7-8)

> **验证策略：Task 7 先编码 + 手动启动验证，Task 8 补写 TestClient 测试（TDD 补测）。**

### Task 7: FastAPI Server + REST Routes

**Files:**
- Create: `live_dp/monitor/server.py`
- Create: `live_dp/monitor/api/batches.py`
- Create: `live_dp/monitor/api/accounts.py`
- Create: `live_dp/monitor/api/rooms.py`

**Step 1: Install FastAPI dependency**

```bash
cd live_dp && pip install fastapi uvicorn
```

Add to `requirements.txt`:
```
fastapi
uvicorn
```

**Step 2: Implement API routes**

```python
# live_dp/monitor/api/batches.py
"""Batch-related API routes."""

from fastapi import APIRouter, Query
from monitor.db import get_connection
from monitor.reporter import MonitorReporter
from monitor.classifier import ACCOUNT_API_TYPES, ROOM_API_TYPES
from pathlib import Path

router = APIRouter(prefix="/api/batches", tags=["batches"])

_DB_PATH = str(Path(__file__).parent.parent / "data" / "monitor.db")


@router.get("")
def list_batches(limit: int = Query(20, le=100)):
    """List recent collection batches."""
    conn = get_connection(_DB_PATH)
    rows = conn.execute(
        "SELECT * FROM collection_batches ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.get("/{batch_id}/summary")
def batch_summary(batch_id: str):
    """Get completeness summary for a batch."""
    reporter = MonitorReporter(db_path=_DB_PATH)
    report = reporter.generate_batch_report(batch_id)

    accounts_summary = []
    for account_id, data in report.items():
        account_total = len(ACCOUNT_API_TYPES)
        account_collected = sum(1 for v in data["account_apis"].values() if v)

        room_total = 0
        room_collected = 0
        for room_data in data["rooms"].values():
            room_total += len(ROOM_API_TYPES)
            room_collected += sum(1 for v in room_data.values() if v)

        total = account_total + room_total
        collected = account_collected + room_collected
        rate = round(collected / total * 100, 1) if total > 0 else 0

        accounts_summary.append({
            "account_id": account_id,
            "total_apis": total,
            "collected_apis": collected,
            "completeness_rate": rate,
            "room_count": len(data["rooms"]),
        })

    return {
        "batch_id": batch_id,
        "total_accounts": len(report),
        "accounts": accounts_summary,
    }
```

```python
# live_dp/monitor/api/accounts.py
"""Account-related API routes."""

from fastapi import APIRouter
from monitor.db import get_connection
from monitor.reporter import MonitorReporter
from monitor.classifier import ACCOUNT_API_TYPES, ROOM_API_TYPES
from pathlib import Path

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

_DB_PATH = str(Path(__file__).parent.parent / "data" / "monitor.db")


@router.get("/{batch_id}/{account_id}")
def account_detail(batch_id: str, account_id: str):
    """Get account-level API status and room list."""
    reporter = MonitorReporter(db_path=_DB_PATH)
    report = reporter.generate_batch_report(batch_id)

    if account_id not in report:
        return {"error": "Account not found", "account_id": account_id}

    data = report[account_id]

    rooms = []
    for room_id, room_data in data["rooms"].items():
        total = len(ROOM_API_TYPES)
        collected = sum(1 for v in room_data.values() if v)
        rooms.append({
            "room_id": room_id,
            "total_apis": total,
            "collected_apis": collected,
            "completeness_rate": round(collected / total * 100, 1) if total > 0 else 0,
        })

    return {
        "account_id": account_id,
        "batch_id": batch_id,
        "account_apis": data["account_apis"],
        "rooms": rooms,
    }
```

```python
# live_dp/monitor/api/rooms.py
"""Room-related API routes."""

from fastapi import APIRouter
from monitor.db import get_connection
from monitor.reporter import MonitorReporter
from pathlib import Path

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

_DB_PATH = str(Path(__file__).parent.parent / "data" / "monitor.db")


@router.get("/{batch_id}/{account_id}/{room_id}")
def room_detail(batch_id: str, account_id: str, room_id: str):
    """Get room-level API checklist."""
    reporter = MonitorReporter(db_path=_DB_PATH)
    report = reporter.generate_batch_report(batch_id)

    if account_id not in report:
        return {"error": "Account not found"}

    rooms = report[account_id].get("rooms", {})
    if room_id not in rooms:
        return {"error": "Room not found"}

    # Also fetch raw records for detail
    conn = get_connection(_DB_PATH)
    records = conn.execute(
        """SELECT api_type, api_url, status, response_size, collected_at
           FROM collection_records
           WHERE batch_id = ? AND account_id = ? AND room_id = ?""",
        (batch_id, account_id, room_id),
    ).fetchall()
    conn.close()

    return {
        "batch_id": batch_id,
        "account_id": account_id,
        "room_id": room_id,
        "checklist": rooms[room_id],
        "records": [dict(r) for r in records],
    }
```

**Step 3: Implement server.py**

```python
# live_dp/monitor/server.py
"""FastAPI server for collection monitor dashboard."""

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from monitor.db import init_db
from monitor.api.batches import router as batches_router
from monitor.api.accounts import router as accounts_router
from monitor.api.rooms import router as rooms_router

# Initialize database
_DB_PATH = str(Path(__file__).parent / "data" / "monitor.db")
init_db(_DB_PATH)

app = FastAPI(title="LiveLab Collection Monitor", version="1.0.0")

# CORS for dev mode
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(batches_router)
app.include_router(accounts_router)
app.include_router(rooms_router)

# Serve frontend static files (after build)
_frontend_dist = Path(__file__).parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8777)
```

**Step 4: Verify server starts**

```bash
cd live_dp && python -m monitor.server
```
Expected: Server starts at http://0.0.0.0:8777, Ctrl+C to stop.

**Step 5: Commit**

```bash
git add live_dp/monitor/server.py live_dp/monitor/api/
git commit -m "feat(monitor): add FastAPI server with REST API routes"
```

---

### Task 8: Test API Endpoints

**Files:**
- Create: `live_dp/tests/monitor/test_api.py`

**Step 1: Write API tests**

```python
# live_dp/tests/monitor/test_api.py
import pytest
from fastapi.testclient import TestClient

from monitor.db import init_db
from monitor.tracker import CollectionMonitor
from monitor.classifier import ACCOUNT_API_TYPES, ROOM_API_TYPES


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client with a temp database."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    # Seed data
    monitor = CollectionMonitor(db_path=db_path, batch_id="2026-03-06_20:00", platform="tiktok")
    monitor.start_batch(mode="once", total_accounts=1)
    for api_type in ACCOUNT_API_TYPES:
        monitor.record("acct_1", "", api_type, f"https://ex.com/{api_type}", "success", 1000)
    for api_type in list(ROOM_API_TYPES)[:5]:
        monitor.record("acct_1", "room_1", api_type, f"https://ex.com/{api_type}", "success", 500)
    monitor.finish_batch(success_accounts=1)

    # Patch DB paths in all route modules
    monkeypatch.setattr("monitor.api.batches._DB_PATH", db_path)
    monkeypatch.setattr("monitor.api.accounts._DB_PATH", db_path)
    monkeypatch.setattr("monitor.api.rooms._DB_PATH", db_path)
    monkeypatch.setattr("monitor.server._DB_PATH", db_path)

    from monitor.server import app
    return TestClient(app)


def test_list_batches(client):
    resp = client.get("/api/batches")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["batch_id"] == "2026-03-06_20:00"


def test_batch_summary(client):
    resp = client.get("/api/batches/2026-03-06_20:00/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_accounts"] == 1
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["account_id"] == "acct_1"


def test_account_detail(client):
    resp = client.get("/api/accounts/2026-03-06_20:00/acct_1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["account_id"] == "acct_1"
    assert len(data["rooms"]) == 1


def test_room_detail(client):
    resp = client.get("/api/rooms/2026-03-06_20:00/acct_1/room_1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["room_id"] == "room_1"
    assert "checklist" in data
```

**Step 2: Run tests**

Run: `cd live_dp && python -m pytest tests/monitor/test_api.py -v`
Expected: 4 PASSED

**Step 3: Commit**

```bash
git add live_dp/tests/monitor/test_api.py
git commit -m "test(monitor): add FastAPI endpoint tests"
```

---

## Phase 4: Frontend Dashboard (Tasks 9-12)

> **验证策略：不写前端单元测试。每个 Task 完成后 `npm run dev` + 浏览器目视验证。**

### Task 9: Vue3 Project Init

**Files:**
- Create: `live_dp/monitor/frontend/` (Vite + Vue3 project)

**Step 1: Scaffold Vue3 project**

```bash
cd live_dp/monitor
npm create vite@latest frontend -- --template vue
cd frontend
npm install
npm install element-plus vue-router@4 axios
```

**Step 2: Configure Vite proxy for dev**

```javascript
// live_dp/monitor/frontend/vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8777',
        changeOrigin: true,
      },
    },
  },
})
```

**Step 3: Setup main.js with Element Plus and Router**

```javascript
// live_dp/monitor/frontend/src/main.js
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(ElementPlus)
app.use(router)
app.mount('#app')
```

```javascript
// live_dp/monitor/frontend/src/router/index.js
import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
  { path: '/account/:batchId/:accountId', name: 'AccountDetail', component: () => import('../views/AccountDetail.vue') },
  { path: '/room/:batchId/:accountId/:roomId', name: 'RoomDetail', component: () => import('../views/RoomDetail.vue') },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
```

**Step 4: Create App.vue shell**

```vue
<!-- live_dp/monitor/frontend/src/App.vue -->
<script setup>
</script>

<template>
  <el-container style="min-height: 100vh">
    <el-header style="background: #1a1a2e; color: #fff; display: flex; align-items: center;">
      <h2 style="margin: 0; cursor: pointer;" @click="$router.push('/')">LiveLab Monitor</h2>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>
```

**Step 5: Create placeholder views**

```vue
<!-- live_dp/monitor/frontend/src/views/Dashboard.vue -->
<script setup>
</script>

<template>
  <div>
    <h3>Dashboard (TODO)</h3>
  </div>
</template>
```

```vue
<!-- live_dp/monitor/frontend/src/views/AccountDetail.vue -->
<script setup>
</script>

<template>
  <div>
    <h3>Account Detail (TODO)</h3>
  </div>
</template>
```

```vue
<!-- live_dp/monitor/frontend/src/views/RoomDetail.vue -->
<script setup>
</script>

<template>
  <div>
    <h3>Room Detail (TODO)</h3>
  </div>
</template>
```

**Step 6: Verify dev server starts**

```bash
cd live_dp/monitor/frontend && npm run dev
```
Expected: Vite dev server at http://localhost:5173

**Step 7: Commit**

```bash
git add live_dp/monitor/frontend/
git commit -m "feat(monitor): scaffold Vue3 + Element Plus frontend"
```

---

### Task 10: Dashboard Page

**Files:**
- Modify: `live_dp/monitor/frontend/src/views/Dashboard.vue`

**Step 1: Implement Dashboard**

```vue
<!-- live_dp/monitor/frontend/src/views/Dashboard.vue -->
<script setup>
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'

const batches = ref([])
const selectedBatch = ref('')
const summary = ref(null)
const loading = ref(false)

onMounted(async () => {
  const { data } = await axios.get('/api/batches')
  batches.value = data
  if (data.length > 0) {
    selectedBatch.value = data[0].batch_id
  }
})

watch(selectedBatch, async (batchId) => {
  if (!batchId) return
  loading.value = true
  const { data } = await axios.get(`/api/batches/${encodeURIComponent(batchId)}/summary`)
  summary.value = data
  loading.value = false
})

function rateColor(rate) {
  if (rate >= 100) return 'success'
  if (rate >= 80) return 'warning'
  return 'danger'
}
</script>

<template>
  <div>
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="8">
        <el-select v-model="selectedBatch" placeholder="Select batch" style="width: 100%">
          <el-option
            v-for="b in batches"
            :key="b.batch_id"
            :label="`${b.batch_id} (${b.platform})`"
            :value="b.batch_id"
          />
        </el-select>
      </el-col>
    </el-row>

    <el-table :data="summary?.accounts || []" v-loading="loading" stripe>
      <el-table-column prop="account_id" label="Account ID" />
      <el-table-column prop="room_count" label="Rooms" width="100" />
      <el-table-column label="Collected" width="120">
        <template #default="{ row }">
          {{ row.collected_apis }} / {{ row.total_apis }}
        </template>
      </el-table-column>
      <el-table-column label="Completeness" width="200">
        <template #default="{ row }">
          <el-progress
            :percentage="row.completeness_rate"
            :status="rateColor(row.completeness_rate)"
            :stroke-width="16"
            :text-inside="true"
          />
        </template>
      </el-table-column>
      <el-table-column label="Actions" width="120">
        <template #default="{ row }">
          <el-button
            type="primary"
            size="small"
            @click="$router.push(`/account/${encodeURIComponent(selectedBatch)}/${row.account_id}`)"
          >
            Detail
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
```

**Step 2: Browser Verification**

1. 启动后端：`cd live_dp && python -m monitor.server`（需要先有 seed 数据，参考 Task 13）
2. 启动前端：`cd live_dp/monitor/frontend && npm run dev`
3. 打开 http://localhost:5173
4. 验证：批次选择器显示、账号列表渲染、完整率进度条、Detail 按钮跳转

**Step 3: Commit**

```bash
git add live_dp/monitor/frontend/src/views/Dashboard.vue
git commit -m "feat(monitor): implement Dashboard page with batch selector and account table"
```

---

### Task 11: Account Detail Page

**Files:**
- Modify: `live_dp/monitor/frontend/src/views/AccountDetail.vue`

**Step 1: Implement AccountDetail**

```vue
<!-- live_dp/monitor/frontend/src/views/AccountDetail.vue -->
<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const router = useRouter()
const detail = ref(null)
const loading = ref(true)

const ACCOUNT_API_LABELS = {
  live_list: 'Live List',
  live_stats_7d: 'Live Stats 7D',
  live_stats_yesterday: 'Live Stats Yesterday',
  data_overview: 'Data Overview',
  account_info: 'Account Info',
}

onMounted(async () => {
  const { batchId, accountId } = route.params
  const { data } = await axios.get(`/api/accounts/${encodeURIComponent(batchId)}/${accountId}`)
  detail.value = data
  loading.value = false
})

function statusTag(ok) {
  return ok ? 'success' : 'danger'
}

function statusText(ok) {
  return ok ? 'Collected' : 'Missing'
}

function rateColor(rate) {
  if (rate >= 100) return 'success'
  if (rate >= 80) return 'warning'
  return 'danger'
}
</script>

<template>
  <div v-loading="loading">
    <el-page-header @back="router.push('/')" style="margin-bottom: 20px;">
      <template #content>
        Account: {{ detail?.account_id }}
      </template>
    </el-page-header>

    <template v-if="detail">
      <h4>Account-Level APIs</h4>
      <el-row :gutter="12" style="margin-bottom: 24px;">
        <el-col :span="4" v-for="(ok, apiType) in detail.account_apis" :key="apiType">
          <el-card shadow="hover" :body-style="{ padding: '12px', textAlign: 'center' }">
            <el-tag :type="statusTag(ok)" size="large">{{ statusText(ok) }}</el-tag>
            <div style="margin-top: 8px; font-size: 12px; color: #666;">
              {{ ACCOUNT_API_LABELS[apiType] || apiType }}
            </div>
          </el-card>
        </el-col>
      </el-row>

      <h4>Rooms</h4>
      <el-table :data="detail.rooms" stripe>
        <el-table-column prop="room_id" label="Room ID" />
        <el-table-column label="Collected" width="120">
          <template #default="{ row }">
            {{ row.collected_apis }} / {{ row.total_apis }}
          </template>
        </el-table-column>
        <el-table-column label="Completeness" width="200">
          <template #default="{ row }">
            <el-progress
              :percentage="row.completeness_rate"
              :status="rateColor(row.completeness_rate)"
              :stroke-width="16"
              :text-inside="true"
            />
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="120">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click="router.push(`/room/${encodeURIComponent(route.params.batchId)}/${detail.account_id}/${row.room_id}`)"
            >
              Detail
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </div>
</template>
```

**Step 2: Browser Verification**

1. 打开 http://localhost:5173，从 Dashboard 点击某账号 Detail
2. 验证：5 张 API 状态卡片（绿/红）、直播间列表、完整率、Detail 跳转

**Step 3: Commit**

```bash
git add live_dp/monitor/frontend/src/views/AccountDetail.vue
git commit -m "feat(monitor): implement AccountDetail page with API status cards and room table"
```

---

### Task 12: Room Detail Page

**Files:**
- Modify: `live_dp/monitor/frontend/src/views/RoomDetail.vue`

**Step 1: Implement RoomDetail**

```vue
<!-- live_dp/monitor/frontend/src/views/RoomDetail.vue -->
<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const router = useRouter()
const detail = ref(null)
const loading = ref(true)

const ROOM_API_LABELS = {
  room_core_stats: 'Core Stats',
  room_trend_gmv: 'Trend GMV',
  room_product_list: 'Product List',
  room_traffic_conversion: 'Traffic Conversion',
  room_trend_traffic: 'Trend Traffic',
  room_viewer_portrait: 'Viewer Portrait',
  room_trend_content: 'Trend Content',
  room_traffic_source: 'Traffic Source',
  room_replay: 'Replay',
}

onMounted(async () => {
  const { batchId, accountId, roomId } = route.params
  const { data } = await axios.get(
    `/api/rooms/${encodeURIComponent(batchId)}/${accountId}/${roomId}`
  )
  detail.value = data
  loading.value = false
})

function statusIcon(ok) {
  return ok ? 'SuccessFilled' : 'CircleCloseFilled'
}
</script>

<template>
  <div v-loading="loading">
    <el-page-header
      @back="router.push(`/account/${encodeURIComponent(route.params.batchId)}/${route.params.accountId}`)"
      style="margin-bottom: 20px;"
    >
      <template #content>
        Room: {{ detail?.room_id }}
      </template>
    </el-page-header>

    <template v-if="detail">
      <h4>V1 API Checklist</h4>
      <el-table :data="Object.entries(detail.checklist).map(([k, v]) => ({ api_type: k, collected: v }))" stripe>
        <el-table-column label="API Type" width="250">
          <template #default="{ row }">
            {{ ROOM_API_LABELS[row.api_type] || row.api_type }}
          </template>
        </el-table-column>
        <el-table-column label="Status" width="120">
          <template #default="{ row }">
            <el-tag :type="row.collected ? 'success' : 'danger'">
              {{ row.collected ? 'Collected' : 'Missing' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <h4 style="margin-top: 24px;">Raw Records</h4>
      <el-table :data="detail.records" stripe size="small">
        <el-table-column prop="api_type" label="API Type" width="200" />
        <el-table-column prop="api_url" label="URL" show-overflow-tooltip />
        <el-table-column prop="status" label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="response_size" label="Size (bytes)" width="120" />
        <el-table-column prop="collected_at" label="Collected At" width="180" />
      </el-table>
    </template>
  </div>
</template>
```

**Step 2: Browser Verification**

1. 打开 http://localhost:5173，从 AccountDetail 点击某直播间 Detail
2. 验证：9 项 V1 API Checklist 显示（绿=Collected，红=Missing）、Raw Records 表格

**Step 3: Commit**

```bash
git add live_dp/monitor/frontend/src/views/RoomDetail.vue
git commit -m "feat(monitor): implement RoomDetail page with API checklist"
```

---

## Phase 5: Integration & Verification (Tasks 13-15)

> **验证策略：纯手动验证。Task 13 用 seed 脚本 + SQLite 查询验证后端数据。Task 14 用浏览器操作验证前后端联调。**

### Task 13: Manual Crawl Verification

**Goal:** Run a real crawl (even a short one) and verify data appears in SQLite.

**Step 1: Run a single-account crawl (if possible) or use seed script**

If a real crawl is not possible, create a seed script:

```python
# live_dp/monitor/seed_test_data.py
"""Seed test data for manual verification."""
from monitor.db import init_db
from monitor.tracker import CollectionMonitor
from monitor.classifier import ACCOUNT_API_TYPES, ROOM_API_TYPES
from pathlib import Path

db_path = str(Path(__file__).parent / "data" / "monitor.db")
init_db(db_path)

monitor = CollectionMonitor(db_path=db_path, batch_id="2026-03-06_20:00", platform="tiktok")
monitor.start_batch(mode="once", total_accounts=2)

# Account 1: full collection
for api in ACCOUNT_API_TYPES:
    monitor.record("browser_001", "", api, f"https://shop.tiktok.com/{api}", "success", 2048)

for room in ["room_111", "room_222"]:
    for api in ROOM_API_TYPES:
        monitor.record("browser_001", room, api, f"https://shop.tiktok.com/{api}?roomId={room}", "success", 1024)

# Account 2: partial collection (missing some APIs)
for api in list(ACCOUNT_API_TYPES)[:3]:
    monitor.record("browser_002", "", api, f"https://shop.tiktok.com/{api}", "success", 2048)

for api in list(ROOM_API_TYPES)[:4]:
    monitor.record("browser_002", "room_333", api, f"https://shop.tiktok.com/{api}?roomId=room_333", "success", 1024)

monitor.finish_batch(success_accounts=2)
print("Seed data written successfully!")
```

Run: `cd live_dp && python -m monitor.seed_test_data`
Expected: "Seed data written successfully!"

**Step 2: Verify data in SQLite**

```bash
cd live_dp && python -c "
import sqlite3
conn = sqlite3.connect('monitor/data/monitor.db')
print('Batches:', conn.execute('SELECT count(*) FROM collection_batches').fetchone()[0])
print('Records:', conn.execute('SELECT count(*) FROM collection_records').fetchone()[0])
conn.close()
"
```
Expected: Batches: 1, Records: ~30

**Step 3: Commit seed script**

```bash
git add live_dp/monitor/seed_test_data.py
git commit -m "feat(monitor): add seed script for test data"
```

---

### Task 14: Frontend-Backend Browser Verification

**Step 1: Start backend**

```bash
cd live_dp && python -m monitor.server
```

**Step 2: Start frontend dev server (in another terminal)**

```bash
cd live_dp/monitor/frontend && npm run dev
```

**Step 3: Browser Verification Checklist**

在浏览器中逐一验证以下场景：

1. 打开 http://localhost:5173
2. Dashboard：批次选择器显示 "2026-03-06_20:00 (tiktok)"
3. Dashboard：账号表显示 browser_001 (100%) 和 browser_002 (<100%)
4. 点击 browser_001 的 "Detail" -> AccountDetail 页面加载
5. AccountDetail：5 张绿色 API 状态卡片
6. 点击 room_111 的 "Detail" -> RoomDetail 页面加载
7. RoomDetail：9/9 checklist 全绿
8. 返回 Dashboard，点击 browser_002 -> 验证部分红色缺失标记

**Step 4: Build frontend for production**

```bash
cd live_dp/monitor/frontend && npm run build
```
Expected: `dist/` directory created

**Step 5: Verify FastAPI serves static files**

Restart backend: `cd live_dp && python -m monitor.server`
Open http://localhost:8777 - should serve the Vue3 SPA

**Step 6: Commit**

```bash
git add live_dp/monitor/frontend/dist/
git commit -m "build(monitor): add production frontend build"
```

---

### Task 15: Final Cleanup & Documentation

**Step 1: Run all tests**

```bash
cd live_dp && python -m pytest tests/monitor/ -v
```
Expected: All tests pass

**Step 2: Update memory-bank/architecture.md**

Update the architecture doc to reflect the monitor system is now implemented (change `[待建]` to `[已实现]`).

**Step 3: Final commit**

```bash
git add -A
git commit -m "docs: update architecture for implemented monitor system"
```

---

## Summary

| Phase | Tasks | Description | Verification |
|-------|-------|-------------|-------------|
| 1. Foundation | 1-3 | SQLite DB, API Classifier, Collection Tracker | TDD (pytest) |
| 2. Crawler Integration | 4-5 | Hook + Pipeline injection | Code + import verify |
| 2. Crawler Integration | 6 | Completeness Reporter | TDD (pytest) |
| 3. Backend API | 7 | FastAPI Server + Routes | Code + manual start |
| 3. Backend API | 8 | API Endpoint Tests | TDD (TestClient) |
| 4. Frontend | 9-12 | Vue3 scaffold + 3 pages | Code + browser verify |
| 5. Verification | 13-15 | Seed data, integration, cleanup | Manual + browser |

**Key integration points:**
- `live_dp/spiders/base.py:send_api_request()` - monitor hook
- `live_dp/main.py:run_once()` - batch lifecycle
- `live_dp/scheduler/task_scheduler.py:execute_crawl_task()` - batch lifecycle
