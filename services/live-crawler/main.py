#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/11/12
# @Author     : XBW
# @File       : main.py
# @Description: 直播数据采集系统主入口

import sys
import argparse
from pathlib import Path
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from scheduler.task_scheduler import TaskScheduler
from crawlers.browser.live_crawler import LiveCrawler
from utils.logger import logger
from core.config import Settings
from core.collection_tracker import CollectionTracker
from core.collection_mode import resolve_collection_mode
from webdriver.browserapi import BrowserApi
from datetime import datetime as dt
from monitor import get_monitor
from monitor.login_status_manager import LoginStatusManager
from monitor.recovery_events import append_full_recovery_event_if_needed


def crawl_single_account(platform: str, account, full_collection: bool, batch_id: str = '', crawl_type: str = 'history') -> dict:
    """单账号采集工作函数，在子进程中执行

    必须定义在模块顶层以支持 pickle 序列化。
    Windows spawn 子进程重新 import 模块，logger/Settings 自动重新初始化。
    注意：采集追踪（CollectionTracker）的标记操作在主进程中执行，不要在此函数中操作 tracker。
    """
    if isinstance(account, dict):
        user_id = account.get('user_id', '')
        group_name = account.get('group_name', '')
    else:
        user_id = account
        group_name = ''
    try:
        crawler = LiveCrawler(platform=platform, browser_id=user_id,
                              full_collection=full_collection, group_name=group_name,
                              batch_id=batch_id, crawl_type=crawl_type)
        result = crawler.start_crawl()
        result['user_id'] = user_id
        return result
    except Exception as e:
        logger.exception(f'子进程采集异常 platform={platform} user_id={user_id}: {e}')
        return {'success': False, 'error': str(e), 'user_id': user_id,
                'pages_visited': 0, 'apis_collected': 0, 'data_sent': 0}


def run_scheduler():
    """运行定时任务调度器"""
    logger.info('='*60)
    logger.info('直播数据采集系统 - 定时任务模式')
    logger.info('='*60)
     
    scheduler = TaskScheduler()
    try:
        scheduler.start()
        # 保持主线程运行，以便接收Ctrl+C信号
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info('收到停止信号')
        scheduler.shutdown()
    except Exception as e:
        logger.exception(f'调度器运行异常: {e}')
        sys.exit(1)


def run_once(full_collection: bool = False, workers: int = 1, crawl_type: str = 'history', platforms: list[str] | None = None):
    """手动执行一次采集任务

    Args:
        full_collection: 是否全量采集模式
        workers: 并发进程数，>=2 时开启并发（仅 full 模式生效）
        crawl_type: 采集类型（'realtime' 或 'history'，仅 HTTP 爬虫使用）
        platforms: 指定要采集的平台列表，None 表示采集所有平台
    """
    with logger.contextualize(crawl_type=crawl_type):
        _run_once_impl(full_collection, workers, crawl_type, platforms)


def _run_once_impl(full_collection: bool, workers: int, crawl_type: str, platforms: list[str] | None = None):
    # 采集监控：生成批次ID并记录开始
    mode = 'full' if full_collection else 'once'
    batch_id = dt.now().strftime('%Y-%m-%d_%H:%M')
    monitor = get_monitor()
    monitor.start_batch(batch_id, mode)

    mode_name = '全量采集' if full_collection else '增量采集'
    concurrent_info = f'（{workers}进程并发）' if workers >= 2 else '（串行）'
    platform_filter = f'（仅 {", ".join(platforms)}）' if platforms else '（所有平台）'
    logger.info('='*60)
    logger.info(f'直播数据采集系统 - 手动{mode_name}模式 {concurrent_info} {platform_filter}')
    logger.info('='*60)

    # 获取所有平台配置
    platform_configs = Settings.PLATFORM_CONFIG

    # 平台过滤
    if platforms:
        platform_configs = {k: v for k, v in platform_configs.items() if k in platforms}
        if not platform_configs:
            logger.error(f'指定的平台 {platforms} 未在配置中找到')
            sys.exit(1)
    
    if not platform_configs:
        logger.error('未找到任何平台配置')
        sys.exit(1)
    
    # 采集追踪器（在平台循环外创建一次）
    tracker = CollectionTracker()
    status_mgr = LoginStatusManager(monitor.conn)

    # 统计所有平台的采集结果
    all_results = {}
    total_accounts = 0
    total_success = 0

    # 遍历所有平台
    for platform, config in platform_configs.items():
        with logger.contextualize(platform=platform):
            # 判断是否启用动态获取user_ids
            use_dynamic = config.get('use_dynamic_users', False)

            if use_dynamic:
                use_dynamic_groups = config.get('use_dynamic_groups', False)

                if use_dynamic_groups:
                    # 动态筛选：自动查询所有分组，筛选名称包含 platform 的
                    logger.info(f'🔄 平台 {platform} 动态筛选分组（按platform={platform}）')
                    group_ids = BrowserApi.get_group_ids_by_platform(platform)
                    if not group_ids:
                        logger.warning(f'⊗ 平台 {platform} 未找到匹配的分组，跳过')
                        continue
                    accounts = BrowserApi.get_user_ids_from_group_ids(group_ids)
                else:
                    # 使用配置的 group_names
                    group_names = config.get('group_names', [])
                    if not group_names:
                        logger.warning(f'⊗ 平台 {platform} 启用了动态获取但未配置group_names，跳过')
                        continue
                    logger.info(f'🔄 平台 {platform} 动态获取user_ids from 分组: {group_names}')
                    accounts = BrowserApi.get_user_ids_from_groups(group_names)

                if not accounts:
                    logger.warning(f'⊗ 平台 {platform} 未获取到user_ids，跳过')
                    continue
            else:
                # 直接使用配置的user_ids
                accounts = config.get('user_ids', [])

                # 跳过没有账号的平台
                if not accounts:
                    logger.info(f'⊗ 平台 {platform} 无账号配置，跳过')
                    continue

            logger.info(f'\n📱 平台: {platform.upper()} | 账号数: {len(accounts)}')
            logger.info('='*60)

            # 依次采集该平台的所有账号
            platform_results = []

            if workers >= 2 and full_collection:
                # ---- 并发模式（仅 --mode full 时启用）----
                from concurrent.futures import ProcessPoolExecutor, as_completed
                actual_workers = min(workers, len(accounts))
                logger.info(f'并发采集：{actual_workers} 进程 × {len(accounts)} 账号')

                future_to_account = {}
                with ProcessPoolExecutor(max_workers=actual_workers) as executor:
                    for account in accounts:
                        user_id = account.get('user_id', account) if isinstance(account, dict) else account
                        group_name = account.get('group_name', '') if isinstance(account, dict) else ''
                        mode_label = '手动全量'
                        logger.info(f'提交账号 {user_id} [手动全量] 到并发队列')
                        future = executor.submit(crawl_single_account, platform, account, full_collection, batch_id, crawl_type)
                        future_to_account[future] = {
                            'account': account,
                            'user_id': user_id,
                            'group_name': group_name,
                            'mode_label': mode_label,
                        }

                    for future in as_completed(future_to_account):
                        future_meta = future_to_account[future]
                        user_id = future_meta['user_id']
                        group_name = future_meta['group_name']
                        mode_label = future_meta['mode_label']
                        try:
                            result = future.result()
                            platform_results.append(result)
                            status = '✓' if result.get('success') else '✗'
                            logger.info(f'{status} 账号 {user_id} 采集结果: 页面数={result.get("pages_visited", 0)}, '
                                       f'API数={result.get("apis_collected", 0)}, 数据数={result.get("data_sent", 0)}')
                            if result.get('error'):
                                logger.error(f'  错误: {result["error"]}')

                            # 全量采集成功后标记到追踪文件（在主进程中执行，避免并发写入）
                            if result.get('success'):
                                tracker.mark_full_collected(platform, user_id)
                        except Exception as e:
                            logger.exception(f'✗ 账号 {user_id} 进程异常: {e}')
                            result = {'success': False, 'error': str(e), 'login_status': True}
                            platform_results.append(result)
            else:
                # ---- 串行模式 ----
                for idx, account in enumerate(accounts, 1):
                    # 兼容 dict（动态获取）和 str（配置文件直接指定）两种格式
                    if isinstance(account, dict):
                        user_id = account.get('user_id', '')
                        group_name = account.get('group_name', '')
                        name = account.get('name', '')
                        logger.info(f'\n[{idx}/{len(accounts)}] 账号: {user_id} | 分组: {group_name} | 用户名: {name}')
                    else:
                        user_id = account
                        group_name = ''
                        name = ''
                        logger.info(f'\n[{idx}/{len(accounts)}] 账号: {user_id}')

                    # 判断每个账号的采集模式：手动全量 > 新账号全量 > 登出恢复全量 > 增量
                    account_full_collection, mode_label = resolve_collection_mode(
                        platform, user_id, tracker, status_mgr, force_full_collection=full_collection
                    )
                    if mode_label == '新账号全量':
                        logger.info(f'检测到新账号 {user_id}，分组: {group_name} | 用户名: {name}，自动执行全量采集')
                    elif mode_label == '登出恢复全量':
                        logger.info(f'账号 {user_id} 已恢复登录，执行登出恢复全量采集')
                    elif mode_label == '手动全量':
                        logger.info(f'账号 {user_id} 按手动全量模式执行采集')

                    try:
                        append_full_recovery_event_if_needed(
                            status_mgr=status_mgr,
                            user_id=user_id,
                            platform=platform,
                            group_name=group_name,
                            batch_id=batch_id,
                            mode_label=mode_label,
                            event_type='full_recovery_started',
                            detail={'mode_label': mode_label},
                        )
                        crawler = LiveCrawler(platform=platform, browser_id=user_id,
                                             full_collection=account_full_collection, group_name=group_name,
                                             batch_id=batch_id, crawl_type=crawl_type)
                        result = crawler.start_crawl()
                        platform_results.append(result)

                        # 检测采集过程中是否触发了登出即时恢复
                        if result.get('login_recovery') and not account_full_collection:
                            mode_label = '登出即时恢复全量'
                            account_full_collection = True
                            logger.info(f'账号 {user_id} 在采集过程中触发了登出即时恢复全量')
                            # 补写 full_recovery_started 事件
                            append_full_recovery_event_if_needed(
                                status_mgr=status_mgr,
                                user_id=user_id,
                                platform=platform,
                                group_name=group_name,
                                batch_id=batch_id,
                                mode_label=mode_label,
                                event_type='full_recovery_started',
                                detail={'mode_label': mode_label},
                            )

                        status = '✓' if result.get('success') else '✗'
                        logger.info(f'{status} [{mode_label}] 采集结果: 页面数={result.get("pages_visited", 0)}, '
                                   f'API数={result.get("apis_collected", 0)}, 数据数={result.get("data_sent", 0)}')

                        if result.get('error'):
                            logger.error(f'  错误: {result["error"]}')

                        # 全量采集成功后标记到追踪文件
                        if account_full_collection and result.get('success'):
                            tracker.mark_full_collected(platform, user_id)
                        append_full_recovery_event_if_needed(
                            status_mgr=status_mgr,
                            user_id=user_id,
                            platform=platform,
                            group_name=group_name,
                            batch_id=batch_id,
                            mode_label=mode_label,
                            event_type='full_recovery_succeeded' if result.get('success') else 'full_recovery_failed',
                            detail={
                                'mode_label': mode_label,
                                'success': bool(result.get('success')),
                                'error': result.get('error'),
                                'login_status': result.get('login_status', True),
                            },
                        )

                    except Exception as e:
                        logger.exception(f'✗ 账号 {user_id} 采集异常: {e}')
                        result = {'success': False, 'error': str(e), 'login_status': True}
                        platform_results.append(result)
                        append_full_recovery_event_if_needed(
                            status_mgr=status_mgr,
                            user_id=user_id,
                            platform=platform,
                            group_name=group_name,
                            batch_id=batch_id,
                            mode_label=mode_label,
                            event_type='full_recovery_failed',
                            detail={
                                'mode_label': mode_label,
                                'success': False,
                                'error': str(e),
                                'login_status': True,
                            },
                        )

            # 统计平台采集结果
            platform_success = sum(1 for r in platform_results if r.get('success', False))
            all_results[platform] = {
                'total': len(accounts),
                'success': platform_success
            }

            total_accounts += len(accounts)
            total_success += platform_success

            logger.info(f'\n{platform.upper()} 采集完成: {platform_success}/{len(accounts)} 成功')
    
    # 全局采集总结
    logger.info('\n' + '='*60)
    logger.info('📊 全局采集统计:')
    logger.info('='*60)
    for platform, result in all_results.items():
        status = '✓' if result['success'] == result['total'] else '✗'
        logger.info(f'{status} {platform.upper()}: {result["success"]}/{result["total"]}')
    
    logger.info('='*60)
    logger.info(f'总计: {total_success}/{total_accounts} 账号采集成功')
    logger.info('='*60)

    # 采集监控：记录批次结束
    monitor.finish_batch(batch_id)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='直播数据采集系统')
    
    parser.add_argument(
        '--mode',
        choices=['scheduler', 'once', 'full'],
        default='scheduler',
        help='运行模式：scheduler=定时任务, once=手动执行一次(增量), full=全量采集'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        metavar='N',
        help='并发进程数（默认1=串行，>=2时开启并发，仅 --mode full 生效）'
    )

    parser.add_argument(
        '--crawl-type',
        choices=['realtime', 'history'],
        default='history',
        help='采集类型（仅 HTTP 爬虫使用）：realtime=实时采集, history=历史采集'
    )

    parser.add_argument(
        '--platform',
        type=str,
        action='append',
        dest='platforms',
        help='指定要采集的平台（可多次使用，如 --platform tk --platform shopee），不指定则采集所有平台'
    )

    args = parser.parse_args()
    
    # 显示配置信息
    logger.info(f'Kafka状态: {"启用" if Settings.KAFKA_CONFIG["enabled"] else "禁用"}')
    logger.info(f'定时任务状态: {"启用" if Settings.SCHEDULER_CONFIG["enabled"] else "禁用"}')
    logger.info(f'告警状态: {"启用" if Settings.ALERT_CONFIG["enabled"] else "禁用"}')
    
    # 根据模式执行
    if args.mode == 'scheduler':
        run_scheduler()
    elif args.mode == 'full':
        run_once(full_collection=True, workers=args.workers, crawl_type=args.crawl_type, platforms=args.platforms)
    else:
        run_once(crawl_type=args.crawl_type, platforms=args.platforms)


if __name__ == '__main__':
    main()
