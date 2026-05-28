#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""status_tracker 单元测试 — 重点验证连续登出天数累加逻辑。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts import status_tracker


def _make_parsed_log(date_str: str, accounts: list[dict]) -> dict:
    return {
        "date": date_str,
        "rounds": [],
        "account_results": accounts,
        "errors": [],
        "error_summary": {},
        "stats": {},
    }


def test_first_success_resets_counter(tmp_path: Path) -> None:
    status_path = tmp_path / "account_status.json"
    status: dict = {}

    parsed = _make_parsed_log(
        "2026-05-01",
        [
            {
                "browser_id": "k1",
                "group": "泰国团队-tiktok",
                "platform": "tiktok",
                "country": "TH",
                "result": "success",
                "logout_signal": False,
            }
        ],
    )
    status = status_tracker.update_status(status, parsed, date(2026, 5, 1))
    rec = status["k1"]
    assert rec["last_success_date"] == "2026-05-01"
    assert rec["consecutive_logout_days"] == 0


def test_logout_accumulates_across_days(tmp_path: Path) -> None:
    status: dict = {
        "k1": {
            "browser_id": "k1",
            "last_success_date": "2026-04-28",
            "consecutive_logout_days": 0,
            "platform": "tiktok",
            "country": "TH",
            "group_name": "泰国团队-tiktok",
        }
    }
    parsed = _make_parsed_log(
        "2026-05-01",
        [
            {
                "browser_id": "k1",
                "group": "泰国团队-tiktok",
                "platform": "tiktok",
                "country": "TH",
                "result": "fail",
                "logout_signal": True,
            }
        ],
    )
    status = status_tracker.update_status(status, parsed, date(2026, 5, 1))
    assert status["k1"]["consecutive_logout_days"] == 3  # 5/1 - 4/28


def test_problem_accounts_threshold() -> None:
    status = {
        "a": {"browser_id": "a", "consecutive_logout_days": 5, "platform": "tiktok", "country": "TH"},
        "b": {"browser_id": "b", "consecutive_logout_days": 2, "platform": "lazada", "country": "MY"},
        "c": {"browser_id": "c", "consecutive_logout_days": 7, "platform": "shopee", "country": "TH"},
    }
    out = status_tracker.get_problem_accounts(status, min_days=3)
    assert [r["browser_id"] for r in out] == ["c", "a"]


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    data = {"k1": {"browser_id": "k1", "consecutive_logout_days": 5}}
    status_tracker.save_status(p, data)
    assert json.loads(p.read_text(encoding="utf-8"))["k1"]["consecutive_logout_days"] == 5
    reloaded = status_tracker.load_status(p)
    assert reloaded == data


def test_load_corrupted_file_backs_up(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    p.write_text("{not json", encoding="utf-8")
    out = status_tracker.load_status(p)
    assert out == {}
    assert (tmp_path / "s.json.broken").exists()


def test_never_succeeded_increments(tmp_path: Path) -> None:
    """从未成功过的新账号应每次累加 1。"""
    status: dict = {}
    for i, day in enumerate([date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)], start=1):
        parsed = _make_parsed_log(
            day.isoformat(),
            [
                {
                    "browser_id": "newbie",
                    "group": "马来团队-lazada",
                    "platform": "lazada",
                    "country": "MY",
                    "result": "fail",
                    "logout_signal": True,
                }
            ],
        )
        status = status_tracker.update_status(status, parsed, day)
        assert status["newbie"]["consecutive_logout_days"] == i
