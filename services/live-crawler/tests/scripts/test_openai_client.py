#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from scripts import openai_client


def test_resolve_base_url_prefers_env(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")

    assert openai_client._resolve_base_url() == "https://api.deepseek.com"


def _summary() -> dict:
    return {
        "date": "2026-06-05",
        "account_results": [
            {
                "browser_id": "k1",
                "platform": "tiktok",
                "country": "JP",
                "result": "success",
                "logout_signal": False,
            },
            {
                "browser_id": "k2",
                "platform": "tiktok",
                "country": "JP",
                "result": "logout",
                "logout_signal": True,
                "failure_reason": "账号登出/需要登录",
            },
            {
                "browser_id": "k3",
                "platform": "shopee",
                "country": "TH",
                "result": "fail",
                "logout_signal": False,
                "failure_reason": "HTTP Error 401",
            },
            {
                "browser_id": "k4",
                "platform": "shopee",
                "country": "TH",
                "result": "unknown",
                "logout_signal": False,
            },
        ],
        "error_summary": {
            "凭据缺失，需要刷新": 2,
            "HTTP Error 401": 1,
        },
        "stats": {
            "total_rounds": 1,
            "total_accounts": 4,
            "total_success": 1,
            "total_fail": 1,
            "total_logout": 1,
            "total_errors": 3,
        },
    }


def test_generate_report_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(openai_client, "_openai_config", lambda: {"api_key": ""})

    content, used_llm = openai_client.generate_report(
        prompt_template="prompt",
        today_summary=_summary(),
        yesterday_summary=None,
        problem_accounts=[],
    )

    assert used_llm is False
    assert "采集完整度" in content
    assert "TIKTOK | JP" in content
    assert "登出账号: 1" in content
    assert "采集失败原因 Top 5" in content
    assert "HTTP Error 401" in content
    assert "未知结果账号: 1" in content


def test_generate_report_payload_contains_report_metrics(monkeypatch):
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):  # type: ignore[no-untyped-def]
            captured["kwargs"] = kwargs

            class Message:
                content = "LLM 日报"

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeOpenAI:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            captured["client"] = kwargs
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(openai_client, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(openai_client, "_resolve_base_url", lambda: "https://example.com")
    monkeypatch.setattr(openai_client, "_resolve_timeout", lambda: 10)

    content, used_llm = openai_client.generate_report(
        prompt_template="prompt",
        today_summary=_summary(),
        yesterday_summary=None,
        problem_accounts=[],
    )

    payload = captured["kwargs"]["messages"][1]["content"]
    assert content == "LLM 日报"
    assert used_llm is True
    assert '"report_metrics"' in payload
    assert '"logout_count": 1' in payload
    assert '"failure_reasons"' in payload
