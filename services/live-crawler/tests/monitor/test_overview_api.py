"""账号总览 API 测试"""

import time
import pytest
from fastapi.testclient import TestClient
from monitor.db import get_connection, init_db
from monitor.tracker import CollectionMonitor


@pytest.fixture
def app():
    from fastapi import FastAPI
    from monitor.api.overview import router, set_db_connection
    _app = FastAPI()
    _app.include_router(router)

    # 创建内存数据库并通过 CollectionMonitor 插入测试数据
    monitor = CollectionMonitor(db_path=':memory:')
    conn = monitor.conn
    set_db_connection(conn)

    # 插入测试数据
    batch_id = '2026-03-14_14:30'
    monitor.start_batch(batch_id, 'once')
    monitor.start_account(batch_id, 'acc1', 'TikTok团队')
    monitor.record(batch_id, 'acc1', 'live_list', status='success')
    monitor.record(batch_id, 'acc1', 'replay_info', status='success')
    monitor.record_rooms(batch_id, 'acc1', [
        {'room_id': 'room1', 'live_start_ts': int(time.time()) - 3600,
         'live_end_ts': int(time.time()), 'duration': 3600},
    ])
    monitor.record(batch_id, 'acc1', 'trend_gmv', room_id='room1', status='success')
    # 缺少 trend_stats
    monitor.finish_account(batch_id, 'acc1', 'success')
    monitor.finish_batch(batch_id)

    yield _app
    conn.close()


@pytest.fixture
def client(app):
    return TestClient(app)


class TestOverviewAPI:

    def test_get_overview(self, client):
        resp = client.get('/api/overview?days=3')
        assert resp.status_code == 200
        data = resp.json()
        assert 'accounts' in data
        assert len(data['accounts']) >= 1
        acc = data['accounts'][0]
        assert acc['account_id'] == 'acc1'
        assert 'completeness' in acc
        assert acc['missing_count'] >= 1  # 缺少 trend_stats

    def test_get_account_detail(self, client):
        resp = client.get('/api/overview/acc1?days=3')
        assert resp.status_code == 200
        data = resp.json()
        assert 'account_level' in data
        assert 'room_level' in data
        assert 'completeness' in data
        # 检查 room1 缺少 trend_stats
        room = data['room_level'][0]
        assert room['room_id'] == 'room1'
        statuses = {a['api_type']: a['status'] for a in room['apis']}
        assert statuses['trend_gmv'] == 'success'
        assert statuses['trend_stats'] == 'missing'
