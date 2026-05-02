"""测试 aui Cookie 提取功能"""

import pytest
from unittest.mock import Mock, patch
from crawlers.http.lazada import LazadaHttpCrawler
from downloader import DownloadResult


class TestAuiExtraction:
    """aui Cookie 提取测试"""

    def test_extract_aui_from_response_headers(self):
        """从响应头提取 aui"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')
        headers = {
            'set-cookie': 'aui=123456789; Path=/; Domain=.lazada.co.th, _m_h5_tk=abc; Path=/'
        }
        cookies = crawler._extract_cookies_from_headers(headers)
        assert cookies.get('aui') == '123456789'
        assert cookies.get('_m_h5_tk') == 'abc'

    def test_extract_aui_uppercase_header(self):
        """响应头大小写兼容（Set-Cookie）"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')
        headers = {
            'Set-Cookie': 'aui=987654321; Path=/'
        }
        cookies = crawler._extract_cookies_from_headers(headers)
        assert cookies.get('aui') == '987654321'

    def test_extract_no_aui(self):
        """响应头无 aui"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')
        headers = {
            'set-cookie': '_m_h5_tk=abc; Path=/'
        }
        cookies = crawler._extract_cookies_from_headers(headers)
        assert 'aui' not in cookies

    @patch('services.cookie_manager.save_cookies')
    @patch('crawlers.http.lazada._get_cookies')
    def test_update_cookies_from_response(self, mock_get_cookies, mock_save_cookies):
        """从响应头更新 aui 到内存和数据库"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')

        # 初始化内存中的 live_cookies
        crawler._live_cookies = {'_m_h5_tk': 'old_token'}

        # Mock 数据库返回
        mock_get_cookies.return_value = {'_m_h5_tk': 'old_token'}

        # 模拟响应头
        headers = {
            'set-cookie': 'aui=new_aui_value; Path=/'
        }

        # 执行更新
        crawler._update_cookies_from_response(headers)

        # 验证内存更新
        assert crawler._live_cookies.get('aui') == 'new_aui_value'

        # 验证数据库保存被调用
        mock_save_cookies.assert_called_once()
        call_args = mock_save_cookies.call_args
        assert call_args[0][0] == 'test_account'
        assert call_args[0][1] == 'lazada'
        assert call_args[0][2] == 'live'
        assert call_args[0][3].get('aui') == 'new_aui_value'

    @patch('services.cookie_manager.save_cookies')
    @patch('crawlers.http.lazada._get_cookies')
    def test_update_cookies_skip_if_same(self, mock_get_cookies, mock_save_cookies):
        """aui 值相同时跳过更新"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')

        # 内存中已有相同的 aui
        crawler._live_cookies = {'aui': 'same_aui'}

        headers = {
            'set-cookie': 'aui=same_aui; Path=/'
        }

        crawler._update_cookies_from_response(headers)

        # 验证没有调用数据库保存
        mock_save_cookies.assert_not_called()
