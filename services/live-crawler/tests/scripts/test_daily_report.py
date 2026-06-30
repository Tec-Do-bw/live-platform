#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_report 主流程单元测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts import daily_report


def test_run_dry_run_updates_temp_status_and_prints_report(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    logs_dir = tmp_path / "logs"
    scheduler_dir = logs_dir / "services" / "scheduler"
    scheduler_dir.mkdir(parents=True)
    (scheduler_dir / "2026-06-05.logs").write_text(
        """\
2026-06-05 00:00:00 | INFO     | task_scheduler.py:160 - 开始执行定时采集任务 - 2026-06-05T00:00:00 (crawl_type=history, platform_filter=tiktok) | 时区分组: UTC+9
2026-06-05 00:00:01 | INFO     | task_scheduler.py:253 - [1/1] 账号: kjp | 分组: 日本团队-tiktok | 用户名: jp_user
2026-06-05 00:00:02 | INFO     | task_scheduler.py:308 - ✓ [增量] 采集成功
2026-06-05 00:00:03 | INFO     | task_scheduler.py:377 - 总计: 1/1 账号采集成功, 0 账号失败
""",
        encoding="utf-8",
    )

    status_path = tmp_path / "account_status.json"
    monkeypatch.setattr(daily_report, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(daily_report, "STATUS_PATH", status_path)
    monkeypatch.setattr(daily_report.openai_client, "load_prompt", lambda _path: "prompt")
    monkeypatch.setattr(
        daily_report.openai_client,
        "generate_report",
        lambda **_kwargs: ("日报正文", False),
    )

    called = {"feishu": False}

    def fake_send_card(title: str, content_md: str) -> bool:
        called["feishu"] = True
        return True

    monkeypatch.setattr(daily_report.feishu_webhook, "send_card", fake_send_card)

    code = daily_report.run(date(2026, 6, 5), dry_run=True)

    out = capsys.readouterr().out
    assert code == 0
    assert "日报正文" in out
    assert status_path.exists()
    assert called["feishu"] is False
