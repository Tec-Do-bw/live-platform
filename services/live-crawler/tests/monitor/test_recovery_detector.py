"""恢复补采任务生成器测试"""

import pytest
from datetime import datetime
from monitor.db import get_connection, init_db
from monitor.recrawl.recovery_detector import detect_logout_gaps, create_recovery_tasks


@pytest.fixture
def conn():
    """每个测试使用独立的内存数据库"""
    c = get_connection(':memory:')
    init_db(c)
    yield c
    c.close()


class TestDetectLogoutGaps:
    """测试检测登出期间缺失数据"""

    def test_detect_gaps_basic(self, conn):
        """基本缺失检测"""
        conn.execute(
            """INSERT INTO collection_batches (batch_id, mode) VALUES ('b1', 'once')"""
        )
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        login_at = datetime(2026, 3, 29, 12, 0, 0)
        collected_at = datetime(2026, 3, 29, 11, 0, 0)

        conn.execute(
            """INSERT INTO collection_records
               (batch_id, account_id, room_id, api_type, status, collected_at)
               VALUES ('b1', 'acc1', 'room1', 'trend_gmv', 'invalid', ?)""",
            (collected_at.isoformat(),)
        )
        conn.commit()

        gaps = detect_logout_gaps(conn, 'acc1', '美国团队', logout_at, login_at)

        assert len(gaps) == 1
        assert gaps[0]['account_id'] == 'acc1'
        assert gaps[0]['room_id'] == 'room1'
        assert gaps[0]['api_type'] == 'trend_gmv'
        assert gaps[0]['level'] == 'room'

    def test_detect_gaps_account_level(self, conn):
        """检测账号级别缺失"""
        conn.execute(
            """INSERT INTO collection_batches (batch_id, mode) VALUES ('b1', 'once')"""
        )
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        login_at = datetime(2026, 3, 29, 12, 0, 0)
        collected_at = datetime(2026, 3, 29, 11, 0, 0)

        conn.execute(
            """INSERT INTO collection_records
               (batch_id, account_id, room_id, api_type, status, collected_at)
               VALUES ('b1', 'acc1', '', 'live_list', 'invalid', ?)""",
            (collected_at.isoformat(),)
        )
        conn.commit()

        gaps = detect_logout_gaps(conn, 'acc1', '美国团队', logout_at, login_at)

        assert len(gaps) == 1
        assert gaps[0]['room_id'] == ''
        assert gaps[0]['level'] == 'account'

    def test_detect_gaps_only_invalid_status(self, conn):
        """只检测 status=invalid 的记录"""
        conn.execute(
            """INSERT INTO collection_batches (batch_id, mode) VALUES ('b1', 'once')"""
        )
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        login_at = datetime(2026, 3, 29, 12, 0, 0)
        collected_at = datetime(2026, 3, 29, 11, 0, 0)

        conn.execute(
            """INSERT INTO collection_records
               (batch_id, account_id, api_type, status, collected_at)
               VALUES
               ('b1', 'acc1', 'live_list', 'invalid', ?),
               ('b1', 'acc1', 'trend_gmv', 'success', ?)""",
            (collected_at.isoformat(), collected_at.isoformat())
        )
        conn.commit()

        gaps = detect_logout_gaps(conn, 'acc1', '美国团队', logout_at, login_at)

        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'live_list'

    def test_detect_gaps_time_range(self, conn):
        """只检测时间范围内的记录"""
        conn.execute(
            """INSERT INTO collection_batches (batch_id, mode) VALUES ('b1', 'once')"""
        )
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        login_at = datetime(2026, 3, 29, 12, 0, 0)
        before_logout = datetime(2026, 3, 29, 9, 0, 0)
        after_login = datetime(2026, 3, 29, 13, 0, 0)
        in_range = datetime(2026, 3, 29, 11, 0, 0)

        conn.execute(
            """INSERT INTO collection_records
               (batch_id, account_id, api_type, status, collected_at)
               VALUES
               ('b1', 'acc1', 'api1', 'invalid', ?),
               ('b1', 'acc1', 'api2', 'invalid', ?),
               ('b1', 'acc1', 'api3', 'invalid', ?)""",
            (before_logout.isoformat(), in_range.isoformat(), after_login.isoformat())
        )
        conn.commit()

        gaps = detect_logout_gaps(conn, 'acc1', '美国团队', logout_at, login_at)

        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'api2'

    def test_detect_gaps_multiple_rooms(self, conn):
        """检测多个直播间的缺失"""
        conn.execute(
            """INSERT INTO collection_batches (batch_id, mode) VALUES ('b1', 'once')"""
        )
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        login_at = datetime(2026, 3, 29, 12, 0, 0)
        collected_at = datetime(2026, 3, 29, 11, 0, 0)

        conn.execute(
            """INSERT INTO collection_records
               (batch_id, account_id, room_id, api_type, status, collected_at)
               VALUES
               ('b1', 'acc1', 'room1', 'trend_gmv', 'invalid', ?),
               ('b1', 'acc1', 'room2', 'trend_gmv', 'invalid', ?)""",
            (collected_at.isoformat(), collected_at.isoformat())
        )
        conn.commit()

        gaps = detect_logout_gaps(conn, 'acc1', '美国团队', logout_at, login_at)

        assert len(gaps) == 2

    def test_detect_gaps_empty(self, conn):
        """没有缺失数据时返回空列表"""
        logout_at = datetime(2026, 3, 29, 10, 0, 0)
        login_at = datetime(2026, 3, 29, 12, 0, 0)

        gaps = detect_logout_gaps(conn, 'acc1', '美国团队', logout_at, login_at)

        assert gaps == []


class TestCreateRecoveryTasks:
    """测试创建恢复补采任务"""

    def test_create_recovery_tasks_basic(self, conn):
        """基本任务创建"""
        gaps = [
            {
                'batch_id': 'b1',
                'account_id': 'acc1',
                'room_id': 'room1',
                'target_date': '',
                'api_type': 'trend_gmv',
                'level': 'room',
            }
        ]

        tasks_created = create_recovery_tasks(conn, gaps, 'recovery_20260329')

        assert tasks_created == 1
        row = conn.execute(
            "SELECT * FROM recrawl_tasks WHERE account_id='acc1'"
        ).fetchone()
        assert row is not None
        assert row['source'] == 'logout_recovery'
        assert row['api_type'] == 'trend_gmv'
        assert row['status'] == 'pending'

    def test_create_recovery_tasks_multiple(self, conn):
        """创建多个任务"""
        gaps = [
            {
                'batch_id': 'b1',
                'account_id': 'acc1',
                'room_id': 'room1',
                'target_date': '',
                'api_type': 'trend_gmv',
                'level': 'room',
            },
            {
                'batch_id': 'b1',
                'account_id': 'acc1',
                'room_id': '',
                'target_date': '',
                'api_type': 'live_list',
                'level': 'account',
            },
        ]

        tasks_created = create_recovery_tasks(conn, gaps, 'recovery_20260329')

        assert tasks_created == 2
        rows = conn.execute(
            "SELECT * FROM recrawl_tasks WHERE account_id='acc1'"
        ).fetchall()
        assert len(rows) == 2
        assert all(r['source'] == 'logout_recovery' for r in rows)

    def test_create_recovery_tasks_empty_gaps(self, conn):
        """空缺失列表时返回 0"""
        tasks_created = create_recovery_tasks(conn, [], 'recovery_20260329')
        assert tasks_created == 0

    def test_create_recovery_tasks_duplicate_ignored(self, conn):
        """重复任务应被忽略"""
        gaps = [
            {
                'batch_id': 'b1',
                'account_id': 'acc1',
                'room_id': 'room1',
                'target_date': '',
                'api_type': 'trend_gmv',
                'level': 'room',
            }
        ]

        # 第一次创建
        tasks_created1 = create_recovery_tasks(conn, gaps, 'recovery_20260329')
        # 第二次创建（重复）
        tasks_created2 = create_recovery_tasks(conn, gaps, 'recovery_20260329')

        assert tasks_created1 == 1
        assert tasks_created2 == 0  # 重复任务被忽略

        rows = conn.execute(
            "SELECT * FROM recrawl_tasks WHERE account_id='acc1'"
        ).fetchall()
        assert len(rows) == 1
