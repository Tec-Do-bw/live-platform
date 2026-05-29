#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""feishu_webhook 单元测试 — mock requests 验证 payload 与签名。"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from scripts import feishu_webhook


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "FEISHU_DAILY_REPORT_WEBHOOK",
        "FEISHU_DAILY_REPORT_SECRET",
    ):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _empty_alert_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认隔离 ALERT_CONFIG 回退源,避免单测依赖真实配置。"""
    monkeypatch.setattr(feishu_webhook, "_alert_config", lambda: {})


def test_missing_webhook_returns_false() -> None:
    assert feishu_webhook.send_card("t", "c") is False


def test_fallback_to_alert_config_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境变量缺失时,应回退到 ALERT_CONFIG 的 webhook_url 与 secret。"""
    monkeypatch.setattr(
        feishu_webhook,
        "_alert_config",
        lambda: {"webhook_url": "https://fallback.example.com/hook", "secret": "fb-secret"},
    )
    captured: dict = {}

    def fake_post(url: str, json: dict, timeout: int):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["json"] = json
        resp = MagicMock()
        resp.json.return_value = {"code": 0}
        resp.raise_for_status.return_value = None
        return resp

    with patch("scripts.feishu_webhook.requests.post", side_effect=fake_post):
        assert feishu_webhook.send_card("t", "c") is True

    assert captured["url"] == "https://fallback.example.com/hook"
    assert "sign" in captured["json"]  # 回退 secret 生效


def test_env_overrides_alert_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境变量优先级高于 ALERT_CONFIG 回退源。"""
    monkeypatch.setenv("FEISHU_DAILY_REPORT_WEBHOOK", "https://env.example.com/hook")
    monkeypatch.setattr(
        feishu_webhook,
        "_alert_config",
        lambda: {"webhook_url": "https://fallback.example.com/hook"},
    )
    captured: dict = {}

    def fake_post(url: str, json: dict, timeout: int):  # type: ignore[no-untyped-def]
        captured["url"] = url
        resp = MagicMock()
        resp.json.return_value = {"code": 0}
        resp.raise_for_status.return_value = None
        return resp

    with patch("scripts.feishu_webhook.requests.post", side_effect=fake_post):
        assert feishu_webhook.send_card("t", "c") is True

    assert captured["url"] == "https://env.example.com/hook"


def test_payload_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_DAILY_REPORT_WEBHOOK", "https://example.com/hook")
    captured: dict = {}

    def fake_post(url: str, json: dict, timeout: int):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["json"] = json
        resp = MagicMock()
        resp.json.return_value = {"code": 0, "msg": "ok"}
        resp.raise_for_status.return_value = None
        return resp

    with patch("scripts.feishu_webhook.requests.post", side_effect=fake_post):
        assert feishu_webhook.send_card("标题", "**正文**") is True

    assert captured["url"] == "https://example.com/hook"
    payload = captured["json"]
    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["title"]["content"] == "标题"
    assert payload["card"]["elements"][0]["content"] == "**正文**"
    assert "sign" not in payload  # 未配置 secret 不应有签名


def test_signature_when_secret_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_DAILY_REPORT_WEBHOOK", "https://example.com/hook")
    monkeypatch.setenv("FEISHU_DAILY_REPORT_SECRET", "abc123")
    captured: dict = {}

    def fake_post(url: str, json: dict, timeout: int):  # type: ignore[no-untyped-def]
        captured["json"] = json
        resp = MagicMock()
        resp.json.return_value = {"code": 0}
        resp.raise_for_status.return_value = None
        return resp

    with patch("scripts.feishu_webhook.requests.post", side_effect=fake_post):
        assert feishu_webhook.send_card("t", "c") is True

    assert "sign" in captured["json"]
    assert "timestamp" in captured["json"]


def test_retry_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_DAILY_REPORT_WEBHOOK", "https://example.com/hook")
    monkeypatch.setattr("scripts.feishu_webhook.time.sleep", lambda _s: None)
    call_count = {"n": 0}

    def fake_post(url: str, json: dict, timeout: int):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        raise RuntimeError("network down")

    with patch("scripts.feishu_webhook.requests.post", side_effect=fake_post):
        assert feishu_webhook.send_card("t", "c") is False
    assert call_count["n"] == 3
