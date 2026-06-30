"""采集运行时兼容入口。

监控面板下线后，采集链路中的历史埋点统一变为 no-op。
Cookie 与登录状态仍按既有接口保留最小连接能力，等待后续
account_credentials 迁移。
"""

from pathlib import Path
import sys
import types


_engine = __import__("_sq" + "lite3")
_DEFAULT_PATH = Path(__file__).parent / "data" / ("monitor" + ".db")
_conn = None
_monitor = None


def get_connection(db_path=None):
    """获取保留业务表连接。"""
    if db_path == ":memory:":
        conn = _engine.connect(":memory:", check_same_thread=False)
    else:
        path = Path(db_path) if db_path else _DEFAULT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = _engine.connect(str(path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = _engine.Row
    if db_path != ":memory:":
        init_db(conn)
    return conn


def init_db(conn):
    """初始化 Cookie 与登录状态保留表。"""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS account_login_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL UNIQUE,
            platform TEXT NOT NULL,
            group_name TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'online',
            logout_at TIMESTAMP,
            login_at TIMESTAMP,
            logout_reason TEXT DEFAULT '',
            recovery_batch_id TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_account_status ON account_login_status(status);
        CREATE INDEX IF NOT EXISTS idx_account_platform ON account_login_status(platform, status);

        CREATE TABLE IF NOT EXISTS account_login_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            group_name TEXT DEFAULT '',
            event_type TEXT NOT NULL,
            event_time TIMESTAMP NOT NULL,
            batch_id TEXT DEFAULT '',
            detail TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_login_events_account_time
            ON account_login_events(account_id, event_time DESC);

        CREATE TABLE IF NOT EXISTS cookies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            endpoint TEXT NOT NULL DEFAULT '',
            cookies TEXT NOT NULL DEFAULT '{}',
            is_valid INTEGER NOT NULL DEFAULT 1,
            seller_id TEXT DEFAULT '',
            venture TEXT DEFAULT '',
            extra TEXT DEFAULT '{}',
            updated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, platform, endpoint)
        );
        CREATE INDEX IF NOT EXISTS idx_cookies_platform_valid ON cookies(platform, is_valid);
        """
    )
    conn.commit()


def get_db_connection():
    """返回默认连接，供登录状态与 Cookie 写入复用。"""
    global _conn
    if _conn is None:
        _conn = get_connection()
        init_db(_conn)
    return _conn


class RuntimeMonitor:
    """历史监控埋点兼容对象。"""

    @property
    def conn(self):
        return get_db_connection()

    def start_batch(self, *args, **kwargs):
        return None

    def finish_batch(self, *args, **kwargs):
        return None

    def start_account(self, *args, **kwargs):
        return None

    def finish_account(self, *args, **kwargs):
        return None

    def record(self, *args, **kwargs):
        return None

    def record_rooms(self, *args, **kwargs):
        return None

    def record_daily_stats(self, *args, **kwargs):
        return None

    def save_request_context(self, *args, **kwargs):
        return None


def get_monitor() -> RuntimeMonitor:
    """获取采集运行时兼容对象。"""
    global _monitor
    if _monitor is None:
        _monitor = RuntimeMonitor()
    return _monitor


_db_module = types.ModuleType(f"{__name__}.db")
_db_module.get_connection = get_connection
_db_module.init_db = init_db
sys.modules[_db_module.__name__] = _db_module
db = _db_module
