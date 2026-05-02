"""Lazada 账号养号操作

在登录完成后执行一系列模拟真实用户行为的操作，保持账号活跃度。
"""
import time
import random
from utils.logger import logger


class AccountNurturing:
    """账号养号操作类"""

    @staticmethod
    def nurture_sellercenter(tab, country_domain: str = 'co.th') -> bool:
        """Sellercenter 端口养号操作

        模拟真实卖家行为：浏览首页、商品管理、订单管理、学习资源等

        Args:
            tab: DrissionPage tab 对象
            country_domain: Lazada 国家域名后缀，如 co.th、com.my

        Returns:
            bool: 养号是否成功
        """
        try:
            logger.info('开始 Sellercenter 养号操作...')

            # 1. 停留在首页，模拟查看通知和待办事项
            logger.info('浏览首页，查看通知...')
            time.sleep(random.uniform(2, 4))
            AccountNurturing.random_scroll(tab, times=random.randint(2, 4))

            # 2. 访问商品管理页面
            logger.info('访问商品管理页面...')
            try:
                tab.eles('xpath://*[@class="parent-label"]')[0].click()
                tab.ele('xpath://*[@title="商品管理"]').click()
                time.sleep(random.uniform(3, 5))
                AccountNurturing.random_scroll(tab, times=random.randint(3, 5))
            except:
                logger.debug('未找到商品管理菜单，跳过')




            # 4. 访问营销工具页面
            logger.info('访问营销工具页面...')
            tab.get(f'https://sellercenter.lazada.{country_domain}/ba/dashboard')
            time.sleep(random.uniform(2, 4))
            AccountNurturing.random_scroll(tab, times=random.randint(10, 30))
            # 查看实时大屏
            tab.ele('xpath://*[@class="NbE6JF"]').click()

            # 6. 返回首页
            logger.info('返回首页...')
            tab.get(f'https://sellercenter.lazada.{country_domain}/')
            time.sleep(random.uniform(2, 3))
            AccountNurturing.random_scroll(tab, times=random.randint(1, 3))

            logger.info('✓ Sellercenter 养号操作完成')
            return True

        except Exception as e:
            logger.error(f'Sellercenter 养号操作失败: {e}')
            return False

    @staticmethod
    def nurture_live(tab, country_domain: str = 'co.th') -> bool:
        """Live 端口养号操作

        模拟真实主播行为：浏览直播列表、查看 Dashboard、查看历史直播等

        Args:
            tab: DrissionPage tab 对象
            country_domain: Lazada 国家域名后缀，如 co.th、com.my

        Returns:
            bool: 养号是否成功
        """
        try:
            logger.info('开始 Live 养号操作...')

            # 1. 停留在直播列表页面
            logger.info('浏览直播列表...')
            time.sleep(random.uniform(2, 4))
            AccountNurturing.random_scroll(tab, times=random.randint(2, 4))

            # 2. 访问 Dashboard
            logger.info('访问 LazLive Dashboard...')
            tab.get(f'https://live.lazada.{country_domain}/app/dashboard')
            time.sleep(random.uniform(3, 5))
            AccountNurturing.random_scroll(tab, times=random.randint(3, 5))

            # 3. 查看历史直播（切换到历史标签）
            logger.info('查看历史直播...')
            tab.get(f'https://live.lazada.{country_domain}/app/live-list')
            time.sleep(random.uniform(2, 3))
            AccountNurturing.random_scroll(tab, times=random.randint(2, 4))

            # 模拟点击"历史"标签（如果页面有的话）
            try:
                # 尝试点击历史标签
                history_tab = tab.ele('text:历史', timeout=2)
                if history_tab:
                    history_tab.click()
                    time.sleep(random.uniform(2, 4))
                    AccountNurturing.random_scroll(tab, times=random.randint(2, 4))
            except:
                logger.debug('未找到历史标签，跳过')

            # 4. 返回直播列表首页
            logger.info('返回直播列表首页...')
            tab.get(f'https://live.lazada.{country_domain}/app/live-list')
            time.sleep(random.uniform(2, 3))
            AccountNurturing.random_scroll(tab, times=random.randint(1, 3))

            logger.info('✓ Live 养号操作完成')
            return True

        except Exception as e:
            logger.error(f'Live 养号操作失败: {e}')
            return False

    @staticmethod
    def random_scroll(tab, times: int = 3):
        """随机滚动页面，模拟真实用户浏览行为

        Args:
            tab: DrissionPage tab 对象
            times: 滚动次数
        """
        try:
            for i in range(times):
                # 随机滚动距离（200-800px）
                scroll_distance = random.randint(200, 800)
                tab.run_js(f'window.scrollBy(0, {scroll_distance})')
                time.sleep(random.uniform(0.5, 1.5))

            # 滚动回顶部
            tab.run_js('window.scrollTo(0, 0)')
            time.sleep(random.uniform(0.5, 1))
        except Exception as e:
            logger.debug(f'滚动操作失败: {e}')
