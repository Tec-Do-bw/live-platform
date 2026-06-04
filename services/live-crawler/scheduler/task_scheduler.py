#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/11/12
# @Author     : XBW
# @File       : task_scheduler.py
# @Description: 定时任务调度器

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime

from core.config import Settings
from core.collection_tracker import CollectionTracker
from core.collection_mode import resolve_collection_mode
from crawlers.browser.live_crawler import LiveCrawler
from utils.logger import Logings, logger
from utils.alert import AlertManager
from webdriver.browserapi import BrowserApi
from monitor import get_monitor
from monitor.login_status_manager import LoginStatusManager
from monitor.recovery_events import append_full_recovery_event_if_needed


# 调度专用：国家关键词 → UTC 时区分组映射
COUNTRY_TIMEZONE_GROUP_MAP = {
    "日本": "UTC+9",
    "中国": "UTC+8", "CN": "UTC+8",
    "马来": "UTC+8", "新加坡": "UTC+8", "菲律宾": "UTC+8",
    "印尼": "UTC+7", "泰国": "UTC+7", "越南": "UTC+7",
    "巴西": "UTC-3",
    "墨西哥": "UTC-6",
    "美国": "UTC-8",
}
DEFAULT_TIMEZONE_GROUP = "UTC+8"


class TaskScheduler:
    """定时任务调度器
    
    负责管理和调度直播数据采集任务
    """
    
    def __init__(self):
        """初始化调度器"""
        # 配置任务默认参数，防止misfire警告
        job_defaults = {
            'misfire_grace_time': 60,  # 允许60秒内的延迟仍然执行
            'coalesce': True,          # 合并错过的任务，只执行一次
            'max_instances': 1         # 同一任务最多1个实例运行
        }
        self.scheduler = BackgroundScheduler(job_defaults=job_defaults)
        self.config = Settings.SCHEDULER_CONFIG
        self.alert_manager = AlertManager()
        logger.info('定时任务调度器初始化完成')

    def _resolve_timezone_group(self, group_name: str) -> str:
        """根据分组名解析 UTC 时区分组。"""
        matched = [(kw, tz) for kw, tz in COUNTRY_TIMEZONE_GROUP_MAP.items() if kw in group_name]
        if len(matched) > 1:
            logger.warning(f'group_name "{group_name}" 匹配多个时区分组: {matched}，使用第一个: {matched[0][1]}')
        if matched:
            return matched[0][1]
        logger.warning(f'group_name "{group_name}" 未匹配时区分组，默认归入 {DEFAULT_TIMEZONE_GROUP}')
        return DEFAULT_TIMEZONE_GROUP

    def _filter_accounts_by_timezone(self, accounts: list, timezone_group: str | None) -> list:
        """按时区分组过滤账号列表。"""
        if not timezone_group:
            return accounts

        filtered_accounts = []
        for account in accounts:
            group_name = account.get('group_name', '') if isinstance(account, dict) else ''
            account_timezone_group = self._resolve_timezone_group(group_name) if group_name else DEFAULT_TIMEZONE_GROUP
            if account_timezone_group == timezone_group:
                filtered_accounts.append(account)

        logger.info(f'时区分组过滤: {timezone_group} | 原始账号数={len(accounts)} | 过滤后账号数={len(filtered_accounts)}')
        return filtered_accounts

    def add_crawl_task(self) -> None:
        """添加采集任务到调度器（支持 Lazada 双模式调度）"""
        if not self.config.get('enabled', True):
            logger.warning('定时任务已禁用')
            return

        # 获取cron配置
        cron_config = self.config.get('cron_config', [])

        # 如果是旧格式（dict），转换为列表
        if isinstance(cron_config, dict):
            cron_config = [cron_config]

        if not cron_config:
            logger.warning('未配置定时任务时间')
            return

        # 添加通用平台的定时任务
        for idx, time_config in enumerate(cron_config, 1):
            hour = str(time_config.get('hour', '4'))
            minute = str(time_config.get('minute', '0'))
            tz_group = time_config.get('timezone_group')

            # 创建cron触发器
            trigger = CronTrigger(hour=hour, minute=minute)

            # 添加任务（job_id 包含时区分组，避免同时刻不同分组冲突）
            tz_label = tz_group or 'ALL'
            task_id = f'live_crawl_task_{idx}_{tz_label}'
            self.scheduler.add_job(
                func=self.execute_crawl_task,
                trigger=trigger,
                id=task_id,
                name=f'直播数据采集任务 {idx} [{tz_label}]',
                replace_existing=True,
                kwargs={'timezone_group': tz_group},
            )

            logger.info(f'定时任务 {idx} 已添加：每天 {hour}:{minute} 执行 [时区分组: {tz_label}]')

        # 为 Lazada 平台添加实时采集任务（历史采集遵循通用时区分组调度）
        platform_configs = Settings.PLATFORM_CONFIG
        if 'lazada' in platform_configs:
            lazada_config = platform_configs['lazada']
            realtime_interval = lazada_config.get('realtime_interval_minutes', 10)
            trigger = IntervalTrigger(minutes=realtime_interval)
            self.scheduler.add_job(
                func=self.execute_crawl_task,
                trigger=trigger,
                id='lazada_realtime_task',
                name='Lazada 实时采集任务',
                replace_existing=True,
                kwargs={'crawl_type': 'realtime', 'platform_filter': 'lazada'}
            )
            logger.info(f'Lazada 实时采集任务已添加：每 {realtime_interval} 分钟执行一次')

    def execute_crawl_task(self, crawl_type: str = 'history', platform_filter: str | None = None, timezone_group: str | None = None) -> None:
        """执行采集任务

        Args:
            crawl_type: 采集类型（'realtime' 或 'history'）
            platform_filter: 平台过滤器（仅采集指定平台，None 表示采集所有平台）
            timezone_group: 时区分组过滤（None 表示不过滤）
        """
        ctx = {'crawl_type': crawl_type}
        if platform_filter:
            ctx['platform'] = platform_filter
        with logger.contextualize(**ctx):
            self._do_execute_crawl_task(crawl_type, platform_filter, timezone_group)

    def _do_execute_crawl_task(self, crawl_type: str, platform_filter: str | None, timezone_group: str | None) -> None:
        tz_label = timezone_group or 'ALL'
        logger.info('='*60)
        logger.info(f'开始执行定时采集任务 - {datetime.now().isoformat()} (crawl_type={crawl_type}, platform_filter={platform_filter}) | 时区分组: {tz_label}')
        logger.info('='*60)

        # 采集监控：生成批次ID并记录开始
        base_batch_id = datetime.now().strftime('%Y-%m-%d_%H:%M')
        batch_id = f'{base_batch_id}_{tz_label}' if timezone_group else base_batch_id
        monitor = get_monitor()
        monitor.start_batch(batch_id, 'scheduler')
        
        # 获取所有平台配置
        platform_configs = Settings.PLATFORM_CONFIG
        
        if not platform_configs:
            logger.error('未找到任何平台配置，无法执行采集任务')
            self.alert_manager.send_alert(
                alert_type='crawl_failed',
                title='采集任务失败',
                content='未找到平台配置，请检查配置文件'
            )
            return
        
        # 采集追踪器（在平台循环外创建一次）
        tracker = CollectionTracker()
        status_mgr = LoginStatusManager(monitor.conn)

        # 统计信息
        total_accounts = 0
        success_count = 0
        failed_count = 0
        login_failed_accounts = []
        platform_results = {}
        
        # 遍历所有平台
        for platform, config in platform_configs.items():
            # 平台过滤：如果指定了 platform_filter，只采集该平台
            if platform_filter and platform != platform_filter:
                continue

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
            
            # 按时区分组过滤账号
            accounts = self._filter_accounts_by_timezone(accounts, timezone_group)
            if not accounts:
                logger.info(f'⊗ 平台 {platform} 在时区分组 {tz_label} 中无匹配账号，跳过')
                continue

            logger.info(f'\n📱 平台: {platform.upper()} | 账号数: {len(accounts)} | 时区分组: {tz_label}')
            logger.info('='*60)

            platform_success = 0
            platform_failed = 0

            # 依次采集该平台的所有账号
            for idx, account in enumerate(accounts, 1):
                total_accounts += 1
                # 兼容 dict（动态获取）和 str（配置文件直接指定）两种格式
                if isinstance(account, dict):
                    user_id = account.get('user_id', '')
                    group_name = account.get('group_name', '')
                    name = account.get('name', '')
                    logger.info(f'[{idx}/{len(accounts)}] 账号: {user_id} | 分组: {group_name} | 用户名: {name}')
                else:
                    user_id = account
                    group_name = ''
                    name = ''
                    logger.info(f'[{idx}/{len(accounts)}] 账号: {user_id}')

                # 新账号全量 > 登出恢复全量 > 增量
                account_full_collection, mode_label = resolve_collection_mode(
                    platform, user_id, tracker, status_mgr
                )
                if mode_label == '新账号全量':
                    logger.info(f'检测到新账号 {user_id}，分组: {group_name} | 用户名: {name}，自动执行全量采集')
                elif mode_label == '登出恢复全量':
                    logger.info(f'账号 {user_id} 已恢复登录，执行登出恢复全量采集')

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
                    # 创建爬虫实例并执行采集（传递 crawl_type 参数）
                    crawler = LiveCrawler(platform=platform, browser_id=user_id,
                                         full_collection=account_full_collection, group_name=group_name,
                                         batch_id=batch_id, crawl_type=crawl_type)
                    result = crawler.start_crawl()

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

                    # 检查采集结果
                    if result.get('success'):
                        success_count += 1
                        platform_success += 1
                        status = '✓'
                        logger.info(f'{status} [{mode_label}] 采集成功')

                        # 全量采集成功后标记到追踪文件
                        if account_full_collection:
                            tracker.mark_full_collected(platform, user_id)
                    else:
                        failed_count += 1
                        platform_failed += 1
                        status = '✗'
                        logger.error(f'{status} 采集失败: {result.get("error")}')

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

                    # 检查登录状态
                    if not result.get('login_status', True):
                        login_failed_accounts.append(f'{platform}:{user_id}')
                        logger.warning(f'账号 {user_id} 已登出')

                except Exception as e:
                    failed_count += 1
                    platform_failed += 1
                    logger.exception(f'✗ 账号 {user_id} 采集异常: {e}')
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
            
            # 记录平台结果
            platform_results[platform] = {
                'total': len(accounts),
                'success': platform_success,
                'failed': platform_failed
            }
            logger.info(f'\n{platform.upper()} 采集完成: {platform_success}/{len(accounts)} 成功')
        
        # 汇总结果
        logger.info('\n' + '='*60)
        logger.info(f'📊 定时采集任务完成 | 时区分组: {tz_label}')
        logger.info('='*60)
        for platform, result in platform_results.items():
            status = '✓' if result['success'] == result['total'] else '✗'
            logger.info(f'{status} {platform.upper()}: {result["success"]}/{result["total"]} 成功')
        
        logger.info('='*60)
        logger.info(f'总计: {success_count}/{total_accounts} 账号采集成功, {failed_count} 账号失败')
        
        if login_failed_accounts:
            logger.warning(f'登出账号: {", ".join(login_failed_accounts)}')
        logger.info('='*60)
        
        # 发送告警
        if login_failed_accounts:
            self.alert_manager.send_alert(
                alert_type='login_failed',
                title='账号登出告警',
                content=f'以下账号已登出，请及时处理：\n{", ".join(login_failed_accounts)}'
            )
        
        if failed_count > 0:
            self.alert_manager.send_alert(
                alert_type='crawl_failed',
                title='采集任务部分失败',
                content=f'总账号数: {total_accounts}, 失败: {failed_count}'
            )

        # 采集监控：记录批次结束
        monitor.finish_batch(batch_id)

    def execute_once(self) -> None:
        """手动执行一次采集任务（用于测试）"""
        logger.info('手动触发采集任务')
        self.execute_crawl_task()
    
    def start(self) -> None:
        """启动调度器"""
        logger.info('启动定时任务调度器...')
        
        # 添加采集任务
        self.add_crawl_task()
        
        # 显示所有任务
        jobs = self.scheduler.get_jobs()
        if jobs:
            logger.info(f'已添加 {len(jobs)} 个定时任务：')
            for job in jobs:
                try:
                    logger.info(f'  - {job.name} (ID: {job.id}), 下次运行: {job.next_run_time}')
                except Exception:
                    logger.info(f'  - {job.name} (ID: {job.id})')
        else:
            logger.info('未添加任何定时任务')

        # 启动调度器
        self.scheduler.start()
    
    def shutdown(self) -> None:
        """关闭调度器"""
        logger.info('正在关闭调度器...')
        self.scheduler.shutdown(wait=True)
        logger.info('调度器已关闭')


if __name__ == '__main__':
    # 测试代码
    Logings.configure('scheduler')
    scheduler = TaskScheduler()
    
    # 手动执行一次
    scheduler.execute_once()
    
    # 或启动定时任务
    # scheduler.start()
