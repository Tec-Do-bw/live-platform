"""TikTok HTTP adapter 登出即时恢复逻辑测试。

验证 adapter 在 logout→login 切换时正确触发当轮全量，
以及登录态失效时发送 logout 回调。不触达真实网络/DB。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from crawlers.http.tiktok import adapter as adapter_mod
from crawlers.http.tiktok.adapter import TikTokHttpCollector
from utils.types import LoginRequired


class _FakeCred:
    """最小凭据替身，仅暴露 adapter 用到的 token_data。"""

    token_data = {"sessionid": "x"}


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


_LOGIN_RESULT = {
    "ok": True,
    "url": "https://shop.tiktok.com/account_info",
    "request_body": None,
    "response_body": "{}",
    "data": {"user_id": "1"},
}


def _patch(monkeypatch, *, recovery: bool, captured_full: list, callbacks: list):
    """打桩 adapter 依赖，记录回调与 collect_tiktok 收到的 full。"""
    fake_session = _FakeSession()

    monkeypatch.setattr(
        adapter_mod,
        "setup_session",
        lambda account_id: (_FakeCred(), fake_session, _LOGIN_RESULT),
    )

    def fake_callback(**kwargs):
        callbacks.append(kwargs)
        return {"callback_sent": True, "login_recovery": recovery and kwargs["login_status"] == "success"}

    monkeypatch.setattr(adapter_mod, "send_login_callback", fake_callback)
    monkeypatch.setattr(adapter_mod, "send_api_request", lambda *a, **k: True)

    def fake_collect(account_id, full=False, **kwargs):
        captured_full.append(full)
        return iter(())

    monkeypatch.setattr(adapter_mod, "collect_tiktok", fake_collect)
    return fake_session


def test_logout_to_login_triggers_full_recovery(monkeypatch):
    """logout→login：success 回调返回 login_recovery=True，当轮切全量。"""
    captured_full: list = []
    callbacks: list = []
    fake_session = _patch(monkeypatch, recovery=True, captured_full=captured_full, callbacks=callbacks)

    collector = TikTokHttpCollector(browser_id="acc-1", full_collection=False)
    result = collector.start_crawl()

    assert result["login_recovery"] is True
    assert result["login_status"] is True
    assert captured_full == [True]  # 数据采集主体收到 full=True
    assert collector.full_collection is True
    assert fake_session.closed is True
    assert [c["login_status"] for c in callbacks] == ["success"]


def test_normal_login_keeps_incremental(monkeypatch):
    """无登出历史：success 回调不触发恢复，保持增量。"""
    captured_full: list = []
    callbacks: list = []
    _patch(monkeypatch, recovery=False, captured_full=captured_full, callbacks=callbacks)

    collector = TikTokHttpCollector(browser_id="acc-2", full_collection=False)
    result = collector.start_crawl()

    assert result["login_recovery"] is False
    assert captured_full == [False]


def test_login_required_sends_logout_callback(monkeypatch):
    """登录态失效：抛 LoginRequired → 发 logout 回调并标记 login_status=False。"""
    callbacks: list = []

    def fake_setup(account_id):
        raise LoginRequired(f"[{account_id}] 登录态失效")

    monkeypatch.setattr(adapter_mod, "setup_session", fake_setup)
    monkeypatch.setattr(
        adapter_mod,
        "send_login_callback",
        lambda **kwargs: callbacks.append(kwargs) or {"callback_sent": True, "login_recovery": False},
    )

    collector = TikTokHttpCollector(browser_id="acc-3", full_collection=False)
    result = collector.start_crawl()

    assert result["login_status"] is False
    assert result["success"] is False
    assert len(callbacks) == 1
    assert callbacks[0]["login_status"] == "logout"
    assert "登录态失效" in callbacks[0]["reason"]
