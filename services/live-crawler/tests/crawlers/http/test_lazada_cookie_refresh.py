"""Lazada 采集前 Cookie 自动刷新测试"""

import pytest
from unittest.mock import patch, MagicMock


class TestRefreshCookies:
    """_refresh_cookies() 方法测试"""

    def _make_crawler(self):
        from crawlers.http.lazada import LazadaHttpCrawler
        return LazadaHttpCrawler('test_account', group_name='泰国团队-lazada')

    @patch('crawlers.http.lazada.cookie_manager')
    @patch('cookie_keeper.browser_refresher.BrowserRefresher.refresh_account')
    def test_refresh_success(self, mock_refresh, mock_cm):
        """刷新成功：两个端点都返回 Cookie"""
        mock_cm.get_account_credentials.return_value = {'username': 'u', 'password': 'p'}
        mock_refresh.return_value = {
            'sellercenter': {'cookie_a': '1'},
            'live': {'cookie_b': '2'},
        }

        crawler = self._make_crawler()
        assert crawler._refresh_cookies() is True

        assert mock_cm.save_cookies.call_count == 2
        mock_cm.save_cookies.assert_any_call(
            'test_account', 'lazada', endpoint='sellercenter', cookies={'cookie_a': '1'}
        )
        mock_cm.save_cookies.assert_any_call(
            'test_account', 'lazada', endpoint='live', cookies={'cookie_b': '2'}
        )

    @patch('crawlers.http.lazada.cookie_manager')
    def test_no_credentials(self, mock_cm):
        """无凭证时返回 False，不调用 BrowserRefresher"""
        mock_cm.get_account_credentials.return_value = None

        crawler = self._make_crawler()
        assert crawler._refresh_cookies() is False

    @patch('crawlers.http.lazada.cookie_manager')
    @patch('cookie_keeper.browser_refresher.BrowserRefresher.refresh_account')
    def test_refresh_exception(self, mock_refresh, mock_cm):
        """BrowserRefresher 抛异常时返回 False"""
        mock_cm.get_account_credentials.return_value = {'username': 'u', 'password': 'p'}
        mock_refresh.side_effect = Exception('浏览器启动失败')

        crawler = self._make_crawler()
        assert crawler._refresh_cookies() is False

    @patch('crawlers.http.lazada.cookie_manager')
    @patch('cookie_keeper.browser_refresher.BrowserRefresher.refresh_account')
    def test_partial_failure(self, mock_refresh, mock_cm):
        """一个端点刷新失败（返回 None）时返回 False"""
        mock_cm.get_account_credentials.return_value = {'username': 'u', 'password': 'p'}
        mock_refresh.return_value = {
            'sellercenter': {'cookie_a': '1'},
            'live': None,
        }

        crawler = self._make_crawler()
        assert crawler._refresh_cookies() is False
        # sellercenter 的 Cookie 仍然应该被保存
        mock_cm.save_cookies.assert_called_once_with(
            'test_account', 'lazada', endpoint='sellercenter', cookies={'cookie_a': '1'}
        )


class TestStartCrawlCallsRefresh:
    """验证 start_crawl() 在采集前调用 _refresh_cookies()"""

    @patch('crawlers.http.lazada.LazadaHttpCrawler._refresh_cookies')
    @patch('crawlers.http.base.BaseHttpCrawler.start_crawl')
    def test_refresh_called_before_crawl(self, mock_super_crawl, mock_refresh):
        """start_crawl() 先调用 _refresh_cookies()，再调用 super().start_crawl()"""
        from crawlers.http.lazada import LazadaHttpCrawler

        mock_refresh.return_value = True
        mock_super_crawl.return_value = {'success': True}

        crawler = LazadaHttpCrawler('test_account', group_name='泰国团队-lazada')
        crawler.skipped_api_types = []
        result = crawler.start_crawl()

        mock_refresh.assert_called_once()
        mock_super_crawl.assert_called_once()
        assert result['success'] is True

    @patch('crawlers.http.lazada.LazadaHttpCrawler._refresh_cookies')
    @patch('crawlers.http.base.BaseHttpCrawler.start_crawl')
    def test_crawl_stops_on_refresh_failure(self, mock_super_crawl, mock_refresh):
        """Cookie 不存在且刷新失败时终止采集"""
        from crawlers.http.lazada import LazadaHttpCrawler

        mock_refresh.return_value = False
        mock_super_crawl.return_value = {'success': False}

        crawler = LazadaHttpCrawler('test_account', group_name='泰国团队-lazada')
        crawler.skipped_api_types = []
        result = crawler.start_crawl()

        mock_refresh.assert_called_once()
        mock_super_crawl.assert_not_called()
        assert result == {'success': False, 'error': 'refresh_failed'}
