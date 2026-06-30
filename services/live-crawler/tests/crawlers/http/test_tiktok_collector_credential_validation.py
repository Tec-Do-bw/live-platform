"""TikTok HTTP 凭据完整性校验测试。

验证 setup_session 在凭据缺失关键字段（token / query_string）时
于采集前快速失败，以及 _region_profile 在 region 缺失/未知时降级告警。
不触达真实网络/DB。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from crawlers.http.tiktok import collector
from utils.credentials import Credentials
from utils.types import FatalError, LoginRequired


def _cred(
    *,
    token: str = '{"sessionid":"x"}',
    ext_json: str = '{"query_string":"device_id=1&fp=x"}',
    region: str = "SG",
) -> Credentials:
    """构造带可控 token/ext_json/region 的凭据替身。"""
    return Credentials(
        account_id="acc-1",
        platform="tiktok",
        group_name="SG团队-tiktok",
        token=token,
        region=region,
        proxy="",
        ext_json=ext_json,
        extra="{}",
    )


def test_setup_session_raises_when_token_missing(monkeypatch):
    """token 为空：抛 FatalError，不建立会话。"""
    monkeypatch.setattr(
        collector,
        "load_credentials",
        lambda account_id, platform="tiktok": _cred(token=""),
    )
    with pytest.raises(FatalError, match="凭据缺失"):
        collector.setup_session("acc-1")


def test_setup_session_raises_when_query_string_missing(monkeypatch):
    """ext_json 无 query_string：抛 FatalError（设备指纹缺失，不可降级）。"""
    monkeypatch.setattr(
        collector,
        "load_credentials",
        lambda account_id, platform="tiktok": _cred(ext_json='{"user_agent":"Mozilla/5.0"}'),
    )
    with pytest.raises(FatalError, match="query_string 缺失"):
        collector.setup_session("acc-1")


def test_setup_session_query_string_error_is_not_login_required(monkeypatch):
    """query_string 缺失抛的是 FatalError 而非 LoginRequired。

    adapter 先 except LoginRequired 再 except Exception，二者区分决定是否发 logout 回调：
    凭据未同步（query_string 缺失）不应被当作账号登出。
    """
    monkeypatch.setattr(
        collector,
        "load_credentials",
        lambda account_id, platform="tiktok": _cred(ext_json="{}"),
    )
    with pytest.raises(FatalError) as exc_info:
        collector.setup_session("acc-1")
    assert not isinstance(exc_info.value, LoginRequired)


def test_region_profile_fallback_when_region_missing():
    """region 空串：降级到 UTC+0 默认特征。"""
    profile = collector._region_profile("")
    assert profile == collector.DEFAULT_REGION_PROFILE
    assert profile["timezone_offset"] == 0


def test_region_profile_fallback_when_region_unknown():
    """未知 region：降级到 UTC+0 默认特征。"""
    profile = collector._region_profile("ZZ")
    assert profile == collector.DEFAULT_REGION_PROFILE


def test_region_profile_known_region_unaffected():
    """已知 region：正常返回对应特征，校验未引入回归。"""
    assert collector._region_profile("JP")["timezone_offset"] == 32400
    assert collector._region_profile("us")["timezone_offset"] == -28800


def test_setup_session_skip_verification_returns_none_login_result(monkeypatch):
    """skip_verification=True：跳过 fetch_account_info，返回 (cred, session, None)。"""
    call_count = {"fetch_account_info": 0}

    def mock_fetch_account_info(session, cred):
        call_count["fetch_account_info"] += 1
        return {"ok": True, "url": "", "request_body": None, "response_body": "", "data": {}}

    monkeypatch.setattr(collector, "load_credentials", lambda account_id, platform="tiktok": _cred())
    monkeypatch.setattr(collector, "get_session", lambda spec, proxy=None: _FakeSession())
    monkeypatch.setattr(collector, "fetch_account_info", mock_fetch_account_info)

    cred, session, login_result = collector.setup_session("acc-1", skip_verification=True)

    assert cred is not None
    assert session is not None
    assert login_result is None  # 跳过验证时返回 None
    assert call_count["fetch_account_info"] == 0  # 未调用 fetch_account_info
    session.close()


def test_setup_session_default_behavior_verifies_login(monkeypatch):
    """默认行为（skip_verification=False）：验证登录态，返回 login_result。"""
    call_count = {"fetch_account_info": 0}

    def mock_fetch_account_info(session, cred):
        call_count["fetch_account_info"] += 1
        return {"ok": True, "url": "", "request_body": None, "response_body": "", "data": {"user_id": "123"}}

    monkeypatch.setattr(collector, "load_credentials", lambda account_id, platform="tiktok": _cred())
    monkeypatch.setattr(collector, "get_session", lambda spec, proxy=None: _FakeSession())
    monkeypatch.setattr(collector, "fetch_account_info", mock_fetch_account_info)

    cred, session, login_result = collector.setup_session("acc-1")

    assert login_result is not None
    assert login_result["ok"] is True
    assert call_count["fetch_account_info"] == 1  # 调用了 fetch_account_info
    session.close()


class _FakeSession:
    """测试用轻量 Session 替身。"""

    def __init__(self):
        self.cookies = _FakeCookies()
        self.closed = False

    def close(self):
        self.closed = True


class _FakeCookies:
    """测试用 cookies 容器。"""

    def update(self, cookies):
        pass

