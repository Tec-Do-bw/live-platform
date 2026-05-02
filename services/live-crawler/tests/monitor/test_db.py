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


def test_init_db_drops_needs_full_recovery_column():
    """旧库遗留 needs_full_recovery 列时应自动移除。"""
    conn = get_connection(':memory:')
    conn.execute("""
        CREATE TABLE account_login_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL UNIQUE,
            platform TEXT NOT NULL,
            group_name TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'online',
            logout_at TIMESTAMP,
            login_at TIMESTAMP,
            logout_reason TEXT DEFAULT '',
            recovery_batch_id TEXT DEFAULT '',
            needs_full_recovery INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    init_db(conn)

    columns = conn.execute("PRAGMA table_info(account_login_status)").fetchall()
    column_names = {row['name'] for row in columns}
    assert 'needs_full_recovery' not in column_names
