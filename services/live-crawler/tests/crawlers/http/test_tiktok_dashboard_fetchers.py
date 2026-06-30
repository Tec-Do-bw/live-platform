from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from crawlers.http.tiktok import collector, real_collector
from utils.credentials import Credentials


DASHBOARD_CORE_STATS_TYPES = [
    15, 27, 7, 344, 50, 346, 348, 71, 10, 20, 330, 29, 70, 11, 39, 43, 343, 23, 310, 325, 130, 30,
    332, 323, 349, 62, 61, 60, 331, 312, 313, 314, 315, 241, 283, 3, 2, 5, 18, 17, 290, 291,
    292, -3, -2, -7, -344, -23, -20, -18, -39, -10, -11, -70, -71,
]
DASHBOARD_TREND_CHART_TYPES = [
    3, 52, 82, 41, 344, 20, 11, 50, 14, 84, 51, 92, 23, 13, 12, 16, 312, 313, 314, 315, 401,
    15, 91, 343, 350, 81, 323,
]
USER_PORTRAIT_TYPES = [80, 81, 82, 83, 90, 85, 86, 87, 88, 350, 351, 352, 353]
PRODUCT_LIST_TYPES = [4, 5, 6, 7, 10, 15, 17, 18, 21, 30, 35, 41, 48, 51, 55, 64, 120, 301, 345]


class FakeResponse:
    status_code = 200

    def __init__(self, data: dict[str, Any]):
        self._data = data
        self.text = json.dumps(data)

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, response_data: dict[str, Any] | None = None):
        self.response_data = response_data or {"code": 0, "message": "success", "data": {"ok": True}}
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.posts.append({"url": url, "kwargs": kwargs})
        return FakeResponse(self.response_data)


def _cred() -> Credentials:
    query_string = (
        "app_name=i18n_ecom_alliance&device_id=0&fp=verify_test&device_platform=web"
        "&cookie_enabled=true&screen_width=1920&screen_height=1080"
        "&browser_language=vi-VN&browser_platform=Win32&browser_name=Mozilla"
        "&browser_version=5.0&browser_online=true&timezone_name=Asia%2FHo_Chi_Minh"
        "&vertical=1&msToken=dirty-token&X-Bogus=dirty-sign"
    )
    return Credentials(
        account_id="k19f2q44",
        platform="tiktok",
        group_name="越南团队-tiktok",
        token="{}",
        region="VN",
        proxy="",
        ext_json=json.dumps(
            {
                "query_string": query_string,
                "creator_id": "7158775580024210437",
                "user_agent": "Mozilla/5.0",
            }
        ),
        extra="{}",
    )


def _last_payload(session: FakeSession) -> dict[str, Any]:
    return session.posts[-1]["kwargs"]["json"]


def _last_query(session: FakeSession) -> dict[str, list[str]]:
    return parse_qs(urlparse(session.posts[-1]["url"]).query, keep_blank_values=True)


def test_core_stats_uses_dashboard_full_stats_creator_and_country():
    session = FakeSession()

    result = real_collector.fetch_dashboard_core_stats(session, _cred(), "7651420995556182804")

    payload = _last_payload(session)
    room_filter = payload["request"]["room_filter"]
    assert result["ok"] is True
    assert "/api/v1/insights/workbench/live/detail/core/stats" in result["url"]
    assert room_filter == {
        "room_id": "7651420995556182804",
        "is_content_type": 1,
        "creator_id": "7158775580024210437",
        "country": "VN",
    }
    assert payload["request"]["stats_types"] == DASHBOARD_CORE_STATS_TYPES
    assert real_collector.DASHBOARD_CORE_STATS_TYPES == DASHBOARD_CORE_STATS_TYPES
    assert len(payload["request"]["stats_types"]) == 55
    assert -344 in payload["request"]["stats_types"]


def test_dashboard_urls_filter_dirty_query_keys_and_override_app_name():
    session = FakeSession()

    real_collector.fetch_dashboard_room_info(session, _cred(), "room-1")

    query = _last_query(session)
    assert query["app_name"] == ["i18n_ecom_shop"]
    assert query["vertical"] == ["3"]
    assert query["fp"] == ["verify_test"]
    assert "msToken" not in query
    assert "X-Bogus" not in query


def test_trend_chart_uses_independent_27_ids_and_optional_start_time():
    session = FakeSession()

    real_collector.fetch_dashboard_trend_chart(session, _cred(), "room-1", start_time=1782211225)

    payload = _last_payload(session)
    assert payload["request"]["stats_types"] == DASHBOARD_TREND_CHART_TYPES
    assert real_collector.DASHBOARD_TREND_CHART_TYPES == DASHBOARD_TREND_CHART_TYPES
    assert len(payload["request"]["stats_types"]) == 27
    assert payload["request"]["stats_types"] != collector.CORE_STATS_TYPES
    assert payload["request"]["start_time"] == 1782211225


def test_trend_chart_full_range_omits_start_time():
    session = FakeSession()

    real_collector.fetch_dashboard_trend_chart(session, _cred(), "room-1")

    assert "start_time" not in _last_payload(session)["request"]


def test_source_new_uses_v3_room_filter_payload():
    session = FakeSession()

    real_collector.fetch_dashboard_source_new(session, _cred(), "room-1")

    payload = _last_payload(session)
    assert "/api/v3/insights/workbench/live/detail/source/new" in session.posts[-1]["url"]
    assert payload == {
        "request": {"stats_types": [100], "room_filter": {"room_id": "room-1", "is_content_type": 1}},
        "version": 3,
    }


def test_user_portrait_product_list_and_room_info_payloads():
    cred = _cred()

    portrait_session = FakeSession()
    real_collector.fetch_dashboard_user_portrait(portrait_session, cred, "room-1")
    assert _last_payload(portrait_session)["request"]["stats_types"] == USER_PORTRAIT_TYPES
    assert real_collector.USER_PORTRAIT_TYPES == USER_PORTRAIT_TYPES

    product_session = FakeSession()
    real_collector.fetch_dashboard_product_list(product_session, cred, "room-1")
    product_payload = _last_payload(product_session)
    assert product_payload["request"]["sorting_type"] == 1
    assert product_payload["request"]["stats_types"] == PRODUCT_LIST_TYPES
    assert real_collector.PRODUCT_LIST_TYPES == PRODUCT_LIST_TYPES

    room_session = FakeSession()
    real_collector.fetch_dashboard_room_info(room_session, cred, "room-1")
    room_payload = _last_payload(room_session)
    assert room_payload["request"] == {"room_filter": {"room_id": "room-1", "is_content_type": 1}}


def test_product_list_optional_granularity_payload():
    cred = _cred()

    product_session = FakeSession()
    real_collector.fetch_dashboard_product_list(product_session, cred, "room-1")
    product_payload = _last_payload(product_session)
    assert "granularity" not in product_payload["request"]

    product_last_5m_session = FakeSession()
    real_collector.fetch_dashboard_product_list(product_last_5m_session, cred, "room-1", granularity=5)
    product_last_5m_payload = _last_payload(product_last_5m_session)
    assert product_last_5m_payload["request"]["granularity"] == 5


def test_tiktok_business_code_is_preserved_as_successful_fetch_result():
    session = FakeSession({"code": 98001021, "message": "call downstream server error", "data": {}})

    result = real_collector.fetch_dashboard_trend_chart(session, _cred(), "room-1")

    assert result["ok"] is True
    assert json.loads(result["response_body"])["code"] == 98001021
