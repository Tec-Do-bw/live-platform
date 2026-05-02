"""BaseHttpCrawler 单元测试（API 序列驱动模式）"""

import sys
from unittest.mock import patch, MagicMock
import pytest

sys.modules.setdefault('never_primp', MagicMock())

from downloader import Task, DownloadResult


def _make_crawler_class():
    from crawlers.http.base import BaseHttpCrawler, ApiSequence

    class StubCrawler(BaseHttpCrawler):
        def get_platform_name(self):
            return 'test_http'

        def build_api_sequence(self, cookies, is_full):
            return [
                ApiSequence(
                    api_type='test_list',
                    build_initial_tasks=lambda: [
                        Task(url='http://api/list', task_id='t1', meta={'extra': None}),
                    ],
                ),
            ]

        def parse_response(self, result):
            if result.text is None:
                return None
            return {'api_type': 'test_list', 'room_id': ''}

    return StubCrawler


def _make_multi_sequence_class():
    from crawlers.http.base import BaseHttpCrawler, ApiSequence

    class MultiSeqCrawler(BaseHttpCrawler):
        def get_platform_name(self):
            return 'test_http'

        def build_api_sequence(self, cookies, is_full):
            def on_list_completed(results):
                return [
                    Task(url='http://api/detail', task_id='t2', meta={'extra': None}),
                ]

            return [
                ApiSequence(
                    api_type='test_list',
                    build_initial_tasks=lambda: [
                        Task(url='http://api/list', task_id='t1', meta={'extra': None}),
                    ],
                    on_completed=on_list_completed,
                ),
            ]

        def parse_response(self, result):
            if result.text is None:
                return None
            return {'api_type': 'test_list', 'room_id': 'r1'}

    return MultiSeqCrawler


@pytest.fixture(autouse=True)
def _mock_settings(monkeypatch):
    monkeypatch.setattr(
        'crawlers.http.base.Settings.PLATFORM_CONFIG',
        {'test_http': {'page_urls': [], 'listen_urls': []}},
    )
    monkeypatch.setattr(
        'crawlers.http.base.Settings.DATA_SERVER_CONFIG',
        {
            'enabled': True,
            'api_url': 'http://s',
            'api_sign': 's',
            'send_endpoint': '/send',
            'access_token': 't',
            'timeout': 5,
            'retries': 1,
            'retry_delay': 0,
        },
    )


@pytest.fixture()
def _mock_deps():
    mock_monitor = MagicMock()
    mock_monitor.conn = MagicMock()
    mock_status_mgr = MagicMock()
    mock_status_mgr.get_recent_events.return_value = []
    mock_tracker = MagicMock()
    mock_tracker.is_new_account.return_value = False

    patches = {
        'monitor': patch('crawlers.http.base.get_monitor', return_value=mock_monitor),
        'status_mgr': patch('crawlers.http.base.LoginStatusManager', return_value=mock_status_mgr),
        'tracker': patch('crawlers.http.base.CollectionTracker', return_value=mock_tracker),
        'send': patch('crawlers.http.base.producer_client'),
        'alert': patch('crawlers.http.base.alert_manager'),
        'dl': patch('crawlers.http.base.Downloader'),
    }
    mocks = {}
    for k, p in patches.items():
        mocks[k] = p.start()
    mocks['send'].send_to_topic.return_value = True
    yield mocks
    for p in patches.values():
        p.stop()


def _ok_result(task=None):
    t = task or Task(url='http://api/list', task_id='t1', meta={'extra': None})
    return DownloadResult(
        task=t,
        success=True,
        status_code=200,
        text='{"ok":true}',
        attempts=1,
        elapsed_ms=100,
    )


def _fail_result(task=None):
    t = task or Task(url='http://api/list', task_id='t1', meta={'extra': None})
    return DownloadResult(
        task=t,
        success=False,
        error='timeout',
        attempts=3,
        elapsed_ms=5000,
    )


class TestSingleSequence:

    def test_success(self, _mock_deps):
        _mock_deps['dl'].return_value.run.return_value = [_ok_result()]

        Cls = _make_crawler_class()
        crawler = Cls(browser_id='b1', batch_id='batch1')
        crawler.get_cookies = lambda: {'sid': 'abc'}
        result = crawler.start_crawl()

        assert result['success'] is True
        assert result['sequences_completed'] == 1
        assert result['tasks_success'] == 1
        _mock_deps['send'].send_to_topic.assert_called_once()

    def test_no_cookies_skip(self, _mock_deps):
        Cls = _make_crawler_class()
        crawler = Cls(browser_id='b1', batch_id='batch1')
        crawler.get_cookies = lambda: None
        result = crawler.start_crawl()

        assert result['success'] is False
        assert result['error'] == 'no_cookies'


class TestMultiSequence:

    def test_sequence_with_dependency(self, _mock_deps):
        dl_instance = _mock_deps['dl'].return_value
        dl_instance.run.side_effect = [
            [_ok_result()],
            [_ok_result(Task(url='http://api/detail', task_id='t2', meta={'extra': None}))],
        ]

        Cls = _make_multi_sequence_class()
        crawler = Cls(browser_id='b1', batch_id='batch1')
        crawler.get_cookies = lambda: {'sid': 'abc'}
        result = crawler.start_crawl()

        assert result['success'] is True
        assert result['sequences_completed'] == 1
        assert result['tasks_success'] == 2


class TestFailureScenarios:

    def test_sequence_all_failed_does_not_block(self, _mock_deps):
        _mock_deps['dl'].return_value.run.return_value = [_fail_result()]

        Cls = _make_crawler_class()
        crawler = Cls(browser_id='b1', batch_id='batch1')
        crawler.get_cookies = lambda: {'sid': 'abc'}
        result = crawler.start_crawl()

        assert result['success'] is True
        assert result['tasks_success'] == 0


class TestMonitorHooks:

    def test_hooks_called(self, _mock_deps):
        _mock_deps['dl'].return_value.run.return_value = [_ok_result()]

        Cls = _make_crawler_class()
        crawler = Cls(browser_id='b1', batch_id='batch1')
        crawler.get_cookies = lambda: {'sid': 'abc'}
        crawler.start_crawl()

        monitor = _mock_deps['monitor'].return_value
        monitor.start_account.assert_called_once()
        monitor.record.assert_called_once()
        monitor.finish_account.assert_called_once()


class TestAbstractMethods:

    def test_cannot_instantiate_abstract(self, _mock_deps):
        from crawlers.http.base import BaseHttpCrawler

        class IncompleteCrawler(BaseHttpCrawler):
            def get_platform_name(self):
                return 'test_http'

        with pytest.raises(TypeError):
            IncompleteCrawler(browser_id='b1')


class TestCookieHeader:

    def test_format(self):
        from crawlers.http.base import BaseHttpCrawler
        assert BaseHttpCrawler._cookie_header({'a': '1', 'b': '2'}) == 'a=1; b=2'
