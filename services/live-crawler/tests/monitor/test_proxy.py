"""代理获取模块测试"""

from unittest.mock import patch, MagicMock
from monitor.recrawl.proxy import get_proxy_for_account, build_proxy_url


class TestBuildProxyUrl:

    def test_socks5_with_auth(self):
        config = {
            'proxy_soft': 'other', 'proxy_type': 'socks5',
            'proxy_host': '1.2.3.4', 'proxy_port': '1080',
            'proxy_user': 'user', 'proxy_password': 'pass',
        }
        url = build_proxy_url(config)
        assert url == 'socks5://user:pass@1.2.3.4:1080'

    def test_http_without_auth(self):
        config = {
            'proxy_soft': 'other', 'proxy_type': 'http',
            'proxy_host': '1.2.3.4', 'proxy_port': '8080',
        }
        url = build_proxy_url(config)
        assert url == 'http://1.2.3.4:8080'

    def test_no_proxy(self):
        config = {'proxy_soft': 'no_proxy'}
        url = build_proxy_url(config)
        assert url is None


class TestGetProxyForAccount:

    @patch('monitor.recrawl.proxy.requests.post')
    def test_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                'code': 0,
                'data': {
                    'list': [{
                        'profile_id': 'acc1',
                        'user_proxy_config': {
                            'proxy_soft': 'other', 'proxy_type': 'socks5',
                            'proxy_host': '1.2.3.4', 'proxy_port': '1080',
                            'proxy_user': 'user', 'proxy_password': 'pass',
                        },
                    }],
                },
            },
        )
        proxy = get_proxy_for_account('acc1')
        assert proxy == {'https': 'socks5://user:pass@1.2.3.4:1080', 'http': 'socks5://user:pass@1.2.3.4:1080'}

    @patch('monitor.recrawl.proxy.requests.post')
    def test_not_found(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {'code': 0, 'data': {'list': []}},
        )
        proxy = get_proxy_for_account('nonexistent')
        assert proxy is None
