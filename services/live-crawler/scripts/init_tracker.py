#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2026/03/04
# @Author     : XBW
# @File       : init_tracker.py
# @Description: 初始化采集追踪文件（临时脚本，部署后运行一次即可）
#
# 用法：python scripts/init_tracker.py
#
# 该脚本会查询 AdsPower 中所有平台的所有账号，
# 并将它们写入追踪文件标记为"已采集"，
# 这样后续只有新增的账号才会触发全量采集。

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parents[1]
sys.path.insert(0, str(project_root))

from core.config import Settings
from core.collection_tracker import CollectionTracker
from webdriver.browserapi import BrowserApi
from utils.logger import logger


def main():
    logger.info('='*60)
    logger.info('初始化采集追踪文件')
    logger.info('='*60)

    tracker = CollectionTracker()
    total_count = 0

    platform_configs = Settings.PLATFORM_CONFIG
    if not platform_configs:
        logger.error('未找到任何平台配置')
        sys.exit(1)

    for platform, config in platform_configs.items():
        # 获取该平台的所有账号（复用 main.py 中的获取逻辑）
        use_dynamic = config.get('use_dynamic_users', False)

        if use_dynamic:
            use_dynamic_groups = config.get('use_dynamic_groups', False)
            if use_dynamic_groups:
                group_ids = BrowserApi.get_group_ids_by_platform(platform)
                if not group_ids:
                    logger.warning(f'平台 {platform} 未找到匹配的分组，跳过')
                    continue
                accounts = BrowserApi.get_user_ids_from_group_ids(group_ids)
            else:
                group_names = config.get('group_names', [])
                if not group_names:
                    logger.warning(f'平台 {platform} 未配置 group_names，跳过')
                    continue
                accounts = BrowserApi.get_user_ids_from_groups(group_names)

            if not accounts:
                logger.warning(f'平台 {platform} 未获取到账号，跳过')
                continue
        else:
            accounts = config.get('user_ids', [])
            if not accounts:
                logger.info(f'平台 {platform} 无账号配置，跳过')
                continue

        # 收集新账号，批量标记
        batch_items = []
        for account in accounts:
            if isinstance(account, dict):
                user_id = account.get('user_id', '')
            else:
                user_id = account

            if not user_id:
                continue

            if tracker.is_new_account(platform, user_id):
                batch_items.append((platform, user_id))

        if batch_items:
            tracker.mark_full_collected_batch(batch_items)

        total_count += len(batch_items)
        logger.info(f'平台 {platform.upper()}: 标记了 {len(batch_items)} 个账号')

    logger.info('='*60)
    logger.info(f'初始化完成，共标记 {total_count} 个账号为已采集')
    logger.info('='*60)


if __name__ == '__main__':
    main()
