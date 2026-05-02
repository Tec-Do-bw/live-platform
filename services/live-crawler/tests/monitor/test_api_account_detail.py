"""测试账号详情 API：GET /api/batches/{batch_id}/accounts/{account_id}"""

import json
import pytest
from fastapi.testclient import TestClient
from monitor.server import app
from monitor.tracker import CollectionMonitor
from monitor.db import get_connection, init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_data(monkeypatch):
    """为每个测试注入内存数据库中的测试数据"""
    conn = get_connection(':memory:')
    init_db(conn)

    # 让 accounts.py 中的 _get_conn() 使用测试连接
    monkeypatch.setattr('monitor.api.accounts._get_conn', lambda: conn)

    # 使用内存数据库创建 monitor 实例
    monitor = CollectionMonitor(db_path=':memory:')
    # 替换其连接为已初始化的测试连接
    monitor._conn = conn

    # 准备测试数据
    monitor.start_batch('b1', 'once')
    monitor.start_account('b1', 'acc1', 'TikTok团队')

    # live_list + room_sessions
    monitor.record_rooms('b1', 'acc1', [
        {'room_id': 'r1', 'room_name': 'SALE', 'live_start_ts': 1000, 'live_end_ts': 2000},
        {'room_id': 'r2', 'room_name': 'LIVE', 'live_start_ts': 3000, 'live_end_ts': 4000},
    ])
    monitor.record('b1', 'acc1', 'replay_info', status='success')

    # room 级记录
    monitor.record('b1', 'acc1', 'trend_gmv', room_id='r1', status='success')
    monitor.record('b1', 'acc1', 'trend_stats', room_id='r1', status='success')
    monitor.record('b1', 'acc1', 'trend_gmv', room_id='r2', status='success')
    # r2 的 trend_stats 缺失

    # 日期级记录
    monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'success')
    monitor.record_daily_stats('b1', 'acc1', '2026-03-13', 'live_stats', 'success')
    # 2026-03-14 缺失

    monitor.finish_account('b1', 'acc1', 'success')
    monitor.finish_batch('b1')

    return conn


def test_account_detail_has_three_sections():
    """账号详情 API 应返回 account_indicators + daily_stats + rooms"""
    resp = client.get('/api/batches/b1/accounts/acc1')
    assert resp.status_code == 200
    data = resp.json()
    assert 'account_indicators' in data
    assert 'daily_stats' in data
    assert 'rooms' in data


def test_account_detail_account_indicators():
    """account_indicators 应包含账号级 API 状态"""
    resp = client.get('/api/batches/b1/accounts/acc1')
    data = resp.json()
    indicators = data['account_indicators']
    assert indicators['live_list']['status'] == 'success'
    assert indicators['replay_info']['status'] == 'success'


def test_account_detail_daily_stats():
    """daily_stats 应包含日期级采集状态"""
    resp = client.get('/api/batches/b1/accounts/acc1')
    data = resp.json()
    daily = data['daily_stats']
    assert len(daily) >= 2
    # 检查已采集的日期
    dates = {d['target_date']: d for d in daily}
    assert dates['2026-03-12']['live_stats']['status'] == 'success'
    assert dates['2026-03-13']['live_stats']['status'] == 'success'


def test_account_detail_rooms():
    """rooms 应包含直播间级指标和完整率"""
    resp = client.get('/api/batches/b1/accounts/acc1')
    data = resp.json()
    rooms = data['rooms']
    assert len(rooms) == 2

    # 找到 r1（完整）和 r2（不完整）
    rooms_map = {r['room_id']: r for r in rooms}
    assert rooms_map['r1']['indicators']['trend_gmv']['status'] == 'success'
    assert rooms_map['r1']['indicators']['trend_stats']['status'] == 'success'
    assert rooms_map['r1']['completeness'] == 1.0

    assert rooms_map['r2']['indicators']['trend_gmv']['status'] == 'success'
    assert rooms_map['r2']['indicators']['trend_stats']['status'] is None
    assert rooms_map['r2']['completeness'] == 0.5


def test_account_detail_overall_completeness():
    """overall_completeness 应综合账号级 + 直播间级完整率"""
    resp = client.get('/api/batches/b1/accounts/acc1')
    data = resp.json()
    # 账号级: live_list(success) + replay_info(success) = 2/2
    # 直播间级: r1(2/2) + r2(1/2) = 3/4
    # 总计: 5 / 6 ≈ 0.8333
    assert abs(data['overall_completeness'] - 5 / 6) < 1e-6
