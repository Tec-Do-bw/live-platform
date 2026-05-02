#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/11/12
# @Author     : XBW
# @File       : alert.py
# @Description: 告警模块 - 飞书机器人通知

import json
import time
from datetime import datetime

import requests

from core.config import Settings
from utils.logger import logger


class AlertManager:
    """告警管理器（飞书机器人）"""

    def __init__(self):
        self.config = Settings.ALERT_CONFIG
        self.enabled = self.config.get('enabled', True)
        self.webhook_url = self.config.get('webhook_url', '')
        self._last_sent: dict[str, float] = {}
        self._cooldown: int = self.config.get('cooldown_seconds', 300)

        if not self.enabled:
            logger.warning('告警功能已禁用')

    def send_alert(self, alert_type: str, title: str, content: str) -> bool:
        """发送告警

        Args:
            alert_type: 告警类型 ('login_failed', 'crawl_failed', 'task_timeout')
            title: 告警标题
            content: 告警内容

        Returns:
            bool: 是否发送成功
        """
        if not self.enabled:
            logger.debug(f'告警已禁用，跳过发送: {title}')
            return False

        alert_types_config = self.config.get('alert_types', {})
        if not alert_types_config.get(alert_type, True):
            logger.debug(f'告警类型 {alert_type} 已禁用')
            return False

        now = time.time()
        if now - self._last_sent.get(alert_type, 0) < self._cooldown:
            logger.info(f'告警冷却中，跳过: {alert_type} - {title}')
            return False
        self._last_sent[alert_type] = now

        logger.info(f'发送告警: {alert_type} - {title}')
        text = f"{title}\n\n{content}\n\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return self._send_message(text)

    def _send_message(self, content: str) -> bool:
        """发送飞书消息

        Args:
            content: 消息内容

        Returns:
            是否发送成功
        """
        if not self.webhook_url:
            logger.warning('未配置飞书 Webhook URL，无法发送告警')
            return False

        payload = {"msg_type": "text", "content": {"text": content}}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                self.webhook_url, headers=headers,
                data=json.dumps(payload), timeout=10,
            )
            result = response.json()
            status_code = result.get("code") if "code" in result else result.get("StatusCode")
            if status_code == 0:
                logger.debug("飞书消息发送成功")
                return True
            else:
                logger.error(f"飞书消息发送失败: {result}")
                return False
        except Exception as e:
            logger.error(f"飞书消息发送异常: {e}")
            return False

    def send_login_failed_alert(self, browser_ids: list) -> bool:
        """发送账号登出告警"""
        title = '账号登出告警'
        content = "检测到以下账号已登出，请及时处理：\n"
        for browser_id in browser_ids:
            content += f"- {browser_id}\n"
        return self.send_alert('login_failed', title, content)

    def send_crawl_failed_alert(self, total: int, failed: int, error_msg: str = '') -> bool:
        """发送采集失败告警"""
        title = '采集任务失败告警'
        content = f"采集任务执行异常：\n- 总任务数: {total}\n- 失败任务数: {failed}\n"
        if error_msg:
            content += f"- 错误信息: {error_msg}\n"
        return self.send_alert('crawl_failed', title, content)

    def send_task_timeout_alert(self, task_name: str, timeout: int) -> bool:
        """发送任务超时告警"""
        title = '任务超时告警'
        content = f"任务执行超时：\n- 任务名称: {task_name}\n- 超时时间: {timeout}秒\n"
        return self.send_alert('task_timeout', title, content)


# 单例
alert_manager = AlertManager()

