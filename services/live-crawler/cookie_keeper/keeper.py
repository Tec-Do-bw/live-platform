"""Cookie 养号调度器

负责定时刷新所有 Lazada 账号的 Cookie，并记录登录态事件。
"""

import sys
from pathlib import Path

# 添加 live_dp 根目录到路径，确保直接运行本文件时也能正确导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from services import cookie_manager
from services.login_callback import send_login_callback
from utils.logger import logger
from webdriver.browserapi import BrowserApi
from cookie_keeper.browser_refresher import BrowserRefresher


class CookieKeeperScheduler:
    """Cookie 养号调度器

    职责约束：
    - 是 HTTP 采集体系中唯一负责登录态管理的模块
    - 必须在 Cookie 刷新后调用 send_login_callback 记录登录态事件
    - 采集器不发送 send_login_callback，完全依赖本服务记录的事件
    """

    def __init__(self):
        """初始化调度器、cookie_manager 模块、BrowserRefresher"""
        self.scheduler = BackgroundScheduler()
        self.refresher = BrowserRefresher()

    def start(self):
        """启动定时任务（每天 3 次：22:00、02:00 和 14:00）"""
        self.scheduler.add_job(
            self.refresh_all_accounts,
            CronTrigger(hour='22,2,14', minute='0'),
            id='cookie_refresh',
        )
        self.scheduler.start()
        logger.info('Cookie 养号调度器启动成功，任务已注册（每天 22:00、02:00 和 14:00 执行）')

    def refresh_all_accounts(self):
        """刷新所有 Lazada 账号的 Cookie（两个端口）

        从 AdsPower 动态获取 Lazada 用户组的账号列表，模仿 main.py 的实现方式。
        """
        logger.info('开始刷新 Lazada 账号 Cookie...')

        # 从 AdsPower 动态获取 Lazada 分组的账号列表
        logger.info('🔄 动态筛选分组（按 platform=lazada）')
        group_ids = BrowserApi.get_group_ids_by_platform('lazada')

        if not group_ids:
            logger.warning('⊗ 未找到 Lazada 匹配的分组，跳过刷新')
            return

        accounts = BrowserApi.get_user_ids_from_group_ids(group_ids)

        if not accounts:
            logger.warning('⊗ 未获取到 Lazada 账号，跳过刷新')
            return

        logger.info(f'📱 获取到 {len(accounts)} 个 Lazada 账号，开始刷新')

        for idx, account in enumerate(accounts, 1):
            account_id = account.get('user_id', '')
            group_name = account.get('group_name', '')
            name = account.get('name', '')

            logger.info(f'\n[{idx}/{len(accounts)}] 账号: {account_id} | 分组: {group_name} | 用户名: {name}')

            # 获取账密信息（从 sellercenter 端口的 extra 字段）
            credentials = cookie_manager.get_account_credentials(
                account_id, 'lazada', endpoint='sellercenter'
            )
            if not credentials:
                logger.warning(f'账号 {account_id} 无账密信息，跳过自动登录')
                continue

            # 一次浏览器会话刷新两个端口
            results = self.refresher.refresh_account(account_id, credentials, group_name)

            # 保存 Cookie 到数据库并记录登录回调
            try:
                failed_endpoints = []
                for endpoint, cookies in results.items():
                    if cookies:
                        cookie_manager.save_cookies(
                            account_id, 'lazada', endpoint=endpoint, cookies=cookies
                        )
                        logger.info(f'✓ 刷新成功: {account_id}/{endpoint}')
                    else:
                        failed_endpoints.append(endpoint)
                        logger.warning(f'✗ 刷新失败: {account_id}/{endpoint}')

                # 只发送一次登录回调（两个端口都成功才算成功）
                if not failed_endpoints:
                    send_login_callback(
                        browser_id=account_id,
                        platform='lazada',
                        group_name=group_name,
                        login_status='success',
                        reason='cookie_refreshed'
                    )
                else:
                    send_login_callback(
                        browser_id=account_id,
                        platform='lazada',
                        group_name=group_name,
                        login_status='logout',
                        reason=f'cookie_refresh_failed: {", ".join(failed_endpoints)}'
                    )
            except Exception as e:
                logger.error(f'处理刷新结果异常: {account_id}: {e}')

        logger.info(f'\n✓ Lazada 账号 Cookie 刷新完成，共处理 {len(accounts)} 个账号')


if __name__ == '__main__':
    # 测试单个账号
    scheduler = CookieKeeperScheduler()

    if len(sys.argv) > 1:
        # 命令行传入账号 ID：python cookie_keeper/keeper.py k1bhj6l4
        test_account_id = sys.argv[1]
        logger.info(f'测试模式：仅刷新账号 {test_account_id}')

        # 获取账密和分组信息
        credentials = cookie_manager.get_account_credentials(
            test_account_id, 'lazada', endpoint='sellercenter'
        )
        if not credentials:
            logger.error(f'账号 {test_account_id} 无账密信息')
            sys.exit(1)

        # 从 AdsPower 获取分组名（用于国家域名识别）
        try:
            from webdriver.browserapi import BrowserApi
            group_ids = BrowserApi.get_group_ids_by_platform('lazada')
            accounts = BrowserApi.get_user_ids_from_group_ids(group_ids)
            test_account = next((a for a in accounts if a.get('user_id') == test_account_id), None)
            group_name = test_account.get('group_name', '') if test_account else ''
        except Exception as e:
            logger.warning(f'获取分组名失败: {e}，使用默认国家域名')
            group_name = ''

        # 刷新两个端口
        results = scheduler.refresher.refresh_account(test_account_id, credentials, group_name)

        # 保存 Cookie 并发送回调（复用生产逻辑）
        try:
            failed_endpoints = []
            for endpoint, cookies in results.items():
                if cookies:
                    cookie_manager.save_cookies(
                        test_account_id, 'lazada', endpoint=endpoint, cookies=cookies
                    )
                    logger.info(f'✓ 刷新成功: {test_account_id}/{endpoint}')
                else:
                    failed_endpoints.append(endpoint)
                    logger.warning(f'✗ 刷新失败: {test_account_id}/{endpoint}')

            # 只发送一次登录回调
            if not failed_endpoints:
                send_login_callback(
                    browser_id=test_account_id,
                    platform='lazada',
                    group_name=group_name,
                    login_status='success',
                    reason='cookie_refreshed'
                )
            else:
                send_login_callback(
                    browser_id=test_account_id,
                    platform='lazada',
                    group_name=group_name,
                    login_status='logout',
                    reason=f'cookie_refresh_failed: {", ".join(failed_endpoints)}'
                )
        except Exception as e:
            logger.error(f'处理刷新结果异常: {test_account_id}: {e}')
    else:
        # 正常模式：刷新所有账号
        scheduler.refresh_all_accounts()