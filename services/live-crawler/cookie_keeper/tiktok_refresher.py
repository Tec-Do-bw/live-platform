"""TikTok 上下文刷新器。

职责：
- 启动 AdsPower 浏览器
- 导航到 Livestream analytics 页面 或 dashboard(跳转时兼容 fallback API)
- 等待指定 API 触发(live/list / feelgood/token / creator/post_limit / live_relation/popup)
- 首轮拦截超时 + HTTP 验证账号在线时,自动重试 1 次导航再抓
- 提取 cookies、query_string、creator_id、user_agent、region
- 登录态验证:用 curl_cffi + cookies 直连 account_info(绕开浏览器 tab,
  与实际 HTTP 采集口径一致),失败降级到 sessionid cookie 检查
- 验证通过后写入 account_credentials 表 + 发送登录回调
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from crawlers.http.tiktok.collector import fetch_account_info
from services.login_callback import send_login_callback
from utils.adspower_client import AdsPowerApiError, AdsPowerRateLimitError, get_adspower_client
from utils.adspower_proxy import build_proxy_url
from utils.credentials import Credentials, load_credentials, save_credentials
from utils.http_session import get_session
from utils.logger import logger
from webdriver.browserapi import BrowserApi


ANALYTICS_URL = "https://shop.tiktok.com/streamer/compass/livestream-analytics/view"
ANALYTICS_NAV_SELECTOR = 'xpath://span[contains(text(), "Livestream analytics")]'
# 兼容跳转到 dashboard 时的 fallback API(命中任一即可)
# 选取标准:dashboard 跳转后必触发 + URL 含 carrier_region/fp/device_id 等设备指纹参数
# 实测来源:CDP 直连指纹浏览器抓 dashboard?region=us 页面的 XHR/Fetch 请求(2026-06-04)
# 排除 live_relation/popup:URL 不含 carrier_region,会导致 region 字段为空,影响后续 HTTP 采集时区推断
FALLBACK_APIS = [
    "api/v2/insights/creator/live/list",
    "api/v1/affiliate/lux/feelgood/token",
    "api/v1/streamer_desktop/creator/post_limit",
]
API_WAIT_TIMEOUT = 15


class TikTokRefresher:
    """TikTok 凭据刷新器。"""

    def refresh_account(self, account_id: str, group_name: str = "", proxy: str = "") -> bool:
        """刷新单个账号上下文并写入 account_credentials。

        流程:
        1. 开浏览器 → 导航 analytics(或 dashboard)
        2. 拦截 API(live/list 或三个 fallback 之一)
        3. 提取上下文 → 登录态验证(API 探测 + Cookie 降级)
        4. 验证通过 → 写库 + 发 login_status=success 回调
        5. 验证失败 → 发 login_status=logout 回调
        """
        browser_api = BrowserApi()
        driver = None
        profile_group_name, profile_proxy = self._load_profile_context(account_id)
        group_name = group_name or profile_group_name
        proxy = proxy or profile_proxy

        try:
            driver = browser_api.get_driver(account_id)
            tab = driver.latest_tab
            # 监听主 API + 三个 fallback(跳转 dashboard 时兼容)
            listen_apis = FALLBACK_APIS
            browser_api.listen_api(tab, listen_apis, timeout=API_WAIT_TIMEOUT)

            tab.get(ANALYTICS_URL)
            time.sleep(3)

            api_data = browser_api.get_listened_data(
                tab,
                listen_apis,
                wait_time=API_WAIT_TIMEOUT,
                count=1,
            )
            if not api_data:
                logger.error(f"[{account_id}] 未拦截到任何目标 API，超时={API_WAIT_TIMEOUT}s")
                # 拦截不到不等于登出,用浏览器 cookies 直连 HTTP 验证再判断
                # 验证在线时会重试 1 次导航,重试拿到 API 则正常落库
                return self._handle_failure_with_login_check(
                    browser_api, tab, account_id, group_name, proxy,
                    failure_reason=f"拦截超时(等待 {API_WAIT_TIMEOUT}s 未捕获 API 响应)",
                )

            return self._finalize_success(
                browser_api, tab, account_id, group_name, proxy, api_data[0]
            )

        except Exception as e:
            # 程序异常不算登录态判断,只记日志,不发任何回调
            # (浏览器崩溃/网络错误/AdsPower 故障都可能进这里,误报 logout 会污染状态)
            logger.exception(f"[{account_id}] TikTok 上下文刷新异常(状态未知,不发回调): {e}")
            return False
        finally:
            if driver:
                browser_api.close_driver(driver)

    def _finalize_success(
        self,
        browser_api: BrowserApi,
        tab,
        account_id: str,
        group_name: str,
        proxy: str,
        api_item: dict,
    ) -> bool:
        """从拦截到的 API 提取上下文 → 登录态验证 → 写库 + 发回调。

        首轮拦截成功与重试拦截成功复用此分支,确保口径完全一致。

        Returns:
            bool: 写库并发出 success 回调返回 True;HTTP 验证明确登出返回 False。
        """
        context = self._extract_context(browser_api, tab, api_item)

        # 登录态验证:curl_cffi + cookies 直连 account_info,失败降级 sessionid Cookie
        login_valid, reason = self._check_login_status(context, proxy)
        if not login_valid:
            logger.warning(f"[{account_id}] 登录态验证失败: {reason}")
            send_login_callback(
                browser_id=account_id,
                platform="tiktok",
                group_name=group_name,
                login_status="logout",
                reason=reason,
            )
            return False

        # 验证通过,写库
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
        # 发送成功回调
        send_login_callback(
            browser_id=account_id,
            platform="tiktok",
            group_name=group_name,
            login_status="success",
            reason="credential_refreshed",
        )
        logger.info(
            f"[{account_id}] TikTok 上下文刷新成功 "
            f"region={context['region']} creator_id={context['creator_id']}"
        )
        return True

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

    def _handle_failure_with_login_check(
        self, browser_api: BrowserApi, tab, account_id: str, group_name: str, proxy: str, failure_reason: str
    ) -> bool:
        """拦截失败时用 curl_cffi + 浏览器实时 cookies 直连验证登录态。

        拦截不到 API 时没有新 query_string,从历史凭据补全(query_string/ua 短期稳定),
        配合浏览器当前 cookies 直连 account_info 探测。三种结果:
        - HTTP 验证通过 → 账号实际在线,触发 1 次重试导航再抓 API:
            - 重试拿到 → 走 _finalize_success 写库 + 发 success 回调
            - 重试仍空 → 不发回调(账号在线但本次刷新失败,保护登录态)
        - HTTP 验证明确失败 → 发 logout 回调
        - HTTP 验证调用异常 / 无历史凭据可补全 → 状态未知,不发回调

        Returns:
            bool: 重试成功落库返回 True;其余场景返回 False(本次刷新失败)
        """
        try:
            cookies = browser_api.get_cookies(tab)
            if not cookies:
                logger.warning(f"[{account_id}] {failure_reason},且取不到浏览器 cookies,状态未知,不发回调")
                return False

            # 从历史凭据补全 query_string/region/ua(拦截超时时无新值,这些短期稳定)
            history = load_credentials(account_id, platform="tiktok")
            ext = history.ext if history else {}
            context = {
                "cookies": cookies,
                "query_string": ext.get("query_string", ""),
                "creator_id": ext.get("creator_id", ""),
                "user_agent": ext.get("user_agent", ""),
                "region": history.region if history else "",
            }

            valid, reason = self._check_login_status(context, proxy)
            if valid:
                # 在线但首轮拦截超时:重试 1 次导航,争取拿到新 query_string 落库
                logger.info(f"[{account_id}] {failure_reason},HTTP 验证账号在线,触发 1 次重试导航")
                retry_item = self._retry_navigation_and_capture(browser_api, tab, account_id)
                if retry_item:
                    logger.info(f"[{account_id}] 重试拦截命中,走正常落库分支")
                    return self._finalize_success(
                        browser_api, tab, account_id, group_name, proxy, retry_item
                    )
                logger.warning(
                    f"[{account_id}] {failure_reason},重试仍未拦截到 API,但 HTTP 验证账号在线,不发 logout 回调"
                )
                return False

            if reason:
                # 明确登出(API code≠0 或 sessionid 缺失/过期)
                logger.warning(f"[{account_id}] {failure_reason},HTTP 验证确认登出: {reason}")
                send_login_callback(
                    browser_id=account_id,
                    platform="tiktok",
                    group_name=group_name,
                    login_status="logout",
                    reason=f"{failure_reason}; {reason}",
                )
                return False

            # reason 为空 = 验证调用本身异常 → 状态未知,不发回调
            logger.warning(f"[{account_id}] {failure_reason},HTTP 验证调用异常,状态未知,不发回调")
            return False
        except Exception as e:
            logger.exception(f"[{account_id}] 失败兜底 HTTP 验证异常: {e}")
            return False

    def _retry_navigation_and_capture(
        self, browser_api: BrowserApi, tab, account_id: str
    ) -> dict | None:
        """重试 1 次导航并拦截 API。

        触发条件:首轮拦截超时但 HTTP 验证账号在线(说明账号没问题,
        是页面 SPA 路由 / 网络抖动等导致首轮 15s 没拦到目标 API)。

        策略:
        - 不重开浏览器(避免拉长批次时间)
        - 重新挂载监听 → 二次 tab.get(ANALYTICS_URL) → 等待 API_WAIT_TIMEOUT
        - 拿到任意 FALLBACK_APIS 即返回 packet,失败返回 None

        Returns:
            dict | None: 与 _extract_context 输入兼容的 api_item;失败返回 None
        """
        try:
            # 重新挂载监听器(首轮的监听已被 get_listened_data 消费完)
            browser_api.listen_api(tab, FALLBACK_APIS, timeout=API_WAIT_TIMEOUT)
            tab.get(ANALYTICS_URL)
            time.sleep(3)
            api_data = browser_api.get_listened_data(
                tab,
                FALLBACK_APIS,
                wait_time=API_WAIT_TIMEOUT,
                count=1,
            )
            if api_data:
                return api_data[0]
            return None
        except Exception as e:
            logger.warning(f"[{account_id}] 重试导航/拦截异常: {e}")
            return None

    def _check_login_status(self, context: dict, proxy: str) -> tuple[bool, str]:
        """检测 TikTok 登录状态(组合策略)。

        优先用 curl_cffi + cookies 直连 account_info(与实际采集口径一致),
        失败时降级到 sessionid cookie 检查。

        Args:
            context: _extract_context 返回的上下文(cookies/query_string/user_agent/region)
            proxy: 账号代理

        Returns:
            tuple[bool, str]: (是否登录, 失败原因)
        """
        # 1. 优先 HTTP API 探测 account_info
        api_valid, reason = self._check_login_by_api(context, proxy)
        if api_valid:
            return True, ""
        # API 明确返回登录失败
        if reason:
            return False, reason

        # 2. API 调用异常,降级到 Cookie 检查
        logger.warning("account_info API 探测异常,降级到 sessionid Cookie 检查")
        cookie_valid, cookie_reason = self._check_sessionid_cookie(context["cookies"])
        return cookie_valid, cookie_reason

    def _build_probe_credentials(self, context: dict, proxy: str) -> Credentials:
        """用拦截到的 context 构造临时 Credentials,供 curl_cffi 登录探测复用。

        与 collector.load_credentials 产出的对象同构,确保探测口径
        (headers/cookies/指纹/query_string)与实际 HTTP 采集完全一致。
        """
        return Credentials(
            account_id="__probe__",
            platform="tiktok",
            group_name="",
            token=json.dumps(context["cookies"], ensure_ascii=False),
            region=context["region"],
            proxy=proxy,
            ext_json=json.dumps(
                {
                    "query_string": context["query_string"],
                    "creator_id": context["creator_id"],
                    "user_agent": context["user_agent"],
                },
                ensure_ascii=False,
            ),
            extra="{}",
        )

    def _check_login_by_api(self, context: dict, proxy: str) -> tuple[bool, str]:
        """用 curl_cffi + cookies 直连 account_info 探测登录态(绕开浏览器 tab)。

        复用 collector.fetch_account_info,验证口径与实际 HTTP 采集一致,
        不受 tab 落在 dashboard/登录页/异域的影响。

        Returns:
            tuple[bool, str]: (是否有效, 失败原因)
                - (True, ""): 登录有效
                - (False, "具体原因"): 明确的登录失败(HTTP 200 + code≠0 或 user_id 缺失)
                - (False, ""): 接口调用异常(网络/解析失败),需降级
        """
        session = None
        try:
            cred = self._build_probe_credentials(context, proxy)
            session = get_session(cred.fingerprint_spec, proxy=cred.proxy)
            session.cookies.update(self._cookie_dict(context["cookies"]))

            result = fetch_account_info(session, cred)
            if result["ok"]:
                user_id = result["data"].get("data", {}).get("user_id", "")
                logger.info(f"account_info 直连验证成功 user_id={user_id}")
                return True, ""

            data = result["data"]
            reason = (
                f"account_info 返回失败 code={data.get('code')} "
                f"message={data.get('message', '')}"
            )
            logger.warning(reason)
            return False, reason

        except Exception as e:
            # 网络异常/重试耗尽/解析失败 → 状态未知,交由调用方降级
            logger.error(f"account_info 直连调用异常: {e}")
            return False, ""
        finally:
            if session is not None:
                session.close()

    @staticmethod
    def _cookie_dict(cookies: list[dict]) -> dict[str, str]:
        """浏览器 cookie list 转 curl_cffi session 可接受的 dict。"""
        result: dict[str, str] = {}
        for item in cookies:
            name = item.get("name")
            if name:
                result[str(name)] = str(item.get("value", ""))
        return result

    def _check_sessionid_cookie(self, cookies: list[dict]) -> tuple[bool, str]:
        """通过 sessionid cookie 检查登录态(降级方案)。

        Args:
            cookies: 浏览器 cookie 列表

        Returns:
            tuple[bool, str]: (是否有效, 失败原因)
        """
        try:
            session_cookie = None
            for cookie in cookies:
                if cookie.get("name") == "sessionid":
                    session_cookie = cookie
                    break

            if not session_cookie:
                return False, "sessionid cookie 缺失"

            value = session_cookie.get("value")
            if not value:
                return False, "sessionid cookie 值为空"

            # 检查过期(提前 1 天 buffer)
            expires = session_cookie.get("expires", 0)
            if expires > 0:
                current_time = int(time.time())
                buffer_time = 86400  # 1 day
                if (expires - buffer_time) < current_time:
                    return False, f"sessionid cookie 已过期 expires={expires}"

            logger.info(f"sessionid cookie 有效 expires={expires}")
            return True, ""

        except Exception as e:
            logger.error(f"sessionid cookie 检查异常: {e}")
            return False, f"sessionid 检查异常: {type(e).__name__}"
