"""登出期间数据标记测试"""

import pytest
from datetime import datetime
from monitor.db import get_connection, init_db
from monitor.invalid_marker import mark_invalid_records


@pytest.fixture
def conn():
    """每个测试使用独立的内存数据库"""
    c = get_connection(':memory:')
    init_db(c)
    yield c
    c.close()


class TestMarkInvalidRecords:
    """测试标记 invalid 记录"""

    def test_mark_invalid_basic(self, conn):
        """基本标记功能"""
        # 插入批次和采集记录
        conn.execute(
            """INSERT INTO collection_batches (batch_id, mode) VALUES ('b1', 'once')"""
        )
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        conn.execute(
            """INSERT INTO collection_records
               (batch_id, account_id, api_type, status, response_size, collected_at)
               VALUES ('b1', 'acc1', 'live_list', 'success', 0, ?)""",
            (logout_at.isoformat(),)
        )
        conn.commit()

        marked = mark_invalid_records(conn, 'b1', 'acc1', logout_at)

        assert marked == 1
        row = conn.execute(
            "SELECT status FROM collection_records WHERE account_id='acc1'"
        ).fetchone()
        assert row['status'] == 'invalid'

    def test_mark_invalid_only_zero_response_size(self, conn):
        """只标记 response_size == 0 的记录"""
        conn.execute(
            """INSERT INTO collection_batches (batch_id, mode) VALUES ('b1', 'once')"""
        )
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        conn.execute(
            """INSERT INTO collection_records
               (batch_id, account_id, api_type, status, response_size, collected_at)
               VALUES
               ('b1', 'acc1', 'live_list', 'success', 0, ?),
               ('b1', 'acc1', 'trend_gmv', 'success', 1024, ?)""",
            (logout_at.isoformat(), logout_at.isoformat())
        )
        conn.commit()

        marked = mark_invalid_records(conn, 'b1', 'acc1', logout_at)

        assert marked == 1
        rows = conn.execute(
            "SELECT api_type, status FROM collection_records ORDER BY api_type"
        ).fetchall()
        assert rows[0]['api_type'] == 'live_list'
        assert rows[0]['status'] == 'invalid'
        assert rows[1]['api_type'] == 'trend_gmv'
        assert rows[1]['status'] == 'success'

    def test_mark_invalid_only_after_logout(self, conn):
        """只标记登出时间之后的记录"""
        conn.execute(
            """INSERT INTO collection_batches (batch_id, mode) VALUES ('b1', 'once')"""
        )
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        before_logout = datetime(2026, 3, 29, 9, 0, 0)
        after_logout = datetime(2026, 3, 29, 11, 0, 0)

        conn.execute(
            """INSERT INTO collection_records
               (batch_id, account_id, api_type, status, response_size, collected_at)
               VALUES
               ('b1', 'acc1', 'live_list', 'success', 0, ?),
               ('b1', 'acc1', 'trend_gmv', 'success', 0, ?)""",
            (before_logout.isoformat(), after_logout.isoformat())
        )
        conn.commit()

        marked = mark_invalid_records(conn, 'b1', 'acc1', logout_at)

        assert marked == 1
        rows = conn.execute(
            "SELECT api_type, status FROM collection_records ORDER BY collected_at"
        ).fetchall()
        assert rows[0]['status'] == 'success'  # 登出前的记录
        assert rows[1]['status'] == 'invalid'  # 登出后的记录

    def test_mark_invalid_skip_already_invalid(self, conn):
        """跳过已经是 invalid 的记录"""
        conn.execute(
            """INSERT INTO collection_batches (batch_id, mode) VALUES ('b1', 'once')"""
        )
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        conn.execute(
            """INSERT INTO collection_records
               (batch_id, account_id, api_type, status, response_size, collected_at)
               VALUES ('b1', 'acc1', 'live_list', 'invalid', 0, ?)""",
            (logout_at.isoformat(),)
        )
        conn.commit()

        marked = mark_invalid_records(conn, 'b1', 'acc1', logout_at)

        assert marked == 0

    def test_mark_invalid_multiple_accounts(self, conn):
        """只标记指定账号的记录"""
        conn.execute(
            """INSERT INTO collection_batches (batch_id, mode) VALUES ('b1', 'once')"""
        )
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        conn.execute(
            """INSERT INTO collection_records
               (batch_id, account_id, api_type, status, response_size, collected_at)
               VALUES
               ('b1', 'acc1', 'live_list', 'success', 0, ?),
               ('b1', 'acc2', 'live_list', 'success', 0, ?)""",
            (logout_at.isoformat(), logout_at.isoformat())
        )
        conn.commit()

        marked = mark_invalid_records(conn, 'b1', 'acc1', logout_at)

        assert marked == 1
        rows = conn.execute(
            "SELECT account_id, status FROM collection_records ORDER BY account_id"
        ).fetchall()
        assert rows[0]['account_id'] == 'acc1'
        assert rows[0]['status'] == 'invalid'
        assert rows[1]['account_id'] == 'acc2'
        assert rows[1]['status'] == 'success'

    def test_mark_invalid_empty_result(self, conn):
        """没有符合条件的记录时返回 0"""
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        marked = mark_invalid_records(conn, 'b1', 'acc1', logout_at)
        assert marked == 0
