#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""飞书 Webhook 推送 — 富文本卡片,失败重试。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

import requests

from utils.logger import logger

DEFAULT_TIMEOUT = 10
DEFAULT_MAX_RETRIES = 3


def _alert_config() -> dict:
    """读取 ALERT_CONFIG 作为 webhook/secret 的回退源。

    懒加载导入,避免模块级硬依赖 core.config;导入失败时返回空字典安全降级。
    """
    try:
        from core.config import Settings

        return Settings.ALERT_CONFIG or {}
    except Exception as e:  # 配置不可用时不应阻断推送链路
        logger.warning(f"读取 ALERT_CONFIG 失败,回退源不可用: {e}")
        return {}


def send_card(title: str, content_md: str) -> bool:
    """发送飞书富文本卡片。

    Webhook 与签名密钥优先读环境变量,缺失时回退到 Settings.ALERT_CONFIG,
    与运行时告警(utils/alert.py)共用同一个飞书机器人:
    - 环境变量 FEISHU_DAILY_REPORT_WEBHOOK / FEISHU_DAILY_REPORT_SECRET(可选覆盖)
    - 回退源 ALERT_CONFIG['webhook_url'] / ALERT_CONFIG['secret']

    Returns:
        bool: 是否发送成功
    """
    webhook = os.getenv("FEISHU_DAILY_REPORT_WEBHOOK") or _alert_config().get("webhook_url")
    if not webhook:
        logger.error("飞书 Webhook 未配置(环境变量与 ALERT_CONFIG 均为空),放弃推送")
        return False

    secret = os.getenv("FEISHU_DAILY_REPORT_SECRET") or _alert_config().get("secret")
    payload = _build_card_payload(title, content_md, secret)

    last_err: Exception | None = None
    for attempt in range(1, DEFAULT_MAX_RETRIES + 1):
        try:
            resp = requests.post(webhook, json=payload, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") in (0, None):  # 飞书成功 code=0,部分版本无该字段
                logger.info(f"飞书日报推送成功 | title={title}")
                return True
            raise RuntimeError(f"飞书返回错误: {data}")
        except Exception as e:
            last_err = e
            logger.warning(f"飞书推送失败(第 {attempt} 次): {e}")
            if attempt < DEFAULT_MAX_RETRIES:
                time.sleep(2 * attempt)

    logger.error(f"飞书推送最终失败: {last_err}")
    return False


def _build_card_payload(title: str, content_md: str, secret: str | None) -> dict:
    """构造飞书 interactive 卡片 payload,可选加签。"""
    payload: dict = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": [
                {"tag": "markdown", "content": content_md},
            ],
        },
    }
    if secret:
        ts = str(int(time.time()))
        payload["timestamp"] = ts
        payload["sign"] = _gen_sign(secret, ts)
    return payload


def _gen_sign(secret: str, timestamp: str) -> str:
    """飞书自定义机器人签名算法。"""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"), b"", hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")
