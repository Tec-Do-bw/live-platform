#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/11/12
# @Author     : XBW
# @File       : shopee.py
# @Description: Shopee平台直播数据采集爬虫
import copy
import math
import time
import json
import re
import requests
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode


from utils.logger import logger
from crawlers.browser.base import BaseLiveCrawler
from crawlers.constants import DataSource
from utils.request import RequestSession
from core.config import Settings
from monitor import get_monitor
from utils.adspower_client import get_adspower_client, AdsPowerRateLimitError, AdsPowerApiError

# 国家代码 → 货币符号映射（与 scripts/list_shopee_accounts.py 保持一致）
CURRENCY_MAPPING = {
    "id": {"currency": "IDR", "symbol": "Rp"},
    "my": {"currency": "MYR", "symbol": "RM"},
    "th": {"currency": "THB", "symbol": "฿"},
    "vn": {"currency": "VND", "symbol": "₫"},
    "ph": {"currency": "PHP", "symbol": "₱"},
    "sg": {"currency": "SGD", "symbol": "$"},
    "tw": {"currency": "TWD", "symbol": "NT$"},
    "br": {"currency": "BRL", "symbol": "R$"},
    "mx": {"currency": "MXN", "symbol": "$"},
}

class ShopeeLiveCrawler(BaseLiveCrawler):
    """Shopee平台直播数据采集爬虫"""

    SHOPEE_DOMAIN_PATTERN = re.compile(r'shopee\.(?:cn|com\.my|co\.id|co\.th|sg|vn|com\.br|com\.mx|ph)')

    # 分组名关键词 → Shopee国家域名后缀映射
    SHOPEE_COUNTRY_MAP = {
        "马来": "com.my",
        "印尼": "co.id",
        "泰国": "co.th",
        "新加坡": "sg",
        "越南": "vn",
        "巴西":  "com.br",
        "墨西哥": "com.mx"
    }

    # Shopee 国家域名 → 时区偏移（小时）映射
    SHOPEE_TIMEZONE_MAP = {
        "cn": 8,        # 跨境店 UTC+8
        "com.my": 8,    # 马来西亚 UTC+8
        "co.id": 7,     # 印尼 UTC+7
        "co.th": 7,     # 泰国 UTC+7
        "sg": 8,        # 新加坡 UTC+8
        "ph": 8,        # 菲律宾 UTC+8
        "vn": 7,        # 越南 UTC+7
        "com.br": -3,   # 巴西 UTC-3
        "com.mx": -6    # 墨西哥 UTC-6
    }

    def __init__(self, browser_id: str = None, full_collection: bool = False, **kwargs: Any) -> None:
        super().__init__(browser_id=browser_id, full_collection=full_collection, **kwargs)
        self.login_checked = False  # 标记是否已检测过登录状态
        self.replay_collected = False  # 标记是否已采集过回放数据
        self._country_yesterday_cache = None  # 缓存国家时区的昨天日期
        self._remark_cache = None  # 缓存 AdsPower remark，避免重复 API 请求
        # Shopee登录信息携带的媒体ID
        self.media_user_id = None
        self.media_shop_id = None
        self.username =  None
        # 缓存待发送的API数据，直到拿到媒体ID
        self.pending_messages = []

        # 判断是否跨境店（必须在解析域名之前）
        self.is_cross_border = self._resolve_cross_border()
        # 三层来源解析国家域名：remark > group_name > 默认值
        self.country_domain = self._resolve_prelogin_country_domain()
        # 深拷贝配置，避免修改全局共享对象，然后动态替换 page_urls 和 wait_page_map 域名
        self.config = copy.deepcopy(self.config)
        self._sync_country_runtime_config()
        self.processed_room_ids = set()
        self.session = RequestSession.get_session()
        headers = {
            "User-Agent": "language=zh-Hans app_type=1 platform=native_ios appver=34929 os_ver=14.2.0 Cronet/102.0.5005.61",
            "content-type": "application/json",
            "accept-language": "en-US,en"
        }
        self.session.headers.update( headers)




    def get_platform_name(self) -> str:
        """返回Shopee平台标识"""
        return 'shopee'

    def get_data_source(self) -> str:
        """返回数据源标识"""
        return DataSource.SHOPEE

    def _get_country_yesterday(self) -> str:
        """获取对应国家时区的昨天日期（YYYY-MM-DD 格式）。"""
        if self._country_yesterday_cache is None:
            tz_offset = self.SHOPEE_TIMEZONE_MAP.get(self.country_domain, 8)
            country_tz = timezone(timedelta(hours=tz_offset))
            country_now = datetime.now(country_tz)
            country_yesterday = country_now - timedelta(days=1)
            self._country_yesterday_cache = country_yesterday.strftime('%Y-%m-%d')
        return self._country_yesterday_cache

    def _get_country_date_range(self) -> List[str]:
        """生成逐日日期列表（YYYY-MM-DD 格式），增量7天/全量30天。"""
        tz_offset = self.SHOPEE_TIMEZONE_MAP.get(self.country_domain, 8)
        country_tz = timezone(timedelta(hours=tz_offset))
        country_now = datetime.now(country_tz)
        days = 30 if self.full_collection else 7
        return [
            (country_now - timedelta(days=i)).strftime('%Y-%m-%d')
            for i in range(1, days + 1)
        ]

    def _get_timezone_string(self) -> str:
        """获取时区字符串（如 +0800）。"""
        tz_offset = self.SHOPEE_TIMEZONE_MAP.get(self.country_domain, 8)
        tz_sign = '+' if tz_offset >= 0 else '-'
        return f'{tz_sign}{abs(tz_offset):04d}'

    def _get_country_code(self) -> str:
        """从域名提取国家代码（如 com.my -> my）。"""
        return self.country_domain.split('.')[-1]

    def _build_shopee_api_headers(self) -> Dict[str, str]:
        """构造 Shopee API 通用请求头。"""
        return {
            'x-region': self._get_country_code(),
            'x-region-domain': self.country_domain,
            'x-region-timezone': self._get_timezone_string(),
            'language': 'en',
            'x-env': 'live',
            'accept': 'application/json',
            'content-type': 'application/json',
        }

    def _parse_json_response(self, response: str | dict) -> dict:
        """统一解析 JSON 响应。"""
        return json.loads(response) if isinstance(response, str) else response

    def _get_base_url(self) -> str:
        """获取当前 Shopee Seller 域名。"""
        return f'https://seller.shopee.{self.country_domain}'

    def _replace_shopee_domain(self, text: str) -> str:
        """将 URL 中的 Shopee 国家域名统一替换为当前 country_domain。"""
        if not isinstance(text, str) or 'shopee.' not in text:
            return text
        return self.SHOPEE_DOMAIN_PATTERN.sub(f'shopee.{self.country_domain}', text)

    def _sync_country_runtime_config(self) -> None:
        """同步刷新当前国家域名对应的 page_urls 与 wait_page_map。"""
        self.config['page_urls'] = [
            self._replace_shopee_domain(url)
            for url in self.config.get('page_urls', [])
        ]
        self.config['wait_page_map'] = {
            self._replace_shopee_domain(k): v
            for k, v in self.config.get('wait_page_map', {}).items()
        }

    def _update_country_domain(self, country_domain: str) -> None:
        """更新国家域名并同步刷新运行时配置。"""
        if not country_domain or country_domain == self.country_domain:
            return
        self.country_domain = country_domain
        self._country_yesterday_cache = None
        self._sync_country_runtime_config()

    def _open_collection_page(self, url: str) -> None:
        """打开采集页面并按当前运行时配置等待页面就绪。"""
        wait_time = self.config.get('wait_time', 8)
        self.tab.get(url)
        self.browser_api.wait_page_load(
            self.tab,
            url=url,
            timeout=wait_time,
            wait_page_map=self.config.get('wait_page_map', {}),
        )
        time.sleep(5)

    def _initialize_first_visit(self, url: str) -> str | None:
        """首次访问前完成登录校验、自动登录和国家域名修正。"""
        target_url = self._replace_shopee_domain(url)
        self._open_collection_page(target_url)

        login_status = self._check_login_status()
        if login_status == "logged_out":
            logger.warning('检测到登出，尝试自动重新登录...')
            relogin_status = self._auto_relogin()
            if relogin_status != "logged_in":
                self.send_login_callback("logout", reason="cookies 缺失且自动登录失败")
                self.login_status = False
                return None
            logger.info('自动重新登录成功')
            self._open_collection_page(target_url)

        if not self._fetch_login_info_via_js():
            logger.error('获取 media IDs 失败')
            self.send_login_callback("success", reason="无法获取商家后台数据，可能权限不足")
            self.login_status = False
            return None

        validate_id = self._get_validate_id_from_remark()
        if validate_id and not self.is_cross_border:
            shop_country = self._get_shop_country_by_id(validate_id)
            if shop_country:
                correct_domain = self._country_code_to_domain(shop_country)
                if correct_domain != self.country_domain:
                    old_domain = self.country_domain
                    logger.warning(
                        f'检测到域名不匹配：分组推断={old_domain}, '
                        f'实际店铺国家={correct_domain}，切换到实际域名'
                    )
                    self._update_country_domain(correct_domain)
                    target_url = self._replace_shopee_domain(target_url)
                    logger.info(f'已更新 country_domain: {self.country_domain}，同步更新配置 URL')

                self._sync_remark_country_if_needed(validate_id, shop_country)
            else:
                logger.warning(f'无法查询店铺 {validate_id} 的国家，保持当前域名: {self.country_domain}')

        # 跨境店：反查实际国家用于币种上报（不改域名，始终保持 cn）
        if validate_id and self.is_cross_border:
            country_from_remark = self._get_country_from_remark()
            if not country_from_remark:
                shop_country = self._get_cross_border_shop_country(validate_id)
                if shop_country:
                    self._sync_remark_country_if_needed(validate_id, shop_country)
                else:
                    logger.warning(f'跨境店无法查询店铺 {validate_id} 的国家，币种上报可能为空')

        if not self._ensure_correct_shop(target_url):
            logger.error('店铺切换失败，终止采集')
            self.login_status = False
            return None

        current_url = getattr(self.tab, 'url', '')
        if current_url != target_url:
            self._open_collection_page(target_url)

        self.send_login_callback("success")
        self.login_checked = True
        return target_url

    def _build_request_headers(self, headers: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """清洗请求头，供 JS 注入复用。"""
        fetch_headers = {
            key: value
            for key, value in (headers or {}).items()
            if not str(key).startswith(':')
        }

        lowered_headers = {str(key).lower() for key in fetch_headers}
        if 'accept' not in lowered_headers:
            fetch_headers['accept'] = 'application/json, text/plain, */*'

        tab_url = getattr(self.tab, 'url', '')
        if 'referer' not in lowered_headers and isinstance(tab_url, str) and tab_url:
            fetch_headers['referer'] = tab_url

        return fetch_headers
    
    def _get_account_credentials(self) -> tuple:
        """从配置文件获取账号密码"""
        try:
            config_path = Path(__file__).parent.parent / 'resource' / 'accounts' /  'shopee_accounts.json'
            if not config_path.exists():
                logger.warning(f'账号配置文件不存在: {config_path}')
                return None, None
                
            with open(config_path, 'r', encoding='utf-8') as f:
                accounts = json.load(f)
            
            # 优先使用browser_id查找，如果没找到尝试default
            account_config = accounts.get(self.browser_id)
            
            if account_config:
                return account_config.get('username'), account_config.get('password')
            return None, None
        except Exception as e:
            logger.error(f'读取账号配置失败: {e}')
            return None, None

    def visit_page_and_collect(self, url: str) -> Dict[str, Any]:
        """访问页面并通过 sessionList + JS 注入采集数据。"""
        result = {'url': url, 'apis_count': 0, 'data_sent': 0}

        try:
            if not self.login_checked:
                prepared_url = self._initialize_first_visit(url)
                if not prepared_url:
                    return result
                url = prepared_url
            else:
                url = self._replace_shopee_domain(url)
                self._open_collection_page(url)

            # 登录信息获取成功后，采集回放数据（只采集一次）
            if not self.replay_collected:
                replay_stats = self.handle_shopee_replay()
                result['apis_count'] += replay_stats.get('apis_count', 0)
                result['data_sent'] += replay_stats.get('data_sent', 0)
                self.replay_collected = True

            if 'live/list' in url:
                page_stats = self._handle_live_list_page()
                result['apis_count'] = page_stats.get('apis_count', 0)
                result['data_sent'] = page_stats.get('data_sent', 0)
        except Exception as e:
            logger.error(f'访问页面失败: {url}, 错误: {e}')
            raise

        return result

    def _fetch_login_info_via_js(self) -> bool:
        """通过 JS 注入获取 login 接口数据。

        跨境店使用 CN 接口（get_session），本土店使用 MY 接口（api/v2/login）。
        """
        try:
            if self.is_cross_border:
                login_url = 'https://seller.shopee.cn/api/cnsc/selleraccount/get_session/'
            else:
                login_url = f'{self._get_base_url()}/api/v2/login/'

            headers = self._build_request_headers({
                'referer': getattr(self.tab, 'url', self._get_base_url()),
            })

            results = self.browser_api.run_js_fetch(
                self.tab,
                [{
                    'url': login_url,
                    'method': 'GET',
                    'headers': headers,
                    'credentials': 'include',
                }],
                max_retries=2,
            )

            if not results or not results[0] or not results[0].get('response'):
                logger.error('login 接口返回数据异常')
                return False

            response = results[0]['response']
            response_json = json.loads(response) if isinstance(response, str) else response

            if self.is_cross_border:
                results = self.browser_api.run_js_fetch(
                    self.tab,
                    [{
                        'url': 'https://seller.shopee.cn/api/supply/lm/sellercenter/userInfo',
                        'method': 'GET',
                        'headers': headers,
                        'credentials': 'include',
                    }],
                    max_retries=2,
                )
                userinfo_response = results[0]['response']
                response_json['sub_account_info']['id'] = userinfo_response['data']['userId']
                sub_account_info = response_json.get('sub_account_info', {}) or {}
                self.media_user_id = sub_account_info.get('id')
                self.media_shop_id = sub_account_info.get('current_shop_id')
                self.username = userinfo_response['data']['userName']
            else:
                user_info = response_json.get('user', {}) or {}
                self.media_user_id = response_json.get('id') or user_info.get('user_id')
                self.media_shop_id = response_json.get('shopid') or user_info.get('shop_id')
                self.username = response_json.get('username')

            if self.media_user_id and self.media_shop_id:
                logger.info(
                    f'获取 media IDs 成功: user_id={self.media_user_id}, shop_id={self.media_shop_id}'
                )
                self._send_data({'url': login_url, 'response': response_json})
                return True

            logger.error('login 接口返回数据异常')
            return False
        except Exception as e:
            logger.error(f'获取 login 信息失败: {e}')
            return False

    def _fetch_remark(self, use_cache: bool = True) -> str:
        """从 AdsPower API 获取当前环境的 remark 原始字符串

        Args:
            use_cache: 是否使用缓存，默认 True。更新 remark 后应传 False 强制刷新
        """
        if use_cache and self._remark_cache is not None:
            return self._remark_cache

        try:
            client = get_adspower_client()
            resp = client.get('/api/v1/user/list', params={"user_id": self.browser_id})
            users = resp.get('data', {}).get('list', [])
            if not users:
                self._remark_cache = ''
                return ''
            self._remark_cache = users[0].get('remark', '')
            return self._remark_cache
        except (AdsPowerRateLimitError, AdsPowerApiError) as e:
            logger.warning(f'获取 remark 失败: {e}')
            return ''
        except Exception as e:
            logger.warning(f'获取 remark 失败: {e}')
            return ''

    @staticmethod
    def _parse_remark(remark: str) -> dict:
        """解析 remark 字符串，支持格式：vid:{id} 或 vid:{id}|country:{code} 或 vid:{id}|country:{code}|cb:{0|1}"""
        result = {'vid': None, 'country': None, 'cb': None}
        if not remark or not remark.startswith('vid:'):
            return result
        for part in remark.split('|'):
            part = part.strip()
            if part.startswith('vid:'):
                result['vid'] = part[4:].strip()
            elif part.startswith('country:'):
                result['country'] = part[8:].strip().lower()
            elif part.startswith('cb:'):
                try:
                    result['cb'] = int(part[3:].strip())
                except ValueError:
                    pass
        return result

    def _get_validate_id_from_remark(self) -> str | None:
        """从 AdsPower 环境的 remark 中提取 validate_id"""
        remark = self._fetch_remark()
        parsed = self._parse_remark(remark)
        return parsed['vid'] or None

    def _get_country_from_remark(self) -> str | None:
        """从 AdsPower 环境的 remark 中提取国家代码"""
        remark = self._fetch_remark()
        parsed = self._parse_remark(remark)
        return parsed['country'] or None

    def _resolve_cross_border(self) -> bool:
        """判断是否跨境店（cb:1），缺失 cb 字段时默认为本土店"""
        remark = self._fetch_remark()
        parsed = self._parse_remark(remark)
        return parsed['cb'] == 1

    def _resolve_prelogin_country_domain(self, replay_domain=False) -> str:
        """登录前解析国家域名（四层来源）

        优先级：
        0. 跨境店统一使用 cn 域名（最高优先级）
        1. remark 中的显式国家代码
        2. group_name 推断
        3. 默认值 com.my

        Returns:
            国家域名后缀，如 'cn', 'com.my', 'sg', 'co.id'
        """
        # 第零层：跨境店统一使用 cn 域名
        if self.is_cross_border and not replay_domain:
            logger.info('跨境店，使用 seller.shopee.cn 域名')
            return 'cn'

        # 第一层：从 remark 解析国家代码
        country_from_remark = self._get_country_from_remark()
        if country_from_remark:
            domain = self._country_code_to_domain(country_from_remark)
            logger.info(f'从 remark 解析到国家域名: {domain}')
            return domain

        # 第二层：从 group_name 推断
        for keyword, domain in self.SHOPEE_COUNTRY_MAP.items():
            if keyword in self.group_name:
                logger.info(f'从分组名推断国家域名: {domain}（关键词: {keyword}）')
                return domain

        # 第三层：默认值
        logger.warning('无法从 remark 或分组名推断国家，使用默认值: com.my')
        return "com.my"

    def _update_remark_with_country(self, shop_id: str, country_code: str) -> bool:
        """更新 AdsPower remark，补充国家信息（保留 cb 字段）

        Args:
            shop_id: 店铺 ID
            country_code: 国家代码（小写），如 'sg', 'my'

        Returns:
            是否更新成功
        """
        try:
            # 获取当前 remark 并解析
            remark = self._fetch_remark()
            parsed = self._parse_remark(remark)

            # 构建新 remark，保留 cb 字段
            parts = [f"vid:{shop_id}", f"country:{country_code.lower()}"]
            if parsed.get('cb') is not None:
                parts.append(f"cb:{parsed['cb']}")
            new_remark = "|".join(parts)

            # 调用 AdsPower API 更新
            client = get_adspower_client()
            resp = client.post('/api/v1/user/update', json={
                "user_id": self.browser_id,
                "remark": new_remark
            })

            logger.info(f'已更新 remark: {new_remark}')
            self._remark_cache = new_remark
            return True

        except Exception as e:
            logger.error(f'更新 remark 异常: {e}')
            return False

    def _get_shop_country_by_id(self, shop_id: str) -> str | None:
        """通过 shop_id 查询店铺所属国家

        优先使用 get_shop_list 接口（主账号 / 被授权多店铺的子账号可用），
        若失败（单店铺权限子账号无该接口权限）则回退到 shop_info 接口。

        Args:
            shop_id: 店铺 ID（validate_id）

        Returns:
            国家代码，例如 'sg', 'my', 'id', 'th'
            如果查询失败则返回 None
        """
        country = self._get_shop_country_by_shop_list(shop_id)
        if country:
            return country

        logger.info(f'get_shop_list 未取到店铺 {shop_id} 的国家，回退到 shop_info 接口')
        return self._get_shop_country_by_shop_info(shop_id)

    def _get_shop_country_by_shop_list(self, shop_id: str) -> str | None:
        """通过 subaccount/get_shop_list 查询店铺国家。

        适用账号类型：主账号 / 被授权多店铺权限的子账号。
        单店铺权限子账号（Sub-account）请求该接口会因权限不足失败，
        调用方需自行回退到 _get_shop_country_by_shop_info。
        """
        try:
            # 使用当前域名构建 API URL（初始域名作为入口）
            api_url = f'https://seller.shopee.{self.country_domain}/api/selleraccount/subaccount/get_shop_list/'

            # 构建请求头
            headers = self._build_request_headers({
                'referer': getattr(self.tab, 'url', self._get_base_url()),
            })

            # 通过 JS 注入调用 API
            results = self.browser_api.run_js_fetch(
                self.tab,
                [{
                    'url': api_url,
                    'method': 'GET',
                    'headers': headers,
                    'credentials': 'include',
                }],
                max_retries=2,
            )

            if not results or not results[0] or not results[0].get('response'):
                logger.warning('get_shop_list 接口返回数据异常')
                return None

            response = results[0]['response']
            response_json = json.loads(response) if isinstance(response, str) else response

            if response_json.get('code') != 0:
                logger.warning(f'get_shop_list 接口返回错误: {response_json.get("message")}')
                return None

            shops = response_json.get('shops', [])
            if not shops:
                logger.warning('get_shop_list 返回空店铺列表')
                return None

            # 查找匹配的店铺
            for shop in shops:
                if str(shop.get('shop_id')) == str(shop_id):
                    country = shop.get('country', '').lower()
                    logger.info(f'查询到店铺 {shop_id} 所属国家: {country}')
                    return country

            logger.warning(f'未在店铺列表中找到 shop_id={shop_id}')
            return None

        except Exception as e:
            logger.error(f'查询店铺国家失败: {e}')
            return None

    def _get_shop_country_by_shop_info(self, shop_id: str) -> str | None:
        """通过 selleraccount/shop_info 查询当前登录店铺的国家。

        适用账号类型：单店铺权限子账号（Sub-account），其无 get_shop_list 权限。
        该接口返回当前登录上下文的店铺信息，不接受 shop_id 参数，因此仅在
        响应中的 shop_id 与传入的 shop_id 匹配时才视为命中（避免店铺切换前误判）。

        响应示例：
            {"code":0, "data":{"shop_id":1015334690, "shop_region":"MY", ...}}
        """
        try:
            api_url = f'https://seller.shopee.{self.country_domain}/api/selleraccount/shop_info/'

            headers = self._build_request_headers({
                'referer': getattr(self.tab, 'url', self._get_base_url()),
            })

            results = self.browser_api.run_js_fetch(
                self.tab,
                [{
                    'url': api_url,
                    'method': 'GET',
                    'headers': headers,
                    'credentials': 'include',
                }],
                max_retries=2,
            )

            if not results or not results[0] or not results[0].get('response'):
                logger.warning('shop_info 接口返回数据异常')
                return None

            response = results[0]['response']
            response_json = json.loads(response) if isinstance(response, str) else response

            if response_json.get('code') != 0:
                logger.warning(f'shop_info 接口返回错误: {response_json.get("message")}')
                return None

            data = response_json.get('data') or {}
            resp_shop_id = data.get('shop_id')
            shop_region = (data.get('shop_region') or '').lower()

            if not shop_region:
                logger.warning('shop_info 响应中缺少 shop_region')
                return None

            # shop_info 返回的是当前登录店铺；只有 shop_id 一致才认定为目标店铺
            if str(resp_shop_id) != str(shop_id):
                logger.warning(
                    f'shop_info 当前店铺 {resp_shop_id} 与目标 {shop_id} 不一致，'
                    f'shop_region={shop_region} 暂不采用'
                )
                return None

            logger.info(f'shop_info 查询到店铺 {shop_id} 所属国家: {shop_region}')
            return shop_region

        except Exception as e:
            logger.error(f'shop_info 查询店铺国家失败: {e}')
            return None

    def _get_cross_border_shop_country(self, shop_id: str) -> str | None:
        """通过跨境店 CN 接口查询店铺所属国家

        Args:
            shop_id: 店铺 ID（cnsc_shop_id / validate_id）

        Returns:
            国家代码（小写），例如 'my', 'id', 'th'
            如果查询失败则返回 None
        """
        try:
            api_url = 'https://seller.shopee.cn/api/cnsc/selleraccount/get_or_set_shop/'
            headers = self._build_request_headers({
                'referer': getattr(self.tab, 'url', 'https://seller.shopee.cn/'),
                'content-type': 'application/json',
            })

            body = json.dumps({"cnsc_shop_id": int(shop_id)}, separators=(',', ':'))

            results = self.browser_api.run_js_fetch(
                self.tab,
                [{
                    'url': api_url,
                    'method': 'POST',
                    'headers': headers,
                    'credentials': 'include',
                    'body': body,
                }],
                max_retries=2,
            )

            if not results or not results[0] or not results[0].get('response'):
                logger.warning('跨境店 get_or_set_shop 接口返回数据异常')
                return None

            response = results[0]['response']
            response_json = json.loads(response) if isinstance(response, str) else response

            if response_json.get('code') != 0:
                logger.warning(f'跨境店 get_or_set_shop 接口返回错误: {response_json.get("message")}')
                return None

            shop_region = response_json.get('shop_region', '').lower()
            if shop_region:
                logger.info(f'跨境店查询到店铺 {shop_id} 所属国家: {shop_region}')
                return shop_region

            logger.warning(f'跨境店 get_or_set_shop 响应中未找到 shop_region')
            return None

        except Exception as e:
            logger.error(f'跨境店查询店铺国家失败: {e}')
            return None

    def _country_code_to_domain(self, country_code: str) -> str:
        """将国家代码转换为 Shopee 域名后缀

        Args:
            country_code: 国家代码，例如 'sg', 'my', 'id', 'th'

        Returns:
            域名后缀，例如 'sg', 'com.my', 'co.id', 'co.th'
        """
        # 国家代码到域名后缀的映射（反向映射 SHOPEE_COUNTRY_MAP）
        code_to_domain = {
            'cn': 'cn',
            'my': 'com.my',
            'id': 'co.id',
            'th': 'co.th',
            'sg': 'sg',
            'ph': 'ph',
            'vn': 'vn',
            'br': 'com.br',
            'mx': 'com.mx',
        }
        return code_to_domain.get(country_code.lower(), 'com.my')

    def _get_current_country_code(self) -> str:
        """获取当前国家代码，优先从 remark 取，否则从 country_domain 推导

        Returns:
            国家代码（小写），如 'my', 'id', 'sg'；若无法推导则返回空字符串
        """
        # 优先从 remark 获取
        country_from_remark = self._get_country_from_remark()
        if country_from_remark:
            return country_from_remark

        # 从 country_domain 反推（如 'com.my' -> 'my', 'sg' -> 'sg'）
        if not self.country_domain:
            return ''

        # 提取域名后缀最后一段作为国家代码
        parts = self.country_domain.split('.')
        return parts[-1] if parts else ''

    def _get_currency_symbol(self, country_code: str) -> str:
        """根据国家代码获取货币符号

        Args:
            country_code: 国家代码（小写），如 'my', 'id'

        Returns:
            货币符号，如 'RM', 'Rp'；若无映射则返回空字符串
        """
        return CURRENCY_MAPPING.get(country_code, {}).get('symbol', '')

    def _sync_remark_country_if_needed(self, shop_id: str, shop_country: str | None = None) -> None:
        """检查并补充 remark 中的国家信息（如果缺失或不匹配）

        Args:
            shop_id: 店铺 ID
            shop_country: 店铺国家代码，如果为 None 则自动查询
        """
        if not shop_country:
            shop_country = self._get_shop_country_by_id(shop_id)
        if not shop_country:
            return

        country_from_remark = self._get_country_from_remark()
        if not country_from_remark or country_from_remark != shop_country:
            logger.info(f'补充 remark 国家信息: {shop_country}')
            self._update_remark_with_country(shop_id, shop_country)

    def _ensure_correct_shop(self, original_url: str) -> bool:
        """确保当前浏览器处于目标店铺上下文

        Args:
            original_url: 原始采集页面 URL，切换后需要回到此页面
        """
        validate_id = self._get_validate_id_from_remark()
        if not validate_id:
            logger.warning('未获取到 validate_id，可能是 AdsPower API 调用失败或 remark 为空')
            # P2 修复：对于 Shopee 会话，validate_id 是必填的，不应静默跳过
            return False

        if str(self.media_shop_id) == str(validate_id):
            logger.info(f'当前已是目标店铺: {validate_id}')
            return True

        logger.info(f'当前店铺 {self.media_shop_id} 与目标 {validate_id} 不符，尝试切换')
        return self._switch_to_shop(str(validate_id), original_url)

    def _switch_to_shop(self, target_shop_id: str, original_url: str) -> bool:
        """导航到店铺列表页，点击目标店铺的 Details 按钮完成切换

        Args:
            target_shop_id: 目标店铺 ID
            original_url: 原始采集页面 URL，切换后需要回到此页面
        """
        try:
            shop_list_url = f'https://seller.shopee.{self.country_domain}/portal/shop'
            logger.info(f'导航到店铺列表页: {shop_list_url}')
            self.tab.get(shop_list_url)
            time.sleep(3)
            self.tab.wait.eles_loaded('xpath://*[@class="eds-react-table"]', timeout=5)

            # 查找包含目标 shop_id 的 Details 链接
            detail_link = self.tab.ele(
               f'xpath://*[@data-row-key="{target_shop_id}"]//button',
                timeout=5
            )

            # 点击 Details 会在新 tab 打开
            self.tab.run_js('arguments[0].click();', detail_link)
            time.sleep(3)

            # 切换到最新的 tab（新打开的店铺详情页）
            latest_tab = self.driver.latest_tab
            if latest_tab:
                self.tab = latest_tab
                logger.info('已切换到新打开的店铺 tab')

            # 关闭其他无用的 tab，只保留当前 tab
            try:
                self.tab.close(others=True)
                logger.info('已关闭其他无用的 tab')
            except Exception as e:
                logger.warning(f'关闭其他 tab 失败: {e}')

            # 重新获取 shop_id 验证切换结果
            if not self._fetch_login_info_via_js():
                return False

            if str(self.media_shop_id) != target_shop_id:
                logger.warning(f'切换后 shop_id 仍不匹配: {self.media_shop_id} != {target_shop_id}')
                return False

            logger.info(f'店铺切换成功: {target_shop_id}')
            self._sync_remark_country_if_needed(target_shop_id)

            # 导航回原始采集页面
            logger.info(f'导航回原始采集页面: {original_url}')
            self._open_collection_page(original_url)

            return True
        except Exception as e:
            logger.error(f'店铺切换异常: {e}')
            return False

    def _build_live_list_params(self, page: int = 1) -> Dict[str, str]:
        """构造 liveList/v2 请求参数。"""
        time_dim = '30d' if self.full_collection else '7d'
        end_date = self._get_country_yesterday()
        return {
            'page': str(page),
            'pageSize': '100',
            'name': '',
            'orderBy': '',
            'sort': '',
            'timeDim': time_dim,
            'endDate': end_date,
        }

    def _build_overview_params(self, end_date: str) -> Dict[str, str]:
        """构造概览数据请求参数（按天查询）。"""
        return {
            'endDate': end_date,
            'timeDim': '1d',
        }

    def _fetch_session_list_via_js(self) -> Dict[str, Any] | None:
        """通过 JS 注入获取 sessionList 数据（替代拦截）。"""
        try:
            # 构造请求头
            fetch_headers = self._build_request_headers()
            fetch_headers.update(self._build_shopee_api_headers())

            # 构造请求
            request = {
                'url': f"{self._get_base_url()}/api/supply/lm/sellercenter/realtime/sessionList?page=1&pageSize=100&name=&orderBy=&sort=",
                'method': 'GET',
                'headers': fetch_headers,
                'credentials': 'include',
            }

            # 发起 JS 注入请求
            results = self.browser_api.run_js_fetch(self.tab, [request], max_retries=2)

            if not results or not results[0]:
                logger.warning('sessionList JS 注入请求失败')
                return None

            result = results[0]
            if result.get('error'):
                logger.error(f'sessionList 请求返回错误: {result["error"]}')
                return None

            return result
        except Exception as e:
            logger.error(f'_fetch_session_list_via_js 执行失败: {e}')
            return None

    def _fetch_live_list_pages_via_js(self, headers: Dict[str, Any]) -> List[Dict[str, Any]]:
        """按页抓取 liveList/v2，增量抓第一页，全量抓到结束。"""
        results: List[Dict[str, Any]] = []
        fetch_headers = self._build_request_headers(headers)
        page = 1
        page_size = int(self._build_live_list_params().get('pageSize', '100'))
        max_pages = self.config.get('live_list_max_pages', 50)

        while page <= max_pages:
            live_list_params = self._build_live_list_params(page=page)
            request = {
                'url': f"{self._get_base_url()}/api/supply/lm/sellercenter/liveList/v2?{urlencode(live_list_params)}",
                'method': 'GET',
                'headers': fetch_headers,
                'credentials': 'include',
            }
            fetch_results = self.browser_api.run_js_fetch(self.tab, [request], max_retries=2)
            if not fetch_results or not fetch_results[0] or not fetch_results[0].get('response'):
                logger.warning(f'liveList/v2 第 {page} 页请求失败')
                break

            result = fetch_results[0]
            results.append(result)

            if not self.full_collection:
                break

            response_json = self._parse_json_response(result.get('response'))
            response_data = response_json.get('data', {})
            sessions = response_data.get('list', [])
            if not sessions:
                break

            total = response_data.get('total')
            try:
                total = int(total) if total is not None else None
            except (TypeError, ValueError):
                total = None

            if total is not None and page * page_size >= total:
                break

            if total is None and len(sessions) < page_size:
                break

            page += 1

        return results

    def _fetch_overview_requests_via_js(self, headers: Dict[str, Any]) -> List[Dict[str, Any]]:
        """抓取 overview 与 metricTrend 概览接口（逐日请求）。"""
        date_range = self._get_country_date_range()
        fetch_headers = self._build_request_headers(headers)
        all_results = []

        logger.info(f'开始逐日请求 overview/metricTrend，共 {len(date_range)} 天')

        for end_date in date_range:
            overview_params = self._build_overview_params(end_date)
            requests = [
                {
                    'url': f"{self._get_base_url()}/api/supply/lm/sellercenter/overview/v3?{urlencode(overview_params)}",
                    'method': 'GET',
                    'headers': fetch_headers,
                    'credentials': 'include',
                },
                {
                    'url': f"{self._get_base_url()}/api/supply/lm/sellercenter/metricTrend/v2?{urlencode(overview_params)}",
                    'method': 'GET',
                    'headers': fetch_headers,
                    'credentials': 'include',
                },
            ]

            results = self.browser_api.run_js_fetch(self.tab, requests, max_retries=2)
            valid_results = [result for result in results if result and result.get('response')]
            all_results.extend(valid_results)
            logger.debug(f'日期 {end_date}: 成功 {len(valid_results)}/2 个请求')

            # 监控钩子：记录逐日 overview 和 metric_trend 采集状态
            try:
                monitor = get_monitor()
                if monitor and self.batch_id:
                    overview_ok = len(results) >= 1 and results[0] and results[0].get('response')
                    monitor.record_daily_stats(
                        self.batch_id, self.browser_id, end_date, 'overview',
                        'success' if overview_ok else 'failed'
                    )
                    trend_ok = len(results) >= 2 and results[1] and results[1].get('response')
                    monitor.record_daily_stats(
                        self.batch_id, self.browser_id, end_date, 'metric_trend',
                        'success' if trend_ok else 'failed'
                    )
            except Exception:
                pass

        logger.info(f'overview/metricTrend 逐日请求完成，共 {len(all_results)} 个响应')
        return all_results

    def _handle_live_list_page(self) -> Dict[str, int]:
        """处理列表页：通过 JS 注入获取 sessionList 及其他数据。"""
        stats = {'apis_count': 0, 'data_sent': 0}
        try:
            # 通过 JS 注入获取 sessionList（替代拦截）
            session_data = self._fetch_session_list_via_js()
            if not session_data or not session_data.get('response'):
                logger.warning('未获取到 sessionList 数据')
                return stats

            stats['apis_count'] += 1

            # 监控钩子：记录 sessionList 采集成功
            try:
                monitor = get_monitor()
                if monitor and self.batch_id:
                    monitor.record(self.batch_id, self.browser_id, 'session_list', status='success')
            except Exception:
                pass

            sent = self._send_data({'url': session_data['url'], 'response': session_data['response']})
            if isinstance(sent, (bool, int)):
                stats['data_sent'] += int(sent)

            # 构造统一的 headers（不再依赖拦截数据）
            fetch_headers = self._build_request_headers()
            fetch_headers.update(self._build_shopee_api_headers())

            live_list_results = self._fetch_live_list_pages_via_js(fetch_headers)
            overview_results = self._fetch_overview_requests_via_js(fetch_headers)

            # 监控钩子：记录 liveList/v2 采集状态
            try:
                monitor = get_monitor()
                if monitor and self.batch_id:
                    status = 'success' if live_list_results else 'failed'
                    monitor.record(self.batch_id, self.browser_id, 'live_list', status=status)
            except Exception:
                pass

            # 提取并记录直播间信息（只注册回放场次，实时场次不纳入完整率计算）
            try:
                rooms_data = []
                # 从 liveList/v2 提取回放直播间信息
                for live_list_result in live_list_results:
                    response_json = self._parse_json_response(live_list_result.get('response'))
                    sessions = response_json.get('data', {}).get('list', [])
                    for session in sessions:
                        session_id = str(session.get('sessionId', ''))
                        if session_id:
                            rooms_data.append({
                                'room_id': session_id,
                                'room_name': session.get('title', ''),
                                'live_start_ts': session.get('startTime', 0) // 1000 if session.get('startTime') else 0,
                                'live_end_ts': (session.get('startTime', 0) + session.get('duration', 0)) // 1000 if session.get('startTime') and session.get('duration') else 0,
                                'duration': session.get('duration', 0) // 1000 if session.get('duration') else 0,
                                'revenue': str(session.get('confirmedSales', 0)),
                                'currency_code': 'MYR',  # 根据国家域名可以动态设置
                                'item_sold_cnt': session.get('confirmedItemSold', 0),
                                'view_cnt': session.get('viewers', 0),
                            })

                # 调用 record_rooms 存储回放直播间信息（内部会自动调用 _insert_room_session）
                if rooms_data:
                    monitor = get_monitor()
                    if monitor and self.batch_id:
                        monitor.record_rooms(self.batch_id, self.browser_id, rooms_data)
                        logger.info(f'已记录 {len(rooms_data)} 个回放直播间信息到监控系统')
            except Exception as e:
                logger.warning(f'记录直播间信息失败: {e}')

            for result in [*live_list_results, *overview_results]:
                if result and result.get('response'):
                    stats['apis_count'] += 1
                    sent = self._send_data({'url': result.get('url'), 'response': result.get('response')})
                    if isinstance(sent, (bool, int)):
                        stats['data_sent'] += int(sent)

            # 处理 sessionList 响应中的实时直播间详情
            try:
                session_list_json = self._parse_json_response(session_data['response'])
                sessions = session_list_json.get('data', {}).get('list', [])
                live_sessions = self._filter_sessions(sessions)

                if live_sessions:
                    logger.info(f'找到 {len(live_sessions)} 个实时直播间，开始采集详情数据')
                    for session in live_sessions:
                        session_id = str(session.get('sessionId', ''))

                        detail_results = self._fetch_session_detail_via_js(session, fetch_headers)
                        for detail_result in detail_results:
                            if detail_result and detail_result.get('response'):
                                stats['apis_count'] += 1
                                sent = self._send_data({'url': detail_result.get('url'), 'response': detail_result.get('response')})
                                if isinstance(sent, (bool, int)):
                                    stats['data_sent'] += int(sent)

                        # 监控钩子：记录 session_detail 采集状态
                        try:
                            monitor = get_monitor()
                            if monitor and self.batch_id and session_id:
                                has_data = any(r and r.get('response') for r in detail_results)
                                monitor.record(
                                    self.batch_id, self.browser_id, 'session_detail',
                                    room_id=session_id, status='success' if has_data else 'failed'
                                )
                        except Exception:
                            pass

            except Exception as e:
                logger.error(f'处理实时直播间详情失败: {e}')

            # 处理 liveList/v2 响应中的回放直播间详情
            if live_list_results:
                try:
                    replay_sessions = []
                    for live_list_result in live_list_results:
                        response_json = self._parse_json_response(live_list_result.get('response'))
                        sessions = response_json.get('data', {}).get('list', [])
                        replay_sessions.extend([s for s in sessions if s.get('status') == 2])

                    if replay_sessions:
                        logger.info(f'找到 {len(replay_sessions)} 个回放直播间，开始采集详情数据')
                        for session in replay_sessions:
                            session_id = str(session.get('sessionId', ''))

                            detail_results = self._fetch_replay_detail_via_js(session, fetch_headers)
                            for detail_result in detail_results:
                                if detail_result and detail_result.get('response'):
                                    stats['apis_count'] += 1
                                    sent = self._send_data({'url': detail_result.get('url'), 'response': detail_result.get('response')})
                                    if isinstance(sent, (bool, int)):
                                        stats['data_sent'] += int(sent)
                                    time.sleep(0.5)

                            # 监控钩子：记录 replay_detail 采集状态
                            try:
                                monitor = get_monitor()
                                if monitor and self.batch_id and session_id:
                                    has_data = any(r and r.get('response') for r in detail_results)
                                    monitor.record(
                                        self.batch_id, self.browser_id, 'replay_detail',
                                        room_id=session_id, status='success' if has_data else 'failed'
                                    )
                            except Exception:
                                pass
                except Exception as e:
                    logger.error(f'处理回放详情失败: {e}')

            return stats
        except Exception as e:
            logger.error(f'处理列表页失败: {e}')
            return stats

    def _send_data(self, data: Dict[str, Any]) -> bool:
        """格式化并发送数据。"""
        cookies = self.browser_api.get_cookies(self.tab)
        message = self.format_api_message(
            url=data['url'],
            request_body='',
            response_body=data['response'],
            cookies=cookies,
        )
        return self.send_api_request(message)

    def _filter_sessions(self, sessions: List[dict]) -> List[dict]:
        """过滤出非实时直播间（status != 1）。"""
        return [s for s in sessions if s.get('status') != 1]
    def _build_trends_requests(self, session: dict) -> List[Dict[str, Any]]:
        """为单个 session 构造 3 个 trends 接口请求配置。"""
        session_id = session.get('sessionId')
        start_time = session.get('startTime')

        if not all([session_id, start_time]):
            return []

        # 动态生成当地时区的当前时间（毫秒时间戳）
        tz_offset = self.SHOPEE_TIMEZONE_MAP.get(self.country_domain, 8)
        country_tz = timezone(timedelta(hours=tz_offset))
        end_time = int(datetime.now(country_tz).timestamp() * 1000)

        base_url = self._get_base_url()
        headers = self._build_request_headers()
        headers.update(self._build_shopee_api_headers())  # 添加 Shopee API 必需 headers

        return [
            {
                'url': f'{base_url}/api/supply/lm/sellercenter/realtime/dashboard/trends?sessionId={session_id}&startTime={start_time}&endTime={end_time}&metricTrend=order,gmv,confirmedGmv,confirmedOrder',
                'method': 'GET',
                'headers': headers,
                'credentials': 'include',
            },
            {
                'url': f'{base_url}/api/supply/lm/sellercenter/realtime/dashboard/trends?sessionId={session_id}&startTime={start_time}&endTime={end_time}&metricTrend=ccu,engagedCcu,entering',
                'method': 'GET',
                'headers': headers,
                'credentials': 'include',
            },
            {
                'url': f'{base_url}/api/supply/lm/sellercenter/realtime/dashboard/trends?sessionId={session_id}&startTime={start_time}&endTime={end_time}&metricTrend=comment,addToCart',
                'method': 'GET',
                'headers': headers,
                'credentials': 'include',
            },
        ]

    def _fetch_session_detail_via_js(self, session: Dict[str, Any], headers: Dict[str, Any]) -> List[Dict[str, Any]]:
        """对单个实时 session 发起 7 个详情接口的 JS 注入。"""
        results = []
        try:
            session_id = session.get('sessionId')
            if not session_id:
                return results

            base_url = self._get_base_url()
            fetch_headers = self._build_request_headers(headers)
            fetch_headers.update(self._build_shopee_api_headers())  # 添加 Shopee API 必需 headers

            # 构造 4 个固定接口 + 3 个 trends 接口
            all_requests = [
                {
                    'url': f'{base_url}/api/supply/lm/sellercenter/realtime/dashboard/overview?sessionId={session_id}',
                    'method': 'GET',
                    'headers': fetch_headers,
                    'credentials': 'include',
                },
                {
                    'url': f'{base_url}/api/supply/lm/sellercenter/realtime/dashboard/viewer-source?sessionId={session_id}',
                    'method': 'GET',
                    'headers': fetch_headers,
                    'credentials': 'include',
                },
                {
                    'url': f'{base_url}/api/supply/lm/sellercenter/realtime/dashboard/viewer-profile?sessionId={session_id}',
                    'method': 'GET',
                    'headers': fetch_headers,
                    'credentials': 'include',
                },
                {
                    'url': f'{base_url}/api/supply/lm/sellercenter/realtime/dashboard/buyer-profile?sessionId={session_id}',
                    'method': 'GET',
                    'headers': fetch_headers,
                    'credentials': 'include',
                },
            ]

            # 添加 trends 请求
            trends_requests = self._build_trends_requests(session)
            all_requests.extend(trends_requests)

            # 并发执行所有请求
            results = self.browser_api.run_js_fetch(self.tab, all_requests, max_retries=2)
            return results if results else []

        except Exception as e:
            logger.error(f'获取实时直播间详情失败: sessionId={session.get("sessionId")}, 错误: {e}')
            return results

    def _capture_login_media_ids(self, response: Any) -> bool:
        """从登录接口响应中提取媒体ID"""
        if self.media_user_id and self.media_shop_id:
            return False
        try:
            if isinstance(response, str):
                response_json = json.loads(response)
            else:
                response_json = response

            media_user_id = response_json.get('id')
            media_shop_id = response_json.get('shopid')

            if media_user_id and media_shop_id:
                self.media_user_id = media_user_id
                self.media_shop_id = media_shop_id
                logger.info(f'获取媒体ID成功 media_user_id={media_user_id}, media_shop_id={media_shop_id}')
                return True
            else:
                logger.warning('登录响应中未找到媒体ID字段')
                return False
        except Exception as e:
            logger.warning(f'解析登录响应获取媒体ID失败: {e}')
            return False

    def _queue_or_send_payload(self, payload: Dict[str, Any]) -> int:
        """根据是否已获取媒体ID决定发送或缓存"""
        if self.media_user_id and self.media_shop_id:
            message = self.format_api_message(**payload)
            return 1 if self.send_api_request(message) else 0

        self.pending_messages.append(payload)
        logger.debug(f'媒体ID未获取，缓存待发消息，当前缓存 {len(self.pending_messages)} 条')
        return 0

    def _flush_pending_messages(self) -> int:
        """媒体ID获取后，批量发送缓存"""
        if not self.pending_messages:
            return 0

        sent_count = 0
        buffered = self.pending_messages
        self.pending_messages = []

        for payload in buffered:
            try:
                message = self.format_api_message(**payload)
                if self.send_api_request(message):
                    sent_count += 1
            except Exception as e:
                logger.warning(f'发送缓存消息失败: {e}')

        logger.info(f'已发送缓存消息 {sent_count}/{len(buffered)} 条')
        return sent_count

    def format_api_message(self, url: str, request_body: Any, 
                          response_body: Any, cookies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Shopee专用格式化，强制携带媒体ID"""
        # 处理请求体
        if request_body == "No request body" or not request_body:
            base_extra = {}
        elif isinstance(request_body, str):
            try:
                base_extra = json.loads(request_body)
            except:
                base_extra = {"raw": request_body}
        else:
            base_extra = request_body

        # 合并媒体ID、国家和货币符号
        base_extra = base_extra if isinstance(base_extra, dict) else {"raw": str(base_extra)}
        country_code = self._get_current_country_code()
        base_extra.update({
            "media_user_id": self.media_user_id,
            "media_shop_id": self.media_shop_id,
            "username": self.username,
            "country": country_code,
            "symbol": self._get_currency_symbol(country_code),
            "cross_border": 1 if self.is_cross_border else 0,
        })
        extra_str = json.dumps(base_extra, ensure_ascii=False)

        # 格式化响应体
        if isinstance(response_body, dict):
            response_str = json.dumps(response_body, ensure_ascii=False)
        else:
            response_str = str(response_body)

        # 构造消息体
        message = {
            "params": "",
            "cookies": json.dumps(cookies, ensure_ascii=False),
            "fromUrl": url,
            "extra": extra_str,
            "sign": Settings.DATA_SERVER_CONFIG['api_sign'],
            "userType": 6.0,
            "dataSource": DataSource.SHOPEE,
            "updateTime": int(time.time() * 1000),
            "request": {
                "response": response_str,
                "url": url
            },
            "socketUserId": self.socket_user_id,
        }

        return message

    def _handle_shopee_live_list(self, response: Any) -> None:
        """处理Shopee直播列表，自动打开当前到昨天的直播详情页
        
        Args:
            response: API响应数据
        """

        try:
            # 解析响应
            if isinstance(response, str):
                if len(response) < 100:  # 响应太小，跳过
                    return
                response_json = json.loads(response)
            else:
                response_json = response
            
            # 检查响应状态
            if response_json.get('code') != 0:
                return

            # 提取直播间列表
            live_list = response_json.get('data', {}).get('list', [])

            if not live_list:
                return

            # 计算昨天的时间戳
            now = datetime.now()
            yesterday = now - timedelta(days=1)
            yesterday_start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
            yesterday_timestamp = int(yesterday_start.timestamp() * 1000) # Shopee时间戳为毫秒

            # 筛选昨天开始的直播，并保留时间范围
            session_info_list = []
            for item in live_list:
                session_id = item.get('sessionId')
                start_time = item.get('startTime', 0) # 直播开始时间
                duration = item.get('duration', 0)
                
                # 转换为字符串以便存储
                session_id_str = str(session_id)
                
                # 过滤无效或已处理的直播间
                if not session_id or session_id_str in self.processed_room_ids or duration == 0:
                    continue

                if start_time >= yesterday_timestamp:
                    session_info_list.append({
                        "session_id": session_id,
                        "start_time": start_time,
                        "end_time": start_time + duration
                    })
                    self.processed_room_ids.add(session_id_str)

            if session_info_list:
                logger.info(f'找到 {len(session_info_list)} 个昨天的直播间，将依次访问详情页')

                # 依次访问直播详情页，并为趋势接口提供时间区间
                for i, session_info in enumerate(session_info_list):
                    session_id = session_info["session_id"]
                    start_time = session_info["start_time"]
                    end_time = session_info["end_time"]
                    # 提前写入趋势接口参数，仅覆盖时间区间
                    self.browser_api.shopee_trends_params = {
                        "startTime": str(start_time),
                        "endTime": str(end_time),
                    }

                    detail_url = f"https://seller.shopee.{self.country_domain}/creator-center/realtime/live/{session_id}"
                    logger.info(f'[{i+1}/{len(session_info_list)}] 访问直播详情页: {session_id}')

                    try:
                        # 访问详情页并采集
                        self.visit_page_and_collect(detail_url)

                        if i < len(session_info_list) - 1:
                            time.sleep(5)
                    except Exception as e:
                        logger.error(f'访问直播详情页失败 {session_id}: {e}')
                        continue

        except Exception as e:
            logger.warning(f'处理Shopee直播列表失败: {e}')

    def handle_shopee_replay(self) -> Dict[str, int]:
        """采集 Shopee 直播回放数据并上报。

        增量模式只取第一页，全量模式翻页获取全部。
        每条 replay 额外请求 detail 接口，将 replay_info 合并到 replay 数据中。

        Returns:
            dict: {'apis_count': int, 'data_sent': int}
        """
        stats = {'apis_count': 0, 'data_sent': 0}

        if not self.media_user_id:
            logger.warning('media_user_id 未获取，跳过回放数据采集')
            return stats
        country_domain = self._resolve_prelogin_country_domain(replay_domain=True)
        base_url = f"https://live.shopee.{country_domain}/api/v1/shop_page/live/replay_list"
        limit = 50
        offset = 0
        max_pages = 20  # 防止无限循环
        all_replays = []

        for _ in range(max_pages):
            params = {"offset": str(offset), "limit": str(limit), "uid": str(self.media_user_id)}
            try:
                res = self.session.get(base_url, params=params, timeout=30)
                if res.status_code != 200:
                    logger.warning(f'replay_list 请求失败，HTTP {res.status_code}')
                    break
                response_data = res.json()
                stats['apis_count'] += 1
            except Exception as e:
                logger.error(f'replay_list 请求异常: {e}')
                break

            replays = response_data.get('data', {}).get('replay', [])
            all_replays.extend(replays)
            logger.info(f'replay_list offset={offset}: 获取 {len(replays)} 条，累计 {len(all_replays)} 条')

            # 增量模式只取第一页；当前页无数据也退出
            if not self.full_collection or not replays:
                break

            has_more = response_data.get('data', {}).get('has_more', False)
            if not has_more:
                break
            offset += limit
            time.sleep(0.5)

        if not all_replays:
            logger.info('未获取到回放数据')
            return stats

        # 逐条请求 replay detail，合并 replay_info
        for replay in all_replays:
            record_id = replay.get('record_id')
            if not record_id:
                continue
            try:
                detail_url = f"https://live.shopee.{country_domain}/api/v1/replay/{record_id}"
                detail_res = self.session.get(detail_url, timeout=30)
                if detail_res.status_code == 200:
                    detail_data = detail_res.json()
                    replay['replay_info'] = detail_data.get('data', {}).get('replay_info')
                    stats['apis_count'] += 1
                else:
                    logger.warning(f'replay detail 请求失败: record_id={record_id}, HTTP {detail_res.status_code}')
            except Exception as e:
                logger.warning(f'replay detail 请求异常: record_id={record_id}, {e}')
            time.sleep(0.3)

        # 构造完整响应并上报
        merged_response = {"data": {"replay": all_replays, "has_more": False}}
        request_url = f"{base_url}?uid={self.media_user_id}&offset=0&limit={limit}"

        cookies = self.browser_api.get_cookies(self.tab)
        message = self.format_api_message(
            url=request_url,
            request_body='',
            response_body=merged_response,
            cookies=cookies,
        )
        if self.send_api_request(message):
            stats['data_sent'] += 1

        logger.info(f'回放数据采集完成: {len(all_replays)} 条, 上报 {stats["data_sent"]} 次')
        return stats


    def handle_special_logic(self, url: str, response: Any, **kwargs) -> int:
        """处理Shopee平台特殊逻辑
        
        Args:
            url: API URL
            response: 响应数据
        """
        _ = (url, response, kwargs)
        return 0
    
    def _verify_login_by_api(self) -> tuple[bool, dict | None]:
        """通过 API 验证 Shopee 登录态是否有效。

        跨境店使用 CN 专属验证接口（seller.shopee.cn），本土店使用当前域名接口。
        - CN: code == 0 → 登录有效，sub_account_info 包含 account_id/current_shop_id
        - MY: errcode == 0 → 登录有效

        Returns:
            tuple: (is_logged_in, response_data or None)
        """
        try:
            if self.is_cross_border:
                api_label = 'CN'
                api_url = 'https://seller.shopee.cn/api/cnsc/selleraccount/get_session/'
            else:
                api_label = '本土'
                api_url = f'{self._get_base_url()}/api/v2/login/'

            results = self.browser_api.run_js_fetch(
                self.tab,
                [{'url': api_url, 'method': 'GET', 'credentials': 'include'}],
                max_retries=1,
                retry_delay=1.0,
            )

            result = results[0] if results else None
            if not result or not result.get('response'):
                logger.warning(f'[{self.browser_id}] Shopee login API ({api_label}) 无响应')
                return False, None

            response = result['response']
            response_data = json.loads(response) if isinstance(response, str) else response

            if self.is_cross_border:
                # CN API: {"code": 0, "sub_account_info": {"account_id": ..., "current_shop_id": ...}, "message": "success"}
                code = response_data.get('code')
                if code == 0:
                    sub_info = response_data.get('sub_account_info', {}) or {}
                    logger.info(
                        f'[{self.browser_id}] Shopee API (CN) 验证登录成功: '
                        f'account_id={sub_info.get("account_id")}, current_shop_id={sub_info.get("current_shop_id")}'
                    )
                    return True, response_data
                else:
                    logger.warning(
                        f'[{self.browser_id}] Shopee API (CN) 验证登录失败: '
                        f'code={code}, message={response_data.get("message")}'
                    )
                    return False, None
            else:
                errcode = response_data.get('errcode')
                if errcode == 0:
                    logger.info(
                        f'[{self.browser_id}] Shopee API (MY) 验证登录成功: '
                        f'user_id={response_data.get("id")}, shop_id={response_data.get("shopid")}'
                    )
                    return True, response_data
                else:
                    logger.warning(f'[{self.browser_id}] Shopee API (MY) 验证登录失败: errcode={errcode}')
                    return False, None

        except Exception as e:
            logger.warning(f'[{self.browser_id}] Shopee API 验证异常: {e}')
            return False, None

    def _check_login_status(self) -> str:
        """检测账号登录状态

        本土店：Cookie 预检 + API 二次验证
        跨境店：跳过 Cookie 预检（cn 域名 cookie 名称不同），直接 API 验证

        Returns:
            str: "logged_in"（已登录）| "logged_out"（未登录）
        """
        try:
            cookies = self.tab.cookies(all_info=True)
            cookie_dict = {c.get('name'): c.get('value') for c in cookies if c.get('name')}

            if self.is_cross_border:
                # 跨境店 cookie 名称与本土店不同，跳过 cookie 预检，直接 API 验证
                api_ok, _ = self._verify_login_by_api()
                if api_ok:
                    logger.info('跨境店 Shopee 登录验证通过（API 确认）')
                    return "logged_in"
                else:
                    logger.warning('跨境店 Shopee API 验证登录失败，判定为登出')
                    return "logged_out"

            has_session = bool(cookie_dict.get('SPC_SC_SESSION'))

            if not has_session :
                logger.warning('Shopee 登录 cookies 缺失（无 SPC_SC_SESSION）')
                return "logged_out"

            # Cookie 存在，通过 API 二次验证登录态
            api_ok, _ = self._verify_login_by_api()
            if api_ok:
                logger.info('Shopee 登录验证通过（API 确认）')
                return "logged_in"
            else:
                logger.warning('Shopee Cookie 存在但 API 验证失败，判定为登出')
                return "logged_out"

        except Exception as e:
            logger.error(f'检测登录状态失败: {e}')
            return "logged_out"


    def _auto_relogin(self) -> str:
        """检测到登出后自动重新登录：先导航到登录页，再点击已保存账号。

        Returns:
            str: "logged_in"（登录成功）| "logged_out"（登录失败）
        """
        button_selector = 'xpath://*[@class="gLYGM2"]'
        click_button_selector = 'xpath://*[@class="account-item"]/div'

        try:
            # 根据跨境标记选择登录 URL
            if self.is_cross_border:
                login_url = 'https://seller.shopee.cn/seller/login'
            else:
                login_url = f'https://accounts.shopee.{self.country_domain}/seller/login'
            logger.info(f'导航到登录页: {login_url}')
            self.tab.get(login_url)
            time.sleep(5)

            # 尝试点击登录方式选择按钮
            if self.tab.ele(button_selector):
                self.tab.ele(button_selector).click()
                time.sleep(10)


            if self.tab.ele(click_button_selector):
                self.tab.ele(click_button_selector).click()
                time.sleep(10)
                return self._check_login_status()

            return "logged_out"
        except Exception as e:
            logger.warning(f'自动重新登录异常: {e}')
            return "logged_out"


    def _simulate_login(self, account: str, password: str) -> str:
        """执行模拟登录

        此方法用于在检测到账号登出时，自动执行模拟登录操作。

        Args:
            account: 账号
            password: 密码

        Returns:
            str: "logged_in" | "logged_out"
        """
        account_selector = 'xpath://*[contains(@class, "shopee-input__input") and @type="text"]'
        password_selector = 'xpath://*[contains(@class, "shopee-input__input") and @type="password"]'
        login_button_selector = 'xpath://button[@class="shopee-button login-btn shopee-button--primary shopee-button--large shopee-button--block"]'

        try:
            logger.info('开始执行模拟登录流程...')

            # 输入账号密码
            logger.info(f'输入账号: {account}')
            self.tab.ele(account_selector).input(account)
            self.tab.ele(password_selector).input(password)

            logger.info('点击登录按钮...')
            self.tab.ele(login_button_selector).click()

            # 等待登录结果
            time.sleep(5)
            return self._check_login_status()

        except Exception as e:
            logger.error(f'模拟登录失败: {e}')
            return "logged_out"

    def _build_live_detail_request(self, session_id: str, headers: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """构造 liveDetail 接口请求参数。"""
        request_headers = self._build_request_headers(headers)
        request_headers.update(self._build_shopee_api_headers())
        return {
            'url': f'{self._get_base_url()}/api/supply/lm/sellercenter/liveDetail?sessionId={session_id}',
            'method': 'GET',
            'headers': request_headers,
            'credentials': 'include',
        }

    def _fetch_replay_detail_via_js(self, session: Dict[str, Any], headers: Dict[str, Any]) -> List[Dict[str, Any]]:
        """对单个回放 session 发起详情接口 JS 注入。"""
        results = []
        try:
            session_id = session.get('sessionId')
            if not session_id:
                return results

            # 请求 liveDetail 接口
            detail_request = self._build_live_detail_request(str(session_id), headers=headers)
            detail_results = self.browser_api.run_js_fetch(self.tab, [detail_request], max_retries=2)

            if not detail_results or not detail_results[0] or not detail_results[0].get('response'):
                logger.warning(f'liveDetail 接口失败: sessionId={session_id}')
                return results

            detail_result = detail_results[0]
            results.append(detail_result)

            # 解析响应获取时间参数
            response_json = self._parse_json_response(detail_result.get('response'))
            live_info = response_json.get('data', {}).get('liveInfo', {})
            start_time = live_info.get('startTime')
            duration = live_info.get('duration')

            if not start_time:
                logger.warning(f'liveDetail 响应中未找到 startTime: sessionId={session_id}')
                return results

            if not duration:
                logger.warning(f'liveDetail 响应中未找到 duration: sessionId={session_id}')
                return results

            logger.debug(f'解析时间参数: sessionId={session_id}, startTime={start_time}, duration={duration}')

            # 请求 liveCoordinate 接口
            coordinate_request = self._build_live_coordinate_request(
                str(session_id), start_time, duration, headers=headers
            )
            coordinate_results = self.browser_api.run_js_fetch(self.tab, [coordinate_request], max_retries=2)

            if coordinate_results and coordinate_results[0] and coordinate_results[0].get('response'):
                results.append(coordinate_results[0])

            logger.info(f'回放详情获取完成: sessionId={session_id}, 共 {len(results)} 个接口响应')
            return results
        except Exception as e:
            logger.error(f'获取回放详情失败: sessionId={session.get("sessionId")}, 错误: {e}')
            return results

    def _build_live_coordinate_request(
        self,
        session_id: str,
        start_time: int,
        duration: int,
        headers: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """构造 liveCoordinate/v2 接口请求参数。"""
        request_headers = self._build_request_headers(headers)
        request_headers.update(self._build_shopee_api_headers())

        # startTime 向下取整到分钟级
        aligned_start_time = (start_time // 60000) * 60000
        # size 根据 duration 计算（向上取整）
        size = math.ceil(duration / 60000)

        return {
            'url': f'{self._get_base_url()}/api/supply/lm/sellercenter/liveCoordinate/v2?sessionId={session_id}&startTime={aligned_start_time}&size={size}',
            'method': 'GET',
            'headers': request_headers,
            'credentials': 'include',
        }
