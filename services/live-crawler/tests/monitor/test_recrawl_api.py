"""补采任务 API 测试"""

import pytest
from fastapi.testclient import TestClient
from monitor.db import get_connection, init_db


@pytest.fixture
def app():
    from fastapi import FastAPI
    from monitor.api.recrawl_routes import router, set_db_connection
    _app = FastAPI()
    _app.include_router(router)
    conn = get_connection(':memory:')
    init_db(conn)
    set_db_connection(conn)
    yield _app
    conn.close()


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRecrawlAPI:

    def test_trigger_manual_recrawl(self, client):
        resp = client.post('/api/recrawl/trigger', json={
            'account_id': 'acc1', 'level': 'room',
            'room_id': 'room1', 'api_type': 'trend_gmv',
            'target_date': '', 'batch_id': '2026-03-14_14:30',
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'created'

    def test_get_tasks(self, client):
        # 先创建一个任务
        client.post('/api/recrawl/trigger', json={
            'account_id': 'acc1', 'level': 'room',
            'room_id': 'room1', 'api_type': 'trend_gmv',
            'target_date': '', 'batch_id': '2026-03-14_14:30',
        })
        resp = client.get('/api/recrawl/tasks?account_id=acc1')
        assert resp.status_code == 200
        data = resp.json()
        assert len(data['tasks']) == 1
        assert data['tasks'][0]['api_type'] == 'trend_gmv'
