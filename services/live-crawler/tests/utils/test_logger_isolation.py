#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志入口隔离测试。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from utils.logger import Logings, logger


def _today_log_name() -> str:
    return f"{datetime.now():%Y-%m-%d}.logs"


@pytest.fixture(autouse=True)
def restore_logger_config():
    original_service_name = Logings.service_name
    original_log_dir = Logings.logpath
    yield
    Logings.configure(service_name=original_service_name, log_dir=original_log_dir)


def test_service_log_excludes_realtime_logs(tmp_path: Path) -> None:
    Logings.configure(service_name="scheduler", log_dir=tmp_path)

    logger.info("history message")
    with logger.contextualize(crawl_type="realtime", platform="lazada"):
        logger.info("realtime message")

    logger.complete()

    service_log = tmp_path / "services" / "scheduler" / _today_log_name()
    realtime_log = tmp_path / "realtime" / "lazada" / _today_log_name()

    assert service_log.exists()
    assert realtime_log.exists()

    service_text = service_log.read_text(encoding="utf-8")
    realtime_text = realtime_log.read_text(encoding="utf-8")

    assert "history message" in service_text
    assert "realtime message" not in service_text
    assert "realtime message" in realtime_text


def test_reconfigure_service_log_target(tmp_path: Path) -> None:
    Logings.configure(service_name="scheduler", log_dir=tmp_path)
    logger.info("scheduler message")
    logger.complete()

    Logings.configure(service_name="refresh_tiktok_credentials", log_dir=tmp_path)
    logger.info("refresh message")
    logger.complete()

    today = _today_log_name()
    scheduler_log = tmp_path / "services" / "scheduler" / today
    refresh_log = tmp_path / "services" / "refresh_tiktok_credentials" / today

    assert "scheduler message" in scheduler_log.read_text(encoding="utf-8")
    assert "refresh message" in refresh_log.read_text(encoding="utf-8")
    assert "refresh message" not in scheduler_log.read_text(encoding="utf-8")
