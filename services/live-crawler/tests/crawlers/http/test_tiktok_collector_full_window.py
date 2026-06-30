"""TikTok HTTP 全量采集时间窗测试。"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from crawlers.http.tiktok import collector
from utils.credentials import Credentials


class FixedDatetime(datetime):
    """固定当前时间，便于断言账号当地日期边界。"""

    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        value = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


class FakeResponse:
    """模拟 TikTok live/list 响应。"""

    status_code = 200
    text = '{"code":0,"data":{"segments":[]}}'

    def json(self) -> dict[str, Any]:
        return {"code": 0, "data": {"segments": []}}

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    """记录 POST payload 的 fake session。"""

    def __init__(self) -> None:
        self.posted_json: dict[str, Any] = {}

    def post(self, _: str, **kwargs: Any) -> FakeResponse:
        self.posted_json = kwargs["json"]
        return FakeResponse()


def _cred(region: str = "US") -> Credentials:
    return Credentials(
        account_id="acc-1",
        platform="tiktok",
        group_name=f"{region}团队-tiktok",
        token="{}",
        region=region,
        proxy="",
        ext_json='{"query_string":"device_id=1&fp=x","user_agent":"Mozilla/5.0"}',
        extra="{}",
    )


def _local_date(ts: int | str, offset: int) -> datetime.date:
    tz_obj = timezone(timedelta(seconds=offset))
    return datetime.fromtimestamp(int(ts), tz_obj).date()


def _ok_result(data: dict[str, Any] | None = None) -> collector.FetchResult:
    return {
        "ok": True,
        "url": "https://example.test",
        "request_body": None,
        "response_body": "{}",
        "data": data or {},
    }


def _patch_tiktok_http_config(monkeypatch: pytest.MonkeyPatch, config: dict[str, Any]) -> None:
    """替换 collector.Settings，避免 pydantic 对未定义字段的赋值限制影响测试。"""
    monkeypatch.setattr(
        collector,
        "Settings",
        SimpleNamespace(
            TIKTOK_HTTP_CONFIG=config,
            DATA_SERVER_CONFIG=getattr(collector.Settings, "DATA_SERVER_CONFIG", {}),
        ),
    )


def _rooms(count: int, prefix: str) -> list[collector.RoomMeta]:
    return [
        {
            "room_id": f"{prefix}-{index}",
            "room_name": f"room-{index}",
            "live_start_ts": 1,
            "live_end_ts": 2,
            "revenue": "0",
            "currency_code": "USD",
        }
        for index in range(count)
    ]


def test_time_window_defaults_to_last_60_local_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认全量窗口：账号当地 today-60 00:00 到 today 00:00。"""
    monkeypatch.setattr(collector, "datetime", FixedDatetime)
    _patch_tiktok_http_config(monkeypatch, {"full_window_days": 60, "full_start_date": ""})

    tw = collector._time_window("US", full=True)

    assert tw["period"] == 2
    assert tw["granularity"] == 1
    assert tw["timezone_offset"] == -28800
    assert _local_date(tw["start_timestamp"], -28800).isoformat() == "2026-03-30"
    assert _local_date(tw["end_timestamp"], -28800).isoformat() == "2026-05-29"


def test_time_window_start_date_overrides_window_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """指定起始日期时：优先按账号当地日期从该日起采到今天。"""
    monkeypatch.setattr(collector, "datetime", FixedDatetime)
    _patch_tiktok_http_config(monkeypatch, {"full_window_days": 60, "full_start_date": "2026-04-01"})

    tw = collector._time_window("US", full=True)

    assert _local_date(tw["start_timestamp"], -28800).isoformat() == "2026-04-01"
    assert _local_date(tw["end_timestamp"], -28800).isoformat() == "2026-05-29"


def test_invalid_full_start_date_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """起始日期格式错误时直接失败，避免静默采错范围。"""
    _patch_tiktok_http_config(monkeypatch, {"full_window_days": 60, "full_start_date": "2026/04/01"})

    with pytest.raises(ValueError, match="TIKTOK_HTTP_FULL_START_DATE"):
        collector._time_window("US", full=True)


def test_fetch_live_list_uses_custom_full_window_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """live/list 全量请求使用自定义时间窗和分页参数。"""
    monkeypatch.setattr(collector, "datetime", FixedDatetime)
    _patch_tiktok_http_config(monkeypatch, {"full_window_days": 60, "full_start_date": "2026-04-01"})
    session = FakeSession()

    result = collector.fetch_live_list(session, _cred("US"), full=True, page=2)

    assert result["ok"] is True
    params = session.posted_json["request"]["params"][0]
    time_selector = params["time_selector"]
    assert time_selector["period"] == 2
    assert time_selector["granularity"] == 1
    assert _local_date(time_selector["start_timestamp"], -28800).isoformat() == "2026-04-01"
    assert _local_date(time_selector["end_timestamp"], -28800).isoformat() == "2026-05-29"
    assert time_selector["timezone_offset"] == -28800
    assert "base_timestamp" not in time_selector
    assert params["list_control"]["pagination"] == {"size": 500, "page": 2}


def test_full_live_stats_uses_configured_start_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """live/stats 全量日聚合天数跟随固定起始日期。"""
    monkeypatch.setattr(collector, "datetime", FixedDatetime)
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    _patch_tiktok_http_config(monkeypatch, {"full_window_days": 60, "full_start_date": "2026-04-01"})
    targets: list[str] = []

    monkeypatch.setattr(collector, "fetch_live_list", lambda *_, **__: _ok_result())
    monkeypatch.setattr(collector, "parse_rooms", lambda _: ([], "creator-1"))
    monkeypatch.setattr(collector, "fetch_live_stats", lambda _session, _cred, target: targets.append(target.isoformat()) or _ok_result())
    monkeypatch.setattr(collector, "_collect_replay_info", lambda *_: iter(()))

    list(collector.collect_tiktok("acc-1", full=True, cred=_cred("US"), session=object(), login_result=_ok_result()))

    assert len(targets) == 58
    assert targets[0] == "2026-05-28"
    assert targets[-1] == "2026-04-01"


def test_collect_tiktok_paginates_full_live_list_until_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """live/list 全量翻页到短页停止，并合并所有页房间再过滤。"""
    monkeypatch.setattr(collector, "datetime", FixedDatetime)
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    _patch_tiktok_http_config(monkeypatch, {"full_window_days": 60, "full_start_date": ""})
    requested_pages: list[int] = []
    filtered_room_counts: list[int] = []

    def fake_fetch_live_list(_session: object, _cred: Credentials, full: bool = False, page: int = 0) -> collector.FetchResult:
        requested_pages.append(page)
        return _ok_result({"page": page})

    def fake_parse_rooms(data: dict[str, Any]) -> tuple[list[collector.RoomMeta], str]:
        page = int(data["page"])
        return (_rooms(500, "p0") if page == 0 else _rooms(1, "p1")), "creator-1"

    def fake_filter_rooms(rooms: list[collector.RoomMeta], _region: str, _full: bool) -> list[collector.RoomMeta]:
        filtered_room_counts.append(len(rooms))
        return []

    monkeypatch.setattr(collector, "fetch_live_list", fake_fetch_live_list)
    monkeypatch.setattr(collector, "parse_rooms", fake_parse_rooms)
    monkeypatch.setattr(collector, "filter_rooms_by_window", fake_filter_rooms)
    monkeypatch.setattr(collector, "fetch_live_stats", lambda *_: _ok_result())
    monkeypatch.setattr(collector, "_collect_replay_info", lambda *_: iter(()))

    list(collector.collect_tiktok("acc-1", full=True, cred=_cred("US"), session=object(), login_result=_ok_result()))

    assert requested_pages == [0, 1]
    assert filtered_room_counts == [501]
