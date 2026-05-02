"""SQLite 数据库初始化与连接管理"""

import sqlite3
from pathlib import Path

DB_DIR = Path(__file__).parent / 'data'
DB_PATH = DB_DIR / 'monitor.db'


def _ensure_column(conn: sqlite3.Connection, table_name: str,
                   column_name: str, column_def: str) -> None:
    """为旧表补齐缺失列，保证初始化可向后兼容。"""
    columns = {
        row['name']
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in columns:
        return

    conn.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"
    )


def _drop_needs_full_recovery_column(conn: sqlite3.Connection) -> None:
    """将旧版 account_login_status 表迁移为无 needs_full_recovery 字段。"""
    columns = {
        row['name']
        for row in conn.execute("PRAGMA table_info(account_login_status)").fetchall()
    }
    if 'needs_full_recovery' not in columns:
        return

    conn.executescript("""
        DROP INDEX IF EXISTS idx_account_status;
        DROP INDEX IF EXISTS idx_account_platform;

        CREATE TABLE account_login_status__new (
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

        INSERT INTO account_login_status__new (
            id,
            account_id,
            platform,
            group_name,
            status,
            logout_at,
            login_at,
            logout_reason,
            recovery_batch_id,
            updated_at,
            created_at
        )
        SELECT
            id,
            account_id,
            platform,
            group_name,
            status,
            logout_at,
            login_at,
            logout_reason,
            recovery_batch_id,
            updated_at,
            created_at
        FROM account_login_status;

        DROP TABLE account_login_status;
        ALTER TABLE account_login_status__new RENAME TO account_login_status;

        CREATE INDEX IF NOT EXISTS idx_account_status ON account_login_status(status);
        CREATE INDEX IF NOT EXISTS idx_account_platform ON account_login_status(platform, status);
    """)


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
            platform TEXT DEFAULT 'tiktok',
            crawl_type TEXT DEFAULT '',
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
    """)

    _drop_needs_full_recovery_column(conn)
    _ensure_column(conn, 'account_sessions', 'platform', "TEXT DEFAULT 'tiktok'")
    _ensure_column(conn, 'account_sessions', 'crawl_type', "TEXT DEFAULT ''")
    conn.commit()
