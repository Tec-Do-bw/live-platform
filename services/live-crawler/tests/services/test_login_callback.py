"""services/login_callback 单元测试"""

import sys
from unittest.mock import patch, MagicMock
import pytest

# mock 缺失的重量级模块
sys.modules.setdefault('never_primp', MagicMock())
sys.modules.setdefault('DrissionPage', MagicMock())


@pytest.fixture(autouse=True)
def _mock_settings(monkeypatch):
    """统一 mock Settings"""
    monkeypatch.setattr(
        "services.login_callback.Settings.LOGIN_CALLBACK_CONFIG",
        {
            "enabled": True,
            "url": "http://test-callback/api",
            "access_token": "tok",
            "timeout": 5,
        },
    )


@pytest.fixture()
def _mock_monitor():
    """mock 监控模块，避免真实 SQLite 操作"""
    mock_conn = MagicMock()
    mock_monitor = MagicMock()
    mock_monitor.conn = mock_conn

    mock_status_mgr = MagicMock()
    mock_status_mgr.get_account_status.return_value = None

    with (
        patch("monitor.get_monitor", return_value=mock_monitor),
        patch("monitor.login_status_manager.LoginStatusManager", return_value=mock_status_mgr),
    ):
        yield mock_status_mgr


@patch("services.login_callback.requests.post")
def test_callback_success(mock_post, _mock_monitor):
    """正常登录回调发送成功"""
    mock_post.return_value = MagicMock(status_code=200)
    from services.login_callback import send_login_callback

    result = send_login_callback(
        browser_id="b1", platform="lazada",
        login_status="success",
    )
    assert result['callback_sent'] is True
    assert result['login_recovery'] is False
    mock_post.assert_called_once()


@patch("services.login_callback.requests.post")
def test_login_recovery_detected(mock_post, _mock_monitor):
    """检测到登出→登录恢复"""
    mock_post.return_value = MagicMock(status_code=200)
    # 模拟当前状态为 logout
    _mock_monitor.get_account_status.return_value = {'status': 'logout'}

    from services.login_callback import send_login_callback

    result = send_login_callback(
        browser_id="b1", platform="tiktok",
        login_status="success",
    )
    assert result['callback_sent'] is True
    assert result['login_recovery'] is True


@patch("services.login_callback.requests.post")
def test_logout_no_recovery(mock_post, _mock_monitor):
    """登出状态回调不触发恢复"""
    mock_post.return_value = MagicMock(status_code=200)
    from services.login_callback import send_login_callback

    result = send_login_callback(
        browser_id="b1", platform="tiktok",
        login_status="logout", reason="cookie_expired",
    )
    assert result['callback_sent'] is True
    assert result['login_recovery'] is False
