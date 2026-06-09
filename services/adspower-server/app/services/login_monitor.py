from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings, _LAZADA_COUNTRY_DOMAIN, get_shopee_seller_domain
from app.services.adspower import AdsPowerApiError, AdsPowerConnectionError, AdsPowerService
from app.services.session import Session, session_manager
from loguru import logger


async def _close_all_tabs(session):
    """关闭浏览器中所有 tab 窗口"""
    def _sync_close_tabs():
        try:
            tab = session.drissionpage_tab
            if tab:
                # 先关闭其他 tab
                tab.close(others=True)

        except Exception as e:
            logger.warning("关闭 tab 失败: {}", e)

    await asyncio.to_thread(_sync_close_tabs)


class LoginMonitorService:
    """登录监听与回调处理。"""

    # 监听多个接口：api/v2/login、subaccount/get_shop_list 及兜底接口
    SHOPEE_PATTERN = [
        "api/v2/login",
        "subaccount/get_shop_list",
        "selleraccount/shop_info",
        "shop_info/get_shop_inactive_status",
        "cnsc/selleraccount/get_session",
        "cnsc/selleraccount/get_merchant_shop_list",
    ]

    # TikTok 登录验证 Cookie Key
    TIKTOK_COOKIE_KEY = "multi_sids"

    def __init__(self) -> None:
        self._adspower_service = AdsPowerService()

    def start(self, session: Session) -> None:
        if session.login_task is not None:
            task_done = getattr(session.login_task, "done", None)
            if callable(task_done) and not task_done():
                return

        if not session.drissionpage_tab:
            logger.warning("Session 缺少 DrissionPage tab，无法监听登录: {}", session.session_id)
            return

        media = session.media.lower()
        if media == "shopee":
            session.login_status = "pending"
            session.login_task = asyncio.create_task(self._run(session))
        elif media == "tiktok":
            session.login_status = "pending"
            session.login_task = asyncio.create_task(self._run_tiktok(session))
        elif media == "lazada":
            session.login_status = "pending"
            session.login_task = asyncio.create_task(self._run_lazada(session))
        else:
            logger.info("媒体暂不支持登录监听: {}", session.media)
            return

    async def _run(self, session: Session) -> None:
        try:
            result = await asyncio.to_thread(self._listen_once, session)
        except Exception as exc:
            logger.warning("登录监听异常: {}", exc)
            # 立即设置状态，防止竞态条件导致 closed 回调
            session.login_status = "error"
            await self._handle_result(session, status="error", reason="listen_error", shop_id=None)
            return

        if result is None:
            # 立即设置状态，防止竞态条件导致 closed 回调
            session.login_status = "error"
            await self._handle_result(session, status="error", reason="timeout", shop_id=None)
            return

        login_shop_id = result.get("login_shop_id")
        shop_list_ids = result.get("shop_list_ids", [])
        api_login_verified = result.get("api_login_verified", False)

        # 验证逻辑：任一接口匹配成功即为 success
        validate_id = str(session.validate_id)

        if api_login_verified:
            # 检查 login 接口
            if login_shop_id and str(login_shop_id) == validate_id:
                # 立即设置状态，防止竞态条件导致 closed 回调
                session.login_status = "success"
                await self._handle_result(session, status="success", reason="", shop_id=login_shop_id)
                return

            # 检查 get_shop_list 接口
            if validate_id in [str(sid) for sid in shop_list_ids]:
                # 立即设置状态，防止竞态条件导致 closed 回调
                session.login_status = "success"
                await self._handle_result(session, status="success", reason="", shop_id=int(validate_id) if validate_id.isdigit() else None)
                return

        # 两者都不匹配
        # 立即设置状态，防止竞态条件导致 closed 回调
        session.login_status = "error"
        reported_shop_id = login_shop_id if login_shop_id else (shop_list_ids[0] if shop_list_ids else None)
        await self._handle_result(session, status="error", reason="shop_mismatch", shop_id=reported_shop_id)

    async def _run_tiktok(self, session: Session) -> None:
        """TikTok 登录监听主循环 - 基于 Cookie 监听"""
        try:
            result = await asyncio.to_thread(self._listen_tiktok_cookie, session)
        except Exception as exc:
            logger.warning("TikTok 登录监听异常: {}", exc)
            # 立即设置状态，防止竞态条件导致 closed 回调
            session.login_status = "error"
            await self._handle_result(session, status="error", reason="listen_error", shop_id=None)
            return

        if result is None:
            # 立即设置状态，防止竞态条件导致 closed 回调
            session.login_status = "error"
            await self._handle_result(session, status="error", reason="timeout", shop_id=None)
            return

        if result.get("success"):
            # 立即设置状态，防止竞态条件导致 closed 回调
            session.login_status = "success"
            await self._handle_result(session, status="success", reason="", shop_id=session.validate_id)
            # 复登成功后通知 live-crawler 刷新 HTTP 采集凭据(等投屏浏览器关闭后再开,避免 profile 冲突)
            self._schedule_tiktok_credential_refresh(session)
        else:
            # 店铺不匹配，返回实际登录的 shop_id
            # 立即设置状态，防止竞态条件导致 closed 回调
            session.login_status = "error"
            actual_shop_id = result.get("actual_shop_id")
            await self._handle_result(session, status="error", reason="shop_mismatch", shop_id=actual_shop_id)

    def _check_tiktok_login_by_api(self, tab) -> tuple[bool, dict | None]:
        """通过账号信息接口检测 TikTok 登录状态

        Returns:
            tuple[bool, dict | None]: (是否登录, 用户信息字典)
                - (True, {...}): 登录成功，返回用户信息
                - (False, {}): 明确的登录失败（API 返回失败状态）
                - (False, None): 接口调用异常（网络错误、解析失败等）
        """
        try:
            # 构造请求 URL
            api_url = "https://shop.tiktok.com/api/v1/streamer_desktop/account_info/get?version=1"

            # 使用 window 变量 + poll 机制等待异步 fetch 结果
            ts = int(time.time() * 1000)
            result_key = f"__tiktok_login_check_{ts}"

            # 注入 JS 发起 fetch 请求，结果存入 window 变量
            js_code = f"""
            window['{result_key}'] = null;
            fetch({json.dumps(api_url)}, {{
                method: 'GET',
                credentials: 'include'
            }})
            .then(async response => {{
                if (!response.ok) {{
                    window['{result_key}'] = {{ error: 'HTTP ' + response.status }};
                    return;
                }}
                try {{
                    const data = await response.json();
                    window['{result_key}'] = {{ response: data }};
                }} catch (e) {{
                    window['{result_key}'] = {{ error: 'parse_error: ' + String(e) }};
                }}
            }})
            .catch(e => {{
                window['{result_key}'] = {{ error: String(e) }};
            }});
            """

            tab.run_js(js_code)

            # Poll 等待结果（最多 10 秒）
            poll_timeout = 10.0
            poll_interval = 0.5
            start_time = time.time()
            result = None

            while time.time() - start_time < poll_timeout:
                val = tab.run_js(f"return window['{result_key}'];")
                if val is not None:
                    result = val
                    break
                time.sleep(poll_interval)

            # 清理 window 变量
            try:
                tab.run_js(f"delete window['{result_key}'];")
            except Exception:
                pass

            if not result:
                logger.warning("TikTok 账号信息接口请求超时")
                return False, None

            if result.get('error'):
                logger.warning("TikTok 账号信息接口请求失败: {}", result.get('error'))
                return False, None

            # 解析响应数据
            response_data = result.get('response', {})

            # 判断响应状态
            code = response_data.get('code')
            message = response_data.get('message', '')
            data = response_data.get('data', {})

            if code == 0 and data.get('user_id'):
                # 登录成功
                user_info = {
                    'user_id': data.get('user_id'),
                    'user_name': data.get('user_name'),
                    'user_type': data.get('user_type'),
                    'tt_uid': data.get('tt_uid')
                }
                logger.info(
                    "TikTok API 验证成功: user_name={}, user_id={}",
                    user_info["user_name"], user_info["user_id"]
                )
                return True, user_info
            else:
                # 登录失败或账号异常（明确的失败，不是异常）
                logger.warning("TikTok API 验证失败: code={}, message={}", code, message)
                return False, {}

        except Exception as e:
            logger.error("调用 TikTok 账号信息接口异常: {}", e)
            # 接口调用失败时返回 (False, None)
            return False, None

    def _listen_tiktok_cookie(self, session: Session) -> Optional[Dict[str, Any]]:
        """后台线程：循环检查 TikTok Cookie 直到超时或登录成功或店铺不匹配"""
        tab = session.drissionpage_tab
        validate_id = str(session.validate_id)

        start_time = time.time()
        timeout = settings.LOGIN_TIMEOUT_SECONDS
        check_interval = .1  # 每0.1秒检查一次 Cookie
        api_fail_count = 0  # API 验证失败计数器

        while time.time() - start_time < timeout:
            try:
                # 获取 multi_sids Cookie
                cookies = tab.cookies()
                multi_sids_value = None

                for cookie in cookies:
                    if cookie.get("name") == self.TIKTOK_COOKIE_KEY:
                        multi_sids_value = cookie.get("value", "")
                        break

                # 如果 Cookie 有值，进行校验
                if multi_sids_value:
                    if validate_id in multi_sids_value:
                        # Cookie 匹配成功，增加 API 二次验证
                        is_logged_in, user_info = self._check_tiktok_login_by_api(tab)
                        if is_logged_in:
                            logger.info("TikTok 登录成功（Cookie + API 双重验证）: validate_id={}", validate_id)
                            return {"success": True, "user_info": user_info}
                        else:
                            # API 验证失败，增加计数器
                            api_fail_count += 1
                            logger.warning("TikTok Cookie 有效但 API 验证失败 {}次，继续等待...", api_fail_count)
                            time.sleep(15)
                    else:
                        # 店铺不匹配，提取实际登录的 shop_id
                        actual_shop_id = multi_sids_value
                        logger.warning("TikTok 登录店铺不匹配，期望: {}，实际 Cookie: {}", validate_id, multi_sids_value)
                        return {"success": False, "actual_shop_id": actual_shop_id}

            except Exception as exc:
                logger.debug("获取 Cookie 失败: {}", exc)

            # 等待下次检查
            time.sleep(check_interval)

        # 超时
        return None

    def _listen_once(self, session: Session) -> Optional[Dict[str, Any]]:
        """循环监听，收集多个接口的响应数据，并增加 Cookie 兜底检测"""
        tab = session.drissionpage_tab
        tab.listen.start(self.SHOPEE_PATTERN)

        login_shop_id = None
        shop_list_ids: List[int] = []
        fallback_triggered = False  # 标记是否已触发兜底
        last_cookie_check = 0.0  # 上次 Cookie 检查时间
        cookie_check_interval = 5  # Cookie 检查间隔（秒）

        start_time = time.time()
        timeout = settings.LOGIN_TIMEOUT_SECONDS

        while time.time() - start_time < timeout:
            # 周期性检查 Cookie（兜底机制）
            current_time = time.time()
            if current_time - last_cookie_check >= cookie_check_interval:
                last_cookie_check = current_time

                # 如果 Cookie 有效但没有 shop_id，且未触发过兜底
                if (not login_shop_id
                    and not shop_list_ids
                    and not fallback_triggered
                    and self._check_session_cookie(tab)):

                    logger.info("检测到登录 Cookie 有效但未获取到 shop_id，触发兜底")
                    self._trigger_shop_info(tab, session)
                    fallback_triggered = True

            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                break
            packet = tab.listen.wait(timeout=min(remaining, 2))
            if not packet:
                continue

            url = getattr(packet, "url", "") or ""
            response = getattr(packet, "response", None)
            body = getattr(response, "body", None) if response else None
            parsed_body = self._parse_body(body)

            if "api/v2/login" in url:
                shop_id = self._extract_shop_id(parsed_body)
                if shop_id and shop_id != 0:
                    login_shop_id = shop_id
            elif "subaccount/get_shop_list" in url:
                ids = self._extract_shop_ids_from_shop_list(parsed_body)
                shop_list_ids.extend(ids)
            elif "selleraccount/shop_info" in url or "shop_info/get_shop_inactive_status" in url:
                # 新增接口处理：从 data.shop_id 提取
                shop_id = self._extract_shop_id_from_data(parsed_body)
                if shop_id and shop_id != 0:
                    login_shop_id = shop_id
                    logger.info("从兜底接口获取到 shop_id: {}", shop_id)
            elif "cnsc/selleraccount/get_session" in url:
                shop_id = self._extract_shop_id_from_cn_session(parsed_body)
                if shop_id and shop_id != 0:
                    login_shop_id = shop_id
                    logger.info("从 CN get_session 接口获取到 shop_id: {}", shop_id)

            # 如果任一接口已匹配成功，立即返回
            if login_shop_id and str(login_shop_id) == str(session.validate_id):
                break
            if str(session.validate_id) in [str(sid) for sid in shop_list_ids]:
                break

        # 始终通过 API 验证账号是否登录成功（作为登录成功的必要条件）
        api_login_verified = False
        api_success, _ = self._verify_shopee_login_by_api(tab, session)
        if api_success:
            api_login_verified = True
            logger.info("通过 API 验证确认账号已登录成功")

        try:
            tab.listen.stop()
        except Exception as exc:
            logger.debug("停止监听失败: {}", exc)

        return {
            "login_shop_id": login_shop_id,
            "shop_list_ids": shop_list_ids,
            "api_login_verified": api_login_verified,
        }

    def _parse_body(self, body: Any) -> Any:
        """解析响应体为字典或列表"""
        if body is None:
            return None
        if isinstance(body, (dict, list)):
            return body
        # 尝试解码 bytes
        if isinstance(body, (bytes, bytearray)):
            try:
                body = body.decode("utf-8")
            except Exception:
                return None
        # 尝试解析 JSON 字符串
        if isinstance(body, str):
            try:
                return json.loads(body)
            except Exception:
                return None
        return None

    def _extract_shop_id(self, body: Any) -> Optional[int]:
        if body is None:
            return None
        value = self._find_shop_id(body)
        return self._to_int(value)

    def _find_shop_id(self, obj: Any) -> Optional[Any]:
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_lower = str(key).lower()
                if key_lower in {"shopid", "shop_id"}:
                    return value
                if isinstance(value, (dict, list)):
                    found = self._find_shop_id(value)
                    if found is not None:
                        return found
        elif isinstance(obj, list):
            for item in obj:
                found = self._find_shop_id(item)
                if found is not None:
                    return found
        return None

    def _to_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    def _extract_shop_ids_from_shop_list(self, body: Any) -> List[int]:
        """从 get_shop_list 响应的 shops 数组中提取所有 shop_id"""
        if not isinstance(body, dict):
            return []
        shops = body.get("shops", [])
        shop_ids = []
        for shop in shops:
            if isinstance(shop, dict) and "shop_id" in shop:
                shop_id = self._to_int(shop.get("shop_id"))
                if shop_id is not None:
                    shop_ids.append(shop_id)
        return shop_ids

    def _extract_shop_id_from_data(self, body: Any) -> Optional[int]:
        """从响应的 data.shop_id 中提取 shop_id"""
        if not isinstance(body, dict):
            return None
        data = body.get("data")
        if not isinstance(data, dict):
            return None
        return self._to_int(data.get("shop_id"))

    def _extract_shop_id_from_cn_session(self, body: Any) -> Optional[int]:
        """从 CN get_session 响应的 sub_account_info.current_shop_id 中提取 shop_id"""
        if not isinstance(body, dict):
            return None
        sub_info = body.get("sub_account_info")
        if not isinstance(sub_info, dict):
            return None
        return self._to_int(sub_info.get("current_shop_id"))

    def _check_session_cookie(self, tab) -> bool:
        """检查 SPC_SC_SESSION Cookie 是否存在且有效"""
        try:
            cookie_list = tab.cookies(all_info=True)
            for cookie in cookie_list:
                if cookie.get('name') == 'SPC_SC_SESSION':
                    expires = cookie.get('expires', 0)
                    current_time = int(time.time())
                    # expires 为 0 表示 session cookie，视为有效
                    if expires == 0 or expires > current_time:
                        return True
            return False
        except Exception as e:
            logger.debug("检查 Cookie 失败: {}", e)
            return False

    def _inject_js_with_retry(self, tab, js_code: str) -> None:
        """注入 JS 前先等页面 ready，遇到"页面被刷新"竞态时重试一次

        登录成功瞬间浏览器会立刻跳转，旧 frame 被销毁、新 frame 还没接管，
        此时 DrissionPage 会抛"页面被刷新"。给导航留出落地时间后再试一次即可。
        """
        time.sleep(1.5)

        try:
            tab.wait.doc_loaded(timeout=5)
        except Exception:
            pass

        try:
            tab.run_js(js_code)
            return
        except Exception as e:
            msg = str(e)
            if "页面被刷新" not in msg and "page" not in msg.lower():
                raise
            logger.info("注入 JS 遇到页面刷新竞态，等待 1.5s 后重试")

    def _verify_shopee_login_by_api(self, tab, session: Session) -> tuple[bool, dict | None]:
        """通过 API 验证 Shopee 登录态（JS 注入 + 轮询）。

        跨境店（cb_option=1）使用 CN 专属验证接口，本土店使用当前国家域名接口。

        注入 JS 前会先等待页面加载完成，并在遭遇"页面被刷新"竞态时重试一次，
        避开登录成功瞬间浏览器跳转导致 frame 失效的问题。

        Returns:
            tuple: (is_logged_in, response_data or None)
        """
        try:
            if session.cb_option == 1:
                api_label = "CN"
                api_url = "https://seller.shopee.cn/api/cnsc/selleraccount/get_session/"
            else:
                domain = get_shopee_seller_domain(session.country)
                api_label = domain
                api_url = f"https://{domain}/api/v2/login/"

            ts = int(time.time() * 1000)
            result_key = f"__shopee_login_check_{ts}"

            js_code = f"""
            window['{result_key}'] = null;
            fetch({json.dumps(api_url)}, {{
                method: 'GET',
                credentials: 'include'
            }})
            .then(async response => {{
                try {{
                    const data = await response.json();
                    window['{result_key}'] = {{ status: response.status, response: data }};
                }} catch (e) {{
                    window['{result_key}'] = {{ error: 'parse_error: ' + String(e) }};
                }}
            }})
            .catch(e => {{
                window['{result_key}'] = {{ error: String(e) }};
            }});
            """

            # 注入前先等页面就绪，并在"页面被刷新"竞态下重试一次
            self._inject_js_with_retry(tab, js_code)

            poll_timeout = 10.0
            poll_interval = 0.5
            start_time = time.time()
            result = None
            while time.time() - start_time < poll_timeout:
                val = tab.run_js(f"return window['{result_key}'];")
                if val is not None:
                    result = val
                    break
                time.sleep(poll_interval)

            try:
                tab.run_js(f"delete window['{result_key}'];")
            except Exception:
                pass

            if not result or 'error' in result:
                logger.warning("Shopee login API ({}) 验证失败: {}", api_label, result)
                return False, None

            response_data = result.get('response', {})

            if session.cb_option == 1:
                # CN API: {"code": 0, "sub_account_info": {"account_id": ..., "current_shop_id": ...}, "message": "success"}
                code = response_data.get('code')
                if code == 0:
                    sub_info = response_data.get('sub_account_info', {}) or {}
                    logger.info(
                        "Shopee API (CN) 验证登录成功: account_id={}, current_shop_id={}",
                        sub_info.get('account_id'), sub_info.get('current_shop_id')
                    )
                    return True, response_data
                else:
                    logger.warning("Shopee API (CN) 验证登录失败: code={}, message={}",
                                   code, response_data.get('message'))
                    return False, None
            else:
                errcode = response_data.get('errcode')
                if errcode == 0:
                    logger.info(
                        "Shopee API ({}) 验证登录成功: user_id={}, shop_id={}",
                        api_label, response_data.get('id'), response_data.get('shopid')
                    )
                    return True, response_data
                else:
                    logger.warning("Shopee API ({}) 验证登录失败: errcode={}", api_label, errcode)
                    return False, None

        except Exception as e:
            logger.warning("Shopee API 验证异常: {}", e)
            return False, None

    def _fetch_shopee_shop_ids(self, session: Session) -> tuple[bool, set[int]]:
        """主动验证登录态并获取 shop_id 集合。

        通过 JS 注入调用验证接口 + 店铺列表接口，5s 节流后在 URL 离开登录页时调用。

        Args:
            session: 会话对象，包含 cb_option/country/drissionpage_tab

        Returns:
            (login_ok, shop_ids): 登录态是否有效 + 店铺 ID 集合
        """
        tab = session.drissionpage_tab

        if session.cb_option == 1:
            # 跨境店：CN get_session + get_merchant_shop_list
            return self._fetch_cn_shop_ids(tab)
        else:
            # 本土店：api/v2/login + get_shop_list
            return self._fetch_local_shop_ids(tab, session.country)

    def _fetch_cn_shop_ids(self, tab) -> tuple[bool, set[int]]:
        """跨境店主动验证：CN get_session + get_merchant_shop_list"""
        try:
            ts = int(time.time() * 1000)
            session_key = f"__cn_session_{ts}"
            list_key = f"__cn_list_{ts}"

            js_code = f"""
            window['{session_key}'] = null;
            window['{list_key}'] = null;
            fetch('https://seller.shopee.cn/api/cnsc/selleraccount/get_session/', {{
                method: 'GET', credentials: 'include'
            }}).then(async r => {{
                try {{ window['{session_key}'] = {{ status: r.status, response: await r.json() }}; }}
                catch (e) {{ window['{session_key}'] = {{ error: String(e) }}; }}
            }}).catch(e => {{ window['{session_key}'] = {{ error: String(e) }}; }});

            fetch('https://seller.shopee.cn/api/cnsc/selleraccount/get_merchant_shop_list/', {{
                method: 'GET', credentials: 'include'
            }}).then(async r => {{
                try {{ window['{list_key}'] = {{ status: r.status, response: await r.json() }}; }}
                catch (e) {{ window['{list_key}'] = {{ error: String(e) }}; }}
            }}).catch(e => {{ window['{list_key}'] = {{ error: String(e) }}; }});
            """

            self._inject_js_with_retry(tab, js_code)

            # Poll 等待结果
            session_result = self._poll_window_var(tab, session_key, timeout=10.0)
            list_result = self._poll_window_var(tab, list_key, timeout=10.0)

            # 清理
            try:
                tab.run_js(f"delete window['{session_key}']; delete window['{list_key}'];")
            except Exception:
                pass

            # 验证 get_session
            if not session_result or 'error' in session_result:
                return False, set()
            session_data = session_result.get('response', {})
            if session_data.get('code') != 0:
                return False, set()

            # 提取 current_shop_id
            shop_ids = set()
            sub_info = session_data.get('sub_account_info', {}) or {}
            current_id = self._to_int(sub_info.get('current_shop_id'))
            if current_id:
                shop_ids.add(current_id)

            # 提取 merchant_shop_list（可能无权限，不影响 login_ok）
            if list_result and 'error' not in list_result:
                list_data = list_result.get('response', {})
                if list_data.get('code') == 0:
                    shops = list_data.get('data', {}).get('shops', [])
                    for shop in shops:
                        sid = self._to_int(shop.get('shop_id'))
                        if sid:
                            shop_ids.add(sid)

            return True, shop_ids
        except Exception as e:
            logger.warning("跨境店主动验证异常: {}", e)
            return False, set()

    def _fetch_local_shop_ids(self, tab, country: str) -> tuple[bool, set[int]]:
        """本土店主动验证：api/v2/login + get_shop_list"""
        try:
            domain = get_shopee_seller_domain(country)
            ts = int(time.time() * 1000)
            login_key = f"__local_login_{ts}"
            list_key = f"__local_list_{ts}"

            js_code = f"""
            window['{login_key}'] = null;
            window['{list_key}'] = null;
            fetch('https://{domain}/api/v2/login/', {{
                method: 'GET', credentials: 'include'
            }}).then(async r => {{
                try {{ window['{login_key}'] = {{ status: r.status, response: await r.json() }}; }}
                catch (e) {{ window['{login_key}'] = {{ error: String(e) }}; }}
            }}).catch(e => {{ window['{login_key}'] = {{ error: String(e) }}; }});

            fetch('https://{domain}/api/selleraccount/subaccount/get_shop_list/', {{
                method: 'POST', credentials: 'include'
            }}).then(async r => {{
                try {{ window['{list_key}'] = {{ status: r.status, response: await r.json() }}; }}
                catch (e) {{ window['{list_key}'] = {{ error: String(e) }}; }}
            }}).catch(e => {{ window['{list_key}'] = {{ error: String(e) }}; }});
            """

            self._inject_js_with_retry(tab, js_code)

            login_result = self._poll_window_var(tab, login_key, timeout=10.0)
            list_result = self._poll_window_var(tab, list_key, timeout=10.0)

            try:
                tab.run_js(f"delete window['{login_key}']; delete window['{list_key}'];")
            except Exception:
                pass

            if not login_result or 'error' in login_result:
                return False, set()
            login_data = login_result.get('response', {})
            if login_data.get('errcode') != 0:
                return False, set()

            shop_ids = set()
            current_id = self._to_int(
                login_data.get('shopid') or (login_data.get('user') or {}).get('shop_id')
            )
            if current_id:
                shop_ids.add(current_id)

            if list_result and 'error' not in list_result:
                list_data = list_result.get('response', {})
                if list_data.get('code') == 0:
                    shops = list_data.get('shops', [])
                    for shop in shops:
                        sid = self._to_int(shop.get('shop_id'))
                        if sid:
                            shop_ids.add(sid)

            return True, shop_ids
        except Exception as e:
            logger.warning("本土店主动验证异常: {}", e)
            return False, set()

    def _poll_window_var(self, tab, var_name: str, timeout: float = 10.0) -> dict | None:
        """Poll 等待 window 变量赋值完成"""
        import time
        start = time.time()
        while time.time() - start < timeout:
            val = tab.run_js(f"return window['{var_name}'];")
            if val is not None:
                return val
            time.sleep(0.5)
        return None

    def _trigger_shop_info(self, tab, session: Session) -> None:
        """主动导航到页面触发 shop_id 接口"""
        try:
            from app.config import get_shopee_seller_domain
            # 跨境店使用 seller.shopee.cn
            if session.cb_option == 1:
                domain = "seller.shopee.cn"
            else:
                domain = get_shopee_seller_domain(session.country)
            trigger_url = f"https://{domain}/creator-center/insight/live"
            tab.get(trigger_url)
            logger.info("已触发兜底页面: {}", trigger_url)
        except Exception as e:
            logger.warning("触发兜底页面失败: {}", e)

    def _schedule_tiktok_credential_refresh(self, session: Session) -> None:
        """调度 TikTok 复登后凭据刷新(异步,不阻塞登录回调)。

        投屏浏览器登录成功后 LOGIN_SUCCESS_CLOSE_DELAY_SECONDS 秒会被关闭,
        刷新必须等其关闭后再开新浏览器,否则同一 AdsPower profile 冲突。
        """
        if not settings.TIKTOK_REFRESH_ON_LOGIN:
            return
        if not session.profile_id:
            logger.warning("TikTok 复登刷新跳过：缺少 profile_id, session={}", session.session_id)
            return
        asyncio.create_task(self._refresh_tiktok_credential(session))

    async def _refresh_tiktok_credential(self, session: Session) -> None:
        """等投屏浏览器确实关闭后,通知 live-crawler 刷新 TikTok 采集凭据。

        投屏浏览器和养号刷新用同一个 AdsPower profile,不能同时打开。
        轮询浏览器活跃状态(每 10s 一次,最长 15 分钟),确认 Inactive 才触发刷新;
        超时未关闭则放弃本次刷新(由每日 cron 兜底),避免 profile 冲突。
        """
        account_id = session.profile_id

        # 先给关浏览器流程一点起步时间,再开始轮询
        await asyncio.sleep(settings.LOGIN_SUCCESS_CLOSE_DELAY_SECONDS + 2)

        poll_interval = 10        # 每 10s 查一次状态
        max_wait_seconds = 15 * 60  # 最长等 15 分钟
        waited = 0
        while waited < max_wait_seconds:
            is_active = await self._adspower_service.check_browser_active(account_id)
            if not is_active:
                logger.info("投屏浏览器已关闭,触发 TikTok 凭据刷新: account_id={}", account_id)
                break
            await asyncio.sleep(poll_interval)
            waited += poll_interval
        else:
            # 超时仍未关闭:主动强制关闭浏览器,再继续刷新(避免 profile 冲突)
            logger.warning(
                "等待投屏浏览器关闭超时({}s),主动调用 stop_browser 强制关闭: account_id={}",
                max_wait_seconds, account_id,
            )
            await self._adspower_service.stop_browser(account_id)
            # 给关闭生效留时间,再确认一次
            await asyncio.sleep(5)
            if await self._adspower_service.check_browser_active(account_id):
                logger.warning(
                    "强制关闭后浏览器仍活跃,放弃本次 TikTok 复登刷新(由每日 cron 兜底): account_id={}",
                    account_id,
                )
                return
            logger.info("强制关闭成功,触发 TikTok 凭据刷新: account_id={}", account_id)

        url = f"{settings.MONITOR_API_URL}/api/refresh_tiktok_credential"
        headers = {
            "Content-Type": "application/json",
            "X-API-Token": settings.COOKIE_API_TOKEN,
        }
        # 不传 group_name/proxy: 由 refresher 从 AdsPower profile 查权威值,避免格式不一致
        payload = {"account_id": account_id}

        try:
            # 刷新会开浏览器拦截,耗时较长,给足超时
            async with httpx.AsyncClient(timeout=60*3) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    logger.info("TikTok 复登凭据刷新已触发: account_id={}, resp={}", account_id, resp.json())
                else:
                    logger.warning("TikTok 复登凭据刷新返回异常状态: status={}, account_id={}",
                                   resp.status_code, account_id)
        except Exception as exc:
            logger.warning("TikTok 复登凭据刷新调用失败: account_id={}, err={}", account_id, exc)

    async def callback_close(self, session: Session, reason: str = "closed") -> None:
        """关闭时回调通知后端

        Args:
            session: 会话对象
            reason: 关闭原因（api_close/ws_disconnect/app_shutdown）
        """
        # 避免重复回调（只有在回调真正发送后才跳过）
        if session.login_callback_sent:
            logger.info("Session 已发送过登录回调，跳过关闭回调: {}", session.session_id)
            return

        logger.info("触发关闭回调: session_id={}, reason={}", session.session_id, reason)
        await self._callback_backend(session, status="closed", reason=reason, shop_id=None)

    async def _handle_result(
        self,
        session: Session,
        status: str,
        reason: str,
        shop_id: Optional[int],
    ) -> None:
        # 关键业务逻辑：无论 Session 是否关闭都要执行
        # 店铺不匹配时清除 Cookies，以便下次使用时用户能重新登录
        if reason == "shop_mismatch":
            await self._clear_cookies(session)

        # 登录成功时移动环境到对应分组
        if status == "success" and session.profile_id and session.target_group_id:
            await self._move_to_group(session)

        # Session 已关闭，仅执行回调，跳过通知前端和调度关闭
        if session.status != "active" or session.cleanup_started:
            logger.info("Session 已关闭，但仍执行登录结果回调: {}", session.session_id)
            await self._callback_backend(session, status=status, reason=reason, shop_id=shop_id)
            return

        # Session 正常，执行完整流程
        session.login_status = status
        session.login_reason = reason
        session.login_shop_id = shop_id

        await self._callback_backend(session, status, reason, shop_id)  # 先回调后端
        await self._notify_frontend(session, status, reason, shop_id)   # 再通知前端
        await self._schedule_close(session, status, reason)

    async def _clear_cookies(self, session: Session) -> None:
        """清除浏览器 Cookies，用于 shop_mismatch 时重置登录状态"""
        def _sync_clear():
            try:
                tab = session.drissionpage_tab
                if tab:
                    tab.clear_cache(cookies=True)
                    logger.info("已清除浏览器 Cookies: {}", session.session_id)
            except Exception as e:
                logger.warning("清除 Cookies 失败: {}", e)

        await asyncio.to_thread(_sync_clear)

    async def _notify_frontend(
        self,
        session: Session,
        status: str,
        reason: str,
        shop_id: Optional[int],
    ) -> None:
        """通知前端登录结果"""
        websocket = session.frontend_ws
        if websocket is None:
            logger.info("前端未连接，跳过登录结果通知: {}", session.session_id)
            return

        # 构建通知消息
        payload = self._build_login_notification(session, status, reason, shop_id)

        try:
            await websocket.send_text(json.dumps(payload))
        except Exception as exc:
            logger.warning("发送登录结果通知失败: {}", exc)

    def _build_login_notification(
        self,
        session: Session,
        status: str,
        reason: str,
        shop_id: Optional[int],
    ) -> Dict[str, Any]:
        """构建登录通知消息"""
        if status == "success":
            return {
                "type": "login_success",
                "data": {
                    "shop_id": shop_id,
                    "validate_id": session.validate_id,
                    "profile_id": session.profile_id,
                },
            }
        if reason == "timeout":
            return {"type": "login_timeout"}
        # 登录失败
        payload: Dict[str, Any] = {"type": "login_failed", "reason": reason}
        if shop_id is not None:
            payload["shop_id"] = shop_id
        return payload

    async def _callback_backend(
        self,
        session: Session,
        status: str,
        reason: str,  # 保留参数，目标接口暂不使用
        shop_id: Optional[int],  # 保留参数，目标接口暂不使用
    ) -> None:
        callback_url = settings.LOGIN_CALLBACK_URL
        # 构建回调 payload，collection_id 使用 profile_id
        payload = {
            "login_status": status,
            "media": session.media,
            "validate_id": session.validate_id,
            "collection_id": session.profile_id,
            "reason": reason,
            "session_id": session.session_id,
            "shop_id": shop_id,
        }
        # 构建请求头，添加 accessToken
        headers = {
            "Content-Type": "application/json",
            "accessToken": settings.LOGIN_CALLBACK_ACCESS_TOKEN,
        }
        if not callback_url:
            logger.info("未配置回调地址，跳过登录结果回调: {}，回调内容：{}", session.session_id, payload)
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(callback_url, json=payload, headers=headers)
                logger.info("登录结果回调成功: {},回调内容: {}", response.status_code, payload)
                session.login_callback_sent = True  # 标记回调已发送
            if response.status_code >= 400:
                logger.warning("回调返回异常状态码: {}", response.status_code)
        except Exception as exc:
            logger.warning("登录结果回调失败: {}", exc)

    async def _schedule_close(self, session: Session, status: str, reason: str) -> None:
        """根据登录结果调度关闭任务"""
        delay_map = {
            "success": settings.LOGIN_SUCCESS_CLOSE_DELAY_SECONDS,
            "timeout": settings.LOGIN_TIMEOUT_CLOSE_DELAY_SECONDS,
        }
        delay = delay_map.get(status if status == "success" else reason, settings.LOGIN_FAILED_CLOSE_DELAY_SECONDS)
        asyncio.create_task(self._close_after_delay(session.session_id, delay))

    async def _move_to_group(self, session: Session) -> None:
        """登录成功后移动环境到对应分组"""
        try:
            await self._adspower_service.move_to_group(
                profile_ids=[session.profile_id],
                group_id=str(session.target_group_id),
            )
            logger.info(
                "环境已移动到分组: profile_id={}, group_id={}",
                session.profile_id,
                session.target_group_id,
            )
        except (AdsPowerConnectionError, AdsPowerApiError) as exc:
            logger.warning("移动分组失败: {}", exc)
        except Exception as exc:
            logger.warning("移动分组异常: {}", exc)

    async def _close_after_delay(self, session_id: str, delay: int) -> None:
        """延迟关闭 Session 及浏览器"""
        if delay > 0:
            await asyncio.sleep(delay)

        session, is_owner = session_manager.begin_cleanup(session_id, owner="login_monitor")
        if not session or not is_owner:
            return

        await session_manager.close(session_id)
        # 先关闭所有 tab 窗口
        await _close_all_tabs(session)
        await self._adspower_service.stop_browser(session.profile_id)  # 只关闭浏览器，不删除环境
        session_manager.remove(session_id)

    # ==================== Lazada 登录监听 ====================

    async def _run_lazada(self, session: Session) -> None:
        """Lazada 双端口登录监听主流程（live → sellercenter）"""
        try:
            # 1. 注入 JS Hook 拦截账密
            await asyncio.to_thread(self._inject_credentials_hook, session)

            # 2. 监听 live 登录成功（同时缓存账密到 Python 侧）
            live_result = await asyncio.to_thread(self._listen_live_login, session)
            if not live_result:
                session.login_status = "error"
                await self._handle_result(session, "error", "timeout", None)
                return

            # 3. 从 live_result 获取账密（已在轮询中缓存）
            credentials = live_result.get('credentials')
            if not credentials:
                session.login_status = "error"
                await self._handle_result(session, "error", "credentials_missing", None)
                return

            # 4. 从 live Cookie 的 aui 获取 seller_id
            seller_id = live_result['seller_id']
            venture = self._detect_venture(session.drissionpage_tab.url)

            # 5. 验证 seller_id 与 validate_id 是否一致
            if session.validate_id and str(seller_id) != str(session.validate_id):
                session.login_status = "error"
                await self._handle_result(session, "error", "shop_mismatch", seller_id)
                return

            # 6. 保存 live Cookie（必须成功）
            live_saved = await self._save_cookies(
                session.profile_id, "lazada", "live",
                live_result['cookies'], seller_id, venture, credentials
            )
            if not live_saved:
                session.login_status = "error"
                await self._handle_result(session, "error", "cookie_save_failed", None)
                return

            # 7. 自动登录 sellercenter
            sc_cookies = await asyncio.to_thread(
                self._auto_login_sellercenter, session, credentials, venture
            )
            if not sc_cookies:
                session.login_status = "error"
                await self._handle_result(session, "error", "sellercenter_login_failed", None)
                return

            # 8. 保存 sellercenter Cookie（必须成功）
            sc_saved = await self._save_cookies(
                session.profile_id, "lazada", "sellercenter",
                sc_cookies, seller_id, venture, credentials
            )
            if not sc_saved:
                session.login_status = "error"
                await self._handle_result(session, "error", "cookie_save_failed", None)
                return

            # 9. 两个端口 Cookie 都已成功保存，回调 success
            session.login_status = "success"
            session.login_shop_id = seller_id
            await self._handle_result(session, "success", "", seller_id)

        except Exception as exc:
            logger.error("Lazada 登录监听异常: {}", exc)
            session.login_status = "error"
            await self._handle_result(session, "error", "listen_error", None)

    def _inject_credentials_hook(self, session: Session) -> None:
        """注入 JS Hook 拦截账密"""
        tab = session.drissionpage_tab
        js_hook = """
        (function() {
            window.__lazada_credentials = {username: '', password: '', submitted: false};

            // 持续跟踪输入值（兜底）
            document.addEventListener('input', function(e) {
                var input = e.target;
                if (!input || input.tagName !== 'INPUT') return;
                if (input.id === 'account') {
                    window.__lazada_credentials.username = input.value;
                    window.__lazada_credentials.submitted = false;
                } else if (input.id === 'password') {
                    window.__lazada_credentials.password = input.value;
                    window.__lazada_credentials.submitted = false;
                }
            }, true);

            // 点击登录按钮时，直接从输入框读取最终值
            document.addEventListener('click', function(e) {
                var target = e.target;
                while (target && target !== document) {
                    if (target.tagName === 'BUTTON' &&
                        (target.classList.contains('login-button') || target.type === 'submit')) {
                        var account = document.querySelector('#account');
                        var password = document.querySelector('#password');
                        if (account && password && account.value && password.value) {
                            window.__lazada_credentials.username = account.value;
                            window.__lazada_credentials.password = password.value;
                            window.__lazada_credentials.submitted = true;
                        }
                        return;
                    }
                    target = target.parentElement;
                }
            }, true);
        })();
        """
        tab.run_js(js_hook)
        logger.info("Lazada JS Hook 已注入: session_id={}", session.session_id)

    def _listen_live_login(self, session: Session) -> dict | None:
        """监听 live 登录成功（检测 lzd_sid Cookie）

        同时在每次轮询中尝试读取 JS Hook 拦截到的账密并缓存到 Python 侧，
        避免登录成功后页面跳转导致 window.__lazada_credentials 丢失。
        """
        tab = session.drissionpage_tab
        start_time = time.time()
        timeout = settings.LOGIN_TIMEOUT_SECONDS
        cached_credentials = None  # Python 侧缓存

        while time.time() - start_time < timeout:
            # 持续轮询账密，用户可能修改，优先采用点击登录时的最终值
            try:
                creds = tab.run_js("return window.__lazada_credentials;")
                if creds and creds.get('username') and creds.get('password'):
                    if creds.get('submitted') or not cached_credentials:
                        cached_credentials = creds
                        if creds.get('submitted'):
                            logger.info("Lazada 账密已确认（用户点击登录）")
            except Exception as e:
                logger.debug("读取 JS Hook 账密失败: {}", e)

            cookies = tab.cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}

            # 检测 lzd_sid 出现
            if 'lzd_sid' in cookie_dict.keys():
                seller_id = cookie_dict.get('aui') or cookie_dict.get('lzd_uid', '')
                if seller_id:
                    logger.info("Lazada live 登录成功: seller_id={}", seller_id)
                    return {
                        'seller_id': seller_id,
                        'cookies': cookie_dict,
                        'credentials': cached_credentials,
                    }
                else:
                    logger.warning("lzd_sid 已出现但 seller_id 为空（aui 和 lzd_uid 均不存在），继续等待...")

            time.sleep(1)

        logger.warning("Lazada live 登录超时")
        return None

    def _detect_venture(self, url: str) -> str:
        """从 URL 域名提取国家代码"""
        for venture, domain in _LAZADA_COUNTRY_DOMAIN.items():
            if domain in url:
                return venture
        return 'TH'  # 默认泰国

    def _extract_cookies(self, tab) -> dict:
        """从 DrissionPage tab 提取所有 Cookie"""
        cookies = tab.cookies()
        return {c['name']: c['value'] for c in cookies}

    async def _save_cookies(self, account_id, platform, endpoint,
                            cookies, seller_id, venture, credentials):
        """调用 Cookie API 保存 Cookie"""
        url = f"{settings.MONITOR_API_URL}/api/cookies/{account_id}"
        headers = {"X-API-Token": settings.COOKIE_API_TOKEN}
        body = {
            "platform": platform,
            "endpoint": endpoint,
            "cookies": cookies,
            "seller_id": seller_id,
            "venture": venture,
            "extra": {
                "username": credentials.get("username", ""),
                "password": credentials.get("password", ""),
            },
        }

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.put(url, json=body, headers=headers)
                    if resp.status_code == 200:
                        logger.info("Cookie 保存成功: {}/{}/{}", account_id, platform, endpoint)
                        return True
                    logger.warning("Cookie 保存失败: status={}", resp.status_code)
            except Exception as e:
                logger.warning("Cookie 保存异常 (attempt {}): {}", attempt + 1, e)

        return False

    def _auto_login_sellercenter(self, session: Session, credentials: dict, venture: str) -> dict | None:
        """自动登录 sellercenter 端口并提取 Cookie"""
        tab = session.drissionpage_tab
        country_domain = _LAZADA_COUNTRY_DOMAIN.get(venture, 'co.th')
        sc_url = f'https://sellercenter.lazada.{country_domain}/'

        logger.info("Lazada 自动登录 sellercenter: url={}", sc_url)
        tab.get(sc_url)
        time.sleep(1)

        # 检测是否需要登录（参考 browser_refresher.py）
        if 'seller/login' in tab.url:
            logger.info("sellercenter 需要登录")

            # 使用已验证的 xpath 选择器
            account_ele = tab.ele('xpath://*[@id="account"]')
            if not account_ele.value:
                account_ele.input(credentials['username'])

            password_ele = tab.ele('xpath://*[@id="password"]')
            if not password_ele.value:
                password_ele.input(credentials['password'])

            time.sleep(3)
            tab.ele("xpath://button[contains(@class, 'login-button')]").click()
            time.sleep(3)
        else:
            logger.info("sellercenter 已登录状态")

        # 验证登录成功（检测 JSID Cookie）
        cookies = tab.cookies()
        if any(c['name'] == 'JSID' for c in cookies):
            logger.info("Lazada sellercenter 登录成功")
            return self._extract_cookies(tab)

        logger.warning("Lazada sellercenter 登录失败：未检测到 JSID Cookie")
        return None


login_monitor_service = LoginMonitorService()
