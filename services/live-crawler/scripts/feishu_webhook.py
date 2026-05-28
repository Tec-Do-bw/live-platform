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


def send_card(title: str, content_md: str) -> bool:
    """发送飞书富文本卡片。

    依赖环境变量:
    - FEISHU_DAILY_REPORT_WEBHOOK: 必填,Webhook URL
    - FEISHU_DAILY_REPORT_SECRET: 选填,签名密钥(机器人启用了"自定义关键词加签"时必填)

    Returns:
        bool: 是否发送成功
    """
    webhook = os.getenv("FEISHU_DAILY_REPORT_WEBHOOK")
    if not webhook:
        logger.error("FEISHU_DAILY_REPORT_WEBHOOK 未配置,放弃推送")
        return False

    secret = os.getenv("FEISHU_DAILY_REPORT_SECRET")
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
