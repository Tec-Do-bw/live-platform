"""补采执行器测试"""

import pytest
from unittest.mock import patch, MagicMock
from monitor.db import get_connection, init_db
from monitor.recrawl.models import create_task_auto, save_request_context, get_pending_tasks
from monitor.recrawl.executor import execute_pending_tasks, _execute_single_task, RecrawlHTTPError


@pytest.fixture
def conn():
    c = get_connection(':memory:')
    init_db(c)
    yield c
    c.close()


class TestExecutor:

    def test_empty_tasks(self, conn):
        """无 pending 任务时直接返回"""
        stats = execute_pending_tasks(conn)
        assert stats['total'] == 0

    @patch('monitor.recrawl.executor.Settings')
    def test_disabled_config(self, mock_settings, conn):
        """配置关闭时跳过执行"""
        mock_settings.RECRAWL_CONFIG = {'enabled': False}
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', '', '', 'live_list', 'account')
        stats = execute_pending_tasks(conn)
        assert stats['total'] == 0

    def test_skip_without_context(self, conn):
        """无请求上下文时任务被 skip"""
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        task = get_pending_tasks(conn)[0]
        config = {'max_retry': 3, 'retry_delays': [1, 3, 10]}
        result = _execute_single_task(conn, task, None, config)
        assert result == 'skipped'

    @patch('monitor.recrawl.executor.http_requests.post')
    def test_trend_gmv_success(self, mock_post, conn):
        """有上下文时成功发起 HTTP 请求并上报"""
        # mock TikTok API 返回
        mock_api_resp = MagicMock()
        mock_api_resp.status_code = 200
        mock_api_resp.json.return_value = {'code': 0, 'data': {'stats': []}}

        # mock 数据服务器上报返回
        mock_upload_resp = MagicMock()
        mock_upload_resp.status_code = 200

        mock_post.side_effect = [mock_api_resp, mock_upload_resp]

        save_request_context(
            conn, 'acc1', 'trend_chart',
            api_base_url='https://shop.tiktok.com',
            query_string='aid=123&fp=abc',
            headers='{"Content-Type": "application/json"}',
            cookies='[{"name": "sessionid", "value": "xxx"}]',
        )
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        task = get_pending_tasks(conn)[0]
        config = {'max_retry': 3, 'retry_delays': [1, 3, 10]}
        result = _execute_single_task(conn, task, None, config)
        assert result == 'success'
        # 验证调用了两次 POST（一次 TikTok API，一次数据服务器）
        assert mock_post.call_count == 2

    @patch('monitor.recrawl.executor.http_requests.post')
    def test_http_403_marks_failed_immediately(self, mock_post, conn):
        """HTTP 403 直接标记失败，不做无意义重试"""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = 'Forbidden'
        mock_post.return_value = mock_resp

        save_request_context(conn, 'acc1', 'trend_chart', api_base_url='https://shop.tiktok.com')
        create_task_auto(conn, '2026-03-14_14:30', 'acc1', '', 'room1', '', 'trend_gmv', 'room')
        task = get_pending_tasks(conn)[0]
        config = {'max_retry': 3, 'retry_delays': [0, 0, 0]}
        result = _execute_single_task(conn, task, None, config)
        assert result == 'failed'
        # 403 应该使用 RecrawlHTTPError 精确判断，只调用一次就终止
        assert mock_post.call_count == 1
