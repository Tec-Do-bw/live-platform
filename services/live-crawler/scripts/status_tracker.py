#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""账号状态追踪器 — 跨天维护连续登出/未成功天数。

状态文件: services/live-crawler/account_status.json(运行时数据,gitignored)
每次日报运行后用当天解析结果更新。
"""

from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

STATUS_SCHEMA_VERSION = 1


def load_status(status_path: Path) -> dict[str, dict[str, Any]]:
    """读取状态文件,损坏时备份并返回空字典。"""
    if not status_path.exists():
        return {}
    try:
        with status_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("status 文件根节点必须是 dict")
        return data
    except (json.JSONDecodeError, ValueError):
        backup = status_path.with_suffix(".json.broken")
        shutil.copy(status_path, backup)
        return {}


def save_status(status_path: Path, status: dict[str, dict[str, Any]]) -> None:
    """原子写入(先写临时文件再 rename)。"""
    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = status_path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    tmp.replace(status_path)


def update_status(
    status: dict[str, dict[str, Any]],
    parsed_log: dict,
    today: date,
) -> dict[str, dict[str, Any]]:
    """根据当天日志结果更新每个账号的状态。

    规则:
    - 当天有任意一次"成功" → last_success_date=today, consecutive_logout_days=0
    - 当天全部失败/登出 → consecutive_logout_days = today - last_success_date
    - 完全没出现的账号保持原状态(可能是当天未轮到)
    """
    today_iso = today.isoformat()

    # 按 browser_id 聚合当天结果
    today_results: dict[str, dict[str, Any]] = {}
    for ar in parsed_log.get("account_results", []):
        bid = ar["browser_id"]
        bucket = today_results.setdefault(
            bid,
            {
                "platform": ar.get("platform"),
                "country": ar.get("country"),
                "group": ar.get("group"),
                "any_success": False,
                "any_logout_signal": False,
                "fail_count": 0,
            },
        )
        if ar["result"] == "success":
            bucket["any_success"] = True
        elif ar["result"] == "fail":
            bucket["fail_count"] += 1
        if ar.get("logout_signal"):
            bucket["any_logout_signal"] = True

    for bid, today_info in today_results.items():
        rec = status.setdefault(
            bid,
            {
                "browser_id": bid,
                "last_success_date": None,
                "consecutive_logout_days": 0,
                "platform": today_info["platform"],
                "country": today_info["country"],
                "group_name": today_info["group"],
            },
        )
        # 元信息总是用最新的覆盖
        rec["platform"] = today_info["platform"] or rec.get("platform")
        rec["country"] = today_info["country"] or rec.get("country")
        rec["group_name"] = today_info["group"] or rec.get("group_name")

        if today_info["any_success"]:
            rec["last_success_date"] = today_iso
            rec["consecutive_logout_days"] = 0
        else:
            # 当天全失败/登出
            last = rec.get("last_success_date")
            if last:
                last_d = date.fromisoformat(last)
                rec["consecutive_logout_days"] = max(0, (today - last_d).days)
            else:
                # 从未成功过 → 把未成功天数累计 +1
                rec["consecutive_logout_days"] = (
                    int(rec.get("consecutive_logout_days") or 0) + 1
                )

    return status


def get_problem_accounts(
    status: dict[str, dict[str, Any]],
    min_days: int = 3,
) -> list[dict[str, Any]]:
    """返回连续登出/未成功 ≥ min_days 的账号列表,按天数降序。"""
    out = [
        rec
        for rec in status.values()
        if int(rec.get("consecutive_logout_days") or 0) >= min_days
    ]
    out.sort(key=lambda r: r.get("consecutive_logout_days", 0), reverse=True)
    return out
