"""TikTok HTTP collector 单元测试。"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).parents[3]
LIVE_CRAWLER_ROOT = PROJECT_ROOT / "services" / "live-crawler"
if str(LIVE_CRAWLER_ROOT) not in sys.path:
    sys.path.insert(0, str(LIVE_CRAWLER_ROOT))

from crawlers.http.tiktok.collector import (  # noqa: E402
    _format_message,
    collect_tiktok,
    fetch_account_info,
    fetch_core_stats,
    fetch_live_list,
    fetch_live_stats,
    fetch_trend_chart,
    filter_rooms_by_window,
    parse_rooms,
)
import crawlers.http.tiktok.collector as collector_mod  # noqa: E402
from utils.credentials import Credentials  # noqa: E402


class FakeResponse:
    """curl_cffi Response 的最小桩。"""

    def __init__(self, data: dict[str, Any], status_code: int = 200):
        self._data = data
        self.status_code = status_code
        self.text = json.dumps(data, ensure_ascii=False)

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """按 URL 端点返回固定响应的 Session 桩。"""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self.cookies: dict[str, str] = {}

    def close(self) -> None:
        """collect_tiktok 在 finally 中会调用，桩需提供空实现。"""

    def get(self, url: str, *, headers: dict[str, str], timeout: int) -> FakeResponse:
        self.calls.append({"method": "GET", "url": url, "headers": headers, "timeout": timeout})
        assert headers
        assert timeout == 10
        assert "api/v1/streamer_desktop/account_info/get" in url
        return FakeResponse({"code": 0, "data": {"user_id": "creator-1"}})

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: int,
    ) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, "headers": headers, "json": json, "timeout": timeout})
        assert headers
        assert timeout in {10, 15}

        if "api/v2/insights/creator/live/list" in url:
            return FakeResponse(_live_list_payload())
        if "api/v2/insights/creator/live/stats" in url:
            return FakeResponse({"code": 0, "data": {"stats": []}})
        if "api/v1/insights/creator/liveroom/recap/trend/chart" in url:
            return FakeResponse({"code": 0, "data": {"trend": []}})
        if "api/v1/insights/workbench/live/detail/core/stats" in url:
            return FakeResponse({"code": 0, "data": {"core": []}})
        raise AssertionError(f"unexpected url: {url}")


def _cred() -> Credentials:
    ext = {
        "query_string": "device_id=dev1&fp=fp1&browser_name=Chrome&carrier_region=SG",
        "creator_id": "creator-1",
        "user_agent": "Mozilla/5.0",
    }
    return Credentials(
        account_id="acct-1",
        platform="tiktok",
        group_name="sg-team",
        token=json.dumps([{"name": "sessionid", "value": "sid"}]),
        region="SG",
        proxy="",
        ext_json=json.dumps(ext),
        extra="{}",
    )


def _live_list_payload() -> dict[str, Any]:
    now = int(datetime.now(timezone.utc).timestamp())
    return {
        "code": 0,
        "data": {
            "segments": [
                {
                    "filter": {"creator_id": ["creator-1"]},
                    "timed_lists": [
                        {
                            "stats": [
                                {
                                    "live_id": "room-1",
                                    "live_name": "Morning Live",
                                    "live_start_timestamp": now - 7200,
                                    "live_end_timestamp": now - 3600,
                                    "revenue": {"amount": "12.34", "currency_code": "SGD"},
                                },
                                {
                                    "live_id": "room-open",
                                    "live_name": "Open Live",
                                    "live_start_timestamp": now,
                                    "live_end_timestamp": 0,
                                    "revenue": {"amount": "0", "currency_code": "SGD"},
                                },
                            ]
                        }
                    ],
                }
            ]
        },
    }


def _assert_fetch_result(result: dict[str, Any]) -> None:
    assert set(result) == {"ok", "url", "request_body", "response_body", "data"}
    assert result["ok"] is True
    assert isinstance(result["url"], str)
    assert "shop.tiktok.com" in result["url"]
    assert isinstance(result["response_body"], str)
    assert isinstance(result["data"], dict)


def test_fetch_account_info_returns_fetch_result() -> None:
    result = fetch_account_info(FakeSession(), _cred())
    _assert_fetch_result(result)
    assert result["request_body"] is None


def test_fetch_live_list_returns_fetch_result() -> None:
    result = fetch_live_list(FakeSession(), _cred(), full=False)
    _assert_fetch_result(result)
    assert "stats_types" in result["request_body"]


def test_fetch_live_stats_returns_fetch_result() -> None:
    result = fetch_live_stats(FakeSession(), _cred(), date(2026, 5, 28))
    _assert_fetch_result(result)
    assert "start_timestamp" in result["request_body"]
    # 结构须对齐页面原生 payload：params 数组 + is_live_type + 专用 stats_types（接口文档 §2.1）
    body = json.loads(result["request_body"])
    params = body["request"]["params"][0]
    assert params["is_live_type"] is True
    assert params["stats_types"] == [11, 115, 13, 200, 106, 81, 82, 201, 202, 70, 210, 211, 212, 213]


def test_fetch_trend_chart_returns_fetch_result() -> None:
    result = fetch_trend_chart(FakeSession(), _cred(), "room-1")
    _assert_fetch_result(result)
    assert "room-1" in result["request_body"]


def test_fetch_core_stats_returns_fetch_result() -> None:
    result = fetch_core_stats(FakeSession(), _cred(), "room-1")
    _assert_fetch_result(result)
    assert "creator-1" in result["request_body"]


def test_parse_rooms_extracts_closed_rooms_and_creator_id() -> None:
    rooms, creator_id = parse_rooms(_live_list_payload())
    assert creator_id == "creator-1"
    assert len(rooms) == 1
    assert rooms[0]["room_id"] == "room-1"
    assert rooms[0]["currency_code"] == "SGD"


def test_filter_rooms_by_window_keeps_recent_incremental_rooms() -> None:
    now = int(datetime.now(timezone.utc).timestamp())
    rooms = [
        {
            "room_id": "recent",
            "room_name": "",
            "live_start_ts": now - 100,
            "live_end_ts": now - 50,
            "revenue": "0",
            "currency_code": "",
        },
        {
            "room_id": "old",
            "room_name": "",
            "live_start_ts": now - 10 * 86400,
            "live_end_ts": now - 9 * 86400,
            "revenue": "0",
            "currency_code": "",
        },
    ]
    assert [room["room_id"] for room in filter_rooms_by_window(rooms, "SG", full=False)] == ["recent"]
    assert len(filter_rooms_by_window(rooms, "SG", full=True)) == 2


def test_format_message_matches_browser_field_contract_for_dicts() -> None:
    message = _format_message(
        "https://shop.tiktok.com/api",
        {"a": "中文"},
        {"ok": True},
        [{"name": "sessionid", "value": "sid"}],
        "socket-1",
    )
    assert set(message) == {
        "params",
        "cookies",
        "fromUrl",
        "extra",
        "sign",
        "userType",
        "updateTime",
        "request",
        "socketUserId",
    }
    assert message["params"] == ""
    assert json.loads(message["extra"]) == {"a": "中文"}
    assert json.loads(message["request"]["response"]) == {"ok": True}
    assert message["socketUserId"] == "socket-1"


def test_format_message_preserves_browser_none_extra_behavior() -> None:
    message = _format_message("https://shop.tiktok.com/api", None, "{}", {}, "socket-1")
    assert message["extra"] is None


# ============ 回归：业务码校验（B 修复）============


class FakeErrorCodeSession(FakeSession):
    """所有 POST 端点返回 HTTP 200 + code≠0（模拟风控/登出脏响应）。"""

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return FakeResponse({"code": 10002, "message": "not login"})


def test_fetch_returns_not_ok_on_business_error_code() -> None:
    """HTTP 200 + code≠0 时 fetch 必须返回 ok=False，避免脏数据上报。"""
    session = FakeErrorCodeSession()
    cred = _cred()
    assert fetch_live_list(session, cred, full=False)["ok"] is False
    assert fetch_live_stats(session, cred, date(2026, 5, 28))["ok"] is False
    assert fetch_trend_chart(session, cred, "room-1")["ok"] is False
    assert fetch_core_stats(session, cred, "room-1")["ok"] is False


# ============ 回归：增量模式 live/stats 不缺失（P0 修复）============


def _patch_collect_deps(monkeypatch: Any, session: FakeSession, cred: Credentials) -> None:
    monkeypatch.setattr(collector_mod, "load_credentials", lambda *a, **k: cred)
    monkeypatch.setattr(collector_mod, "get_session", lambda *a, **k: session)


def _count_live_stats_calls(session: FakeSession) -> int:
    return sum(
        1
        for call in session.calls
        if call.get("method") == "POST" and "creator/live/stats" in call["url"]
    )


def test_collect_tiktok_incremental_emits_three_daily_stats(monkeypatch: Any) -> None:
    """增量模式必须发出 T-1/T-2/T-3 共 3 天 live/stats（修复前为 0 天）。"""
    session = FakeSession()
    _patch_collect_deps(monkeypatch, session, _cred())
    list(collect_tiktok("acct-1", full=False))
    assert _count_live_stats_calls(session) == 3


def test_collect_tiktok_full_emits_28_daily_stats(monkeypatch: Any) -> None:
    """全量模式发出 T-1 ~ T-28 共 28 天 live/stats。"""
    session = FakeSession()
    _patch_collect_deps(monkeypatch, session, _cred())
    list(collect_tiktok("acct-1", full=True))
    assert _count_live_stats_calls(session) == 28
