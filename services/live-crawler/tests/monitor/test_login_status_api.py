"""登录状态 API 路由测试。"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from monitor.db import get_connection, init_db
from monitor.server import app


@pytest.fixture
def client():
    """创建测试客户端。"""
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """每个测试使用独立的内存数据库。"""
    conn = get_connection(':memory:')
    init_db(conn)

    def mock_get_connection():
        return conn

    monkeypatch.setattr('monitor.api.login_status_routes.get_connection', mock_get_connection)
    yield conn
    conn.close()


class TestGetAccountLoginStatus:
    """测试获取账号登录状态 API。"""

    def test_get_status_success(self, client, setup_test_db):
        conn = setup_test_db
        conn.execute(
            """INSERT INTO account_login_status
               (account_id, platform, group_name, status, logout_reason)
               VALUES ('acc1', 'tiktok', '美国团队', 'logout', '登录失效')"""
        )
        conn.commit()

        response = client.get('/api/accounts/acc1/login-status')

        assert response.status_code == 200
        data = response.json()
        assert data['account_id'] == 'acc1'
        assert data['status'] == 'logout'
        assert data['platform'] == 'tiktok'
        assert 'needs_full_recovery' not in data

    def test_get_status_not_found(self, client):
        response = client.get('/api/accounts/nonexistent/login-status')

        assert response.status_code == 404
        assert '账号状态不存在' in response.json()['detail']


class TestGetAccountLoginEvents:
    """测试获取账号登录事件 API。"""

    def test_get_events_success(self, client, setup_test_db):
        conn = setup_test_db
        conn.execute(
            """INSERT INTO account_login_events
               (account_id, platform, group_name, event_type, event_time, detail)
               VALUES
               ('acc1', 'tiktok', '美国团队', 'logout', '2026-04-01T10:00:00', '{"reason": "登录失效"}'),
               ('acc1', 'tiktok', '美国团队', 'login', '2026-04-01T11:00:00', '{}')"""
        )
        conn.commit()

        response = client.get('/api/accounts/acc1/login-events?limit=2')

        assert response.status_code == 200
        data = response.json()
        assert data['account_id'] == 'acc1'
        assert [event['event_type'] for event in data['events']] == ['login', 'logout']
        assert data['events'][1]['detail']['reason'] == '登录失效'


class TestListLogoutAccounts:
    """测试列出登出账号 API。"""

    def test_list_logout_accounts_all(self, client, setup_test_db):
        conn = setup_test_db
        conn.execute(
            """INSERT INTO account_login_status
               (account_id, platform, group_name, status)
               VALUES
               ('acc1', 'tiktok', '美国团队', 'logout'),
               ('acc2', 'shopee', '新加坡团队', 'logout'),
               ('acc3', 'tiktok', '美国团队', 'online')"""
        )
        conn.commit()

        response = client.get('/api/accounts/logout-list')

        assert response.status_code == 200
        data = response.json()
        assert len(data['accounts']) == 2
        assert all(acc['status'] == 'logout' for acc in data['accounts'])

    def test_list_logout_accounts_by_platform(self, client, setup_test_db):
        conn = setup_test_db
        conn.execute(
            """INSERT INTO account_login_status
               (account_id, platform, group_name, status)
               VALUES
               ('acc1', 'tiktok', '美国团队', 'logout'),
               ('acc2', 'shopee', '新加坡团队', 'logout')"""
        )
        conn.commit()

        response = client.get('/api/accounts/logout-list?platform=tiktok')

        assert response.status_code == 200
        data = response.json()
        assert len(data['accounts']) == 1
        assert data['accounts'][0]['platform'] == 'tiktok'

    def test_list_logout_accounts_empty(self, client):
        response = client.get('/api/accounts/logout-list')

        assert response.status_code == 200
        assert response.json()['accounts'] == []


class TestTriggerRecovery:
    """测试手动恢复请求 API。"""

    def test_trigger_recovery_success_existing_account(self, client, setup_test_db):
        conn = setup_test_db
        conn.execute(
            """INSERT INTO account_login_status
               (account_id, platform, group_name, status)
               VALUES ('acc1', 'tiktok', '美国团队', 'online')"""
        )
        conn.commit()

        response = client.post(
            '/api/accounts/acc1/trigger-recovery',
            json={'platform': 'tiktok', 'group_name': '美国团队'}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['event_recorded'] is True

        row = conn.execute(
            "SELECT status FROM account_login_status WHERE account_id='acc1'"
        ).fetchone()
        events = conn.execute(
            """SELECT event_type, detail FROM account_login_events
               WHERE account_id='acc1'
               ORDER BY event_time DESC, id DESC"""
        ).fetchall()
        assert row['status'] == 'online'
        assert events[0]['event_type'] == 'full_recovery_marked'
        assert 'manual_trigger' in events[0]['detail']

    def test_trigger_recovery_creates_account_status_when_missing(self, client, setup_test_db):
        conn = setup_test_db

        response = client.post(
            '/api/accounts/nonexistent/trigger-recovery',
            json={'platform': 'tiktok', 'group_name': '美国团队'}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['event_recorded'] is True

        row = conn.execute(
            "SELECT * FROM account_login_status WHERE account_id='nonexistent'"
        ).fetchone()
        assert row is not None
        assert row['platform'] == 'tiktok'
        assert row['status'] == 'online'

    def test_trigger_recovery_rejects_non_tiktok(self, client):
        response = client.post(
            '/api/accounts/acc1/trigger-recovery',
            json={'platform': 'shopee', 'group_name': '新加坡团队'}
        )

        assert response.status_code == 400
        assert '仅支持 TikTok 恢复全量' in response.json()['detail']

    def test_trigger_recovery_does_not_create_recrawl_tasks(self, client, setup_test_db):
        conn = setup_test_db

        response = client.post(
            '/api/accounts/acc1/trigger-recovery',
            json={'platform': 'tiktok', 'group_name': '美国团队'}
        )

        assert response.status_code == 200
        tasks = conn.execute(
            "SELECT * FROM recrawl_tasks WHERE account_id='acc1'"
        ).fetchall()
        assert tasks == []

    def test_trigger_recovery_returns_error_when_event_write_fails(self, client, monkeypatch):
        def mock_mark_full_recovery_pending(self, account_id, platform, group_name):
            raise sqlite3.OperationalError('event write failed')

        monkeypatch.setattr(
            'monitor.api.login_status_routes.LoginStatusManager.mark_full_recovery_pending',
            mock_mark_full_recovery_pending,
        )

        response = client.post(
            '/api/accounts/acc1/trigger-recovery',
            json={'platform': 'tiktok', 'group_name': '美国团队'}
        )

        assert response.status_code == 500
        assert 'event write failed' in response.json()['detail']


class TestListRecoveryTasks:
    """测试列出恢复补采任务 API。"""

    def test_list_recovery_tasks_all(self, client, setup_test_db):
        conn = setup_test_db
        conn.execute(
            """INSERT INTO recrawl_tasks
               (batch_id, account_id, group_name, api_type, level, source, status)
               VALUES
               ('b1', 'acc1', '美国团队', 'trend_gmv', 'room', 'logout_recovery', 'pending'),
               ('b1', 'acc1', '美国团队', 'live_list', 'account', 'logout_recovery', 'success'),
               ('b1', 'acc2', '新加坡团队', 'trend_gmv', 'room', 'auto', 'pending')"""
        )
        conn.commit()

        response = client.get('/api/recrawl/tasks/recovery')

        assert response.status_code == 200
        data = response.json()
        assert len(data['tasks']) == 2

    def test_list_recovery_tasks_by_account(self, client, setup_test_db):
        conn = setup_test_db
        conn.execute(
            """INSERT INTO recrawl_tasks
               (batch_id, account_id, group_name, api_type, level, source, status)
               VALUES
               ('b1', 'acc1', '美国团队', 'trend_gmv', 'room', 'logout_recovery', 'pending'),
               ('b1', 'acc2', '新加坡团队', 'live_list', 'account', 'logout_recovery', 'pending')"""
        )
        conn.commit()

        response = client.get('/api/recrawl/tasks/recovery?account_id=acc1')

        assert response.status_code == 200
        data = response.json()
        assert len(data['tasks']) == 1
        assert data['tasks'][0]['account_id'] == 'acc1'

    def test_list_recovery_tasks_by_status(self, client, setup_test_db):
        conn = setup_test_db
        conn.execute(
            """INSERT INTO recrawl_tasks
               (batch_id, account_id, group_name, api_type, level, source, status)
               VALUES
               ('b1', 'acc1', '美国团队', 'trend_gmv', 'room', 'logout_recovery', 'pending'),
               ('b1', 'acc1', '美国团队', 'live_list', 'account', 'logout_recovery', 'success')"""
        )
        conn.commit()

        response = client.get('/api/recrawl/tasks/recovery?status=pending')

        assert response.status_code == 200
        data = response.json()
        assert len(data['tasks']) == 1
        assert data['tasks'][0]['status'] == 'pending'

    def test_list_recovery_tasks_empty(self, client):
        response = client.get('/api/recrawl/tasks/recovery')

        assert response.status_code == 200
        assert response.json()['tasks'] == []
