from __future__ import annotations

import pytest

from monitor.schemas.dashboard import DashboardDataRequest, DashboardDataType, DashboardTimeRange
from services import dashboard_data
from services.dashboard_data import DashboardApiError
from utils.types import FatalError, LoginRequired


class FakeCred:
    token_data = [{"name": "sid", "value": "token"}]


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _req(data_type=DashboardDataType.core_stats, time_range=DashboardTimeRange.full):
    return DashboardDataRequest(
        dataType=data_type,
        roomId="room-1",
        collectionId="coll-1",
        timeRange=time_range,
    )


def _fetch_result():
    return {
        "ok": True,
        "url": "https://shop.tiktok.com/api",
        "request_body": "{\"request\":{}}",
        "response_body": "{\"code\":0}",
        "data": {"code": 0},
    }


def test_fetch_dashboard_data_builds_success_envelope(monkeypatch):
    session = FakeSession()
    seen = {}

    def mock_setup_session(collection_id, *, skip_verification=False):
        seen["skip_verification"] = skip_verification
        return FakeCred(), session, None

    monkeypatch.setattr(dashboard_data, "setup_session", mock_setup_session)

    def fake_fetcher(got_session, got_cred, room_id):
        seen["args"] = (got_session, got_cred, room_id)
        return _fetch_result()

    monkeypatch.setitem(dashboard_data.DASHBOARD_FETCHERS, DashboardDataType.core_stats, fake_fetcher)
    monkeypatch.setattr(
        dashboard_data,
        "_format_message",
        lambda url, request_body, response_body, cookies, socket_user_id: {
            "fromUrl": url,
            "extra": request_body,
            "request": {"response": response_body, "url": url},
            "cookies": cookies,
            "socketUserId": socket_user_id,
        },
    )

    result = dashboard_data.fetch_dashboard_data(_req())

    assert result["code"] == 200
    assert result["message"] == "success"
    assert result["data"]["dataSource"] == "live_crawler_tiktok_http"
    assert result["data"]["dataType"] == "core_stats"
    assert result["data"]["roomId"] == "room-1"
    assert result["data"]["socketUserId"] == "coll-1"
    assert seen["args"][0] is session
    assert seen["args"][2] == "room-1"
    assert seen["skip_verification"] is True  # 验证传入 skip_verification=True
    assert session.closed is True


@pytest.mark.parametrize(
    ("time_range", "expected_start_time"),
    [
        (DashboardTimeRange.full, None),
        (DashboardTimeRange.last_5m, 1700000000 - 300),
        (DashboardTimeRange.last_30m, 1700000000 - 1800),
    ],
)
def test_trend_chart_time_range_maps_to_start_time(monkeypatch, time_range, expected_start_time):
    session = FakeSession()
    seen = {}

    monkeypatch.setattr(
        dashboard_data,
        "setup_session",
        lambda collection_id, *, skip_verification=False: (FakeCred(), session, None),
    )
    monkeypatch.setattr(
        dashboard_data,
        "_format_message",
        lambda url, request_body, response_body, cookies, socket_user_id: {},
    )

    def fake_fetcher(got_session, got_cred, room_id, start_time):
        seen["args"] = (got_session, room_id, start_time)
        return _fetch_result()

    monkeypatch.setitem(dashboard_data.DASHBOARD_FETCHERS, DashboardDataType.trend_chart, fake_fetcher)

    dashboard_data.fetch_dashboard_data(
        _req(DashboardDataType.trend_chart, time_range),
        now_func=lambda: 1700000000,
    )

    assert seen["args"] == (session, "room-1", expected_start_time)
    assert session.closed is True


@pytest.mark.parametrize(
    ("time_range", "expected_granularity"),
    [
        (DashboardTimeRange.full, None),
        (DashboardTimeRange.last_5m, 5),
    ],
)
def test_product_list_time_range_maps_to_granularity(monkeypatch, time_range, expected_granularity):
    session = FakeSession()
    seen = {}

    monkeypatch.setattr(
        dashboard_data,
        "setup_session",
        lambda collection_id, *, skip_verification=False: (FakeCred(), session, None),
    )
    monkeypatch.setattr(
        dashboard_data,
        "_format_message",
        lambda url, request_body, response_body, cookies, socket_user_id: {},
    )

    def fake_fetcher(got_session, got_cred, room_id, granularity):
        seen["args"] = (got_session, room_id, granularity)
        return _fetch_result()

    monkeypatch.setitem(dashboard_data.DASHBOARD_FETCHERS, DashboardDataType.product_list, fake_fetcher)

    dashboard_data.fetch_dashboard_data(_req(DashboardDataType.product_list, time_range))

    assert seen["args"] == (session, "room-1", expected_granularity)
    assert session.closed is True


def test_product_list_rejects_last_30m_time_range():
    with pytest.raises(ValueError, match="product_list only supports"):
        _req(DashboardDataType.product_list, DashboardTimeRange.last_30m)


@pytest.mark.parametrize(
    ("exc", "code", "reason"),
    [
        (LoginRequired("login expired"), 5001, "login_required"),
        (FatalError("missing credential"), 4041, "session_not_found"),
        (ValueError("bad response"), 5001, "upstream_error"),
        (RuntimeError("boom"), 5099, "internal_error"),
    ],
)
def test_fetch_dashboard_data_maps_errors_and_closes_session(monkeypatch, exc, code, reason):
    session = FakeSession()
    monkeypatch.setattr(
        dashboard_data,
        "setup_session",
        lambda collection_id, *, skip_verification=False: (FakeCred(), session, None),
    )

    def fake_fetcher(*args):
        raise exc

    monkeypatch.setitem(dashboard_data.DASHBOARD_FETCHERS, DashboardDataType.core_stats, fake_fetcher)

    with pytest.raises(DashboardApiError) as err:
        dashboard_data.fetch_dashboard_data(_req())

    assert err.value.code == code
    assert err.value.reason == reason
    assert err.value.detail == str(exc)
    assert session.closed is True


@pytest.mark.parametrize(
    ("exc", "expected_reason"),
    [
        (TimeoutError("slow"), "upstream_timeout"),
        (ConnectionError("reset"), "upstream_error"),
    ],
)
def test_fetch_dashboard_data_maps_retry_exceptions(monkeypatch, exc, expected_reason):
    session = FakeSession()
    monkeypatch.setattr(
        dashboard_data,
        "setup_session",
        lambda collection_id, *, skip_verification=False: (FakeCred(), session, None),
    )

    def fake_fetcher(*args):
        raise exc

    monkeypatch.setitem(dashboard_data.DASHBOARD_FETCHERS, DashboardDataType.core_stats, fake_fetcher)

    with pytest.raises(DashboardApiError) as err:
        dashboard_data.fetch_dashboard_data(_req())

    assert err.value.code == 5001
    assert err.value.reason == expected_reason
    assert session.closed is True


def test_fetch_dashboard_data_maps_setup_login_required_without_session(monkeypatch):
    def mock_setup_session(collection_id, *, skip_verification=False):
        raise LoginRequired("login expired")

    monkeypatch.setattr(dashboard_data, "setup_session", mock_setup_session)

    with pytest.raises(DashboardApiError) as err:
        dashboard_data.fetch_dashboard_data(_req())

    assert err.value.code == 5001
    assert err.value.reason == "login_required"
