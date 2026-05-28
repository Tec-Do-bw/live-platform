"""TikTok 上下文刷新器。

职责：
- 启动 AdsPower 浏览器
- 导航到 Livestream analytics 页面
- 等待 live/list API 触发
- 提取 cookies、query_string、creator_id、user_agent、region
- 写入 account_credentials 表
"""

from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlparse

from utils.adspower_client import AdsPowerApiError, AdsPowerRateLimitError, get_adspower_client
from utils.adspower_proxy import build_proxy_url
from utils.credentials import save_credentials
from utils.logger import logger
from webdriver.browserapi import BrowserApi


ANALYTICS_URL = "https://shop.tiktok.com/streamer/compass/livestream-analytics/view"
ANALYTICS_NAV_SELECTOR = 'xpath://span[contains(text(), "Livestream analytics")]'
API_WAIT_TIMEOUT = 15


class TikTokRefresher:
    """TikTok 凭据刷新器。"""

    def refresh_account(self, account_id: str, group_name: str = "", proxy: str = "") -> bool:
        """刷新单个账号上下文并写入 account_credentials。"""
        browser_api = BrowserApi()
        driver = None
        profile_group_name, profile_proxy = self._load_profile_context(account_id)
        group_name = group_name or profile_group_name
        proxy = proxy or profile_proxy

        try:
            driver = browser_api.get_driver(account_id)
            tab = driver.latest_tab
            browser_api.listen_api(tab, ["api/v2/insights/creator/live/list"], timeout=API_WAIT_TIMEOUT)

            if not self._navigate_to_analytics(tab):
                logger.error(f"[{account_id}] 无法导航到 Livestream analytics 页面")
                return False

            api_data = browser_api.get_listened_data(
                tab,
                ["api/v2/insights/creator/live/list"],
                wait_time=API_WAIT_TIMEOUT,
                count=1,
            )
            if not api_data:
                logger.error(f"[{account_id}] 未拦截到 live/list API，超时={API_WAIT_TIMEOUT}s")
                return False

            context = self._extract_context(browser_api, tab, api_data[0])
            save_credentials(
                account_id=account_id,
                platform="tiktok",
                group_name=group_name,
                token=json.dumps(context["cookies"], ensure_ascii=False),
                region=context["region"],
                proxy=proxy,
                ext_json={
                    "query_string": context["query_string"],
                    "creator_id": context["creator_id"],
                    "user_agent": context["user_agent"],
                },
            )
            logger.info(
                f"[{account_id}] TikTok 上下文刷新成功 "
                f"region={context['region']} creator_id={context['creator_id']}"
            )
            return True

        except Exception as e:
            logger.exception(f"[{account_id}] TikTok 上下文刷新失败: {e}")
            return False
        finally:
            if driver:
                browser_api.close_driver(driver)

    def _load_profile_context(self, account_id: str) -> tuple[str, str]:
        """从 AdsPower profile 获取 group_name 和 proxy。"""
        try:
            client = get_adspower_client()
            data = client.post("/api/v2/browser-profile/list", json={"profile_id": [account_id]})
            profiles = data.get("data", {}).get("list", [])
            if not profiles:
                logger.warning(f"[{account_id}] AdsPower 未返回 profile，group_name/proxy 留空")
                return "", ""

            profile = profiles[0]
            group_name = (
                profile.get("group_name")
                or profile.get("group", {}).get("group_name")
                or profile.get("groupName")
                or ""
            )
            proxy = build_proxy_url(profile.get("user_proxy_config", {}) or {}) or ""
            return str(group_name or ""), proxy
        except (AdsPowerRateLimitError, AdsPowerApiError) as e:
            logger.warning(f"[{account_id}] 查询 AdsPower profile 失败: {e}")
            return "", ""
        except Exception as e:
            logger.warning(f"[{account_id}] 查询 AdsPower profile 异常: {e}")
            return "", ""

    def _navigate_to_analytics(self, tab) -> bool:
        """try URL → fallback 点击导航到 Livestream analytics。"""
        try:
            tab.get(ANALYTICS_URL)
            time.sleep(3)
            if "livestream-analytics" in getattr(tab, "url", ""):
                return True
        except Exception as e:
            logger.warning(f"TikTok analytics URL 导航失败: {e}")

        try:
            ele = tab.ele(ANALYTICS_NAV_SELECTOR, timeout=5)
            if not ele:
                return False
            ele.click()
            time.sleep(3)
            return "livestream-analytics" in getattr(tab, "url", "")
        except Exception as e:
            logger.warning(f"TikTok analytics fallback 点击失败: {e}")
            return False

    def _extract_context(self, browser_api: BrowserApi, tab, api_item: dict) -> dict:
        """从 live/list 拦截数据提取 HTTP 采集上下文。"""
        parsed = urlparse(api_item.get("url", ""))
        request_headers = api_item.get("headers", {}) or {}
        response_body = api_item.get("response", "{}")
        cookies = browser_api.get_cookies(tab)

        qs_params = parse_qs(parsed.query)
        region = (
            qs_params.get("carrier_region", [""])[0]
            or qs_params.get("region", [""])[0]
            or qs_params.get("store_region", [""])[0]
        ).upper()

        creator_id = ""
        try:
            response_data = json.loads(response_body)
            segments = response_data.get("data", {}).get("segments", [])
            if segments:
                creator_ids = segments[0].get("filter", {}).get("creator_id", [])
                if creator_ids:
                    creator_id = str(creator_ids[0])
        except (TypeError, json.JSONDecodeError, IndexError, KeyError):
            creator_id = ""

        return {
            "cookies": cookies,
            "query_string": parsed.query,
            "creator_id": creator_id,
            "user_agent": request_headers.get("user-agent") or request_headers.get("User-Agent") or "",
            "region": region,
        }
