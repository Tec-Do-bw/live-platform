"""TikTok HTTP URL query 白名单测试。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from crawlers.http.tiktok import collector
from utils.credentials import Credentials


ALLIANCE_KEYS = {
    "user_language",
    "locale",
    "aid",
    "app_name",
    "device_id",
    "fp",
    "device_platform",
    "cookie_enabled",
    "screen_width",
    "screen_height",
    "browser_language",
    "browser_platform",
    "browser_name",
    "browser_version",
    "browser_online",
    "timezone_name",
    "page_scene",
    "carrier_region",
}

CORE_STATS_KEYS = {
    "app_name",
    "device_id",
    "fp",
    "device_platform",
    "cookie_enabled",
    "screen_width",
    "screen_height",
    "browser_language",
    "browser_platform",
    "browser_name",
    "browser_version",
    "browser_online",
    "timezone_name",
    "vertical",
}


class FakeResponse:
    """模拟 TikTok API 响应。"""

    status_code = 200
    text = '{"code":0,"data":{"segments":[]}}'

    def json(self) -> dict[str, Any]:
        return {"code": 0, "data": {"segments": []}}

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    """记录 POST URL 的 fake session。"""

    def __init__(self) -> None:
        self.posted_urls: list[str] = []

    def post(self, url: str, **_: Any) -> FakeResponse:
        self.posted_urls.append(url)
        return FakeResponse()


def _dirty_query_string() -> str:
    return (
        "user_language=en-US&locale=en-US&aid=253642"
        "&app_name=i18n_ecom_alliance&device_id=0"
        "&fp=verify_test&device_platform=web&cookie_enabled=true"
        "&screen_width=1920&screen_height=1080&browser_language=es-MX"
        "&browser_platform=Win32&browser_name=Mozilla"
        "&browser_version=5.0+%28Windows+NT+10.0%3B+Win64%3B+x64%29"
        "&browser_online=true&timezone_name=America%2FMexico_City"
        "&page_scene=0&carrier_region=mx"
        "&msToken=dirty-token&X-Bogus=dirty-sign&extra_key=dirty-extra"
    )


def _cred() -> Credentials:
    return Credentials(
        account_id="acc-1",
        platform="tiktok",
        group_name="MX团队-tiktok",
        token="{}",
        region="MX",
        proxy="",
        ext_json=f'{{"query_string":"{_dirty_query_string()}","user_agent":"Mozilla/5.0"}}',
        extra="{}",
    )


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query, keep_blank_values=True)


def _assert_no_dirty_keys(query: dict[str, list[str]]) -> None:
    assert "msToken" not in query
    assert "X-Bogus" not in query
    assert "extra_key" not in query


def test_live_list_filters_query_string_to_alliance_keys() -> None:
    session = FakeSession()

    collector.fetch_live_list(session, _cred())

    query = _query(session.posted_urls[-1])
    assert set(query) == ALLIANCE_KEYS
    assert query["fp"] == ["verify_test"]
    assert query["app_name"] == ["i18n_ecom_alliance"]
    _assert_no_dirty_keys(query)


def test_live_stats_and_trend_chart_use_alliance_query_keys() -> None:
    session = FakeSession()
    cred = _cred()

    collector.fetch_live_stats(session, cred, date(2026, 6, 9))
    collector.fetch_trend_chart(session, cred, "room-1")

    for url in session.posted_urls:
        query = _query(url)
        assert set(query) == ALLIANCE_KEYS
        assert query["device_id"] == ["0"]
        assert query["carrier_region"] == ["mx"]
        _assert_no_dirty_keys(query)


def test_core_stats_filters_query_string_and_overrides_fixed_params() -> None:
    session = FakeSession()

    collector.fetch_core_stats(session, _cred(), "room-1")

    query = _query(session.posted_urls[-1])
    assert set(query) == CORE_STATS_KEYS
    assert query["fp"] == ["verify_test"]
    assert query["app_name"] == ["i18n_ecom_shop"]
    assert query["vertical"] == ["3"]
    _assert_no_dirty_keys(query)
