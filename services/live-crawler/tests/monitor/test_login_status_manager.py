"""账号登录状态管理器测试。"""

import pytest

from monitor import get_connection, init_db
from monitor.login_status_manager import LoginStatusManager


@pytest.fixture
def conn():
    """每个测试使用独立的内存数据库。"""
    c = get_connection(':memory:')
    init_db(c)
    yield c
    c.close()


@pytest.fixture
def manager(conn):
    """创建状态管理器实例。"""
    return LoginStatusManager(conn)


class TestMarkLogout:
    """测试记录登出事件。"""

    def test_mark_logout_updates_snapshot_and_event(self, manager, conn):
        manager.mark_logout('acc1', 'tiktok', '美国团队', '登录失效')

        row = conn.execute(
            "SELECT * FROM account_login_status WHERE account_id='acc1'"
        ).fetchone()
        events = manager.list_events('acc1')

        assert row is not None
        assert row['status'] == 'logout'
        assert row['platform'] == 'tiktok'
        assert row['group_name'] == '美国团队'
        assert row['logout_reason'] == '登录失效'
        assert row['logout_at'] is not None
        assert [event['event_type'] for event in events] == ['logout']
        assert events[0]['detail']['reason'] == '登录失效'

    def test_mark_logout_repeated_writes_multiple_events(self, manager):
        manager.mark_logout('acc1', 'tiktok', '美国团队', '首次登出')
        manager.mark_logout('acc1', 'tiktok', '美国团队', '二次登出')

        events = manager.list_events('acc1')
        assert [event['event_type'] for event in events] == ['logout', 'logout']
        assert events[0]['detail']['reason'] == '二次登出'


class TestMarkLogin:
    """测试记录登录事件。"""

    def test_mark_login_from_logout_updates_snapshot_and_event(self, manager, conn):
        manager.mark_logout('acc1', 'tiktok', '美国团队', '登录失效')
        manager.mark_login('acc1', 'tiktok', '美国团队')

        row = conn.execute(
            "SELECT * FROM account_login_status WHERE account_id='acc1'"
        ).fetchone()
        events = manager.list_events('acc1')

        assert row['status'] == 'online'
        assert row['login_at'] is not None
        assert row['logout_reason'] == ''
        assert [event['event_type'] for event in events] == ['login', 'logout']

    def test_mark_login_for_missing_account_creates_online_snapshot(self, manager, conn):
        manager.mark_login('acc1', 'shopee', '新加坡团队')

        row = conn.execute(
            "SELECT * FROM account_login_status WHERE account_id='acc1'"
        ).fetchone()
        events = manager.list_events('acc1')

        assert row['status'] == 'online'
        assert row['platform'] == 'shopee'
        assert row['group_name'] == '新加坡团队'
        assert events[0]['event_type'] == 'login'


class TestManualRecoveryRequest:
    """测试手动恢复请求事件。"""

    def test_mark_full_recovery_pending_creates_status_and_event(self, manager, conn):
        manager.mark_full_recovery_pending('acc1', 'tiktok', '美国团队')

        row = conn.execute(
            "SELECT * FROM account_login_status WHERE account_id='acc1'"
        ).fetchone()
        events = manager.list_events('acc1')

        assert row is not None
        assert row['status'] == 'online'
        assert row['platform'] == 'tiktok'
        assert events[0]['event_type'] == 'full_recovery_marked'
        assert events[0]['detail']['source'] == 'manual_trigger'

    def test_mark_full_recovery_pending_keeps_existing_logout_snapshot(self, manager, conn):
        manager.mark_logout('acc1', 'tiktok', '旧分组', '登录失效')

        manager.mark_full_recovery_pending('acc1', 'tiktok', '美国团队')

        row = conn.execute(
            "SELECT * FROM account_login_status WHERE account_id='acc1'"
        ).fetchone()
        events = manager.list_events('acc1')

        assert row['status'] == 'logout'
        assert row['group_name'] == '美国团队'
        assert events[0]['event_type'] == 'full_recovery_marked'
        assert events[1]['event_type'] == 'logout'


class TestQueries:
    """测试查询接口。"""

    def test_get_recent_events_returns_desc_order(self, manager):
        manager.append_event(
            'acc1',
            'tiktok',
            '美国团队',
            'logout',
            detail={'reason': '登录失效'},
            event_time='2026-04-01T10:00:00',
        )
        manager.append_event(
            'acc1',
            'tiktok',
            '美国团队',
            'login',
            event_time='2026-04-01T11:00:00',
        )
        manager.append_event(
            'acc1',
            'tiktok',
            '美国团队',
            'full_recovery_started',
            event_time='2026-04-01T12:00:00',
        )

        events = manager.get_recent_events('acc1', limit=2)
        assert [event['event_type'] for event in events] == [
            'full_recovery_started',
            'login',
        ]

    def test_get_account_status_exists(self, manager):
        manager.mark_logout('acc1', 'tiktok', '美国团队', '登录失效')

        status = manager.get_account_status('acc1')
        assert status is not None
        assert status['account_id'] == 'acc1'
        assert status['status'] == 'logout'

    def test_get_account_status_not_exists(self, manager):
        assert manager.get_account_status('nonexistent') is None

    def test_list_logout_accounts_all(self, manager, conn):
        manager.mark_logout('acc1', 'tiktok', '美国团队', '登录失效')
        manager.mark_logout('acc2', 'shopee', '新加坡团队', '登录失效')
        conn.execute(
            """INSERT INTO account_login_status
               (account_id, platform, group_name, status)
               VALUES ('acc3', 'tiktok', '美国团队', 'online')"""
        )
        conn.commit()

        accounts = manager.list_logout_accounts()
        assert len(accounts) == 2
        assert all(acc['status'] == 'logout' for acc in accounts)

    def test_list_logout_accounts_by_platform(self, manager):
        manager.mark_logout('acc1', 'tiktok', '美国团队', '登录失效')
        manager.mark_logout('acc2', 'shopee', '新加坡团队', '登录失效')

        accounts = manager.list_logout_accounts(platform='tiktok')
        assert len(accounts) == 1
        assert accounts[0]['account_id'] == 'acc1'

    def test_list_logout_accounts_empty(self, manager):
        assert manager.list_logout_accounts() == []
