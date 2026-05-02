"""飞书告警模块测试"""

from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def _mock_settings(monkeypatch):
    """mock Settings"""
    monkeypatch.setattr(
        "utils.alert.Settings.ALERT_CONFIG",
        {
            "enabled": True,
            "webhook_url": "https://open.feishu.cn/test-hook",
            "alert_types": {
                "login_failed": True,
                "crawl_failed": True,
                "task_timeout": True,
            },
        },
    )


@patch("utils.alert.requests.post")
def test_send_feishu_success(mock_post):
    """飞书消息发送成功"""
    mock_post.return_value = MagicMock(
        json=lambda: {"code": 0, "msg": "success"}
    )
    from utils.alert import AlertManager

    mgr = AlertManager()
    result = mgr.send_alert("crawl_failed", "测试标题", "测试内容")

    assert result is True
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "https://open.feishu.cn/test-hook" in call_args[0]


@patch("utils.alert.requests.post")
def test_send_feishu_failed(mock_post):
    """飞书消息发送失败"""
    mock_post.return_value = MagicMock(
        json=lambda: {"code": 1001, "msg": "invalid webhook"}
    )
    from utils.alert import AlertManager

    mgr = AlertManager()
    result = mgr.send_alert("crawl_failed", "测试标题", "测试内容")

    assert result is False


def test_alert_disabled():
    """告警禁用时跳过发送"""
    from utils.alert import AlertManager

    mgr = AlertManager()
    mgr.enabled = False
    result = mgr.send_alert("crawl_failed", "测试标题", "测试内容")

    assert result is False


@patch("utils.alert.requests.post")
def test_send_login_failed_alert(mock_post):
    """账号登出告警"""
    mock_post.return_value = MagicMock(json=lambda: {"code": 0})
    from utils.alert import AlertManager

    mgr = AlertManager()
    result = mgr.send_login_failed_alert(["browser_1", "browser_2"])

    assert result is True
    call_args = mock_post.call_args
    payload = call_args[1]["data"]
    assert "browser_1" in payload
    assert "browser_2" in payload
