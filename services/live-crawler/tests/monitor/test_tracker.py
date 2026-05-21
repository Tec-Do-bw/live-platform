import json
import pytest
from monitor.tracker import CollectionMonitor, extract_target_date


@pytest.fixture
def monitor():
    """每个测试使用独立的内存数据库"""
    return CollectionMonitor(db_path=':memory:')


class TestBatch:
    def test_start_and_finish_batch(self, monitor):
        monitor.start_batch('2026-03-08_20:00', 'once')
        monitor.start_account('2026-03-08_20:00', 'acc1')
        monitor.finish_account('2026-03-08_20:00', 'acc1', 'success')
        monitor.finish_batch('2026-03-08_20:00')

        row = monitor._conn.execute(
            "SELECT * FROM collection_batches WHERE batch_id=?", ('2026-03-08_20:00',)
        ).fetchone()
        assert row['mode'] == 'once'
        assert row['total_accounts'] == 1
        assert row['success_accounts'] == 1
        assert row['finished_at'] is not None


class TestAccount:
    def test_start_and_finish_account(self, monitor):
        monitor.start_batch('b1', 'once')
        monitor.start_account('b1', 'acc1', '美国团队-tiktok')
        monitor.finish_account('b1', 'acc1', 'partial')

        row = monitor._conn.execute(
            "SELECT * FROM account_sessions WHERE account_id='acc1'"
        ).fetchone()
        assert row['group_name'] == '美国团队-tiktok'
        assert row['status'] == 'partial'

    def test_finish_account_counts_rooms(self, monitor):
        monitor.start_batch('b1', 'once')
        monitor.start_account('b1', 'acc1')
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room1')
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room2')
        monitor.finish_account('b1', 'acc1')

        row = monitor._conn.execute(
            "SELECT total_rooms FROM account_sessions WHERE account_id='acc1'"
        ).fetchone()
        assert row['total_rooms'] == 2


class TestRecord:
    def test_record_account_level_api(self, monitor):
        monitor.start_batch('b1', 'once')
        monitor.record('b1', 'acc1', 'replay_info', status='success', response_size=1024)

        row = monitor._conn.execute(
            "SELECT * FROM collection_records WHERE api_type='replay_info'"
        ).fetchone()
        assert row['account_id'] == 'acc1'
        assert row['room_id'] == ''
        assert row['response_size'] == 1024

    def test_record_room_level_api(self, monitor):
        monitor.start_batch('b1', 'once')
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room123', status='success')

        row = monitor._conn.execute(
            "SELECT * FROM collection_records WHERE api_type='trend_gmv'"
        ).fetchone()
        assert row['room_id'] == 'room123'

    def test_record_with_extra_data(self, monitor):
        monitor.start_batch('b1', 'once')
        extra = {'revenue': '3651856', 'currency': 'IDR'}
        monitor.record('b1', 'acc1', 'live_list', extra_data=extra)

        row = monitor._conn.execute(
            "SELECT extra_data FROM collection_records WHERE api_type='live_list'"
        ).fetchone()
        data = json.loads(row['extra_data'])
        assert data['revenue'] == '3651856'

    def test_record_upsert(self, monitor):
        """重复记录应更新而非报错"""
        monitor.start_batch('b1', 'once')
        monitor.record('b1', 'acc1', 'live_list', status='failed')
        monitor.record('b1', 'acc1', 'live_list', status='success')

        rows = monitor._conn.execute(
            "SELECT * FROM collection_records WHERE api_type='live_list' AND account_id='acc1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]['status'] == 'success'


class TestRecordRooms:
    def test_record_rooms_stores_gmv(self, monitor):
        monitor.start_batch('b1', 'once')
        rooms = [
            {'room_id': 'r1', 'room_name': 'SALE', 'revenue': '1000', 'item_sold_cnt': 5},
            {'room_id': 'r2', 'room_name': 'LIVE', 'revenue': '2000', 'item_sold_cnt': 10},
        ]
        monitor.record_rooms('b1', 'acc1', rooms)

        row = monitor._conn.execute(
            "SELECT extra_data FROM collection_records WHERE api_type='live_list'"
        ).fetchone()
        data = json.loads(row['extra_data'])
        assert len(data['rooms']) == 2
        assert data['rooms'][0]['room_id'] == 'r1'


class TestInsertRoomSession:
    def test_insert_room_session_basic(self, monitor):
        """_insert_room_session 应写入 room_sessions 表"""
        monitor.start_batch('b1', 'once')
        monitor._insert_room_session('b1', 'acc1', 'room1', 1710403200, 1710417600)

        row = monitor._conn.execute(
            "SELECT * FROM room_sessions WHERE room_id='room1'"
        ).fetchone()
        assert row is not None
        assert row['batch_id'] == 'b1'
        assert row['account_id'] == 'acc1'
        assert row['start_time'] == 1710403200
        assert row['end_time'] == 1710417600

    def test_insert_room_session_duplicate_ignored(self, monitor):
        """重复写入同一 room 应不报错（UNIQUE 约束用 INSERT OR IGNORE）"""
        monitor.start_batch('b1', 'once')
        monitor._insert_room_session('b1', 'acc1', 'room1', 100, 200)
        monitor._insert_room_session('b1', 'acc1', 'room1', 100, 200)

        rows = monitor._conn.execute(
            "SELECT * FROM room_sessions WHERE room_id='room1'"
        ).fetchall()
        assert len(rows) == 1


class TestRecordRoomsV2:
    def test_record_rooms_writes_room_sessions(self, monitor):
        """record_rooms 应同时写入 room_sessions 表"""
        monitor.start_batch('b1', 'once')
        rooms = [
            {'room_id': 'r1', 'room_name': 'SALE', 'live_start_ts': 1000, 'live_end_ts': 2000},
            {'room_id': 'r2', 'room_name': 'LIVE', 'live_start_ts': 3000, 'live_end_ts': 4000},
        ]
        monitor.record_rooms('b1', 'acc1', rooms)

        sessions = monitor._conn.execute(
            "SELECT * FROM room_sessions WHERE batch_id='b1' ORDER BY room_id"
        ).fetchall()
        assert len(sessions) == 2
        assert sessions[0]['room_id'] == 'r1'
        assert sessions[0]['start_time'] == 1000
        assert sessions[1]['room_id'] == 'r2'
        assert sessions[1]['start_time'] == 3000

    def test_record_rooms_still_records_live_list(self, monitor):
        """record_rooms 改造后仍应记录 live_list 的 collection_record"""
        monitor.start_batch('b1', 'once')
        rooms = [{'room_id': 'r1', 'room_name': 'X'}]
        monitor.record_rooms('b1', 'acc1', rooms)

        row = monitor._conn.execute(
            "SELECT * FROM collection_records WHERE api_type='live_list'"
        ).fetchone()
        assert row is not None
        assert row['status'] == 'success'

    def test_record_rooms_empty_list(self, monitor):
        """空 rooms_data 仍应记录 live_list 成功状态"""
        monitor.start_batch('b1', 'once')
        monitor.record_rooms('b1', 'acc1', [])

        row = monitor._conn.execute(
            "SELECT * FROM collection_records WHERE api_type='live_list'"
        ).fetchone()
        assert row is not None
        assert row['status'] == 'success'

        sessions = monitor._conn.execute(
            "SELECT * FROM room_sessions WHERE batch_id='b1'"
        ).fetchall()
        assert len(sessions) == 0


class TestRecordDailyStats:
    def test_record_daily_stats_basic(self, monitor):
        """record_daily_stats 应写入 daily_collection_status 表"""
        monitor.start_batch('b1', 'once')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'success')

        row = monitor._conn.execute(
            "SELECT * FROM daily_collection_status "
            "WHERE batch_id='b1' AND target_date='2026-03-12'"
        ).fetchone()
        assert row is not None
        assert row['api_type'] == 'live_stats'
        assert row['status'] == 'success'

    def test_record_daily_stats_upsert(self, monitor):
        """重复写入应更新状态"""
        monitor.start_batch('b1', 'once')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'failed')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'success')

        rows = monitor._conn.execute(
            "SELECT * FROM daily_collection_status "
            "WHERE batch_id='b1' AND target_date='2026-03-12'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]['status'] == 'success'

    def test_record_daily_stats_multiple_dates(self, monitor):
        """应支持同一账号多天记录"""
        monitor.start_batch('b1', 'once')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-13')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-14')

        rows = monitor._conn.execute(
            "SELECT * FROM daily_collection_status WHERE batch_id='b1' ORDER BY target_date"
        ).fetchall()
        assert len(rows) == 3


class TestExtractTargetDate:
    def test_extract_from_valid_request_body(self):
        """从标准 live/stats 请求体中提取 target_date"""
        body = {
            'request': {
                'params': [{
                    'time_selector': {
                        'start_timestamp': 1710201600,  # 2024-03-12 00:00:00 UTC
                        'end_timestamp': 1710374400,
                    }
                }]
            }
        }
        result = extract_target_date(body)
        assert result == '2024-03-12'  # 自定义时间模式下 start 即目标日

    def test_extract_returns_none_for_empty_body(self):
        """空请求体应返回 None"""
        assert extract_target_date({}) is None

    def test_extract_returns_none_for_missing_params(self):
        """缺少 params 应返回 None"""
        body = {'request': {}}
        assert extract_target_date(body) is None

    def test_extract_returns_none_for_zero_timestamp(self):
        """timestamp 为 0 应返回 None"""
        body = {
            'request': {
                'params': [{
                    'time_selector': {'start_timestamp': 0}
                }]
            }
        }
        assert extract_target_date(body) is None
