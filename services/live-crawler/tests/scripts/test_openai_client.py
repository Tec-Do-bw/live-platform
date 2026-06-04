#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from scripts import openai_client


def test_resolve_base_url_prefers_env(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")

    assert openai_client._resolve_base_url() == "https://api.deepseek.com"
