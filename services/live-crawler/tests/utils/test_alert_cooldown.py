#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试告警冷却机制"""

import time
from unittest.mock import MagicMock, patch

import pytest

from utils.alert import AlertManager


@pytest.fixture
def mock_config():
    """模拟配置"""
    return {
        'enabled': True,
        'webhook_url': 'https://example.com/webhook',
        'alert_types': {
            'test_alert': True,
        },
        'cooldown_seconds': 2,  # 测试用 2 秒冷却
    }


@pytest.fixture
def alert_manager(mock_config):
    """创建 AlertManager 实例"""
    with patch('utils.alert.Settings.ALERT_CONFIG', mock_config):
        manager = AlertManager()
        # Mock _send_message 避免实际发送请求
        manager._send_message = MagicMock(return_value=True)
        return manager


def test_first_alert_should_send(alert_manager):
    """首次告警应该发送"""
    result = alert_manager.send_alert('test_alert', '测试标题', '测试内容')
    assert result is True
    assert alert_manager._send_message.call_count == 1


def test_second_alert_within_cooldown_should_suppress(alert_manager):
    """冷却期内的第二次告警应该被抑制"""
    alert_manager.send_alert('test_alert', '测试标题', '测试内容')
    result = alert_manager.send_alert('test_alert', '测试标题', '测试内容')

    assert result is False
    assert alert_manager._send_message.call_count == 1  # 只发送了第一次


def test_alert_after_cooldown_should_send(alert_manager):
    """冷却期过后的告警应该发送"""
    alert_manager.send_alert('test_alert', '测试标题', '测试内容')
    time.sleep(2.1)  # 等待冷却期结束
    result = alert_manager.send_alert('test_alert', '测试标题', '测试内容')

    assert result is True
    assert alert_manager._send_message.call_count == 2


def test_different_alert_types_independent(alert_manager):
    """不同 alert_type 的冷却独立"""
    alert_manager.send_alert('test_alert', '测试1', '内容1')
    result = alert_manager.send_alert('another_alert', '测试2', '内容2')

    assert result is True
    assert alert_manager._send_message.call_count == 2


def test_disabled_alert_type_not_affected_by_cooldown(alert_manager):
    """被禁用的告警类型不受冷却影响（直接返回 False）"""
    alert_manager.config['alert_types']['disabled_alert'] = False
    result = alert_manager.send_alert('disabled_alert', '测试', '内容')

    assert result is False
    assert alert_manager._send_message.call_count == 0
