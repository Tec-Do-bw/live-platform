"""TikTok HTTP 业务码重试与跳过语义测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from datetime import date


sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from crawlers.http.tiktok import collector
from utils.credentials import Credentials
from utils.types import LoginRequired


class FakeResponse:
    """模拟 TikTok API 响应。"""

    status_code = 200

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.text = "{}"

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        return None


class SequenceSession:
    """按顺序返回预置响应。"""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.post_count = 0
        self.get_count = 0
        self.cookies: dict[str, str] = {}
        self.closed = False

    def post(self, *_: Any, **__: Any) -> FakeResponse:
        response = self.responses[self.post_count]
        self.post_count += 1
        return response

    def get(self, *_: Any, **__: Any) -> FakeResponse:
        response = self.responses[self.get_count]
        self.get_count += 1
        return response

    def close(self) -> None:
        self.closed = True


def _cred(region: str = "MY") -> Credentials:
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


def _ok_result(data: dict[str, Any] | None = None) -> collector.FetchResult:
    return {
        "ok": True,
        "url": "https://example.test",
        "request_body": None,
        "response_body": "{}",
        "data": data or {},
    }


def test_core_stats_retryable_business_code_retries_until_success(monkeypatch) -> None:
    """core_stats 28001001 会触发业务重试，成功后返回 ok=True。"""
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    session = SequenceSession(
        [
            FakeResponse({"code": 28001001, "message": "request timeout"}),
            FakeResponse({"code": 28001001, "message": "request timeout"}),
            FakeResponse({"code": 0, "data": {"value": 1}}),
        ]
    )

    result = collector.fetch_core_stats(session, _cred(), "room-1")

    assert result["ok"] is True
    assert session.post_count == 3


def test_trend_chart_business_code_retries_until_success(monkeypatch) -> None:
    """trend_chart 98001021 会触发业务重试，成功后返回 ok=True。"""
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    session = SequenceSession(
        [
            FakeResponse({"code": 98001021, "message": "call downstream server error"}),
            FakeResponse({"code": 98001021, "message": "call downstream server error"}),
            FakeResponse({"code": 0, "data": {"value": 1}}),
        ]
    )

    result = collector.fetch_trend_chart(session, _cred(), "room-1")

    assert result["ok"] is True
    assert session.post_count == 3


def test_collect_tiktok_skips_retry_exhausted_core_stats_and_continues(monkeypatch) -> None:
    """core_stats 业务码重试耗尽后跳过该 room，不产出 ok=False。"""
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    core_calls: list[str] = []

    monkeypatch.setattr(collector, "_collect_replay_info", lambda *_: iter(()))
    monkeypatch.setattr(collector, "fetch_live_list", lambda *_args, **_kwargs: _ok_result({"rooms": []}))
    monkeypatch.setattr(
        collector,
        "parse_rooms",
        lambda _data: (
            [
                {"room_id": "room-1", "room_name": "", "live_start_ts": 1, "live_end_ts": 2, "revenue": "0", "currency_code": "USD"},
                {"room_id": "room-2", "room_name": "", "live_start_ts": 1, "live_end_ts": 2, "revenue": "0", "currency_code": "USD"},
            ],
            "creator-1",
        ),
    )
    monkeypatch.setattr(collector, "filter_rooms_by_window", lambda rooms, *_: rooms)
    monkeypatch.setattr(collector, "fetch_trend_chart", lambda *_args, **_kwargs: _ok_result())
    monkeypatch.setattr(collector, "fetch_live_stats", lambda *_args, **_kwargs: _ok_result())

    def fake_core_stats(_session: object, _cred: Credentials, room_id: str) -> collector.FetchResult:
        core_calls.append(room_id)
        if room_id == "room-1":
            raise collector.TikTokBusinessCodeError("acc-1", "core_stats", 28001001, "request timeout")
        return _ok_result()

    monkeypatch.setattr(collector, "fetch_core_stats", fake_core_stats)

    outputs = list(
        collector.collect_tiktok(
            "acc-1",
            full=False,
            cred=_cred(),
            session=object(),
            login_result=_ok_result(),
        )
    )

    assert core_calls == ["room-1", "room-2"]
    assert all(ok for ok, _item in outputs)


def test_collect_tiktok_skips_retry_exhausted_trend_chart_and_continues(monkeypatch) -> None:
    """trend_chart 业务码重试耗尽后跳过该请求，继续 core_stats 和后续 room。"""
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    trend_calls: list[tuple[str, tuple[int, ...]]] = []
    core_calls: list[str] = []

    monkeypatch.setattr(collector, "_collect_replay_info", lambda *_: iter(()))
    monkeypatch.setattr(collector, "fetch_live_list", lambda *_args, **_kwargs: _ok_result({"rooms": []}))
    monkeypatch.setattr(
        collector,
        "parse_rooms",
        lambda _data: (
            [
                {"room_id": "room-1", "room_name": "", "live_start_ts": 1, "live_end_ts": 2, "revenue": "0", "currency_code": "USD"},
                {"room_id": "room-2", "room_name": "", "live_start_ts": 1, "live_end_ts": 2, "revenue": "0", "currency_code": "USD"},
            ],
            "creator-1",
        ),
    )
    monkeypatch.setattr(collector, "filter_rooms_by_window", lambda rooms, *_: rooms)
    monkeypatch.setattr(collector, "fetch_live_stats", lambda *_args, **_kwargs: _ok_result())

    def fake_trend_chart(_session: object, _cred: Credentials, room_id: str, stats_types: list[int] | None = None) -> collector.FetchResult:
        trend_calls.append((room_id, tuple(stats_types or [])))
        if room_id == "room-1" and stats_types == collector.TREND_CHART_STATS_BASIC:
            raise collector.TikTokBusinessCodeError("acc-1", "trend_chart", 98001021, "call downstream server error")
        return _ok_result()

    def fake_core_stats(_session: object, _cred: Credentials, room_id: str) -> collector.FetchResult:
        core_calls.append(room_id)
        return _ok_result()

    monkeypatch.setattr(collector, "fetch_trend_chart", fake_trend_chart)
    monkeypatch.setattr(collector, "fetch_core_stats", fake_core_stats)

    outputs = list(
        collector.collect_tiktok(
            "acc-1",
            full=False,
            cred=_cred(),
            session=object(),
            login_result=_ok_result(),
        )
    )

    assert [room_id for room_id, _ in trend_calls] == ["room-1", "room-1", "room-2", "room-2"]
    assert core_calls == ["room-1", "room-2"]
    assert all(ok for ok, _item in outputs)


def test_retry_exhausted_replay_info_continues_to_live_list(monkeypatch) -> None:
    """replay_info 10002 重试耗尽后停止 replay，继续 live_list。"""
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    live_list_called: list[bool] = []

    def fake_replay_info(*_args: Any, **_kwargs: Any) -> collector.FetchResult:
        raise collector.TikTokBusinessCodeError("acc-1", "replay_info", 10002, "")

    def fake_live_list(*_args: Any, **_kwargs: Any) -> collector.FetchResult:
        live_list_called.append(True)
        return _ok_result({"rooms": []})

    monkeypatch.setattr(collector, "fetch_replay_info", fake_replay_info)
    monkeypatch.setattr(collector, "fetch_live_list", fake_live_list)
    monkeypatch.setattr(collector, "parse_rooms", lambda _data: ([], "creator-1"))
    monkeypatch.setattr(collector, "fetch_live_stats", lambda *_: _ok_result())

    outputs = list(
        collector.collect_tiktok(
            "acc-1",
            full=False,
            cred=_cred(),
            session=object(),
            login_result=_ok_result(),
        )
    )

    assert live_list_called == [True]
    assert all(ok for ok, _item in outputs)


def test_retry_exhausted_live_list_stops_paging_and_continues_existing_rooms(monkeypatch) -> None:
    """live_list 业务码重试耗尽后停止翻页，继续处理已收集 room 和 live_stats。"""
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    monkeypatch.setattr(collector, "_collect_replay_info", lambda *_: iter(()))
    monkeypatch.setattr(collector, "LIVE_LIST_PAGE_SIZE", 1)
    monkeypatch.setattr(collector, "LIVE_LIST_MAX_PAGES", 2)
    monkeypatch.setattr(collector, "_full_stats_days_range", lambda _region: range(0, 1))
    monkeypatch.setattr(collector, "_local_yesterday", lambda _region: date(2026, 6, 8))
    trend_calls: list[str] = []
    stats_calls: list[date] = []

    def fake_live_list(_session: object, _cred: Credentials, _full: bool = False, page: int = 0) -> collector.FetchResult:
        if page == 1:
            raise collector.TikTokBusinessCodeError("acc-1", "live_list", 98001021, "call downstream server error")
        return _ok_result({"page": page})

    def fake_parse_rooms(data: dict[str, Any]) -> tuple[list[collector.RoomMeta], str]:
        return (
            [{"room_id": f"room-{data['page']}", "room_name": "", "live_start_ts": 1, "live_end_ts": 2, "revenue": "0", "currency_code": "USD"}],
            "creator-1",
        )

    def fake_trend_chart(_session: object, _cred: Credentials, room_id: str, _stats_types: list[int] | None = None) -> collector.FetchResult:
        trend_calls.append(room_id)
        return _ok_result()

    def fake_live_stats(_session: object, _cred: Credentials, target_date: date) -> collector.FetchResult:
        stats_calls.append(target_date)
        return _ok_result()

    monkeypatch.setattr(collector, "fetch_live_list", fake_live_list)
    monkeypatch.setattr(collector, "parse_rooms", fake_parse_rooms)
    monkeypatch.setattr(collector, "filter_rooms_by_window", lambda rooms, *_: rooms)
    monkeypatch.setattr(collector, "fetch_trend_chart", fake_trend_chart)
    monkeypatch.setattr(collector, "fetch_core_stats", lambda *_args, **_kwargs: _ok_result())
    monkeypatch.setattr(collector, "fetch_live_stats", fake_live_stats)

    outputs = list(
        collector.collect_tiktok(
            "acc-1",
            full=True,
            cred=_cred(),
            session=object(),
            login_result=_ok_result(),
        )
    )

    assert trend_calls == ["room-0", "room-0"]
    assert stats_calls == [date(2026, 6, 8)]
    assert all(ok for ok, _item in outputs)


def test_retry_exhausted_live_stats_skips_date_and_continues(monkeypatch) -> None:
    """live_stats 业务码重试耗尽后跳过该日期，继续后续日期。"""
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    monkeypatch.setattr(collector, "_collect_replay_info", lambda *_: iter(()))
    monkeypatch.setattr(collector, "fetch_live_list", lambda *_args, **_kwargs: _ok_result({"rooms": []}))
    monkeypatch.setattr(collector, "parse_rooms", lambda _data: ([], "creator-1"))
    monkeypatch.setattr(collector, "_local_yesterday", lambda _region: date(2026, 6, 8))
    stats_calls: list[date] = []

    def fake_live_stats(_session: object, _cred: Credentials, target_date: date) -> collector.FetchResult:
        stats_calls.append(target_date)
        if target_date == date(2026, 6, 8):
            raise collector.TikTokBusinessCodeError("acc-1", "live_stats", 98001021, "call downstream server error")
        return _ok_result()

    monkeypatch.setattr(collector, "fetch_live_stats", fake_live_stats)

    outputs = list(
        collector.collect_tiktok(
            "acc-1",
            full=False,
            cred=_cred(),
            session=object(),
            login_result=_ok_result(),
        )
    )

    assert stats_calls == [date(2026, 6, 8), date(2026, 6, 7), date(2026, 6, 6)]
    assert all(ok for ok, _item in outputs)


def test_account_info_business_code_retries_but_keeps_login_gate(monkeypatch) -> None:
    """account_info 业务码会重试，耗尽后仍作为登录门禁失败。"""
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    cred = _cred()
    session = SequenceSession(
        [
            FakeResponse({"code": 98001002, "message": "You must log in to continue"}),
            FakeResponse({"code": 98001002, "message": "You must log in to continue"}),
            FakeResponse({"code": 98001002, "message": "You must log in to continue"}),
        ]
    )

    monkeypatch.setattr(collector, "load_credentials", lambda *_args, **_kwargs: cred)
    monkeypatch.setattr(collector, "get_session", lambda *_args, **_kwargs: session)

    try:
        collector.setup_session("acc-1")
    except LoginRequired as e:
        assert "登录态失效" in str(e)
    else:
        raise AssertionError("account_info 业务码耗尽后必须保持登录门禁失败")

    assert session.get_count == 3
