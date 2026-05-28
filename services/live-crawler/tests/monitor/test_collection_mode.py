"""采集模式解析测试。"""

import pytest

from core.collection_mode import resolve_collection_mode
from monitor import get_connection, init_db
from monitor.login_status_manager import LoginStatusManager


class DummyTracker:
    """最小 tracker 桩对象。"""

    def __init__(self, new_accounts=None):
        self.new_accounts = set(new_accounts or [])

    def is_new_account(self, platform, user_id):
        return (platform, user_id) in self.new_accounts


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


def test_resolve_collection_mode_returns_full_for_new_account(manager):
    tracker = DummyTracker({('tiktok', 'acc1')})

    assert resolve_collection_mode('tiktok', 'acc1', tracker, manager) == (True, '新账号全量')


def test_resolve_collection_mode_returns_recovery_full_for_recent_login_after_logout(manager):
    manager.append_event(
        'acc1',
        'shopee',
        '新加坡团队',
        'logout',
        event_time='2026-04-01T10:00:00',
    )
    manager.append_event(
        'acc1',
        'shopee',
        '新加坡团队',
        'login',
        event_time='2026-04-01T11:00:00',
    )

    assert resolve_collection_mode('shopee', 'acc1', DummyTracker(), manager) == (True, '登出恢复全量')


def test_resolve_collection_mode_keeps_incremental_for_continuous_logout(manager):
    manager.append_event(
        'acc1',
        'tiktok',
        '美国团队',
        'logout',
        event_time='2026-04-01T10:00:00',
    )
    manager.append_event(
        'acc1',
        'tiktok',
        '美国团队',
        'logout',
        event_time='2026-04-01T11:00:00',
    )

    assert resolve_collection_mode('tiktok', 'acc1', DummyTracker(), manager) == (False, '增量')


def test_resolve_collection_mode_keeps_incremental_for_continuous_login(manager):
    manager.append_event(
        'acc1',
        'tiktok',
        '美国团队',
        'login',
        event_time='2026-04-01T10:00:00',
    )
    manager.append_event(
        'acc1',
        'tiktok',
        '美国团队',
        'login',
        event_time='2026-04-01T11:00:00',
    )

    assert resolve_collection_mode('tiktok', 'acc1', DummyTracker(), manager) == (False, '增量')


def test_resolve_collection_mode_force_full_overrides_recent_events(manager):
    manager.append_event(
        'acc1',
        'tiktok',
        '美国团队',
        'logout',
        event_time='2026-04-01T10:00:00',
    )
    manager.append_event(
        'acc1',
        'tiktok',
        '美国团队',
        'logout',
        event_time='2026-04-01T11:00:00',
    )

    assert resolve_collection_mode(
        'tiktok',
        'acc1',
        DummyTracker(),
        manager,
        force_full_collection=True,
    ) == (True, '手动全量')
