"""AdsPower 代理获取工具测试。"""

from unittest.mock import MagicMock, patch

from utils.adspower_proxy import build_proxy_url, get_proxy_for_account


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

    @patch('utils.adspower_proxy.AdsPowerClient')
    def test_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.post.return_value = {
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
        }
        mock_client_cls.return_value = mock_client

        proxy = get_proxy_for_account('acc1', api_url='http://127.0.0.1:50325')

        mock_client.post.assert_called_once_with(
            '/api/v2/browser-profile/list',
            json={'profile_id': ['acc1']},
        )
        assert proxy == {
            'https': 'socks5://user:pass@1.2.3.4:1080',
            'http': 'socks5://user:pass@1.2.3.4:1080',
        }

    @patch('utils.adspower_proxy.AdsPowerClient')
    def test_not_found(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.post.return_value = {'code': 0, 'data': {'list': []}}
        mock_client_cls.return_value = mock_client

        proxy = get_proxy_for_account('nonexistent', api_url='http://127.0.0.1:50325')

        assert proxy is None
