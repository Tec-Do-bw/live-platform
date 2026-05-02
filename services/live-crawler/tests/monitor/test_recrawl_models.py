"""补采任务数据模型测试"""

import pytest
from monitor.db import get_connection, init_db
from monitor.recrawl.models import (
    create_task_auto, create_task_manual, get_pending_tasks,
    update_task_status, get_tasks_by_account,
    save_request_context, get_request_context, cleanup_old_tasks,
)


@pytest.fixture
def conn():
    c = get_connection(':memory:')
    init_db(c)
    yield c
    c.close()


class TestRecrawlTasks:
    """补采任务 CRUD 测试"""

    def test_create_task_auto(self, conn):
        """自动补采创建任务"""
        task_id = create_task_auto(
            conn, batch_id='2026-03-14_14:30', account_id='acc1',
            group_name='新加坡团队', room_id='room1', target_date='',
            api_type='trend_gmv', level='room',
        )
        assert task_id is not None
        tasks = get_pending_tasks(conn)
        assert len(tasks) == 1
        assert tasks[0]['api_type'] == 'trend_gmv'
        assert tasks[0]['source'] == 'auto'

    def test_create_task_auto_duplicate_ignored(self, conn):
        """自动补采重复任务被忽略"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        tasks = get_pending_tasks(conn)
        assert len(tasks) == 1

    def test_create_task_manual_resets_failed(self, conn):
        """手动触发可重置已失败的任务"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        update_task_status(conn, 1, 'recrawl_failed', retry_count=3, error_msg='timeout')
        create_task_manual(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        tasks = get_pending_tasks(conn)
        assert len(tasks) == 1
        assert tasks[0]['status'] == 'pending'
        assert tasks[0]['retry_count'] == 0
        assert tasks[0]['source'] == 'manual'

    def test_create_task_manual_resets_success(self, conn):
        """手动触发可重置已成功的任务"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        update_task_status(conn, 1, 'success')
        create_task_manual(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        tasks = get_pending_tasks(conn)
        assert len(tasks) == 1

    def test_update_task_status(self, conn):
        """更新任务状态"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', '', '', 'live_list', 'account')
        update_task_status(conn, 1, 'running')
        tasks = get_tasks_by_account(conn, 'acc1')
        assert tasks[0]['status'] == 'running'

    def test_get_tasks_by_account_with_status_filter(self, conn):
        """按账号和状态筛选任务"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', '', '', 'live_list', 'account')
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        update_task_status(conn, 1, 'success')
        pending = get_tasks_by_account(conn, 'acc1', status='pending')
        assert len(pending) == 1
        assert pending[0]['api_type'] == 'trend_gmv'


class TestRequestContext:
    """请求上下文缓存测试"""

    def test_save_and_get_context(self, conn):
        """保存并读取请求上下文"""
        save_request_context(
            conn, account_id='acc1', context_type='trend_chart',
            api_base_url='https://shop.tiktok.com',
            query_string='aid=123&fp=abc',
            headers='{"Content-Type": "application/json"}',
            cookies='[{"name": "sessionid", "value": "xxx"}]',
        )
        ctx = get_request_context(conn, 'acc1', 'trend_chart')
        assert ctx is not None
        assert ctx['api_base_url'] == 'https://shop.tiktok.com'
        assert ctx['query_string'] == 'aid=123&fp=abc'

    def test_save_context_upsert(self, conn):
        """重复保存会更新而非报错"""
        save_request_context(conn, 'acc1', 'trend_chart', api_base_url='https://old.com')
        save_request_context(conn, 'acc1', 'trend_chart', api_base_url='https://new.com')
        ctx = get_request_context(conn, 'acc1', 'trend_chart')
        assert ctx['api_base_url'] == 'https://new.com'

    def test_get_context_not_found(self, conn):
        """未找到上下文返回 None"""
        ctx = get_request_context(conn, 'acc1', 'trend_chart')
        assert ctx is None


class TestCleanup:
    """数据清理测试"""

    def test_cleanup_old_tasks(self, conn):
        """清理旧任务"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', '', '', 'live_list', 'account')
        update_task_status(conn, 1, 'success')
        # 手动修改 updated_at 为 31 天前
        conn.execute(
            "UPDATE recrawl_tasks SET updated_at = datetime('now', '-31 days') WHERE id = 1"
        )
        conn.commit()
        deleted = cleanup_old_tasks(conn, days=30)
        assert deleted == 1
        assert len(get_tasks_by_account(conn, 'acc1')) == 0
