#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/11/12
# @Author     : XBW
# @File       : tiktok.py
# @Description: TikTok平台直播数据采集爬虫

import copy
import json
import time
import random
import requests
from typing import Any, Dict, List
from datetime import timezone as tz
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

from utils.logger import logger
from crawlers.browser.base import BaseLiveCrawler

import ddddocr


class TikTokLiveCrawler(BaseLiveCrawler):
    """TikTok平台直播数据采集爬虫"""

    # shop.tiktok.com 页面 → 侧边栏点击选择器映射（URL 偏移恢复用）
    NAV_CLICK_MAP = {
        "https://shop.tiktok.com/streamer/compass/livestream-analytics/view":
            'xpath://*[@_key="/compass/livestream-analytics/view"]//*[@class="flex w-full items-center "]',
        "https://shop.tiktok.com/streamer/compass/product-analysis/view":
            'xpath://*[@_key="/compass/product-analysis/view"]//*[@class="flex w-full items-center "]',
        "https://shop.tiktok.com/streamer/compass/data-overview/view":
            'xpath://*[@_key="/compass/data-overview/view"]//*[@class="flex w-full items-center "]',
    }

    # 直接 URL 导航最大重试次数（墨西哥等已知 URL 偏移的国家可覆写为 1）
    URL_NAV_MAX_RETRY = 3

    def __init__(self, browser_id: str = None, full_collection: bool = False, **kwargs: Any) -> None:
        super().__init__(browser_id=browser_id, full_collection=full_collection, **kwargs)
        self.processed_room_ids = set()
        self.login_checked = False  # 标记是否已检测过登录状态
        self._api_base_url = "https://shop.tiktok.com"  # 默认值，运行时从 live/list URL 动态更新
        self.user_info = None  # 存储用户信息（user_id, user_name 等）

        # 滑块验证相关属性
        self.ocr = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
        self.URL_NAV_MAX_RETRY = 1 if self.group_name in ['巴西团队-tiktok'] else 3

    def get_platform_name(self) -> str:
        """返回TikTok平台标识"""
        return 'tiktok'

    # ==================== 导航方法 ====================

    def _verify_navigation(self, expected_url: str) -> bool:
        """验证导航结果，支持路径匹配（应对域名/参数差异）"""
        current_url = self.tab.url
        if current_url == expected_url:
            return True
        return urlparse(current_url).path == urlparse(expected_url).path

    def _dismiss_popup(self) -> None:
        """关闭页面弹窗（arco-design 关闭按钮），避免遮挡导航点击"""
        try:
            close_btn = self.tab.ele('xpath://*[@class="arco-icon arco-icon-close "]', timeout=1)
            if close_btn:
                close_btn.click()
                logger.debug(f'[{self.browser_id}] 已关闭页面弹窗')
                time.sleep(0.5)
        except Exception:
            pass

    def _navigate_by_url(self, url: str, max_retry: int = None) -> bool:
        """直接 URL 导航，带重试"""
        if max_retry is None:
            max_retry = self.URL_NAV_MAX_RETRY
        for i in range(max_retry):
            self.tab.get(url)
            self._dismiss_popup()
            if self._verify_navigation(url):
                return True
            logger.warning(f'[{self.browser_id}] 页面加载不为目标url:{url}，重试 {i+1}/{max_retry}')
            time.sleep(1)
        return self._verify_navigation(url)

    def _navigate_by_click(self, url: str) -> bool:
        """通过侧边栏点击导航到目标页面（URL 偏移恢复策略）

        流程：确认侧边栏元素存在 → 点击导航 → 验证 URL → 失败重试
        """
        selector = self.NAV_CLICK_MAP.get(url, '')
        if not selector:
            return False

        # 确保侧边栏元素已加载（可能需要先导航到 shop 域名）
        page_flag = self.tab.wait.eles_loaded(selector, timeout=3)
        if not page_flag:
            logger.warning(f'[{self.browser_id}] 点击导航元素未就绪，先直接导航: {url}')
            self._navigate_by_url(url)

        # 点击导航，带重试
        for attempt in range(3):
            try:
                self._dismiss_popup()
                element = self.tab.ele(selector, timeout=5)
                if element:
                    self.tab.run_js('arguments[0].click();', element)
                    time.sleep(3)
                    if self._verify_navigation(url):
                        logger.info(f'[{self.browser_id}] 点击导航成功: {url}')
                        return True

                logger.warning(f'[{self.browser_id}] 点击导航第{attempt + 1}次尝试失败')
                if attempt < 2:
                    self._navigate_by_url(url)
                    time.sleep(3)
            except Exception as e:
                logger.error(f'[{self.browser_id}] 点击导航异常(第{attempt + 1}次): {e}')

        logger.warning(f'[{self.browser_id}] 点击导航全部失败，最终回退直接URL导航: {url}')
        self.tab.get(url)
        return True

    def _navigate_to_page(self, url: str) -> bool:
        """导航到目标页面，支持 URL 偏移自动恢复

        策略：直接 URL 导航 → 失败时对 shop 页面尝试点击导航恢复
        子类可覆写此方法改变导航策略（如墨西哥优先点击导航）
        """
        # 已在目标页面
        if self._verify_navigation(url):
            return True

        # 直接 URL 导航
        if self._navigate_by_url(url):
            return True

        # URL 偏移恢复：对 shop 页面尝试点击导航
        if url in self.NAV_CLICK_MAP:
            logger.warning(
                f'[{self.browser_id}] [{self.group_name}] '
                f'URL 偏移检测到，启动点击导航恢复: {url}'
            )
            return self._navigate_by_click(url)

        logger.error(f'[{self.browser_id}] 导航失败且无恢复策略: {url}')
        return False

    def visit_page_and_collect(self, url: str) -> Dict[str, Any]:
        """访问TikTok页面并收集数据

        Args:
            url: 页面URL

        Returns:
            Dict: 页面采集结果
        """
        result = {'url': url, 'apis_count': 0, 'data_sent': 0}

        try:
            # 1. 导航到目标页面（支持 URL 偏移自动恢复）
            nav_success = self._navigate_to_page(url)
            if not nav_success:
                logger.error(f'[{self.browser_id}] 导航失败: {url}')
                # 导航失败时也需要检测登录状态（可能是因为登出导致的）
                if not self.login_checked:
                    self.login_checked = True
                    if not self._check_login_status():
                        self.send_login_callback("logout", reason="导航失败，检测到账号登出")
                        self.login_status = False
                return result

            logger.info(f'TikTok页面加载中...')

            # 2. 等待页面加载
            wait_time = self.config.get('wait_time', 8)
            self.browser_api.wait_page_load(self.tab, url=url, timeout=wait_time)
            time.sleep(2)

            # 首次访问时检测登录状态
            if not self.login_checked:
                time.sleep(3)
                self.login_checked = True
                if not self._check_login_status():
                    # 发送登出回调
                    self.send_login_callback("logout", reason="sessionid cookie 缺失，账号登出")
                    self.login_status = False
                    return result
                else:
                    # 发送登录成功回调
                    self.send_login_callback("success")

            if 'detail' in url and 'roomId' in url:
                # 直播详情页需要更少的等待时间
                wait_time = self.config.get('detail_page_wait', 4)

            # 2.5 检测并处理滑块验证码
            self._detect_and_handle_slider()
            
            # 3. TikTok特定：如果是直播详情页，点击tabs切换
            if 'detail' in url and 'roomId' in url:
                tab_selector = self.config.get('tab_selector', '')
                if tab_selector:
                    tab_interval = self.config.get('tab_click_interval', 3)
                    self.browser_api.simulate_click_tabs(
                        self.tab, 
                        tab_selector, 
                        wait_time=tab_interval
                    )
            
            # 4. 获取cookies
            domain = self._extract_domain(url)
            cookies = self.browser_api.get_cookies(self.tab, domain=domain)
            
            # 5. 全量采集模式：页面特定前置操作（滚动/日期切换），在收集数据前执行
            if self.full_collection:
                if 'livecenter.tiktok.com/replay' in url:
                    self._scroll_replay_list()
                elif 'data-overview/view' in url and 'detail' not in url:
                    self._select_28_days_range()

            # 6. 收集拦截到的API数据
            # 增量模式下 replay 页面限制4个包，全量模式不限制
            if not self.full_collection and 'livecenter.tiktok.com/replay' in url:
                listen_count = 4
            else:
                listen_count = 40
            api_data_list = self.browser_api.get_listened_data(
                self.tab,
                self.config['listen_urls'],
                wait_time=wait_time,
                count=listen_count,
                full_collection=self.full_collection,
                group_name=self.group_name,
                account_id=self.browser_id
            )
            
            result['apis_count'] = len(api_data_list)
            logger.info(f'收集到 {len(api_data_list)} 条TikTok API数据')
            
            # 7. 处理并发送数据
            for api_data in api_data_list:
                try:
                    # live/list 原始拦截数据不上报，由 JS 注入扩展指标请求单独上报
                    is_live_list = 'api/v2/insights/creator/live/list' in api_data['url']

                    if not is_live_list:
                        # 格式化为API上报消息
                        message = self.format_api_message(
                            url=api_data['url'],
                            request_body=api_data['request'],
                            response_body=api_data['response'],
                            cookies=cookies
                        )

                        # 通过API请求发送数据
                        if self.send_api_request(message):
                            result['data_sent'] += 1

                    # 处理TikTok特殊逻辑（直播列表处理）
                    self.handle_special_logic(api_data['url'], api_data['response'],api_data=api_data)

                    # 采集监控：记录 replay_info
                    if self.batch_id and 'replay/info' in api_data['url']:
                        from monitor import get_monitor
                        get_monitor().record(
                            self.batch_id, self.browser_id, 'replay_info',
                            status='success', response_size=len(str(api_data.get('response', '')))
                        )

                    # 采集监控：记录 live/stats 日期级采集状态
                    if self.batch_id and 'live/stats' in api_data.get('url', ''):
                        try:
                            from monitor import get_monitor
                            from monitor.tracker import extract_target_date
                            # api_data 的请求体 key 是 'request'（不是 'request_body'）
                            _request_body = api_data.get('request', {})
                            if isinstance(_request_body, str):
                                import json as _json
                                _request_body = _json.loads(_request_body)
                            _target_date = extract_target_date(_request_body)
                            if _target_date:
                                get_monitor().record_daily_stats(
                                    self.batch_id, self.browser_id,
                                    _target_date, 'live_stats', 'success'
                                )
                        except Exception:
                            pass  # 监控不阻塞采集

                except Exception as e:
                    logger.error(f'处理TikTok API数据失败: {e}')
                    continue
            
        except Exception as e:
            logger.error(f'访问TikTok页面失败: {url}, 错误: {e}')
            raise
        
        return result
    
    def handle_special_logic(self, url: str, response: Any, **kwargs: Any) -> None:
        """处理TikTok平台特殊逻辑
        
        Args:
            url: API URL
            response: 响应数据
        """
        try:
            # TikTok直播列表特殊处理
            if 'api/v2/insights/creator/live/list' in url:
                self._handle_tiktok_live_list(response,**kwargs)
        except Exception as e:
            logger.warning(f'处理TikTok特殊逻辑失败: {e}')
    
    def _handle_tiktok_live_list(self, response: Any,**kwargs :Any) -> None:
        """处理TikTok直播列表，通过 JS 注入 fetch 获取直播趋势数据

        增量模式：仅采集昨天的直播间
        全量模式：采集所有已结束的直播间

        Args:
            response: API响应数据
        """

        def is_full_collection(d):
            params = d.get("request", {}).get("params", [])
            if not params:
                return False
            tsel = params[0].get("time_selector", {})
            stats = params[0].get("stats_types", [])
            return ("base_timestamp" in tsel and "timezone_offset" in tsel) or any(x in stats for x in [100, 101])

        try:
            # 过滤数据 只获取全量的数据接口
            api_data = kwargs.get("api_data", {})
            request = api_data.get("request", {})
            if not is_full_collection(request):
                return

            # 提取 headers、base URL 和查询参数（供 JS 注入使用）
            headers = api_data.get("headers", {})
            list_url = api_data.get("url", "")
            parsed = urlparse(list_url)
            self._api_base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else "https://shop.tiktok.com"
            # 保留 live/list 原始 URL 的查询参数（user_language, locale, aid, fp 等），
            # 不同账号/地区的参数不同，trend/chart 请求需要继承这些参数否则返回 no login
            self._api_query_string = parsed.query or ""
            # 提取 carrier_region（供 core/stats 请求使用）
            _query_params = parse_qs(parsed.query)
            self._carrier_region = _query_params.get('carrier_region', [''])[0].upper()

            # 采集监控：持久化请求上下文，供补采模块复用
            if self.batch_id and headers:
                try:
                    import json as _json
                    from monitor import get_monitor
                    _filtered_headers = {k: v for k, v in headers.items() if not k.startswith(':')}
                    if not any(k.lower() == 'content-type' for k in _filtered_headers):
                        _filtered_headers['Content-Type'] = 'application/json'
                    # 获取 cookies，供补采模块复用
                    _cookies = []
                    try:
                        _cookies = self.browser_api.get_cookies(self.tab)
                    except Exception:
                        pass

                    # 保存 trend_chart 请求上下文（用于补采 trend_gmv/trend_stats）
                    get_monitor().save_request_context(
                        account_id=self.browser_id,
                        context_type='trend_chart',
                        api_base_url=self._api_base_url,
                        query_string=self._api_query_string,
                        headers=_json.dumps(_filtered_headers),
                        cookies=_json.dumps(_cookies),
                    )

                    # 保存 live_list 请求上下文（用于补采 live_list）
                    # 保存真实的请求 body，供补采时复用
                    _payload = _json.dumps(request) if request else '{}'
                    get_monitor().save_request_context(
                        account_id=self.browser_id,
                        context_type='live_list',
                        api_base_url=self._api_base_url,
                        query_string=self._api_query_string,
                        headers=_json.dumps(_filtered_headers),
                        cookies=_json.dumps(_cookies),
                        payload_template=_payload,
                    )
                except Exception:
                    pass  # 监控不阻塞采集

            if not headers:
                logger.warning('live/list 未携带 headers，JS 注入可能失败')

            # JS 注入获取扩展指标数据（不阻塞主流程）
            try:
                self._fetch_live_list_extended_via_js(request, headers, list_url)
            except Exception as e:
                logger.warning(f'live/list 扩展指标 JS 注入失败: {e}')

            # 解析响应
            if isinstance(response, str):
                if len(response) < 10000:  # 响应太小，跳过
                    return
                response_json = json.loads(response)
            else:
                response_json = response

            # 提取直播间列表
            _first_segment = response_json.get('data', {}).get('segments', [{}])[0]
            stats = _first_segment.get('timed_lists', [{}])[0].get('stats', [])

            # 提取 creator_id（供 core/stats 请求使用）
            _creator_id_list = _first_segment.get('filter', {}).get('creator_id', [])
            self._creator_id = _creator_id_list[0] if _creator_id_list else ''

            if not stats:
                # 账号无直播间，记录 live_list 采集成功（空列表）
                if self.batch_id:
                    try:
                        from monitor import get_monitor
                        get_monitor().record_rooms(self.batch_id, self.browser_id, [])
                    except Exception:
                        pass  # 监控不阻塞采集
                return

            # 增量模式：基于账号时区计算前三天起始时间戳用于过滤
            if not self.full_collection:
                # 从请求体中提取账号时区偏移（秒），如 25200=UTC+7 印尼，-21600=UTC-6 墨西哥
                tz_offset_seconds = 0
                try:
                    params = request.get("request", {}).get("params", [])
                    if params:
                        tz_offset_seconds = params[0].get("time_selector", {}).get("timezone_offset", 0)
                        if isinstance(tz_offset_seconds, str):
                            tz_offset_seconds = int(tz_offset_seconds)
                except (ValueError, TypeError, IndexError):
                    pass

                account_tz = tz(timedelta(seconds=tz_offset_seconds))
                now = datetime.now(account_tz)
                three_days_ago = now - timedelta(days=3)
                three_days_ago_start = datetime(
                    three_days_ago.year, three_days_ago.month, three_days_ago.day,
                    0, 0, 0, tzinfo=account_tz
                )
                three_days_ago_timestamp = int(three_days_ago_start.timestamp())
                logger.info(
                    f'增量过滤：账号时区 UTC{tz_offset_seconds//3600:+d}，当地日期 {now.strftime("%Y-%m-%d")}，'
                    f'过滤 {three_days_ago.strftime("%Y-%m-%d")} 00:00:00 之前的直播间'
                )

            # 筛选直播间（先不标记 processed，成功后再标记）
            room_id_list = []
            for stat in stats:
                live_end_timestamp = stat.get('live_end_timestamp', 0)
                room_id = stat.get('live_id')

                # 过滤无效、正在直播或已处理的直播间
                if not room_id or live_end_timestamp == 0 or room_id in self.processed_room_ids:
                    continue

                # 增量模式只取近三天的，全量模式取全部
                if not self.full_collection:
                    if live_end_timestamp < three_days_ago_timestamp:
                        continue

                room_id_list.append(room_id)

            if room_id_list:
                mode_desc = '全部' if self.full_collection else '近三天的'
                logger.info(f'找到 {len(room_id_list)} 个{mode_desc}直播间，将通过 JS 注入获取趋势数据')

                # 采集监控：记录 live_list 及 rooms GMV 数据
                if self.batch_id:
                    from monitor import get_monitor
                    _monitor = get_monitor()
                    rooms_data = []
                    for stat in stats:
                        rid = stat.get('live_id')
                        if rid and rid in room_id_list:
                            revenue = stat.get('revenue', {})
                            rooms_data.append({
                                'room_id': str(rid),
                                'room_name': stat.get('live_name', ''),
                                'live_start_ts': stat.get('live_start_timestamp', 0),
                                'live_end_ts': stat.get('live_end_timestamp', 0),
                                'duration': stat.get('live_duration', 0),
                                'cover_url': stat.get('live_meta', {}).get('cover_url', ''),
                                'revenue': revenue.get('amount', '0'),
                                'currency_code': revenue.get('currency_code', ''),
                                'direct_revenue': stat.get('direct_revenue', {}).get('amount', '0'),
                                'item_sold_cnt': stat.get('item_sold_cnt', 0),
                                'view_cnt': stat.get('view_cnt', 0),
                                'ctr': stat.get('ctr', 0),
                                'c_o': stat.get('c_o', 0),
                            })
                    _monitor.record_rooms(self.batch_id, self.browser_id, rooms_data)

                success_count = 0
                fail_count = 0
                failed_rooms = []
                core_stats_success = 0
                core_stats_fail = 0

                # 依次 JS 注入获取趋势数据
                for i, room_id in enumerate(room_id_list):
                    logger.info(f'[{i+1}/{len(room_id_list)}] JS注入获取直播趋势: {room_id}')

                    try:
                        result = self._fetch_trend_chart_via_js(room_id, headers)
                        if result['success']:
                            success_count += 1
                            # 成功后才标记为已处理
                            self.processed_room_ids.add(room_id)
                        else:
                            fail_count += 1
                            failed_rooms.append(room_id)
                    except Exception as e:
                        logger.error(f'JS注入获取趋势数据异常 {room_id}: {e}')
                        fail_count += 1
                        failed_rooms.append(room_id)

                    # core/stats：采集直播大屏核心统计数据
                    try:
                        core_result = self._fetch_core_stats_via_js(
                            room_id, headers,
                            creator_id=self._creator_id,
                            country=self._carrier_region
                        )
                        if core_result['success']:
                            core_stats_success += 1
                        else:
                            core_stats_fail += 1
                    except Exception as e:
                        logger.error(f'JS注入获取核心统计异常 {room_id}: {e}')
                        core_stats_fail += 1

                    # 间隔 2~4 秒，避免请求过快
                    if i < len(room_id_list) - 1:
                        time.sleep(random.uniform(2, 4))

                # 汇总日志
                logger.info(
                    f'直播采集完成：总计 {len(room_id_list)} 个, '
                    f'trend 成功 {success_count} 失败 {fail_count}, '
                    f'core_stats 成功 {core_stats_success} 失败 {core_stats_fail}'
                )
                if failed_rooms:
                    logger.warning(f'采集失败的直播间: {failed_rooms}')

                # B类告警：live/list 有数据但 trend/chart 全部失败
                if success_count == 0 and fail_count > 0:
                    logger.warning(
                        f'[B类告警] [{self.browser_id}] [{self.group_name}] '
                        f'live/list 返回 {len(room_id_list)} 个直播间但 trend/chart 全部失败 '
                        f'(fail={fail_count})，请检查 JS 注入或 API 权限'
                    )
            else:
                # 近期无需处理的直播间，仅在首次调用时记录空 live_list，
                # 避免覆盖已有的房间元数据（GMV、房间名等）
                if self.batch_id and not self.processed_room_ids:
                    try:
                        from monitor import get_monitor
                        get_monitor().record_rooms(self.batch_id, self.browser_id, [])
                    except Exception:
                        pass  # 监控不阻塞采集

        except Exception as e:
            logger.warning(f'处理TikTok直播列表失败: {e}')

    def _fetch_live_list_extended_via_js(self, original_request: dict, headers: dict, list_url: str) -> None:
        """通过 JS 注入请求 live/list 扩展指标（补充 stats_types）

        深拷贝原始请求体，替换 stats_types 为扩展列表后发送，
        响应通过 format_api_message + send_api_request 上报。

        Args:
            original_request: 原始拦截到的请求体
            headers: 从 live/list 请求中提取的 headers
            list_url: 完整的 live/list URL（含 query string）
        """
        EXTENDED_STATS_TYPES = [
            10, 15, 11, 12, 13, 14, 80, 88, 95, 90, 72, 96, 70, 86,
            20, 29, 25, 50, 41, 42, 21, 40, 100, 101, 62, 61
        ]

        # 过滤伪头部，确保 Content-Type
        fetch_headers = {k: v for k, v in headers.items() if not k.startswith(':')}
        if not any(k.lower() == 'content-type' for k in fetch_headers):
            fetch_headers['Content-Type'] = 'application/json'

        # 深拷贝原始请求体，替换 stats_types
        body_dict = copy.deepcopy(original_request)
        body_dict["request"]["params"][0]["stats_types"] = EXTENDED_STATS_TYPES
        body = json.dumps(body_dict)

        results = self.browser_api.run_js_fetch(
            self.tab,
            [{'url': list_url, 'method': 'POST', 'headers': fetch_headers,
              'credentials': 'include', 'body': body}],
            max_retries=1,
            retry_delay=2.0,
        )
        result = results[0]

        if result and result.get('response'):
            cookies = self.browser_api.get_cookies(self.tab)
            msg = self.format_api_message(
                url=list_url,
                request_body=body,
                response_body=result['response'],
                cookies=cookies,
            )
            if self.send_api_request(msg):
                logger.info('live/list 扩展指标数据上报成功')
        else:
            logger.warning(f'live/list 扩展指标 JS 注入无响应: {result}')

    def _fetch_trend_chart_via_js(self, room_id: str, headers: dict, max_retries: int = 2) -> dict:
        """通过 JS 注入 fetch 请求获取直播趋势数据

        对每个 room_id 并行发送两个 POST 请求（Promise.all），
        poll window 变量获取异步结果，失败自动重试。

        Args:
            room_id: 直播间 ID
            headers: 从 live/list 请求中提取的 headers
            max_retries: 失败重试次数

        Returns:
            dict: {'success': bool, 'sent_count': int, 'error': str|None}
        """
        # 继承 live/list 原始 URL 的查询参数（不同账号/地区参数不同）
        trend_path = "/api/v1/insights/creator/liveroom/recap/trend/chart"
        query_string = getattr(self, '_api_query_string', '')
        if query_string:
            trend_url = f"{self._api_base_url}{trend_path}?{query_string}"
        else:
            trend_url = f"{self._api_base_url}{trend_path}"

        body1 = json.dumps({
            "request": {
                "room_filter": {"room_id": room_id, "query_online": True},
                "stats_types": [3],
                "granularity": 1
            }
        })
        body2 = json.dumps({
            "request": {
                "room_filter": {"room_id": room_id, "query_online": True},
                "stats_types": [3, 20, 341, 21, 22, 12, 16, 23, 50, 51, 40],
                "granularity": 1
            }
        })

        # 确保 headers 中包含 Content-Type
        fetch_headers = dict(headers)
        if not any(k.lower() == 'content-type' for k in fetch_headers):
            fetch_headers['Content-Type'] = 'application/json'

        # 通过统一方法并行发送两个请求
        results = self.browser_api.run_js_fetch(
            self.tab,
            [
                {'url': trend_url, 'method': 'POST', 'headers': fetch_headers,
                 'credentials': 'include', 'body': body1},
                {'url': trend_url, 'method': 'POST', 'headers': fetch_headers,
                 'credentials': 'include', 'body': body2},
            ],
            max_retries=max_retries,
            retry_delay=2.0,
        )
        result1, result2 = results[0], results[1]

        success = (
            result1 and result1.get('response') and
            result2 and result2.get('response')
        )

        if success:
            cookies = self.browser_api.get_cookies(self.tab)
            sent_count = 0

            # 上报第一个请求（stats_types=[3]）
            msg1 = self.format_api_message(
                url=trend_url,
                request_body=body1,
                response_body=result1['response'],
                cookies=cookies
            )
            if self.send_api_request(msg1):
                sent_count += 1

            # 上报第二个请求（stats_types=[3,20,341,...]）
            msg2 = self.format_api_message(
                url=trend_url,
                request_body=body2,
                response_body=result2['response'],
                cookies=cookies
            )
            if self.send_api_request(msg2):
                sent_count += 1

            logger.info(f'room {room_id} 趋势数据获取成功，上报 {sent_count} 条')
            # 采集监控：记录 trend 成功
            if self.batch_id:
                from monitor import get_monitor
                _m = get_monitor()
                _m.record(self.batch_id, self.browser_id, 'trend_gmv', room_id=str(room_id), status='success')
                _m.record(self.batch_id, self.browser_id, 'trend_stats', room_id=str(room_id), status='success')
            return {'success': True, 'sent_count': sent_count, 'error': None}

        # 所有重试都失败
        error_msg = f"result1={'有error' if result1 and isinstance(result1, dict) and result1.get('error') else '超时'}, result2={'有error' if result2 and isinstance(result2, dict) and result2.get('error') else '超时'}"
        logger.error(f'room {room_id} 趋势数据获取失败（已重试 {max_retries} 次）: {error_msg}')
        # 采集监控：记录 trend 失败
        if self.batch_id:
            from monitor import get_monitor
            _m = get_monitor()
            _m.record(self.batch_id, self.browser_id, 'trend_gmv', room_id=str(room_id), status='failed')
            _m.record(self.batch_id, self.browser_id, 'trend_stats', room_id=str(room_id), status='failed')
        return {'success': False, 'sent_count': 0, 'error': error_msg}

    def _fetch_core_stats_via_js(self, room_id: str, headers: dict,
                                 creator_id: str, country: str,
                                 max_retries: int = 2) -> dict:
        """通过 JS 注入获取直播大屏核心统计数据（流量分析-流量转化）"""
        core_stats_path = "/api/v1/insights/workbench/live/detail/core/stats"

        # core/stats 的 query params 与 live/list 不同，需要从 live/list 中提取公共设备参数
        # 并替换 app_name、添加 vertical=3、移除不需要的参数
        raw_qs = getattr(self, '_api_query_string', '')
        params = parse_qs(raw_qs, keep_blank_values=True)
        # 只保留设备/浏览器相关参数
        KEEP_KEYS = {
            'device_id', 'fp', 'device_platform', 'cookie_enabled',
            'screen_width', 'screen_height', 'browser_language', 'browser_platform',
            'browser_name', 'browser_version', 'browser_online', 'timezone_name',
        }
        core_params = {k: v[0] for k, v in params.items() if k in KEEP_KEYS}
        core_params['app_name'] = 'i18n_ecom_shop'
        core_params['vertical'] = '3'
        core_qs = '&'.join(f'{k}={v}' for k, v in core_params.items())
        core_stats_url = f"{self._api_base_url}{core_stats_path}?{core_qs}" if core_qs else f"{self._api_base_url}{core_stats_path}"

        body = json.dumps({
            "request": {
                "room_filter": {
                    "room_id": room_id,
                    "is_content_type": 1,
                    "creator_id": creator_id,
                    "country": country
                },
                "stats_types": [
                    23, 20, 325, 310, 39, 29, 312, 313, 332, 330, 10, 323,
                    315, 314, 349, 241, 3, 2, 5, 18, 290, 291, 292,
                    -23, -20, -39, -330, -10, -3, -2, -18
                ]
            }
        }, separators=(',', ':'))


        fetch_headers = {k: v for k, v in headers.items() if not k.startswith(':')}
        if not any(k.lower() == 'content-type' for k in fetch_headers):
            fetch_headers['Content-Type'] = 'application/json'

        results = self.browser_api.run_js_fetch(
            self.tab,
            [{'url': core_stats_url, 'method': 'POST', 'headers': fetch_headers,
              'credentials': 'include', 'body': body}],
            max_retries=max_retries,
            retry_delay=2.0,
        )
        result = results[0]

        if result and result.get('response'):
            cookies = self.browser_api.get_cookies(self.tab)
            msg = self.format_api_message(
                url=core_stats_url,
                request_body=body,
                response_body=result['response'],
                cookies=cookies
            )
            sent = self.send_api_request(msg)
            logger.info(f'room {room_id} 核心统计数据{"上报成功" if sent else "上报失败"}')
            return {'success': True, 'sent_count': 1 if sent else 0, 'error': None}

        error_msg = f"{'有error' if result and isinstance(result, dict) and result.get('error') else '超时'}"
        logger.error(f'room {room_id} 核心统计数据获取失败（已重试 {max_retries} 次）: {error_msg}')
        return {'success': False, 'sent_count': 0, 'error': error_msg}

    def _detect_and_handle_slider(self) -> bool:
        """检测并处理滑块验证码
        
        Returns:
            bool: 是否成功处理滑块
        """
        try:
            attempt = 0
            while 1:
                attempt += 1
                # 检测页面是否存在滑块
                if not self._check_slider_exists():
                    logger.debug('页面中未检测到滑块验证码')
                    return False
                
                logger.info(f'第 {attempt} 次尝试滑块验证')
                
                # 获取滑块距离
                distance = self._get_slider_distance()
                
                logger.info(f'计算出滑块滑动距离: {distance}px')
                
                # 执行滑块操作
                if self._perform_slider_action(distance):
                    logger.success('滑块验证成功！')
                    return True
                else:
                    logger.warning(f'第 {attempt} 次尝试：滑块验证失败，准备重试...')
                    time.sleep(2)
            
        except Exception as e:
            logger.error(f'处理滑块验证异常: {e}')
            return False
    
    def _check_slider_exists(self) -> bool:
        """检查页面中是否存在滑块验证码

        Returns:
            bool: 页面中是否存在滑块
        """
        try:
            self.tab.wait.eles_loaded('xpath://*[@class="sc-eNQAEJ dhEdIP"]',timeout=5)
            # 检查是否存在滑块容器
            slider_container = self.tab.ele('xpath://*[@id="captcha-verify-image"]', timeout=2)
            if not slider_container:
                return False
            self.background_url = self.tab.ele('xpath://*[@id="captcha-verify-image"]', timeout=2).attr('src')

            # 检查是否存在滑块按钮
            slider_button = self.tab.ele('xpath://*[@class="sc-eNQAEJ dhEdIP"]', timeout=2)
            if not slider_button:
                return False
            self.target_url = self.tab.ele('xpath://*[@id="captcha-verify-image"]/../img[2]', timeout=2).attr('src')
            logger.debug(f'背景图片\t{self.background_url}')
            logger.debug(f'目标图片\t{self.target_url}')
            return True

        except Exception as e:
            logger.debug(f'检查滑块是否存在时出错: {e}')
            return False
    
    def _get_slider_distance(self) -> int:
        """获取滑块需要滑动的距离
        
        Returns:
            int: 滑动距离（像素），如果获取失败返回None
        """
        try:
            background_response = requests.get(self.background_url)
            target_response = requests.get(self.target_url)

            ocr_result = self.ocr.slide_match(target_response.content, background_response.content)
            
            # 转换坐标
            x = int(ocr_result['target'][0])
            # 根据原始图片宽度(550px)转换为实际滑块宽度(340px)
            distance = int(int(x) / 550 * 340) - 5
            
            return distance
        except Exception as e:
            logger.error(f'获取滑块距离异常: {e}')
            return None
    
    def _perform_slider_action(self, distance: int) -> bool:
        """执行滑块操作，模拟用户滑动
        
        Args:
            distance: 滑块需要滑动的距离
            
        Returns:
            bool: 是否成功滑动
        """
        try:
            element = 'xpath://*[@class="sc-eNQAEJ dhEdIP"]'
            ele = self.tab.ele(element)
            ele.drag(distance,  random.randint(-2, 2),random.uniform(0.5,1))
            
            time.sleep(2)
            
            # 检查是否验证成功（检查滑块是否消失）
            try:
                slider = self.tab.ele('xpath://*[@id="captcha_container"]', timeout=2)
                if not slider:
                    logger.success('滑块已消失，验证成功')
                    return True
            except:
                logger.success('滑块已消失，验证成功')
                return True
            
            logger.warning('滑块仍然存在，验证可能未成功')
            return False

        except Exception as e:
            logger.error(f'执行滑块操作异常: {e}')
            return False

    def _check_login_by_api(self) -> tuple[bool, dict | None]:
        """通过账号信息接口检测 TikTok 登录状态

        相比只检查 Cookie，此方法能：
        1. 确认 Cookie 真实有效（而非仅存在）
        2. 获取用户身份信息（user_id/user_name）
        3. 检测账号封禁/权限异常

        Returns:
            tuple[bool, dict | None]: (是否登录, 用户信息字典)
                - (True, {...}): 登录成功，返回用户信息
                - (False, {}): 明确的登录失败（API 返回失败状态）
                - (False, None): 接口调用异常（网络错误、解析失败等），需降级
        """
        try:
            # 构造请求 URL
            api_url = f"{self._api_base_url}/api/v1/streamer_desktop/account_info/get?version=1"

            # 使用 run_js_fetch 发起 GET 请求
            results = self.browser_api.run_js_fetch(
                self.tab,
                [{
                    'url': api_url,
                    'method': 'GET',
                    'credentials': 'include',
                }],
                max_retries=1,
                retry_delay=1.0,
            )

            result = results[0]
            if not result or not result.get('response'):
                logger.warning(f'[{self.browser_id}] 账号信息接口无响应')
                return False, None

            # 获取响应数据（run_js_fetch 返回的 response 可能是 str 或 dict）
            response = result['response']
            if isinstance(response, str):
                try:
                    response_data = json.loads(response)
                except json.JSONDecodeError:
                    logger.error(f'[{self.browser_id}] 账号信息接口返回非 JSON 格式')
                    return False, None
            elif isinstance(response, dict):
                response_data = response
            else:
                logger.error(f'[{self.browser_id}] 账号信息接口返回未知格式: {type(response)}')
                return False, None

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
                    f'[{self.browser_id}] TikTok 登录验证成功: '
                    f'user_name={user_info["user_name"]}, user_id={user_info["user_id"]}'
                )
                return True, user_info
            else:
                # 登录失败或账号异常（明确的失败，不是异常）
                logger.warning(
                    f'[{self.browser_id}] TikTok 登录验证失败: '
                    f'code={code}, message={message}'
                )
                return False, {}

        except Exception as e:
            logger.error(f'[{self.browser_id}] 调用账号信息接口异常: {e}')
            # 接口调用失败时返回 (False, None)，用于降级到 Cookie 检测
            return False, None

    def _check_login_status_by_cookie(self) -> bool:
        """通过 Cookie 检测登录状态（降级方案）

        通过检查 sessionid cookie 是否存在且未过期判断

        Returns:
            bool: True表示已登录，False表示已登出
        """
        try:
            current_url = self.tab.url.lower()
            if 'tiktok.com/login' in current_url:
                logger.warning(f'当前页面处于登录路径: {current_url}，判定为未登录状态')
                return False

            # 获取完整的 cookie 信息列表
            cookie_list = self.tab.cookies(all_info=True)

            # 查找 sessionid cookie
            session_cookie = None
            for cookie in cookie_list:
                if cookie.get('name') == 'sessionid':
                    session_cookie = cookie
                    break

            if not session_cookie:
                logger.warning('TikTok sessionid cookie 缺失')
                return False

            # 检查 cookie 值是否为空
            if not session_cookie.get('value'):
                logger.warning('TikTok sessionid cookie 值为空')
                return False

            # 检查是否过期
            expires = session_cookie.get('expires', 0)
            current_time = int(time.time())

            # 提前一天的秒数: 24 * 60 * 60 = 86400
            buffer_time = 86400

            if expires > 0 and (expires - buffer_time) < current_time:
                logger.warning(f'TikTok sessionid cookie 已过期 (expires={expires}, now={current_time})')
                return False

            logger.info(f'检测到有效的 TikTok 登录Cookie (sessionid, expires={expires})')
            return True

        except Exception as e:
            logger.error(f'检测 TikTok 登录状态失败: {e}')
            return False

    def _check_login_status(self) -> bool:
        """检测 TikTok 账号登录状态（组合策略）

        优先使用 API 验证，失败时降级到 Cookie 检测

        Returns:
            bool: True表示已登录，False表示已登出
        """
        # 1. 优先使用 API 检测
        is_logged_in, user_info = self._check_login_by_api()

        # 2. API 成功：记录用户信息
        if is_logged_in and user_info:
            self.user_info = user_info  # 存储用户信息供日志使用
            return True

        # 3. API 明确返回登录失败（user_info 不为 None）
        if not is_logged_in and user_info is not None:
            return False

        # 4. API 调用异常（user_info 为 None），降级到 Cookie 检测
        logger.warning(f'[{self.browser_id}] API 验证异常，降级到 Cookie 检测')
        return self._check_login_status_by_cookie()

    def _scroll_replay_list(self) -> None:
        """滚动 replay 页面列表容器到底部，触发全量数据加载"""
        MAX_SCROLL_TIMES = 50
        try:
            url = "https://livecenter.tiktok.com/replay"

            for i in range(3):
                container = self.tab.ele('.replayListContent-jBlzCz', timeout=8)
                if container:
                    break
                else:
                    self.tab.get(url)


            if not container:
                # 哈希类名 replayListContent-jBlzCz 可能因 TikTok 前端重新部署而失效，需及时更新
                logger.warning('未找到 replay 列表容器元素（类名可能已过期），跳过滚动')
                return

            logger.info('开始滚动 replay 列表加载全量数据...')
            last_scroll_top = -1
            no_change_count = 0

            for i in range(MAX_SCROLL_TIMES):
                container.scroll.to_bottom()
                time.sleep(random.uniform(2, 4))

                # 获取当前滚动位置
                current_scroll_top = self.tab.run_js(
                    'return document.querySelector(".replayListContent-jBlzCz")?.scrollTop || 0'
                )

                if current_scroll_top == last_scroll_top:
                    no_change_count += 1
                    if no_change_count >= 2:
                        logger.info(f'replay 列表已滚动到底部，共滚动 {i + 1} 次')
                        break
                else:
                    no_change_count = 0

                last_scroll_top = current_scroll_top

            else:
                logger.warning(f'replay 列表滚动达到上限 {MAX_SCROLL_TIMES} 次')

        except Exception as e:
            logger.error(f'滚动 replay 列表失败: {e}')

    def _select_28_days_range(self) -> None:
        """在 data-overview 页面切换日期范围为 Last 28 days

        兼容多种国家/地区的 TikTok 日期选择器 UI：
        1. arco-picker 样式：点击 arco-picker-prefix → 选择 "Last 28 days"
        2. flex 布局样式：直接点击包含 "28" 的第三个选项
        """
        try:
            # 方式1：flex 布局样式，检查第三个选项是否包含 "28"
            option_xpath = 'xpath://div[@class="flex items-center h-24"]/div/div[3]'
            option_el = self.tab.ele(option_xpath, timeout=3)
            if option_el and '28' in (option_el.text or ''):
                option_el.click()
                logger.info(f'已点击 28 天选项 (flex 布局): {option_el.text}')
                time.sleep(3)
                return

            # 方式2：arco-picker 样式
            picker = self.tab.ele('.arco-picker-prefix', timeout=3)
            if picker:
                picker.click()
                time.sleep(1)

                option = self.tab.ele('text:Last 28 days', timeout=3)
                if option:
                    option.click()
                    logger.info('已切换 data-overview 日期范围为 Last 28 days (arco-picker)')
                    time.sleep(3)
                    return
                else:
                    logger.warning('未找到 "Last 28 days" 选项')

            logger.warning('未找到任何可用的日期选择器元素，使用默认时间范围')

        except Exception as e:
            logger.error(f'切换日期范围失败: {e}')

