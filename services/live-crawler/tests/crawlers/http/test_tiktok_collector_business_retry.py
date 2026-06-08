"""TikTok HTTP 业务码重试与跳过语义测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from crawlers.http.tiktok import collector
from utils.credentials import Credentials


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

    def post(self, *_: Any, **__: Any) -> FakeResponse:
        response = self.responses[self.post_count]
        self.post_count += 1
        return response

    def get(self, *_: Any, **__: Any) -> FakeResponse:
        response = self.responses[self.get_count]
        self.get_count += 1
        return response


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
            raise collector.TikTokBusinessCodeError("core_stats", "acc-1", 28001001, "request timeout")
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


def test_retry_exhausted_replay_info_continues_to_live_list(monkeypatch) -> None:
    """replay_info 10002 重试耗尽后停止 replay，继续 live_list。"""
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    live_list_called: list[bool] = []

    def fake_replay_info(*_args: Any, **_kwargs: Any) -> collector.FetchResult:
        raise collector.TikTokBusinessCodeError("replay_info", "acc-1", 10002, "")

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


def test_non_retryable_business_code_keeps_existing_failed_payload() -> None:
    """非白名单业务码仍返回 ok=False，保持现有失败语义。"""
    session = SequenceSession([FakeResponse({"code": 12345, "message": "not retryable"})])

    result = collector.fetch_core_stats(session, _cred(), "room-1")

    assert result["ok"] is False
    assert session.post_count == 1
