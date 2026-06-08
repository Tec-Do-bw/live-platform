#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""log_parser 单元测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts import log_parser


SAMPLE_LOG = """\
2026-05-06 00:01:18 | INFO     | task_scheduler.py:155 - 开始执行定时采集任务 - 2026-05-06T00:01:18 (crawl_type=realtime, platform_filter=lazada) | 时区分组: ALL
2026-05-06 00:01:20 | INFO     | task_scheduler.py:234 - 📱 平台: LAZADA | 账号数: 2 | 时区分组: ALL
2026-05-06 00:01:20 | INFO     | task_scheduler.py:248 - [1/2] 账号: k1c0io17 | 分组: 泰国团队-lazada | 用户名: z9Nn0omL
2026-05-06 00:01:30 | INFO     | task_scheduler.py:303 - ✓ [增量] 采集成功
2026-05-06 00:01:31 | INFO     | task_scheduler.py:248 - [2/2] 账号: k1aayvhj | 分组: 马来团队-tiktok | 用户名: foo
2026-05-06 00:01:35 | WARNING  | browser_refresher.py:96 - 需要登录
2026-05-06 00:01:40 | INFO     | task_scheduler.py:303 - ✗ [增量] 采集失败
2026-05-06 00:01:41 | ERROR    | browserapi.py:379 - 查询环境失败: Too many request per second, please check (第1次尝试)
2026-05-06 00:01:42 | ERROR    | browserapi.py:379 - 查询环境失败: Too many request per second, please check (第2次尝试)
2026-05-06 00:05:44 | INFO     | task_scheduler.py:372 - 总计: 1/2 账号采集成功, 1 账号失败
"""


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    p = tmp_path / "2026-05-06.logs"
    p.write_text(SAMPLE_LOG, encoding="utf-8")
    return p


def test_parse_basic_structure(log_file: Path) -> None:
    result = log_parser.parse_log_file(log_file)
    assert result["date"] == "2026-05-06"
    assert result["stats"]["total_rounds"] == 1
    assert result["stats"]["total_success"] == 1
    assert result["stats"]["total_fail"] == 0
    assert result["stats"]["total_logout"] == 1
    assert result["stats"]["total_errors"] == 2


def test_parse_account_results(log_file: Path) -> None:
    result = log_parser.parse_log_file(log_file)
    assert len(result["account_results"]) == 2

    a1, a2 = result["account_results"]
    assert a1["browser_id"] == "k1c0io17"
    assert a1["platform"] == "lazada"
    assert a1["country"] == "TH"
    assert a1["result"] == "success"

    assert a2["browser_id"] == "k1aayvhj"
    assert a2["platform"] == "tiktok"
    assert a2["country"] == "MY"
    assert a2["result"] == "logout"
    assert a2["logout_signal"] is True
    assert a2["failure_reason"] == "账号登出/需要登录"


def test_error_aggregation(log_file: Path) -> None:
    result = log_parser.parse_log_file(log_file)
    # "(第1次尝试)" / "(第2次尝试)" 应被归一化为同一条
    assert len(result["error_summary"]) == 1
    msg, count = next(iter(result["error_summary"].items()))
    assert "Too many request" in msg
    assert count == 2


def test_missing_file(tmp_path: Path) -> None:
    result = log_parser.parse_log_file(tmp_path / "nope.logs")
    assert result["error_summary"] == {"__file_missing__": 1}
    assert result["stats"]["total_rounds"] == 0


def test_parse_by_date(log_file: Path) -> None:
    result = log_parser.parse_by_date(log_file.parent, date(2026, 5, 6))
    assert result["stats"]["total_rounds"] == 1


def test_parse_by_date_merges_service_logs_and_ignores_realtime(tmp_path: Path) -> None:
    services_dir = tmp_path / "services"
    scheduler_dir = services_dir / "scheduler"
    manual_dir = services_dir / "manual_once"
    realtime_dir = tmp_path / "realtime" / "lazada"
    scheduler_dir.mkdir(parents=True)
    manual_dir.mkdir(parents=True)
    realtime_dir.mkdir(parents=True)

    scheduler_log = scheduler_dir / "2026-05-06.logs"
    manual_log = manual_dir / "2026-05-06.logs"
    realtime_log = realtime_dir / "2026-05-06.logs"

    scheduler_log.write_text(SAMPLE_LOG, encoding="utf-8")
    manual_log.write_text(SAMPLE_LOG.replace("00:01", "01:01"), encoding="utf-8")
    realtime_log.write_text(SAMPLE_LOG.replace("00:01", "02:01"), encoding="utf-8")

    result = log_parser.parse_by_date(tmp_path, date(2026, 5, 6))

    assert result["stats"]["total_rounds"] == 2
    assert result["stats"]["total_success"] == 2
    assert result["stats"]["total_fail"] == 0
    assert result["stats"]["total_logout"] == 2
    assert result["stats"]["total_accounts"] == 4


def test_parse_by_date_falls_back_to_legacy_root_log(log_file: Path) -> None:
    result = log_parser.parse_by_date(log_file.parent, date(2026, 5, 6))
    assert result["log_path"] == str(log_file)
    assert result["stats"]["total_rounds"] == 1


def test_parse_manual_full_plain_account_lines_and_new_result_formats(tmp_path: Path) -> None:
    """manual_full 真实日志会混用无前缀账号行和新版结果行。"""
    p = tmp_path / "2026-06-04.logs"
    p.write_text(
        """\
📱 平台: TIKTOK | 账号数: 3
[1/3] 账号: kjp | 分组: 日本团队-tiktok | 用户名: jp_user
2026-06-04 20:58:47 | INFO     | main.py:274 - ✓ [手动全量] 采集结果: 页面数=0, API数=76, 数据数=76
[2/3] 账号: kmx | 分组: 墨西哥团队-tiktok | 用户名: mx_user
2026-06-04 20:58:49 | ERROR    | task_scheduler.py:317 - ✗ 采集失败: [kmx] 凭据缺失，需要刷新
[3/3] 账号: kth | 分组: 泰国团队-shopee | 用户名: th_user
2026-06-04 20:58:51 | ERROR    | base.py:140 - 检测到账号登出 | 采集无权限，停止采集
2026-06-04 20:58:52 | ERROR    | task_scheduler.py:317 - ✗ 采集失败: None
""",
        encoding="utf-8",
    )

    result = log_parser.parse_log_file(p)

    assert result["stats"]["total_rounds"] == 1
    assert result["stats"]["total_accounts"] == 3
    assert result["stats"]["total_success"] == 1
    assert result["stats"]["total_fail"] == 1
    assert result["stats"]["total_logout"] == 1

    accounts = {item["browser_id"]: item for item in result["account_results"]}
    assert accounts["kjp"]["result"] == "success"
    assert accounts["kjp"]["country"] == "JP"
    assert accounts["kmx"]["result"] == "fail"
    assert accounts["kmx"]["country"] == "MX"
    assert accounts["kmx"]["failure_reason"] == "凭据缺失，需要刷新"
    assert accounts["kth"]["result"] == "logout"
    assert accounts["kth"]["logout_signal"] is True
    assert accounts["kth"]["failure_reason"] == "账号登出/需要登录"


def test_parse_ansi_colored_error_line(tmp_path: Path) -> None:
    """loguru exception 行包含 ANSI 颜色时,错误聚合应先清理再归一。"""
    p = tmp_path / "2026-06-04.logs"
    p.write_text(
        "2026-06-04 20:58:09 | ERROR    | adapter.py:132 - "
        "\x1b[31m[k1] TikTok HTTP 采集异常: [k1] 凭据缺失，需要刷新\x1b[0m\n",
        encoding="utf-8",
    )

    result = log_parser.parse_log_file(p)

    msg = next(iter(result["error_summary"]))
    assert "\x1b" not in msg
    assert "凭据缺失" in msg
