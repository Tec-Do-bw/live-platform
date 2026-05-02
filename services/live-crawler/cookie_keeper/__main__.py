"""Cookie 养号服务入口

启动方式：cd live_dp && python -m cookie_keeper
"""

from .keeper import CookieKeeperScheduler
from utils.logger import logger


def main():
    """启动 Cookie 养号调度器"""
    logger.info('正在启动 Cookie 养号服务...')

    scheduler = CookieKeeperScheduler()
    scheduler.start()

    logger.info('Cookie 养号服务已启动，按 Ctrl+C 退出')

    try:
        # 保持进程运行
        input()
    except KeyboardInterrupt:
        logger.info('收到退出信号，正在关闭服务...')


if __name__ == '__main__':
    main()
