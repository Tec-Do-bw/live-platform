#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比浏览器版与 HTTP 版 format_api_message 字段契约。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).parents[2]
LIVE_CRAWLER_ROOT = PROJECT_ROOT / "services" / "live-crawler"
if str(LIVE_CRAWLER_ROOT) not in sys.path:
    sys.path.insert(0, str(LIVE_CRAWLER_ROOT))

from crawlers.http.tiktok.collector import _format_message  # noqa: E402


BROWSER_FIXTURE = Path(__file__).with_name("tiktok_browser_message.json")
REPORT_PATH = Path(__file__).with_name("tiktok_diff_report.md")


def _type_name(value: Any) -> str:
    return type(value).__name__


def _build_http_message() -> dict[str, Any]:
    url = "https://shop.tiktok.com/api/v2/insights/creator/live/list?device_id=dev1"
    request_body = {"request": {"params": [{"stats_types": [10, 15]}]}}
    response_body = {"code": 0, "data": {"segments": []}}
    cookies = [{"name": "sessionid", "value": "sid"}]
    return _format_message(url, request_body, response_body, cookies, "socket-1")


def _render_report(browser_message: dict[str, Any], http_message: dict[str, Any]) -> str:
    browser_fields = set(browser_message)
    http_fields = set(http_message)
    common = sorted(browser_fields & http_fields)
    missing = sorted(browser_fields - http_fields)
    added = sorted(http_fields - browser_fields)
    type_diffs = [
        {
            "field": field,
            "browser": _type_name(browser_message[field]),
            "http": _type_name(http_message[field]),
        }
        for field in common
        if type(browser_message[field]) is not type(http_message[field])
    ]

    lines = [
        "# TikTok format_api_message 字段级 diff 报告",
        "",
        "## 结论",
    ]
    if not missing and not added and not type_diffs:
        lines.append("零字段差异：HTTP 版 `_format_message` 与浏览器版 fixture 字段集合和顶层类型一致。")
    else:
        lines.append("存在字段差异，详见下方列表。")

    lines.extend([
        "",
        "## 共有字段",
        ", ".join(common),
        "",
        "## 缺失字段",
        ", ".join(missing) if missing else "无",
        "",
        "## 新增字段",
        ", ".join(added) if added else "无",
        "",
        "## 类型差异",
    ])
    if type_diffs:
        lines.extend(
            f"- {item['field']}: browser={item['browser']} http={item['http']}"
            for item in type_diffs
        )
    else:
        lines.append("无")

    lines.extend([
        "",
        "## HTTP 版字段类型",
    ])
    lines.extend(f"- {field}: {_type_name(http_message[field])}" for field in sorted(http_fields))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    browser_message = json.loads(BROWSER_FIXTURE.read_text(encoding="utf-8"))
    http_message = _build_http_message()
    REPORT_PATH.write_text(_render_report(browser_message, http_message), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
