"""通过 AdsPower 浏览器自动登录并提取 Cookie

整体架构：
- refresh_account() 为入口方法，一次浏览器会话完成两个端口的登录+养号+Cookie提取
- 浏览器生命周期由本类管理：开一次浏览器，两个端口共用，最后关一次
"""
import time

from webdriver.browserapi import BrowserApi
from utils.logger import logger
from cookie_keeper.account_nurturing import AccountNurturing


class BrowserRefresher:
    """通过 AdsPower 浏览器自动登录并提取 Cookie"""

    # Lazada 国家域名映射（分组名关键词 → 域名后缀）
    LAZADA_COUNTRY_MAP = {
        "泰国": "co.th",
        "马来": "com.my",
        "新加坡": "sg",
        "印尼": "co.id",
        "菲律宾": "com.ph",
        "越南": "vn",
    }

    def refresh_account(self, account_id: str, credentials: dict, group_name: str = '') -> dict[str, dict | None]:
        """一次浏览器会话刷新两个端口的 Cookie

        Args:
            account_id: AdsPower profile_id
            credentials: {"username": "xxx", "password": "xxx"}
            group_name: AdsPower 分组名，用于识别国家域名

        Returns:
            {'sellercenter': cookie_dict | None, 'live': cookie_dict | None}
        """
        # 根据分组名自动识别国家域名，默认泰国
        self.country_domain = next(
            (v for k, v in self.LAZADA_COUNTRY_MAP.items() if k in group_name),
            "co.th"
        )
        logger.info(f'Lazada 国家域名: {self.country_domain}（来自分组: {group_name}）')

        result = {'sellercenter': None, 'live': None}
        driver = None
        browser_api = BrowserApi()

        try:
            driver = browser_api.get_driver(account_id)
            tab = driver.latest_tab

            # 先刷新 sellercenter
            try:
                result['sellercenter'] = self._login_sellercenter(tab, credentials)
            except Exception as e:
                logger.error(f'sellercenter 登录失败 {account_id}: {e}')

            # 同一个浏览器继续刷新 live
            try:
                result['live'] = self._login_live(tab, credentials)
            except Exception as e:
                logger.error(f'live 登录失败 {account_id}: {e}')

        except Exception as e:
            logger.error(f'浏览器启动失败 {account_id}: {e}')
        finally:
            if driver:
                browser_api.close_driver(driver)

        return result

    def _extract_cookies(self, tab) -> dict:
        """从 DrissionPage tab 提取 Cookie"""
        cookies = tab.cookies()
        return {c['name']: c['value'] for c in cookies}

    def _login_sellercenter(self, tab, credentials: dict) -> dict | None:
        """sellercenter 端口自动登录

        预期流程：
            1. tab.get('https://sellercenter.lazada.{country}/')
            2. 检测是否需要登录（是否跳转到登录页）
            3. 如果需要登录：
               a. 定位账号输入框，填写 credentials['username']
               b. 定位密码输入框，填写 credentials['password']
               c. 点击登录按钮
               d. 等待登录完成
            4. 执行养号操作
            5. 提取并返回 Cookie
        """
        tab.get(f'https://sellercenter.lazada.{self.country_domain}/')
        time.sleep(1)
        now_url = tab.url
        if 'seller/login' in now_url:
            logger.info('需要登录')
            accout_ele = tab.ele('xpath://*[@id="account"]')
            if not accout_ele.value:
                accout_ele.input(credentials['username'])

            password_ele = tab.ele('xpath://*[@id="password"]')
            if not password_ele.value:
                password_ele.input(credentials['password'])
            time.sleep(3)
            logger.info('点击登录按钮...')
            tab.ele("xpath://button[contains(@class, 'login-button')]").click()
            time.sleep(3)
        else:
            logger.info('已登录状态')

        # 执行养号操作
        logger.info('开始执行 Sellercenter 养号操作...')
        AccountNurturing.nurture_sellercenter(tab, self.country_domain)

        cookies = self._extract_cookies(tab)
        return cookies if cookies else None

    def _login_live(self, tab, credentials: dict) -> dict | None:
        """live 端口自动登录

        预期流程：
            1. tab.get('https://live.lazada.{country}/app/live-list')
            2. 检测是否需要登录
            3. 如果需要登录：
               a. 填写相同的 credentials
               b. 提交登录
               c. 等待登录完成
            4. 执行养号操作
            5. 提取并返回 Cookie
        """
        tab.get(f'https://live.lazada.{self.country_domain}/')
        time.sleep(1)
        now_url = tab.url
        if 'app/login' in now_url:
            logger.info('需要登录')
            accout_ele = tab.ele('xpath://*[@id="account"]')
            if not accout_ele.value:
                accout_ele.input(credentials['username'])

            password_ele = tab.ele('xpath://*[@id="password"]')
            if not password_ele.value:
                password_ele.input(credentials['password'])
            time.sleep(3)
            logger.info('点击登录按钮...')
            tab.ele("xpath://button[contains(@class, 'login-button')]").click()
            time.sleep(3)
        else:
            logger.info('已登录状态')

        # 执行养号操作
        logger.info('开始执行 Live 养号操作...')
        AccountNurturing.nurture_live(tab, self.country_domain)

        cookies = self._extract_cookies(tab)
        return cookies if cookies else None