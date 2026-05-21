"""Shopee JS 注入主采集链路测试。"""

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


def _load_shopee_module():
    """最小化加载 Shopee 模块，避免真实浏览器与配置依赖。"""
    module_name = "crawlers.browser.shopee_for_test"
    if module_name in sys.modules:
        return sys.modules[module_name]

    swapped_modules = {}

    def _swap_module(name: str, module: types.ModuleType) -> None:
        swapped_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    fake_crawlers = types.ModuleType("crawlers")
    fake_crawlers.__path__ = []
    _swap_module("crawlers", fake_crawlers)

    fake_browser = types.ModuleType("crawlers.browser")
    fake_browser.__path__ = []
    _swap_module("crawlers.browser", fake_browser)

    fake_utils = types.ModuleType("utils")
    fake_utils.__path__ = []
    _swap_module("utils", fake_utils)

    fake_core = types.ModuleType("core")
    fake_core.__path__ = []
    _swap_module("core", fake_core)

    fake_base = types.ModuleType("crawlers.browser.base")

    class DummyBaseLiveCrawler:
        def __init__(
            self,
            browser_id: str | None = None,
            full_collection: bool = False,
            group_name: str = "",
            batch_id: str = "",
            **kwargs,
        ) -> None:
            self.browser_id = browser_id
            self.full_collection = full_collection
            self.group_name = group_name
            self.batch_id = batch_id
            self.socket_user_id = browser_id
            self.config = {}
            self.browser_api = None
            self.login_status = True

        def format_api_message(self, url, request_body, response_body, cookies):
            return {
                "url": url,
                "request_body": request_body,
                "response_body": response_body,
                "cookies": cookies,
            }

        def send_api_request(self, message):
            return True

        def send_login_callback(self, login_status, reason=""):
            return True

    fake_base.BaseLiveCrawler = DummyBaseLiveCrawler
    _swap_module("crawlers.browser.base", fake_base)

    fake_logger_module = types.ModuleType("utils.logger")

    class DummyLogger:
        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

        def success(self, *args, **kwargs):
            pass

    fake_logger_module.logger = DummyLogger()
    _swap_module("utils.logger", fake_logger_module)

    fake_request_module = types.ModuleType("utils.request")

    class DummySession:
        def __init__(self) -> None:
            self.headers = {}

        def get(self, *args, **kwargs):
            raise RuntimeError("测试中不应发起真实 HTTP 请求")

    class DummyRequestSession:
        @staticmethod
        def get_session():
            return DummySession()

    fake_request_module.RequestSession = DummyRequestSession
    _swap_module("utils.request", fake_request_module)

    fake_adspower_module = types.ModuleType("utils.adspower_client")
    fake_adspower_module.get_adspower_client = MagicMock()
    fake_adspower_module.AdsPowerRateLimitError = type("AdsPowerRateLimitError", (Exception,), {})
    fake_adspower_module.AdsPowerApiError = type("AdsPowerApiError", (Exception,), {})
    _swap_module("utils.adspower_client", fake_adspower_module)

    fake_config_module = types.ModuleType("core.config")

    class DummySettings:
        DATA_SERVER_CONFIG = {"api_sign": "test-sign"}

    fake_config_module.Settings = DummySettings
    _swap_module("core.config", fake_config_module)

    module_path = Path(__file__).resolve().parents[3] / "crawlers" / "browser" / "shopee.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in swapped_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _make_crawler(full_collection: bool = False):
    """构造最小可测试的 Shopee 爬虫实例。"""
    shopee_module = _load_shopee_module()
    crawler = object.__new__(shopee_module.ShopeeLiveCrawler)
    crawler.full_collection = full_collection
    crawler.country_domain = "com.my"
    crawler.group_name = "马来团队-shopee"
    crawler.browser_id = "test-browser"
    crawler.batch_id = "batch-1"
    crawler.socket_user_id = "test-browser"
    crawler.login_status = True
    crawler.login_checked = False
    crawler.media_user_id = None
    crawler.media_shop_id = None
    crawler.pending_messages = []
    crawler._country_yesterday_cache = "2026-03-29"
    crawler.config = {
        "wait_time": 8,
        "listen_urls": ["api/supply/lm/sellercenter/realtime/sessionList"],
    }
    crawler.tab = MagicMock()
    crawler.tab.url = "https://seller.shopee.com.my/creator-center/insight/live/list"
    crawler.browser_api = MagicMock()
    crawler.send_login_callback = MagicMock(return_value=True)
    crawler.send_api_request = MagicMock(return_value=True)
    crawler.format_api_message = MagicMock(
        side_effect=lambda **kwargs: {
            "url": kwargs["url"],
            "request_body": kwargs["request_body"],
            "response_body": kwargs["response_body"],
            "cookies": kwargs["cookies"],
        }
    )
    return crawler


def test_check_login_status_reads_required_cookies():
    """登录检测应识别 Shopee 关键 cookies。"""
    crawler = _make_crawler()
    crawler.is_cross_border = False
    crawler.tab.cookies.return_value = [
        {"name": "SPC_SC_SESSION", "value": "session-token"},
        {"name": "SC_SSO", "value": "sso-token"},
    ]
    crawler._verify_login_by_api = MagicMock(return_value=(True, {"id": "u", "shopid": "s"}))

    assert crawler._check_login_status() == "logged_in"


def test_check_login_status_passes_without_sc_sso():
    """缺少 SC_SSO 但 API 验证通过时，应继续采集而非视为无权限。"""
    crawler = _make_crawler()
    crawler.is_cross_border = False
    crawler.tab.cookies.return_value = [
        {"name": "SPC_SC_SESSION", "value": "session-token"},
    ]
    crawler._verify_login_by_api = MagicMock(return_value=(True, {"id": "u", "shopid": "s"}))

    assert crawler._check_login_status() == "logged_in"


def test_fetch_login_info_via_js_captures_media_ids():
    """login 接口返回后应保存 media_user_id 与 media_shop_id。"""
    crawler = _make_crawler()
    crawler.browser_api.run_js_fetch.return_value = [
        {
            "url": "https://seller.shopee.com.my/api/v2/login/",
            "response": json.dumps(
                {
                    "user": {
                        "user_id": "user-1",
                        "shop_id": "shop-2",
                    }
                }
            ),
        }
    ]

    assert crawler._fetch_login_info_via_js() is True
    assert crawler.media_user_id == "user-1"
    assert crawler.media_shop_id == "shop-2"


def test_build_params_for_incremental_mode():
    """增量模式应使用 7d 参数口径，并允许覆盖页码。"""
    crawler = _make_crawler(full_collection=False)

    assert crawler._build_live_list_params(page=2) == {
        "page": "2",
        "pageSize": "100",
        "name": "",
        "orderBy": "",
        "sort": "",
        "timeDim": "7d",
        "endDate": "2026-03-29",
    }
    assert crawler._build_overview_params("2026-03-29") == {
        "endDate": "2026-03-29",
        "timeDim": "1d",
    }


def test_build_params_for_full_mode():
    """全量模式应使用 30d 参数口径（liveList）和 1d 逐日请求（overview）。"""
    crawler = _make_crawler(full_collection=True)

    assert crawler._build_live_list_params()["timeDim"] == "30d"
    assert crawler._build_overview_params("2026-03-29")["timeDim"] == "1d"


def test_fetch_live_list_pages_via_js_fetches_all_pages_in_full_mode():
    """全量模式应翻页拉取 liveList/v2 直到覆盖全部场次。"""
    crawler = _make_crawler(full_collection=True)
    crawler.browser_api.run_js_fetch.side_effect = [
        [
            {
                "url": "https://seller.shopee.com.my/api/supply/lm/sellercenter/liveList/v2?page=1",
                "response": {
                    "data": {
                        "total": 150,
                        "list": [{"sessionId": "room-1"}] * 100,
                    }
                },
            }
        ],
        [
            {
                "url": "https://seller.shopee.com.my/api/supply/lm/sellercenter/liveList/v2?page=2",
                "response": {
                    "data": {
                        "total": 150,
                        "list": [{"sessionId": "room-2"}] * 50,
                    }
                },
            }
        ],
    ]

    results = crawler._fetch_live_list_pages_via_js({"x-test-header": "token"})

    assert [item["url"] for item in results] == [
        "https://seller.shopee.com.my/api/supply/lm/sellercenter/liveList/v2?page=1",
        "https://seller.shopee.com.my/api/supply/lm/sellercenter/liveList/v2?page=2",
    ]
    fetch_calls = crawler.browser_api.run_js_fetch.call_args_list
    assert "page=1" in fetch_calls[0].args[1][0]["url"]
    assert "page=2" in fetch_calls[1].args[1][0]["url"]
    assert fetch_calls[0].args[1][0]["headers"]["x-test-header"] == "token"
    assert fetch_calls[0].args[1][0]["headers"]["referer"] == crawler.tab.url


def test_handle_live_list_page_sends_paginated_live_list_and_detail_requests():
    """列表页应发送 sessionList、分页 liveList、概览与详情请求数据。"""
    crawler = _make_crawler(full_collection=True)
    session_data = {
        "url": "https://seller.shopee.com.my/api/supply/lm/sellercenter/realtime/sessionList",
        "response": {
            "data": {
                "list": [
                    {
                        "sessionId": "live-1",
                        "status": 1,
                        "startTime": 100,
                        "endTime": 200,
                    }
                ]
            }
        },
        "headers": {"x-test-header": "token"},
    }
    crawler.browser_api.get_listened_data.return_value = [session_data]
    crawler._fetch_live_list_pages_via_js = MagicMock(
        return_value=[
            {
                "url": "https://seller.shopee.com.my/api/supply/lm/sellercenter/liveList/v2?page=1",
                "response": {
                    "data": {
                        "list": [
                            {
                                "sessionId": "replay-1",
                                "status": 2,
                            }
                        ]
                    }
                },
            }
        ]
    )
    crawler._fetch_overview_requests_via_js = MagicMock(
        return_value=[
            {
                "url": "https://seller.shopee.com.my/api/supply/lm/sellercenter/overview/v3?timeDim=30d",
                "response": {"overview": True},
            },
            {
                "url": "https://seller.shopee.com.my/api/supply/lm/sellercenter/metricTrend/v2?timeDim=30d",
                "response": {"trend": True},
            },
        ]
    )
    crawler._fetch_session_detail_via_js = MagicMock(
        return_value=[
            {
                "url": "https://seller.shopee.com.my/api/supply/lm/sellercenter/dashboard/overview?sessionId=live-1",
                "response": {"detail": True},
            }
        ]
    )
    crawler._fetch_replay_detail_via_js = MagicMock(
        return_value=[
            {
                "url": "https://seller.shopee.com.my/api/supply/lm/sellercenter/liveDetail?sessionId=replay-1",
                "response": {"replay": True},
            },
            {
                "url": "https://seller.shopee.com.my/api/supply/lm/sellercenter/liveCoordinate/v2?sessionId=replay-1",
                "response": {"coordinate": True},
            },
        ]
    )

    sent_urls = []

    def _record_send(data):
        sent_urls.append(data["url"])
        return True

    crawler._send_data = _record_send

    stats = crawler._handle_live_list_page()

    assert sent_urls == [
        session_data["url"],
        "https://seller.shopee.com.my/api/supply/lm/sellercenter/liveList/v2?page=1",
        "https://seller.shopee.com.my/api/supply/lm/sellercenter/overview/v3?timeDim=30d",
        "https://seller.shopee.com.my/api/supply/lm/sellercenter/metricTrend/v2?timeDim=30d",
        "https://seller.shopee.com.my/api/supply/lm/sellercenter/liveDetail?sessionId=replay-1",
        "https://seller.shopee.com.my/api/supply/lm/sellercenter/liveCoordinate/v2?sessionId=replay-1",
    ]
    # live-1 (status=1) 被 _filter_sessions 过滤，不调用 session_detail
    assert stats == {"apis_count": 6, "data_sent": 6}
    crawler._fetch_live_list_pages_via_js.assert_called_once_with(session_data["headers"])
    crawler._fetch_overview_requests_via_js.assert_called_once_with(session_data["headers"])
    crawler._fetch_session_detail_via_js.assert_not_called()
    crawler._fetch_replay_detail_via_js.assert_called_once()
