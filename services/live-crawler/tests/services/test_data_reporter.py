"""services/data_reporter 单元测试"""

from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def _mock_settings(monkeypatch):
    """统一 mock Settings，避免读取真实配置"""
    fake_cfg = {
        "enabled": True,
        "api_url": "http://test-server",
        "send_endpoint": "/data/info/send",
        "access_token": "tok",
        "timeout": 5,
        "retries": 2,
        "retry_delay": 0,
        "api_sign": "test_sign",
    }
    monkeypatch.setattr("services.data_reporter.Settings.DATA_SERVER_CONFIG", fake_cfg)


def _make_message():
    return {
        "fromUrl": "http://example.com/api/test",
        "request": {"response": '{"ok":true}', "url": "http://example.com/api/test"},
    }


@patch("services.data_reporter.requests.post")
def test_send_success(mock_post):
    """上报成功返回 True"""
    mock_post.return_value = MagicMock(status_code=200)
    from services.data_reporter import send_api_request
    assert send_api_request(_make_message()) is True
    mock_post.assert_called_once()


@patch("services.data_reporter.requests.post")
def test_send_retry_then_success(mock_post):
    """首次失败、重试成功"""
    fail_resp = MagicMock(status_code=500, text="err")
    ok_resp = MagicMock(status_code=200)
    mock_post.side_effect = [fail_resp, ok_resp]
    from services.data_reporter import send_api_request
    assert send_api_request(_make_message()) is True
    assert mock_post.call_count == 2


@patch("services.data_reporter.requests.post")
def test_send_all_retries_fail(mock_post):
    """所有重试均失败返回 False"""
    mock_post.return_value = MagicMock(status_code=500, text="err")
    from services.data_reporter import send_api_request
    assert send_api_request(_make_message()) is False
    assert mock_post.call_count == 2  # retries=2
