"""Shopee 店铺切换单元测试"""
import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys

# 最小化加载避免真实依赖
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def _make_crawler(is_cross_border=False):
    """构造最小可测试的 Shopee 爬虫实例"""
    from crawlers.browser import shopee as shopee_module

    crawler = object.__new__(shopee_module.ShopeeLiveCrawler)
    crawler.is_cross_border = is_cross_border
    crawler.country_domain = "cn" if is_cross_border else "com.my"
    crawler.media_shop_id = "123456"
    crawler.media_user_id = "999"
    crawler.browser_api = MagicMock()
    crawler.tab = MagicMock()
    crawler.tab.cookies.return_value = [
        {'name': 'SPC_CDS', 'value': 'test_cds_token'}
    ]
    crawler.send_login_callback = MagicMock(return_value=True)
    crawler._fetch_login_info_via_js = MagicMock(return_value=True)
    crawler._sync_remark_country_if_needed = MagicMock()
    crawler._open_collection_page = MagicMock()
    crawler._get_country_from_remark = MagicMock(return_value=None)

    return crawler


def test_switch_to_shop_by_http_success():
    """跨境店 HTTP 切换成功"""
    crawler = _make_crawler(is_cross_border=True)

    # Mock run_js_fetch 三次调用：switch / set_language / get_session
    crawler.browser_api.run_js_fetch.side_effect = [
        # ① switch_merchant_shop
        [{'response': {'code': 0}}],
        # ② set_language
        [{'response': {'code': 0}}],
        # ③ get_session 验证
        [{'response': {
            'code': 0,
            'sub_account_info': {'current_shop_id': 789012}
        }}],
    ]

    result = crawler._switch_to_shop_by_http("789012", "MY")

    assert result is True
    assert crawler.browser_api.run_js_fetch.call_count == 3


def test_switch_to_shop_by_http_cookie_expired():
    """跨境店切换遇到 HTTP 403，触发 cookie_expired 回调"""
    crawler = _make_crawler(is_cross_border=True)

    crawler.browser_api.run_js_fetch.return_value = [
        {'error': 'status_403'}
    ]

    result = crawler._switch_to_shop_by_http("789012", "MY")

    assert result is False
    crawler.send_login_callback.assert_called_once_with("logout", reason="cookie_expired")


def test_switch_to_shop_by_http_verify_failed():
    """跨境店切换后校验 shop_id 不匹配"""
    crawler = _make_crawler(is_cross_border=True)

    crawler.browser_api.run_js_fetch.side_effect = [
        [{'response': {'code': 0}}],  # switch 成功
        [{'response': {'code': 0}}],  # set_language 成功
        [{'response': {
            'code': 0,
            'sub_account_info': {'current_shop_id': 999999}  # 不匹配
        }}],
    ]

    result = crawler._switch_to_shop_by_http("789012", "MY")

    assert result is False


def test_switch_to_shop_cross_border_route():
    """_switch_to_shop 跨境店走 HTTP 路径"""
    crawler = _make_crawler(is_cross_border=True)
    crawler._get_shop_region_from_list = MagicMock(return_value="MY")
    crawler._switch_to_shop_by_http = MagicMock(return_value=True)

    result = crawler._switch_to_shop("789012", "https://seller.shopee.cn/test")

    assert result is True
    crawler._switch_to_shop_by_http.assert_called_once_with("789012", "MY")
    crawler._fetch_login_info_via_js.assert_called_once()


def test_switch_to_shop_local_route():
    """_switch_to_shop 本土店走浏览器点击路径"""
    crawler = _make_crawler(is_cross_border=False)
    crawler._switch_to_shop_by_browser = MagicMock(return_value=True)

    result = crawler._switch_to_shop("789012", "https://seller.shopee.com.my/test")

    assert result is True
    crawler._switch_to_shop_by_browser.assert_called_once_with("789012", "https://seller.shopee.com.my/test")
