"""工厂类路由单元测试"""

import sys
from unittest.mock import patch, MagicMock
import pytest

# mock 缺失的重量级模块，避免导入失败
sys.modules.setdefault('never_primp', MagicMock())
sys.modules.setdefault('DrissionPage', MagicMock())
sys.modules.setdefault('ddddocr', MagicMock())


class TestFactoryRouting:
    """工厂类路由测试"""

    def test_browser_crawler_tiktok(self, monkeypatch):
        """tiktok 默认 crawler_type=browser 时路由到浏览器爬虫"""
        from crawlers.browser.live_crawler import LiveCrawler
        from core.config import Settings
        monkeypatch.setitem(
            Settings.PLATFORM_CONFIG,
            'tiktok',
            {**Settings.PLATFORM_CONFIG.get('tiktok', {}), 'crawler_type': 'browser'},
        )
        monkeypatch.setattr('crawlers.browser.live_crawler.load_credentials', lambda *args, **kwargs: None)
        crawler = LiveCrawler(platform='tiktok', browser_id='b1')
        assert crawler.__class__.__name__ == 'TikTokLiveCrawler'

    def test_http_crawler_tiktok_config_mode(self, monkeypatch):
        """PLATFORM_CONFIG.tiktok.crawler_type=http 时 tiktok 路由到 HTTP 适配器"""
        from crawlers.browser.live_crawler import LiveCrawler
        from core.config import Settings
        monkeypatch.setitem(
            Settings.PLATFORM_CONFIG,
            'tiktok',
            {**Settings.PLATFORM_CONFIG.get('tiktok', {}), 'crawler_type': 'http'},
        )
        monkeypatch.setattr('crawlers.browser.live_crawler.load_credentials', lambda *args, **kwargs: None)
        crawler = LiveCrawler(platform='tiktok', browser_id='b1')
        assert crawler.__class__.__name__ == 'TikTokHttpCollector'

    def test_browser_crawler_shopee(self):
        """shopee 路由到浏览器爬虫"""
        from crawlers.browser.live_crawler import LiveCrawler
        crawler = LiveCrawler(platform='shopee', browser_id='b1', group_name='马来西亚')
        assert crawler.__class__.__name__ == 'ShopeeLiveCrawler'

    def test_http_crawler_priority(self):
        """HTTP 爬虫优先级高于浏览器爬虫"""
        from crawlers.browser.live_crawler import LiveCrawler

        mock_http_cls = MagicMock()
        mock_instance = MagicMock()
        mock_http_cls.return_value = mock_instance

        LiveCrawler.HTTP_CRAWLERS['test_platform'] = mock_http_cls
        try:
            result = LiveCrawler(platform='test_platform', browser_id='b1')
            assert result is mock_instance
            mock_http_cls.assert_called_once()
        finally:
            del LiveCrawler.HTTP_CRAWLERS['test_platform']

    def test_unsupported_platform(self):
        """不支持的平台抛出 ValueError"""
        from crawlers.browser.live_crawler import LiveCrawler
        with pytest.raises(ValueError, match="不支持的平台"):
            LiveCrawler(platform='unknown_platform', browser_id='b1')

    def test_get_supported_platforms_includes_http(self):
        """get_supported_platforms 包含 HTTP 平台"""
        from crawlers.browser.live_crawler import LiveCrawler

        LiveCrawler.HTTP_CRAWLERS['lazada'] = MagicMock
        try:
            platforms = LiveCrawler.get_supported_platforms()
            assert 'lazada' in platforms
            assert 'tiktok' in platforms
            assert 'shopee' in platforms
        finally:
            del LiveCrawler.HTTP_CRAWLERS['lazada']
