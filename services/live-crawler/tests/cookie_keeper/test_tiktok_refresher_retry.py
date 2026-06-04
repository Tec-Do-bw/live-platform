"""TikTok 刷新器拦截超时重试逻辑测试。

验证 _handle_failure_with_login_check 在「首轮拦截超时」时的三条路径:
1. HTTP 验证在线 + 重试拦截命中 → 走 _finalize_success 写库 + 发 success 回调
2. HTTP 验证在线 + 重试仍超时 → 不发任何回调(保护登录态)
3. HTTP 验证明确登出 → 发 logout 回调,不触发重试

不触达真实网络/DB/浏览器,全部用替身。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# 测试环境无浏览器依赖：stub 掉 DrissionPage，使 webdriver.browserapi 可导入
if "DrissionPage" not in sys.modules:
    _dp = types.ModuleType("DrissionPage")
    _dp.Chromium = MagicMock()
    _dp.ChromiumOptions = MagicMock()
    sys.modules["DrissionPage"] = _dp
    _errs = types.ModuleType("DrissionPage.errors")
    _errs.ElementNotFoundError = type("ElementNotFoundError", (Exception,), {})
    sys.modules["DrissionPage.errors"] = _errs

from cookie_keeper import tiktok_refresher
from cookie_keeper.tiktok_refresher import FALLBACK_APIS, TikTokRefresher


@pytest.fixture
def patch_io(monkeypatch):
    """拦截 save_credentials / send_login_callback,记录调用。"""
    calls = {"save": [], "callback": []}
    monkeypatch.setattr(
        tiktok_refresher, "save_credentials",
        lambda **kw: calls["save"].append(kw),
    )
    monkeypatch.setattr(
        tiktok_refresher, "send_login_callback",
        lambda **kw: calls["callback"].append(kw),
    )
    # 历史凭据补全：返回 None（无历史，走纯 cookies 验证路径）
    monkeypatch.setattr(tiktok_refresher, "load_credentials", lambda *a, **k: None)
    return calls


def _fake_api_item() -> dict:
    """重试命中时返回的拦截包替身。"""
    return {
        "url": "https://shop.tiktok.com/api/v1/streamer_desktop/creator/post_limit"
               "?carrier_region=US&device_id=1&fp=x",
        "headers": {"user-agent": "UA-test"},
        "response": "{}",
    }


def test_retry_hit_writes_credentials_and_success_callback(patch_io, monkeypatch):
    """在线 + 重试命中 → 落库 + success 回调。"""
    r = TikTokRefresher()
    browser_api = MagicMock()
    browser_api.get_cookies.return_value = [{"name": "sessionid", "value": "abc"}]

    # HTTP 验证：账号在线
    monkeypatch.setattr(r, "_check_login_status", lambda ctx, proxy: (True, ""))
    # 重试导航：命中
    monkeypatch.setattr(
        r, "_retry_navigation_and_capture",
        lambda ba, tab, aid: _fake_api_item(),
    )
    # _extract_context 走真实逻辑（验证 region 从 carrier_region 提取）

    ok = r._handle_failure_with_login_check(
        browser_api, MagicMock(), "k1costhy", "美国团队-tiktok", "http://proxy",
        failure_reason="拦截超时",
    )

    assert ok is True
    assert len(patch_io["save"]) == 1
    assert patch_io["save"][0]["region"] == "US"
    assert patch_io["callback"][0]["login_status"] == "success"


def test_retry_miss_no_callback(patch_io, monkeypatch):
    """在线 + 重试仍超时 → 不发任何回调,不落库。"""
    r = TikTokRefresher()
    browser_api = MagicMock()
    browser_api.get_cookies.return_value = [{"name": "sessionid", "value": "abc"}]

    monkeypatch.setattr(r, "_check_login_status", lambda ctx, proxy: (True, ""))
    monkeypatch.setattr(
        r, "_retry_navigation_and_capture",
        lambda ba, tab, aid: None,
    )

    ok = r._handle_failure_with_login_check(
        browser_api, MagicMock(), "k1costhy", "美国团队-tiktok", "http://proxy",
        failure_reason="拦截超时",
    )

    assert ok is False
    assert patch_io["save"] == []
    assert patch_io["callback"] == []


def test_confirmed_logout_sends_logout_no_retry(patch_io, monkeypatch):
    """HTTP 验证明确登出 → 发 logout,不触发重试。"""
    r = TikTokRefresher()
    browser_api = MagicMock()
    browser_api.get_cookies.return_value = [{"name": "sessionid", "value": "abc"}]

    monkeypatch.setattr(
        r, "_check_login_status",
        lambda ctx, proxy: (False, "account_info 返回失败 code=98001002"),
    )
    retry_called = {"n": 0}
    monkeypatch.setattr(
        r, "_retry_navigation_and_capture",
        lambda ba, tab, aid: retry_called.__setitem__("n", retry_called["n"] + 1) or None,
    )

    ok = r._handle_failure_with_login_check(
        browser_api, MagicMock(), "k16oa8ov", "印尼团队-tiktok", "http://proxy",
        failure_reason="拦截超时",
    )

    assert ok is False
    assert retry_called["n"] == 0  # 登出不重试
    assert patch_io["callback"][0]["login_status"] == "logout"
    assert patch_io["save"] == []


def test_fallback_apis_extended():
    """确认 FALLBACK_APIS 含新增的 creator/post_limit,排除了无 carrier_region 的 live_relation/popup。"""
    assert "api/v1/streamer_desktop/creator/post_limit" in FALLBACK_APIS
    # live_relation/popup 因 URL 不含 carrier_region 已移除
    assert "live_relation/popup" not in FALLBACK_APIS
    # unread_count 已确认不支持,不应出现
    assert not any("unread_count" in a for a in FALLBACK_APIS)
    # 必须保留的两个核心 API
    assert "api/v2/insights/creator/live/list" in FALLBACK_APIS
    assert "api/v1/affiliate/lux/feelgood/token" in FALLBACK_APIS
