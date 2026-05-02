"""缺失检测器测试 — 验证三级缺失检测逻辑"""

import pytest
from monitor.tracker import CollectionMonitor
from monitor.recrawl.gap_detector import (
    detect_account_gaps,
    detect_daily_gaps,
    detect_room_gaps,
    detect_all_gaps,
    detect_and_create_tasks,
)
from monitor.recrawl.models import get_pending_tasks


@pytest.fixture
def monitor():
    """每个测试使用独立的内存数据库"""
    return CollectionMonitor(db_path=':memory:')


def _seed_batch(monitor, batch_id='b1', accounts=None):
    """辅助函数：快速创建批次和账号

    Args:
        monitor: CollectionMonitor 实例
        batch_id: 批次 ID
        accounts: 账号列表，每项为 (account_id, group_name) 或 (account_id, group_name, platform)
    """
    monitor.start_batch(batch_id, 'once')
    if accounts:
        for acc in accounts:
            acc_id, group = acc[0], acc[1]
            platform = acc[2] if len(acc) > 2 else 'tiktok'
            monitor.start_account(batch_id, acc_id, group, platform)


class TestAccountGaps:
    """账号级缺失检测"""

    def test_no_gaps_when_all_collected(self, monitor):
        """所有账号级 API 都已采集，应无缺失"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        # 模拟采集了 live_list 和 replay_info
        monitor.record('b1', 'acc1', 'live_list', status='success')
        monitor.record('b1', 'acc1', 'replay_info', status='success')

        gaps = detect_account_gaps(monitor.conn, 'b1')
        assert len(gaps) == 0

    def test_detect_missing_api(self, monitor):
        """只采集了 live_list，缺少 replay_info"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        monitor.record('b1', 'acc1', 'live_list', status='success')

        gaps = detect_account_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'replay_info'
        assert gaps[0]['account_id'] == 'acc1'
        assert gaps[0]['level'] == 'account'

    def test_detect_all_missing_for_account(self, monitor):
        """账号无任何记录，所有账号级 API 都应标记为缺失"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])

        gaps = detect_account_gaps(monitor.conn, 'b1')
        assert len(gaps) == 2  # live_list + replay_info
        api_types = {g['api_type'] for g in gaps}
        assert 'live_list' in api_types
        assert 'replay_info' in api_types

    def test_failed_status_counts_as_missing(self, monitor):
        """status='failed' 的记录不算成功，应报为缺失"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        monitor.record('b1', 'acc1', 'live_list', status='failed')
        monitor.record('b1', 'acc1', 'replay_info', status='success')

        gaps = detect_account_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'live_list'

    def test_multiple_accounts(self, monitor):
        """多个账号分别检测"""
        _seed_batch(monitor, accounts=[('acc1', '团队A'), ('acc2', '团队B')])
        # acc1 全部采集，acc2 缺少 replay_info
        monitor.record('b1', 'acc1', 'live_list', status='success')
        monitor.record('b1', 'acc1', 'replay_info', status='success')
        monitor.record('b1', 'acc2', 'live_list', status='success')

        gaps = detect_account_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['account_id'] == 'acc2'
        assert gaps[0]['group_name'] == '团队B'


class TestDailyGaps:
    """日期级缺失检测"""

    def test_no_gaps_when_all_success(self, monitor):
        """所有日期级记录都是 success，无缺失"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'success')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-13', 'live_stats', 'success')

        gaps = detect_daily_gaps(monitor.conn, 'b1')
        assert len(gaps) == 0

    def test_detect_failed_daily(self, monitor):
        """status='failed' 的日期级记录应报为缺失"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'success')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-13', 'live_stats', 'failed')

        gaps = detect_daily_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['target_date'] == '2026-03-13'
        assert gaps[0]['api_type'] == 'live_stats'
        assert gaps[0]['level'] == 'daily'

    def test_detect_empty_daily(self, monitor):
        """status='empty' 的日期级记录也应报为缺失"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'empty')

        gaps = detect_daily_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['target_date'] == '2026-03-12'

    def test_no_daily_records_means_no_gaps(self, monitor):
        """如果没有任何日期级记录（即没有尝试采集），不应报缺失"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])

        gaps = detect_daily_gaps(monitor.conn, 'b1')
        assert len(gaps) == 0

    def test_multiple_accounts_daily(self, monitor):
        """多账号日期级检测"""
        _seed_batch(monitor, accounts=[('acc1', '团队A'), ('acc2', '团队B')])
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'success')
        monitor.record_daily_stats('b1', 'acc2', '2026-03-12', 'live_stats', 'failed')

        gaps = detect_daily_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['account_id'] == 'acc2'


class TestRoomGaps:
    """直播间级缺失检测"""

    def test_no_gaps_when_all_collected(self, monitor):
        """所有直播间级 API 都已采集"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        # 模拟 room_sessions
        monitor._insert_room_session('b1', 'acc1', 'room1')
        # 模拟 room 级别的 API 采集
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room1', status='success')
        monitor.record('b1', 'acc1', 'trend_stats', room_id='room1', status='success')

        gaps = detect_room_gaps(monitor.conn, 'b1')
        assert len(gaps) == 0

    def test_detect_missing_room_api(self, monitor):
        """直播间缺少 trend_stats"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        monitor._insert_room_session('b1', 'acc1', 'room1')
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room1', status='success')

        gaps = detect_room_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'trend_stats'
        assert gaps[0]['room_id'] == 'room1'
        assert gaps[0]['level'] == 'room'

    def test_detect_all_missing_for_room(self, monitor):
        """直播间无任何采集记录"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        monitor._insert_room_session('b1', 'acc1', 'room1')

        gaps = detect_room_gaps(monitor.conn, 'b1')
        assert len(gaps) == 2  # trend_gmv + trend_stats
        api_types = {g['api_type'] for g in gaps}
        assert 'trend_gmv' in api_types
        assert 'trend_stats' in api_types

    def test_multiple_rooms(self, monitor):
        """多个直播间分别检测"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        monitor._insert_room_session('b1', 'acc1', 'room1')
        monitor._insert_room_session('b1', 'acc1', 'room2')
        # room1 全部采集，room2 缺少 trend_gmv
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room1', status='success')
        monitor.record('b1', 'acc1', 'trend_stats', room_id='room1', status='success')
        monitor.record('b1', 'acc1', 'trend_stats', room_id='room2', status='success')

        gaps = detect_room_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['room_id'] == 'room2'
        assert gaps[0]['api_type'] == 'trend_gmv'

    def test_carries_group_name(self, monitor):
        """缺失记录应携带 group_name"""
        _seed_batch(monitor, accounts=[('acc1', '新加坡团队')])
        monitor._insert_room_session('b1', 'acc1', 'room1')

        gaps = detect_room_gaps(monitor.conn, 'b1')
        assert gaps[0]['group_name'] == '新加坡团队'


class TestDetectAllGaps:
    """全量检测"""

    def test_detect_all_merges_levels(self, monitor):
        """detect_all_gaps 合并三个级别的缺失"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        # 账号级：缺少 replay_info
        monitor.record('b1', 'acc1', 'live_list', status='success')
        # 日期级：一天失败
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'failed')
        # 直播间级：缺少 trend_stats
        monitor._insert_room_session('b1', 'acc1', 'room1')
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room1', status='success')

        gaps = detect_all_gaps(monitor.conn, 'b1')
        levels = {g['level'] for g in gaps}
        assert 'account' in levels
        assert 'daily' in levels
        assert 'room' in levels

    def test_empty_batch_only_account_gaps(self, monitor):
        """空批次（只有账号但没有任何采集）只报账号级缺失"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])

        gaps = detect_all_gaps(monitor.conn, 'b1')
        # 账号级应有 2 个缺失 (live_list + replay_info)
        # 日期级无记录，不报缺失
        # 直播间级无 room，不报缺失
        assert len(gaps) == 2
        assert all(g['level'] == 'account' for g in gaps)


class TestDetectAndCreateTasks:
    """检测并创建补采任务"""

    def test_creates_tasks_for_gaps(self, monitor):
        """应为每个缺失创建 pending 补采任务"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        # 缺少 replay_info
        monitor.record('b1', 'acc1', 'live_list', status='success')
        # 直播间缺少 trend_stats
        monitor._insert_room_session('b1', 'acc1', 'room1')
        monitor.record('b1', 'acc1', 'trend_gmv', room_id='room1', status='success')

        created = detect_and_create_tasks(monitor.conn, 'b1')
        assert created == 2  # 1 个 account 级 + 1 个 room 级

        tasks = get_pending_tasks(monitor.conn)
        assert len(tasks) == 2
        api_types = {t['api_type'] for t in tasks}
        assert 'replay_info' in api_types
        assert 'trend_stats' in api_types

    def test_duplicate_detection_no_double_tasks(self, monitor):
        """重复检测不应创建重复任务"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])

        created1 = detect_and_create_tasks(monitor.conn, 'b1')
        created2 = detect_and_create_tasks(monitor.conn, 'b1')

        assert created1 == 2  # live_list + replay_info
        assert created2 == 0  # 重复任务被忽略

        tasks = get_pending_tasks(monitor.conn)
        assert len(tasks) == 2

    def test_creates_daily_tasks(self, monitor):
        """日期级缺失也应创建补采任务"""
        _seed_batch(monitor, accounts=[('acc1', '团队A')])
        monitor.record('b1', 'acc1', 'live_list', status='success')
        monitor.record('b1', 'acc1', 'replay_info', status='success')
        monitor.record_daily_stats('b1', 'acc1', '2026-03-12', 'live_stats', 'failed')

        created = detect_and_create_tasks(monitor.conn, 'b1')
        assert created == 1

        tasks = get_pending_tasks(monitor.conn)
        assert tasks[0]['api_type'] == 'live_stats'
        assert tasks[0]['target_date'] == '2026-03-12'
        assert tasks[0]['level'] == 'daily'


class TestShopeeGaps:
    """Shopee 平台缺失检测"""

    def test_shopee_account_gaps(self, monitor):
        """Shopee 账号应检测 session_list 和 live_list"""
        _seed_batch(monitor, accounts=[('sp1', '马来团队', 'shopee')])
        monitor.record('b1', 'sp1', 'session_list', status='success')

        gaps = detect_account_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'live_list'

    def test_shopee_room_gaps(self, monitor):
        """Shopee 直播间应检测 session_detail 和 replay_detail"""
        _seed_batch(monitor, accounts=[('sp1', '印尼团队', 'shopee')])
        monitor._insert_room_session('b1', 'sp1', 'sess1')
        monitor.record('b1', 'sp1', 'session_detail', room_id='sess1', status='success')

        gaps = detect_room_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'replay_detail'

    def test_shopee_daily_gaps(self, monitor):
        """Shopee 日期级应检测 overview 和 metric_trend"""
        _seed_batch(monitor, accounts=[('sp1', '泰国团队', 'shopee')])
        monitor.record_daily_stats('b1', 'sp1', '2026-04-07', 'overview', 'success')
        monitor.record_daily_stats('b1', 'sp1', '2026-04-07', 'metric_trend', 'failed')

        gaps = detect_daily_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['api_type'] == 'metric_trend'

    def test_mixed_platform_batch(self, monitor):
        """混合平台批次：TK 和 Shopee 各自检测对应的 API 类型"""
        _seed_batch(monitor, accounts=[('tk1', '团队A', 'tiktok'), ('sp1', '新加坡团队', 'shopee')])
        # TK 账号全部采集
        monitor.record('b1', 'tk1', 'live_list', status='success')
        monitor.record('b1', 'tk1', 'replay_info', status='success')
        # Shopee 账号缺少 live_list
        monitor.record('b1', 'sp1', 'session_list', status='success')

        gaps = detect_account_gaps(monitor.conn, 'b1')
        assert len(gaps) == 1
        assert gaps[0]['account_id'] == 'sp1'
        assert gaps[0]['api_type'] == 'live_list'
