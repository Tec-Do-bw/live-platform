#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""刷新 TikTok account_credentials 的定时任务入口。"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cookie_keeper.tiktok_refresher import TikTokRefresher
from core.config import Settings
from utils.logger import logger
from webdriver.browserapi import BrowserApi


def _load_tiktok_accounts() -> list[dict[str, str]]:
    """按现有平台配置加载 TikTok 账号列表。"""
    config = Settings.PLATFORM_CONFIG.get("tiktok", {})

    if config.get("use_dynamic_groups"):
        group_ids = BrowserApi.get_group_ids_by_platform("tiktok")
        return BrowserApi.get_user_ids_from_group_ids(group_ids) if group_ids else []

    if config.get("use_dynamic_users"):
        group_names = config.get("group_names", [])
        return BrowserApi.get_user_ids_from_groups(group_names) if group_names else []

    return [
        {"user_id": account_id, "group_name": "", "name": ""}
        for account_id in config.get("user_ids", [])
        if account_id
    ]


def refresh_all() -> int:
    """刷新全部 TikTok 账号，返回失败数。"""
    accounts = _load_tiktok_accounts()
    if not accounts:
        logger.warning("未获取到 TikTok 账号，跳过刷新")
        return 0

    refresher = TikTokRefresher()
    failed = 0
    for idx, account in enumerate(accounts, 1):
        account_id = account.get("user_id", "")
        group_name = account.get("group_name", "")
        if not account_id:
            continue
        logger.info(f"[{idx}/{len(accounts)}] 刷新 TikTok 账号: {account_id} group={group_name}")
        if not refresher.refresh_account(account_id, group_name=group_name):
            failed += 1

    logger.info(f"TikTok 凭据刷新完成，账号数={len(accounts)}，失败数={failed}")
    return failed


def main() -> int:
    failed = refresh_all()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
