"""TikTok HTTP 国家请求特征测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from crawlers.http.tiktok import collector
from utils.credentials import Credentials


class FakeResponse:
    """模拟 TikTok API 响应。"""

    status_code = 200
    text = '{"status_code":0,"data":{"has_more":false}}'

    def json(self) -> dict:
        return {"status_code": 0, "data": {"has_more": False}}

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    """记录请求 URL 的 fake session。"""

    def __init__(self) -> None:
        self.requested_url = ""

    def get(self, url: str, **_: object) -> FakeResponse:
        self.requested_url = url
        return FakeResponse()


def _cred(region: str) -> Credentials:
    return Credentials(
        account_id=f"acc-{region.lower()}",
        platform="tiktok",
        group_name=f"{region}团队-tiktok",
        token="{}",
        region=region,
        proxy="",
        ext_json='{"user_agent":"Mozilla/5.0"}',
        extra="{}",
    )


def test_replay_info_uses_region_specific_host_and_language() -> None:
    cases = {
        "US": ("webcast.us.tiktok.com", "en"),
        "SG": ("webcast.tiktok.com", "en"),
        "JP": ("webcast.tiktok.com", "ja-JP"),
        "VN": ("webcast.tiktok.com", "vi-VN"),
        "BR": ("webcast.tiktok.com", "pt"),
        "MX": ("webcast.tiktok.com", "es-419"),
    }

    for region, (host, language) in cases.items():
        session = FakeSession()

        collector.fetch_replay_info(session, _cred(region), count=6, offset=0)

        parsed = urlparse(session.requested_url)
        query = parse_qs(parsed.query)
        assert parsed.netloc == host
        assert query["webcast_language"] == [language]


def test_region_profiles_cover_scheduler_timezone_groups() -> None:
    scheduler_offsets = {32400, 28800, 25200, -10800, -21600, -28800}

    profile_offsets = {
        profile["timezone_offset"]
        for profile in collector.TIKTOK_REGION_PROFILES.values()
    }

    assert scheduler_offsets <= profile_offsets


def test_time_window_uses_real_region_timezone_offsets() -> None:
    assert collector._time_window("JP", full=False)["timezone_offset"] == 32400
    assert collector._time_window("BR", full=False)["timezone_offset"] == -10800
