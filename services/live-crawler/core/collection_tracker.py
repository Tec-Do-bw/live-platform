#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2026/03/04
# @Author     : XBW
# @File       : collection_tracker.py
# @Description: 采集追踪模块，记录已完成全量采集的账号

import json
from pathlib import Path
from datetime import datetime

from utils.logger import logger

# 追踪文件路径
_TRACKER_DIR = Path(__file__).parents[1] / 'resource'
_TRACKER_FILE = _TRACKER_DIR / 'collection_tracker.json'


class CollectionTracker:
    """追踪已完成全量采集的账号

    使用 JSON 文件持久化，记录每个账号首次完成全量采集的时间。
    在 once/scheduler 模式下，新账号（不在追踪文件中的）自动执行全量采集。

    注意：本类非线程/进程安全，应在单进程中使用。
    并发模式（ProcessPoolExecutor）下的标记操作应在主进程中完成。
    """

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        """从文件加载追踪数据"""
        if _TRACKER_FILE.exists():
            try:
                with open(_TRACKER_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f'追踪文件读取失败，重新初始化: {e}')
        return {}

    def _save(self):
        """保存追踪数据到文件"""
        _TRACKER_DIR.mkdir(parents=True, exist_ok=True)
        with open(_TRACKER_FILE, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def is_new_account(self, platform: str, user_id: str) -> bool:
        """检查账号是否为新账号（未完成过全量采集）

        Args:
            platform: 平台标识（如 'tiktok', 'shopee'）
            user_id: AdsPower 环境 ID

        Returns:
            bool: True 表示新账号，需要全量采集
        """
        key = f"{platform}:{user_id}"
        return key not in self._data

    def mark_full_collected(self, platform: str, user_id: str):
        """标记账号已完成全量采集

        Args:
            platform: 平台标识
            user_id: AdsPower 环境 ID
        """
        key = f"{platform}:{user_id}"
        self._data[key] = {
            'platform': platform,
            'user_id': user_id,
            'collected_at': datetime.now().isoformat(),
        }
        self._save()
        logger.info(f'账号 {user_id}（{platform}）已标记为全量采集完成')

    def mark_full_collected_batch(self, items: list):
        """批量标记账号已完成全量采集（减少文件 I/O）

        Args:
            items: [(platform, user_id), ...] 列表
        """
        now = datetime.now().isoformat()
        for platform, user_id in items:
            key = f"{platform}:{user_id}"
            self._data[key] = {
                'platform': platform,
                'user_id': user_id,
                'collected_at': now,
            }
        self._save()
        logger.info(f'批量标记 {len(items)} 个账号为全量采集完成')
