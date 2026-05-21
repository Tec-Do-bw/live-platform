#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Organization  : CCR DataCenter
# @Time          : 2023/2/15
# @File          : server.py
# @Author        : XBW
# @Function      : selenium自动化常用的方法集成类
import platform
import time
import json
import hashlib
import requests
import copy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, parse_qs, urlsplit
from typing import List, Dict, Any, Optional
from utils.logger import logger
from utils.adspower_client import get_adspower_client, AdsPowerRateLimitError, AdsPowerApiError
from DrissionPage import Chromium, ChromiumOptions
from core.config import Settings


class BrowserApi():
    flag = True

    # 增量模式固定取 T-1（昨天）作为最新可用日期，不再做结算延迟判断

    # 时区映射：根据 group_name 关键词推断时区
    TIMEZONE_MAP = {
        '新加坡': 'Asia/Singapore',
        '印尼': 'Asia/Jakarta',
        '泰国': 'Asia/Bangkok',
        '越南': 'Asia/Ho_Chi_Minh',
        '马来': 'Asia/Kuala_Lumpur',
        '菲律宾': 'Asia/Manila',
        '美国': 'America/New_York',
        '墨西哥': 'America/Mexico_City',
        '巴西': 'America/Sao_Paulo',
    }

    def __init__(self):
        # 保持原有标志位语义，并提供 Shopee 趋势接口参数占位
        self.flag = True
        self.shopee_trends_params: Optional[Dict[str, Any]] = None
        # run_js_fetch 注入请求的指纹集合，用于 get_listened_data 去重
        self._injected_fingerprints: set = set()

    def _make_request_fingerprint(self, url: str, method: str = 'GET', body: str = '') -> str:
        """根据 URL 路径 + 方法 + 规范化 body 生成请求指纹

        用于识别 run_js_fetch 注入的请求，防止 get_listened_data 重复捕获。
        body 会经过 json.loads → json.dumps(sort_keys=True) 规范化，
        消除 Python 端和浏览器端 JSON 序列化顺序差异。
        """
        url_path = url.split('?')[0]
        normalized_body = ''
        if body:
            try:
                parsed = json.loads(body) if isinstance(body, str) else body
                normalized_body = json.dumps(parsed, sort_keys=True, separators=(',', ':'))
            except (json.JSONDecodeError, TypeError):
                normalized_body = str(body)
        raw = f"{method.upper()}|{url_path}|{normalized_body}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_shopee_trends_params(self) -> Dict[str, Any]:
        """获取 Shopee 趋势接口参数，优先使用爬虫注入的时间范围"""
        params = self.shopee_trends_params or {}
        start_time = params.get("startTime")
        end_time = params.get("endTime")
        return {
            "startTime": str(start_time) if start_time is not None else None,
            "endTime": str(end_time) if end_time is not None else None,
        }

    def _infer_timezone(self, group_name: str) -> str:
        """根据 group_name 推断时区，默认 Asia/Singapore"""
        matched = [(kw, tz) for kw, tz in self.TIMEZONE_MAP.items() if kw in group_name]
        if len(matched) > 1:
            logger.warning(f'group_name "{group_name}" 匹配多个时区: {matched}，使用第一个: {matched[0][1]}')
        if matched:
            return matched[0][1]
        return 'Asia/Singapore'  # 默认新加坡时区

    def _generate_daily_payloads(
        self,
        original_payload: dict,
        timezone_str: str,
        full_collection: bool
    ) -> List[dict]:
        """生成多个日期的 live/stats 请求 Payload

        Args:
            original_payload: 原始拦截到的请求体
            timezone_str: 目标时区（如 'Asia/Singapore'）
            full_collection: 是否全量采集

        Returns:
            List[dict]: 每个元素是一个完整的请求 Payload
        """
        try:
            tz = ZoneInfo(timezone_str)
        except KeyError:
            logger.warning(f'时区 "{timezone_str}" 不存在，回退到 Asia/Singapore')
            tz = ZoneInfo('Asia/Singapore')
        except Exception as e:
            logger.warning(f'时区 {timezone_str} 初始化异常（{type(e).__name__}），回退到 Asia/Singapore: {e}')
            tz = ZoneInfo('Asia/Singapore')

        # 获取目标时区的当前时间，动态推算最新可用日期
        now_local = datetime.now(tz)
        today_local = now_local.date()

        latest_available_date = today_local - timedelta(days=1)

        logger.info(
            f'动态可用日期推算: 时区={timezone_str}, 当地时间={now_local.strftime("%Y-%m-%d %H:%M")}, '
            f'latest_available_date={latest_available_date}'
        )

        # 确定目标日期列表
        if full_collection:
            # 全量：近 28 天（latest_available_date - 27 ~ latest_available_date，含端点）
            first_day = latest_available_date - timedelta(days=27)
            target_dates = []
            current = first_day
            while current <= latest_available_date:
                target_dates.append(current)
                current += timedelta(days=1)
        else:
            # 增量：latest_available_date 往前 3 天
            target_dates = [
                latest_available_date,
                latest_available_date - timedelta(days=1),
                latest_available_date - timedelta(days=2),
            ]

        # 为每个日期生成 Payload（24 小时 UTC 窗口，自定义时间模式）
        payloads = []
        for target_date in target_dates:
            # start_timestamp = D at UTC 00:00:00
            start_dt = datetime.combine(target_date, datetime.min.time())
            start_dt_utc = start_dt.replace(tzinfo=timezone.utc)
            start_timestamp = int(start_dt_utc.timestamp())

            # end_timestamp = (D + 1 day) at UTC 00:00:00
            end_dt = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
            end_dt_utc = end_dt.replace(tzinfo=timezone.utc)
            end_timestamp = int(end_dt_utc.timestamp())

            # 深拷贝原始 Payload 并替换 time_selector
            payload = copy.deepcopy(original_payload)
            time_selector = {
                "period": 2,
                "granularity": 1,  # 自定义时间
                "end_timestamp": end_timestamp,
                "start_timestamp": start_timestamp,
                "timezone_offset": "0"
            }
            payload['request']['params'][0]['time_selector'] = time_selector
            payloads.append(payload)

        logger.info(f'生成 {len(payloads)} 个日期的 live/stats Payload（时区: {timezone_str}，模式: {"全量" if full_collection else "增量"}）')
        return payloads

    def _handle_live_stats_injection(
        self,
        tab,
        url: str,
        packet,
        request_body,
        group_name: str,
        full_collection: bool,
        collected_data: list,
        account_id: str = '',
    ) -> None:
        """处理 live/stats 接口的多日数据注入

        Args:
            tab: DrissionPage tab 对象
            url: 请求 URL
            packet: 网络数据包对象
            request_body: 原始请求体
            group_name: 账号分组名
            full_collection: 是否全量采集
            collected_data: 采集数据列表（会被修改）
            account_id: 账号 ID（browser_id），用于持久化请求上下文
        """
        # 采集监控：持久化 live_stats 请求上下文，供补采模块复用
        if account_id:
            try:
                from urllib.parse import urlparse as _urlparse
                import json as _json
                from monitor import get_monitor

                _parsed = _urlparse(url)
                _base_url = f"{_parsed.scheme}://{_parsed.netloc}"
                _qs = _parsed.query or ""

                # 获取 headers
                _headers = {}
                if hasattr(packet, 'request') and hasattr(packet.request, 'headers'):
                    _headers = dict(packet.request.headers) if packet.request.headers else {}

                # 获取 cookies
                _cookies = []
                try:
                    _cookies = self.get_cookies(tab)
                except Exception:
                    pass

                # payload_template：保存完整原始 request_body
                _payload = request_body if isinstance(request_body, str) else _json.dumps(request_body)

                get_monitor().save_request_context(
                    account_id=account_id,
                    context_type='live_stats',
                    api_base_url=_base_url,
                    query_string=_qs,
                    headers=_json.dumps(_headers),
                    cookies=_json.dumps(_cookies),
                    payload_template=_payload,
                )
            except Exception:
                pass  # 监控不阻塞采集

        try:
            # 根据 group_name 推断时区，生成多日 Payload
            tz_str = self._infer_timezone(group_name)
            payloads = self._generate_daily_payloads(
                request_body, tz_str, full_collection
            )

            if not payloads:
                logger.warning("未生成任何 live/stats 日期 Payload")
                return

            fetch_url = url
            headers = packet.request.headers
            batch_size = 2  # 每批并发数
            mode_label = "全量" if full_collection else "增量"
            logger.info(f'live/stats {mode_label}采集：共 {len(payloads)} 条请求，每批 {batch_size} 条，时区 {tz_str}')

            # 分批并发发送
            for batch_start in range(0, len(payloads), batch_size):
                batch = payloads[batch_start:batch_start + batch_size]
                fetch_requests = [{
                    'url': fetch_url,
                    'method': 'POST',
                    'headers': headers,
                    'body': json.dumps(payload),
                } for payload in batch]

                fetch_results = self.run_js_fetch(tab, fetch_requests)

                for j, result in enumerate(fetch_results):
                    idx = batch_start + j
                    if not result:
                        logger.warning(f'live/stats 第 {idx + 1} 条请求超时')
                    elif result.get('response'):
                        collected_data.append({
                            'url': result.get('url'),
                            'method': 'POST',
                            'request': batch[j],
                            'response': result.get('response')
                        })
                        logger.info(f'live/stats 第 {idx + 1}/{len(payloads)} 条数据获取成功')
                    else:
                        logger.warning(f'live/stats 第 {idx + 1} 条请求异常: {result}')

        except Exception as e:
            logger.warning(f"处理并发送 live/stats 新请求失败: {e}")

    @staticmethod
    def get_group_ids_by_platform(platform: str, api_url: str = None) -> List[str]:
        """根据 platform 动态获取匹配的 group_ids

        查询所有分组，筛选 group_name 包含 platform 的分组
        命名规范：{国家}团队-{媒体}（如 印尼团队-tiktok）

        Args:
            platform: 平台名称（如 tiktok、shopee）
            api_url: AdsPower API地址，默认从配置读取

        Returns:
            List[str]: 匹配的 group_id 列表
        """
        from utils.adspower_client import AdsPowerClient

        # 根据是否传入自定义 api_url 构造客户端
        if api_url is None:
            client = get_adspower_client()
        else:
            client = AdsPowerClient(base_url=api_url)

        matched_groups = []

        try:
            logger.info(f'动态查询分组，筛选 platform={platform}')

            # 调用 /api/v1/group/list 获取所有分组
            group_resp = client.get('/api/v1/group/list', params={"page_size": 100})

            groups = group_resp.get('data', {}).get('list', [])
            logger.info(f'获取到 {len(groups)} 个分组')

            # 筛选 group_name 包含 platform 的分组（不区分大小写）
            platform_lower = platform.lower()
            exclude_prefixes = tuple(Settings.ADSPOWER_CONFIG.get("exclude_group_prefixes", []))
            for group in groups:
                group_name = group.get('group_name', '')
                if platform_lower in group_name.lower() and not (exclude_prefixes and group_name.startswith(exclude_prefixes)):
                    group_id = group.get('group_id')
                    if group_id:
                        matched_groups.append({
                            'group_id': group_id,
                            'group_name': group_name
                        })
                        logger.info(f'匹配分组: {group_name} (ID: {group_id})')

            logger.info(f'筛选完成，匹配到 {len(matched_groups)} 个分组')
            return [g['group_id'] for g in matched_groups]

        except (AdsPowerRateLimitError, AdsPowerApiError) as e:
            logger.error(f'查询分组列表失败: {e}')
            return []
        except Exception as e:
            logger.exception(f'动态获取分组失败: {e}')
            return []

    @staticmethod
    def get_user_ids_from_group_ids(group_ids: List[str], api_url: str = None) -> List[Dict[str, str]]:
        """根据 group_ids 直接获取用户信息列表

        使用 group_id 直接查询环境列表，跳过名称查询步骤

        Args:
            group_ids: 分组ID列表
            api_url: AdsPower API地址，默认从配置读取

        Returns:
            List[Dict]: 包含 user_id、group_name、name 的字典列表
        """
        from utils.adspower_client import AdsPowerClient

        if api_url is None:
            client = get_adspower_client()
        else:
            client = AdsPowerClient(base_url=api_url)

        all_users = []

        try:
            for group_id in group_ids:
                logger.info(f'查询分组ID {group_id} 下的环境...')

                try:
                    user_resp = client.get('/api/v1/user/list', params={"group_id": group_id, "page_size": 100})
                except (AdsPowerRateLimitError, AdsPowerApiError) as e:
                    logger.error(f'查询环境失败，跳过分组ID {group_id}: {e}')
                    continue

                users = user_resp.get('data', {}).get('list', [])
                user_infos = [
                    {
                        'user_id': user.get('user_id'),
                        'group_name': user.get('group_name', ''),
                        'name': user.get('name', ''),
                    }
                    for user in users if user.get('user_id')
                ]

                logger.info(f'分组ID {group_id} 下找到 {len(user_infos)} 个环境')
                all_users.extend(user_infos)

            logger.info(f'总共获取到 {len(all_users)} 个用户')
            return all_users

        except Exception as e:
            logger.exception(f'从group_ids获取user_ids失败: {e}')
            return []

    @staticmethod
    def get_user_ids_from_groups(group_names: List[str], api_url: str = None) -> List[Dict[str, str]]:
        """从AdsPower分组中获取用户信息列表

        Args:
            group_names: 分组名称列表
            api_url: AdsPower API地址，默认从配置读取

        Returns:
            List[Dict]: 包含 user_id、group_name、name 的字典列表
        """
        from utils.adspower_client import AdsPowerClient

        if api_url is None:
            client = get_adspower_client()
        else:
            client = AdsPowerClient(base_url=api_url)

        all_users = []

        try:
            for group_name in group_names:
                # 1. 查询分组获取group_id
                logger.info(f'查询分组: {group_name}')
                try:
                    group_resp = client.get('/api/v1/group/list', params={"group_name": group_name, "page_size": 100})
                except (AdsPowerRateLimitError, AdsPowerApiError) as e:
                    logger.error(f'查询分组失败，跳过该分组 {group_name}: {e}')
                    continue

                groups = group_resp.get('data', {}).get('list', [])
                if not groups:
                    logger.warning(f'未找到分组: {group_name}')
                    continue

                group_id = groups[0].get('group_id')
                logger.info(f'分组 {group_name} 的ID: {group_id}')

                # 2. 根据group_id查询用户列表
                logger.info(f'查询分组 {group_name} 下的环境...')
                try:
                    user_resp = client.get('/api/v1/user/list', params={"group_id": group_id, "page_size": 100})
                except (AdsPowerRateLimitError, AdsPowerApiError) as e:
                    logger.error(f'查询环境失败，跳过该分组 {group_name}: {e}')
                    continue

                users = user_resp.get('data', {}).get('list', [])
                user_infos = [
                    {
                        'user_id': user.get('user_id'),
                        'group_name': user.get('group_name', group_name),
                        'name': user.get('name', ''),
                    }
                    for user in users if user.get('user_id')
                ]

                logger.info(f'分组 {group_name} 下找到 {len(user_infos)} 个环境')
                all_users.extend(user_infos)

            logger.info(f'总共获取到 {len(all_users)} 个用户')
            return all_users

        except Exception as e:
            logger.exception(f'获取user_ids失败: {e}')
            return []

    @staticmethod
    def get_driver(id):
        """获取浏览器驱动实例

        Args:
            id: 浏览器ID

        Returns:
            Chromium: DrissionPage浏览器实例
        """
        # 通过统一客户端启动浏览器
        client = get_adspower_client()
        user_resp = client.get('/api/v1/browser/start', params={"user_id": str(id)})
        logger.info(f'打开浏览器响应: {user_resp}')
        debuggerAddress = user_resp['data']['ws']['selenium']
        chrome_driver = user_resp['data']['webdriver']

        # 配置DrissionPage
        co = ChromiumOptions()
        co.set_address(debuggerAddress)
        co.set_browser_path(chrome_driver)

        driver = Chromium(addr_or_opts=co)
        driver.set.auto_handle_alert()
        logger.info(f'浏览器驱动创建成功，browser_id: {id}')
        return driver

    def listen_api(self, tab, listen_urls: List[str], timeout: int = 60) -> None:
        """启动API监听器
        
        Args:
            tab: 浏览器标签页
            listen_urls: 需要监听的URL列表（部分匹配）
            timeout: 监听超时时间（秒）
        """
        try:
            # 启动监听器，监听所有请求
            tab.listen.start(listen_urls)
            logger.info(f'API监听器已启动，监听 {len(listen_urls)} 个API接口')
        except Exception as e:
            logger.error(f'启动API监听器失败: {e}')
            raise

    def get_listened_data(self, tab, listen_urls: List[str],
                         wait_time: int = 5, count: int = None,
                         full_collection: bool = False, group_name: str = '',
                         account_id: str = '') -> List[Dict[str, Any]]:
        """获取拦截到的API数据

        Args:
            tab: 浏览器标签页
            listen_urls: 需要监听的URL列表
            wait_time: 每次轮询等待的时间（秒）
            count: 限制获取的数据包数量，None表示不限制
            full_collection: 是否全量采集模式
            group_name: 账号分组名称，用于推断时区
            account_id: 账号 ID（browser_id），用于持久化请求上下文

        Returns:
            List[Dict]: 拦截到的API数据列表，每个数据包含url、request、response
        """
        collected_data = []
        dupfilter_metricTrend = set()
        try:
            # 获取监听到的数据包
            packets = tab.listen.steps(timeout=wait_time, count=count)

            for packet in packets:
                try:
                    url = packet.url
                    # 检查URL是否匹配监听列表
                    url_before_query = url.split('?')[0]
                    matched = any(
                        url_before_query.endswith(listen_url) or
                        url_before_query.endswith(listen_url + '/') or
                        listen_url in url
                        for listen_url in listen_urls
                    )

                    if matched:
                        # 检查是否为 run_js_fetch 注入的重复包
                        _pkt_method = packet.method.upper() if packet.method else 'GET'
                        _pkt_body = packet.request.postData if packet.request else ''
                        _pkt_fp = self._make_request_fingerprint(url, _pkt_method, _pkt_body if _pkt_body else '')
                        if _pkt_fp in self._injected_fingerprints:
                            logger.debug(f'跳过 JS 注入的重复包: {url[:80]}...')
                            self._injected_fingerprints.discard(_pkt_fp)
                            continue

                        # 获取请求和响应数据
                        response_body = packet.response.body if packet.response else None
                        request_body = packet.request.postData if packet.request else None

                        # 当拦截到 live/stats 接口时，额外发送多日数据请求
                        if 'api/v2/insights/creator/live/stats' in url and packet.method.upper() == 'POST' and request_body and self.flag:
                            self.flag = False
                            self._handle_live_stats_injection(
                                tab, url, packet, request_body,
                                group_name, full_collection, collected_data,
                                account_id=account_id
                            )

                        # Shopee 实时趋势接口：仅补充 start/end，其他参数保持原请求
                        if 'api/supply/lm/sellercenter/realtime/dashboard/trends' in url and packet.method.upper() == 'GET':
                            try:
                                parsed_url = urlsplit(url)
                                base_params = parse_qs(parsed_url.query)
                                metricTrend = base_params.get("metricTrend", [])
                                if metricTrend:
                                    metricTrend = metricTrend[0]
                                    if metricTrend in dupfilter_metricTrend:
                                        continue
                                    dupfilter_metricTrend.add(metricTrend)
                                override = self._get_shopee_trends_params()
                                if override.get("startTime") is not None:
                                    base_params["startTime"] = [override["startTime"]]
                                if override.get("endTime") is not None:
                                    base_params["endTime"] = [override["endTime"]]

                                fetch_query = urlencode(base_params, doseq=True)
                                fetch_url = f"{url_before_query}?{fetch_query}" if fetch_query else url_before_query

                                headers = packet.request.headers if packet.request else {}

                                fetch_results = self.run_js_fetch(tab, [{
                                    'url': fetch_url,
                                    'method': 'GET',
                                    'headers': headers,
                                    'credentials': 'include',
                                }])
                                history_result = fetch_results[0]

                                if not history_result:
                                    logger.warning("等待 Shopee 趋势补全请求超时，未获取到异步结果")
                                elif history_result.get('response'):
                                    collected_data.append({
                                        'url': history_result.get('url') or fetch_url,
                                        'method': 'GET',
                                        'request': base_params,
                                        'response': history_result.get('response')
                                    })
                                    logger.info('成功获取并添加 Shopee 趋势补全数据')
                                    continue
                                else:
                                    logger.warning(f"Shopee 趋势补全请求返回异常: {history_result}")
                            except Exception as e:
                                logger.warning(f"处理 Shopee 趋势补全请求失败: {e}")

                        if response_body:  # 只收集有响应的数据
                            data = {
                                'url': url,
                                'method': packet.method,
                                'request': request_body if request_body else "No request body",
                                'response': response_body
                            }
                            # 当 URL 为 live/list 或 Shopee sessionList 时，附加 headers 供下游 JS 注入复用
                            if (
                                packet.request
                                and (
                                    'api/v2/insights/creator/live/list' in url
                                    or 'api/supply/lm/sellercenter/realtime/sessionList' in url
                                )
                            ):
                                raw_headers = packet.request.headers or {}
                                data['headers'] = {k: v for k, v in raw_headers.items() if not k.startswith(':')}
                            collected_data.append(data)
                            logger.info(f'拦截到API数据: {url[:100]}...')

                except Exception as e:
                    logger.warning(f'处理数据包时出错: {e}')
                    continue

            logger.info(f'API监听完成，共收集到 {len(collected_data)} 条数据')
            return collected_data
            
        except Exception as e:
            logger.error(f'获取监听数据失败: {e}')
            return collected_data

    def run_js_fetch(
        self,
        tab,
        requests: List[Dict[str, Any]],
        poll_timeout: float = 15.0,
        poll_interval: float = 0.5,
        max_retries: int = 0,
        retry_delay: float = 2.0,
    ) -> List[Dict[str, Any] | None]:
        """通过 JS 注入执行一个或多个并行 fetch 请求，poll 等待结果后清理

        Args:
            tab: DrissionPage tab 对象
            requests: fetch 请求描述列表，每个元素支持：
                - url (str): 请求 URL，必填
                - method (str): 'GET' 或 'POST'，默认 'GET'
                - headers (dict): 请求头，自动过滤 ':' 开头的伪头部
                - body (str): 请求体 JSON 字符串，仅 POST 有效
                - credentials (str): 如 'include'
            poll_timeout: poll 超时秒数
            poll_interval: poll 间隔秒数
            max_retries: 失败重试次数，0 表示不重试
            retry_delay: 重试间隔秒数

        Returns:
            与 requests 等长的列表，每个元素为:
            - {'response': ..., 'url': ...} 成功
            - {'error': ...} 失败
            - None 超时
        """
        results = [None] * len(requests)

        # 校验请求 URL 格式，拒绝非 http/https
        for req in requests:
            parsed = urlsplit(req.get('url', ''))
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                logger.error(f'run_js_fetch: 非法 URL，跳过: {req.get("url", "")[:100]}')
                return [None] * len(requests)

        # 记录每个注入请求的指纹，供 get_listened_data 去重
        for req in requests:
            fp = self._make_request_fingerprint(
                req['url'],
                req.get('method', 'GET'),
                req.get('body', ''),
            )
            self._injected_fingerprints.add(fp)

        for attempt in range(max_retries + 1):
            ts = int(time.time() * 1000)
            keys = [f"__jsfetch_{ts}_{i}" for i in range(len(requests))]

            try:
                # 初始化 window 变量（在 Promise.all 外部，避免分号出现在数组字面量内）
                init_js = '; '.join(f"window['{k}'] = null" for k in keys) + '; '

                # 构造每个 fetch 的 JS 表达式（不含 window 初始化）
                fetch_snippets = []
                for i, req in enumerate(requests):
                    key = keys[i]
                    url_js = json.dumps(req['url'])
                    method = req.get('method', 'GET').upper()

                    # 过滤伪头部
                    raw_headers = req.get('headers', {})
                    filtered = {k: v for k, v in raw_headers.items() if not k.startswith(':')}
                    headers_js = json.dumps(filtered)

                    # 构造 fetch options（所有值经 json.dumps 转义，防止 JS 注入）
                    opts_parts = [f"method: {json.dumps(method)}", f"headers: {headers_js}"]
                    if req.get('credentials'):
                        opts_parts.append(f"credentials: {json.dumps(req['credentials'])}")
                    if method == 'POST' and req.get('body'):
                        body_js = json.dumps(req['body'])
                        opts_parts.append(f"body: {body_js}")
                    opts_str = ', '.join(opts_parts)

                    snippet = f"""fetch({url_js}, {{ {opts_str} }})
                        .then(async r => {{
                            if (!r.ok) {{ window['{key}'] = {{ error: 'status_' + r.status }}; return; }}
                            try {{
                                window['{key}'] = {{ response: await r.json(), url: {url_js} }};
                            }} catch (e) {{
                                window['{key}'] = {{ error: 'parse_error: ' + String(e) }};
                            }}
                        }})
                        .catch(e => {{ window['{key}'] = {{ error: String(e) }}; }})"""
                    fetch_snippets.append(snippet)

                # 多请求用 Promise.all 包裹
                if len(fetch_snippets) > 1:
                    inner = ',\n'.join(fetch_snippets)
                    js_code = f"{init_js}Promise.all([{inner}\n]);"
                else:
                    js_code = f"{init_js}{fetch_snippets[0]};"

                tab.run_js(js_code)

                # Poll 等待结果
                results = [None] * len(requests)
                poll_start = time.time()
                while time.time() - poll_start < poll_timeout:
                    for i, key in enumerate(keys):
                        if results[i] is None:
                            val = tab.run_js(f"return window['{key}'];")
                            if val is not None:
                                results[i] = val
                    if all(r is not None for r in results):
                        break
                    time.sleep(poll_interval)

                # 判断是否全部成功
                all_ok = all(r and r.get('response') for r in results)
                if all_ok:
                    return results

                if attempt < max_retries:
                    logger.warning(f'JS fetch 第 {attempt + 1} 次未全部成功，{retry_delay}s 后重试')
                    time.sleep(retry_delay)

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f'JS fetch 异常（第 {attempt + 1} 次）: {e}，重试...')
                    time.sleep(retry_delay)
                else:
                    logger.error(f'JS fetch 异常（已重试 {max_retries} 次）: {e}')
            finally:
                # 清理 window 变量
                cleanup = '; '.join(f"delete window['{k}']" for k in keys)
                try:
                    tab.run_js(cleanup)
                except Exception:
                    pass
        time.sleep(.5)
        return results

    def stop_listen(self, tab) -> None:
        """停止API监听
        
        Args:
            tab: 浏览器标签页
        """
        try:
            tab.listen.stop()
            self._injected_fingerprints.clear()
            logger.info('API监听器已停止')
        except Exception as e:
            logger.warning(f'停止API监听器失败: {e}')

    def get_cookies(self, tab: Chromium, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取浏览器cookies
        
        Args:
            tab: 浏览器驱动实例
            domain: 指定域名，None表示获取所有cookies
            
        Returns:
            List[Dict]: cookies列表
        """
        try:
            cookies = tab.cookies(all_domains=True,all_info=True)
            if domain:
                # 过滤指定域名的cookies
                pass# cookies = [c for c in cookies if domain in c.get('domain', '')]
            logger.debug(f'获取到 {len(cookies)} 个cookies')
            return cookies
        except Exception as e:
            logger.error(f'获取cookies失败: {e}')
            return []

    def simulate_click_tabs(self, tab, selector: str, 
                          wait_time: int = 3, max_clicks: int = 10) -> int:
        """模拟点击页面tab切换
        
        Args:
            tab: 浏览器标签页
            selector: tab元素选择器
            wait_time: 每次点击后等待时间（秒）
            max_clicks: 最大点击次数
            
        Returns:
            int: 实际点击次数
        """
        clicked_count = 0
        try:
            # 等待页面加载
            time.sleep(2)
            
            # 查找所有匹配的tab元素
            elements = tab.eles(selector, timeout=9)
            
            if not elements:
                logger.warning(f'未找到匹配选择器的元素: {selector}')
                return 0
            
            logger.info(f'找到 {len(elements)} 个tab元素，开始依次点击')
            
            for i, element in enumerate(elements):
                if i >= max_clicks:
                    break
                try:
                    element.click()
                    clicked_count += 1
                    logger.info(f'点击第 {clicked_count} 个tab')
                except Exception as e:
                    logger.warning(f'点击第 {i+1} 个tab失败: {e}')
                    continue
                finally:
                    time.sleep(wait_time)
            
            logger.info(f'Tab点击完成，共点击 {clicked_count} 个')
            return clicked_count
            
        except Exception as e:
            logger.error(f'模拟点击tabs失败: {e}')
            return clicked_count

    def wait_page_load(self, tab, url='', timeout: int = 15,
                       wait_page_map: Optional[Dict[str, str]] = None) -> bool:
        """等待页面加载完成

        根据 url 从配置的 wait_page_map 中查找目标元素，等待其加载完成。

        Args:
            tab: 浏览器标签页
            url: 页面URL，用于查找对应的等待元素选择器
            timeout: 超时时间（秒）
            wait_page_map: 运行时传入的等待映射，优先于全局配置

        Returns:
            bool: 是否加载完成
        """
        # 从平台配置的 wait_page_map 中查找等待元素
        wait_ele = ''
        if url:
            runtime_wait_page_map = wait_page_map or {}
            if url in runtime_wait_page_map:
                wait_ele = runtime_wait_page_map[url]
            else:
                for platform_config in Settings.PLATFORM_CONFIG.values():
                    config_wait_page_map = platform_config.get('wait_page_map', {})
                    if url in config_wait_page_map:
                        wait_ele = config_wait_page_map[url]
                        break

        if not wait_ele:
            return True

        flag = tab.wait.eles_loaded(wait_ele, timeout=timeout)
        return flag

    def close_driver(self, driver: Chromium) -> None:
        """关闭浏览器
        
        Args:
            driver: 浏览器实例
        """
        try:
            # 停止监听
            self.stop_listen(driver.latest_tab)
            
            # 关闭所有标签页
            for tab_id in driver.tab_ids:
                try:
                    driver.get_tab(tab_id).close()
                except:
                    pass
            
            # 退出浏览器
            driver.quit()
            logger.info('浏览器关闭成功')
        except Exception as e:
            logger.error(f'关闭浏览器失败: {e}')



    def simulate_slider(self, distance, tab):
        """
        模拟滑动验证码行为。
        """
        element = 'xpath://*[@class="geetest_slider_button"]'
        self.page.actions.hold((element))

        index = 0
        for x in self.geetest3.get_geetest_tracks(distance)[:-5]:
            if index == 0:
                self.page.actions.move(offset_x=x, duration=.1)
            else:
                self.page.actions.move(offset_x=x - self.geetest3.get_geetest_tracks(distance)[index - 1], duration=.1)
            index += 1

        time.sleep(0.1)
        self.page.actions.release((element))



if __name__ == '__main__':
    BrowserApi()
    tab = BrowserApi.get_driver('k16w7jdu')