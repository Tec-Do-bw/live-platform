"""Lazada Token 自动更新功能测试"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from crawlers.http.lazada import LazadaHttpCrawler
from downloader import Task, DownloadResult


class TestTokenExtraction:
    """Token 提取测试"""

    def test_extract_both_tokens_success(self):
        """正常提取 _m_h5_tk 和 _m_h5_tk_enc"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')
        headers = {
            'set-cookie': '_m_h5_tk=abc123_1234567890; Path=/; Domain=.lazada.co.th, _m_h5_tk_enc=def456; Path=/; Domain=.lazada.co.th'
        }
        tokens = crawler._extract_token_from_headers(headers)
        assert tokens == {'_m_h5_tk': 'abc123_1234567890', '_m_h5_tk_enc': 'def456'}

    def test_extract_tokens_uppercase_header(self):
        """响应头大小写兼容（Set-Cookie）"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')
        headers = {
            'Set-Cookie': '_m_h5_tk=xyz789_9876543210; Path=/, _m_h5_tk_enc=uvw321; Path=/'
        }
        tokens = crawler._extract_token_from_headers(headers)
        assert tokens == {'_m_h5_tk': 'xyz789_9876543210', '_m_h5_tk_enc': 'uvw321'}

    def test_extract_tokens_no_set_cookie(self):
        """响应头无 Set-Cookie"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')
        headers = {'content-type': 'application/json'}
        tokens = crawler._extract_token_from_headers(headers)
        assert tokens == {}

    def test_extract_tokens_missing_m_h5_tk(self):
        """缺少 _m_h5_tk"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')
        headers = {'set-cookie': '_m_h5_tk_enc=def456; Path=/'}
        tokens = crawler._extract_token_from_headers(headers)
        assert '_m_h5_tk' not in tokens
        assert tokens.get('_m_h5_tk_enc') == 'def456'

    def test_extract_tokens_missing_m_h5_tk_enc(self):
        """缺少 _m_h5_tk_enc"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')
        headers = {'set-cookie': '_m_h5_tk=abc123_1234567890; Path=/'}
        tokens = crawler._extract_token_from_headers(headers)
        assert tokens.get('_m_h5_tk') == 'abc123_1234567890'
        assert '_m_h5_tk_enc' not in tokens


class TestTaskRebuild:
    """请求任务重构测试"""

    def test_rebuild_task_get_request(self):
        """重构 GET 请求任务"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')

        # 原始任务
        task = Task(
            url='https://sellercenter.lazada.co.th/api/test',
            method='GET',
            params={'t': '1234567890', 'sign': 'old_sign', 'data': '{"key":"value"}'},
            headers={'Cookie': '_m_h5_tk=old_token_111; _m_h5_tk_enc=old_enc_222'},
            meta={'api_type': 'test'},
        )

        new_tokens = {'_m_h5_tk': 'new_token_999', '_m_h5_tk_enc': 'new_enc_888'}
        new_task = crawler._rebuild_task_with_new_tokens(task, new_tokens)

        # 验证 Cookie 已更新
        assert 'new_token_999' in new_task.headers['Cookie']
        assert 'new_enc_888' in new_task.headers['Cookie']
        assert 'old_token_111' not in new_task.headers['Cookie']
        assert 'old_enc_222' not in new_task.headers['Cookie']

        # 验证签名已重新计算
        assert new_task.params['sign'] != 'old_sign'
        assert new_task.params['t'] != '1234567890'

        # 验证重试标记
        assert new_task.meta['_token_retry_count'] == 1

    def test_rebuild_task_post_request(self):
        """重构 POST 请求任务"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')

        task = Task(
            url='https://sellercenter.lazada.co.th/api/test',
            method='POST',
            params={'t': '1234567890', 'sign': 'old_sign'},
            data={'data': '{"key":"value"}'},
            headers={'Cookie': '_m_h5_tk=old_token_111; _m_h5_tk_enc=old_enc_222'},
            meta={'api_type': 'test'},
        )

        new_tokens = {'_m_h5_tk': 'new_token_999', '_m_h5_tk_enc': 'new_enc_888'}
        new_task = crawler._rebuild_task_with_new_tokens(task, new_tokens)

        # 验证 Cookie 已更新
        assert 'new_token_999' in new_task.headers['Cookie']
        assert 'new_enc_888' in new_task.headers['Cookie']

        # 验证签名已重新计算
        assert new_task.params['sign'] != 'old_sign'


class TestTokenExpiredHandling:
    """Token 过期处理测试"""

    @patch('downloader.Downloader')
    @patch('services.cookie_manager.save_cookies')
    def test_handle_token_expired_success(self, mock_save_cookies, mock_downloader_class):
        """Token 过期 → 更新成功 → 重试成功"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')

        # Mock get_cookies 返回双端口 Cookie
        with patch.object(crawler, 'get_cookies', return_value={
            'sellercenter': {'_m_h5_tk': 'old_sc', '_m_h5_tk_enc': 'old_sc_enc'},
            'live': {'_m_h5_tk': 'old_live', '_m_h5_tk_enc': 'old_live_enc'},
        }):
            # Mock get_proxy
            with patch.object(crawler, 'get_proxy', return_value='http://proxy:8080'):
                # 原始失败的响应
                failed_result = Mock(spec=DownloadResult)
                failed_result.headers = {
                    'set-cookie': '_m_h5_tk=new_token_123; Path=/, _m_h5_tk_enc=new_enc_456; Path=/'
                }
                failed_result.task = Task(
                    url='https://test.com',
                    method='GET',
                    params={'t': '111', 'sign': 'old', 'data': '{}'},
                    headers={'Cookie': '_m_h5_tk=old; _m_h5_tk_enc=old_enc'},
                    meta={'api_type': 'test'},
                )

                # Mock 重试成功的响应
                retry_success_result = Mock(spec=DownloadResult)
                retry_success_result.success = True
                retry_success_result.text = '{"code": 0, "data": {}}'
                retry_success_result.task = Mock()
                retry_success_result.task.meta = {'api_type': 'test', '_token_retry_count': 1}

                # Mock Downloader.run 返回成功结果
                mock_downloader_instance = Mock()
                mock_downloader_instance.run.return_value = [retry_success_result]
                mock_downloader_class.return_value = mock_downloader_instance

                # 执行
                result = crawler._handle_token_expired_and_retry(failed_result, 'test_api')

                # 验证 Cookie 更新（两个端口都应该更新）
                assert mock_save_cookies.call_count == 2

                # 验证返回结果
                assert result is not None
                assert result['api_type'] == 'test'

    @patch('crawlers.http.lazada.alert_manager')
    def test_handle_token_expired_no_set_cookie(self, mock_alert):
        """Token 过期但响应头无 Set-Cookie"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')

        failed_result = Mock(spec=DownloadResult)
        failed_result.headers = {}  # 无 Set-Cookie
        failed_result.task = Mock()

        result = crawler._handle_token_expired_and_retry(failed_result, 'test_api')

        # 验证返回 None
        assert result is None

        # 验证发送了告警
        mock_alert.send_alert.assert_called_once()
        assert 'token_extract_failed' in str(mock_alert.send_alert.call_args)

    @patch('downloader.Downloader')
    @patch('services.cookie_manager.save_cookies')
    def test_handle_token_expired_retry_failed(self, mock_save_cookies, mock_downloader_class):
        """Token 更新后重试仍失败"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')

        with patch.object(crawler, 'get_cookies', return_value={
            'live': {'_m_h5_tk': 'old', '_m_h5_tk_enc': 'old_enc'},
        }):
            with patch.object(crawler, 'get_proxy', return_value='http://proxy:8080'):
                failed_result = Mock(spec=DownloadResult)
                failed_result.headers = {
                    'set-cookie': '_m_h5_tk=new_token; Path=/, _m_h5_tk_enc=new_enc; Path=/'
                }
                failed_result.task = Task(
                    url='https://test.com',
                    method='GET',
                    params={'t': '111', 'sign': 'old', 'data': '{}'},
                    headers={'Cookie': '_m_h5_tk=old; _m_h5_tk_enc=old_enc'},
                    meta={'api_type': 'test'},
                )

                # Mock 重试失败
                retry_failed_result = Mock(spec=DownloadResult)
                retry_failed_result.success = False

                mock_downloader_instance = Mock()
                mock_downloader_instance.run.return_value = [retry_failed_result]
                mock_downloader_class.return_value = mock_downloader_instance

                result = crawler._handle_token_expired_and_retry(failed_result, 'test_api')

                # 验证返回 None
                assert result is None


class TestParseResponseTokenExpired:
    """parse_response 中的 Token 过期检测测试"""

    @patch.object(LazadaHttpCrawler, '_handle_token_expired_and_retry')
    def test_parse_response_detects_token_expired(self, mock_handle):
        """parse_response 检测到 Token 过期并调用处理方法"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')

        result = Mock(spec=DownloadResult)
        result.success = True
        result.text = '{"code": 1, "ret": ["FAIL_SYS_TOKEN_EXPIRED::Token expired"]}'
        result.task = Mock()
        result.task.meta = {'api_type': 'test'}
        result.task.url = 'https://test.com'

        mock_handle.return_value = {'api_type': 'test', 'data': {}}

        parsed = crawler.parse_response(result)

        # 验证调用了 Token 过期处理
        mock_handle.assert_called_once_with(result, 'test')
        assert parsed is not None

    @patch('crawlers.http.lazada.alert_manager')
    def test_parse_response_token_expired_retry_limit(self, mock_alert):
        """Token 过期但已重试过，不再重试"""
        crawler = LazadaHttpCrawler('test_account', 'test_group')

        result = Mock(spec=DownloadResult)
        result.success = True
        result.text = '{"code": 1, "ret": ["FAIL_SYS_TOKEN_EXPIRED::Token expired"]}'
        result.task = Mock()
        result.task.meta = {'api_type': 'test', '_token_retry_count': 1}
        result.task.url = 'https://test.com'

        parsed = crawler.parse_response(result)

        # 验证返回 None
        assert parsed is None

        # 验证发送了告警
        mock_alert.send_alert.assert_called_once()
        assert 'token_update_failed' in str(mock_alert.send_alert.call_args)
