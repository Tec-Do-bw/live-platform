"""Lazada HTTP 采集器。

覆盖 Lazada 全部 19 个接口：
- 卖家中心（1.1~1.5）：5 个接口
- 数据洞察（2.1.x~2.4.x）：12 个接口
- LazLive 直播后台（3.1~3.2）：2 个接口

技术特点：
- 双端口 Cookie：sellercenter + live（acs-m mtop）
- mtop 签名：md5(token + '&' + t + '&' + appKey + '&' + data)
- 分页处理：mtop 分页（pageNum, 100），BA 接口无分页
- API 序列驱动：每个 API 类型串行完成（含翻页）后再进入下一个
- 3.1→3.2 依赖：3.1 完成后通过 on_completed 回调构造 3.2 Task
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Any

from crawlers.http.base import BaseHttpCrawler, ApiSequence
from core.config import Settings
from downloader import Task, DownloadResult
from monitor.recrawl.proxy import get_proxy_for_account
from services import cookie_manager
from services.cookie_manager import get_cookies as _get_cookies, get_cookie_extra as _get_cookie_extra
from utils.alert import alert_manager
from utils.logger import logger


# 国家域名映射（6 个国家，支持中英文关键词）
LAZADA_COUNTRY_MAP = {
    '泰国': 'co.th',
    'thailand': 'co.th',
    '马来': 'com.my',
    'malaysia': 'com.my',
    '印尼': 'co.id',
    'indonesia': 'co.id',
    '越南': 'vn',
    'vietnam': 'vn',
    '新加坡': 'sg',
    'singapore': 'sg',
    '菲律宾': 'com.ph',
    'philippines': 'com.ph',
}

# 时区映射（UTC 偏移量，小时）
LAZADA_TIMEZONE_MAP = {
    'co.th': 7,      # 泰国 UTC+7
    'com.my': 8,     # 马来西亚 UTC+8
    'co.id': 7,      # 印尼 UTC+7
    'vn': 7,         # 越南 UTC+7
    'sg': 8,         # 新加坡 UTC+8
    'com.ph': 8,     # 菲律宾 UTC+8
}

# API 类型常量（19 个接口）
API_TYPE_SELLER_METRICS = 'lazada_seller_metrics'              # 1.1
API_TYPE_SELLER_PRODUCT_ROOMS = 'lazada_seller_product_rooms'  # 1.2
API_TYPE_SELLER_PRODUCTS = 'lazada_seller_products'            # 1.3
API_TYPE_REALTIME_TREND = 'lazada_realtime_trend'              # 1.4
API_TYPE_REALTIME_DETAIL = 'lazada_realtime_detail'            # 1.5
API_TYPE_BA_KEY_OVERVIEW = 'lazada_ba_key_overview'            # 2.1.1
API_TYPE_BA_KEY_TREND = 'lazada_ba_key_trend'                  # 2.1.2
API_TYPE_BA_TRAFFIC_OVERALL = 'lazada_ba_traffic_overall'      # 2.2.1
API_TYPE_BA_TRAFFIC_SOURCE = 'lazada_ba_traffic_source'        # 2.2.2
API_TYPE_BA_TRAFFIC_SEARCH = 'lazada_ba_traffic_search'        # 2.2.3
API_TYPE_BA_PRODUCT_OVERVIEW = 'lazada_ba_product_overview'    # 2.3.1
API_TYPE_BA_PRODUCT_DIAGNOSIS = 'lazada_ba_product_diagnosis'  # 2.3.2
API_TYPE_BA_PRODUCT_PERF_REVENUE = 'lazada_ba_product_perf_revenue'  # 2.3.3
API_TYPE_BA_PRODUCT_PERF_VISITOR = 'lazada_ba_product_perf_visitor'  # 2.3.4
API_TYPE_BA_PROMO_OVERVIEW = 'lazada_ba_promo_overview'        # 2.4.1
API_TYPE_BA_PROMO_TREND = 'lazada_ba_promo_trend'              # 2.4.2
API_TYPE_BA_PROMO_CATEGORY = 'lazada_ba_promo_category'        # 2.4.3
API_TYPE_LIVE_LIST = 'lazada_live_list'                        # 3.1
API_TYPE_ROOM_METRICS = 'lazada_room_metrics'                  # 3.2

# 接口分组映射（按 Cookie 端口）
# sellercenter Cookie：1.1~1.5, 2.x（所有卖家中心接口）
SELLERCENTER_API_TYPES = {
    API_TYPE_SELLER_METRICS,
    API_TYPE_SELLER_PRODUCT_ROOMS,
    API_TYPE_SELLER_PRODUCTS,
    API_TYPE_REALTIME_TREND,
    API_TYPE_REALTIME_DETAIL,
    API_TYPE_BA_KEY_OVERVIEW,
    API_TYPE_BA_KEY_TREND,
    API_TYPE_BA_TRAFFIC_OVERALL,
    API_TYPE_BA_TRAFFIC_SOURCE,
    API_TYPE_BA_TRAFFIC_SEARCH,
    API_TYPE_BA_PRODUCT_OVERVIEW,
    API_TYPE_BA_PRODUCT_DIAGNOSIS,
    API_TYPE_BA_PRODUCT_PERF_REVENUE,
    API_TYPE_BA_PRODUCT_PERF_VISITOR,
    API_TYPE_BA_PROMO_OVERVIEW,
    API_TYPE_BA_PROMO_TREND,
    API_TYPE_BA_PROMO_CATEGORY,
}

# live Cookie：仅 3.1, 3.2（LazLive 直播后台接口）
LIVE_API_TYPES = {
    API_TYPE_LIVE_LIST,
    API_TYPE_ROOM_METRICS,
}


class LazadaHttpCrawler(BaseHttpCrawler):
    """Lazada HTTP 采集器。"""

    def __init__(self, browser_id: str = '', full_collection: bool = False,
                 group_name: str = '', batch_id: str = '', crawl_type: str = 'history'):
        super().__init__(browser_id, full_collection, group_name, batch_id)

        # 校验 crawl_type 参数
        if crawl_type not in ('realtime', 'history'):
            raise ValueError(f'crawl_type 必须为 "realtime" 或 "history"，当前值: {crawl_type}')

        # 存储采集类型
        self.crawl_type = crawl_type

        # 从 group_name 解析国家域名（格式：'新加坡团队-lazada' -> 'sg'）
        self.country_domain = self._parse_country_domain(group_name)

        # 初始化 base URL
        self.sellercenter_base = f'https://sellercenter.lazada.{self.country_domain}/ba/sycm/lazada/faas'
        self.live_base = f'https://acs-m.lazada.{self.country_domain}/h5'

        # 记录因 Cookie 缺失跳过的 api_type
        self.skipped_api_types: list[str] = []

        # 缓存 resolve_collection_mode 的结果，供分页早停使用
        self._resolved_is_full: bool | None = None

        logger.info(f'初始化 Lazada HTTP 采集器，country_domain: {self.country_domain}, crawl_type: {crawl_type}')

    def get_platform_name(self) -> str:
        """返回平台标识。"""
        return 'lazada'

    def _parse_country_domain(self, group_name: str) -> str:
        """从 group_name 解析国家域名。

        Args:
            group_name: 分组名称，如 '新加坡团队-lazada'

        Returns:
            国家域名，如 'co.th'
        """
        # 支持中英文关键词匹配
        for keyword, domain in LAZADA_COUNTRY_MAP.items():
            if keyword in group_name or keyword in group_name.lower():
                return domain

        # 默认返回泰国
        logger.warning(f'无法从 group_name 解析国家域名，使用默认值 th: {group_name}')
        return 'co.th'

    # ------------------------------------------------------------------
    # Cookie 与签名（任务 2.1~2.3）
    # ------------------------------------------------------------------

    def get_cookies(self) -> dict | None:
        """获取双端口 Cookie（sellercenter + live）。

        Returns:
            {'sellercenter': {...}, 'live': {...}}，两端口均无 Cookie 返回 None
        """
        sc = _get_cookies(self.browser_id, 'lazada', 'sellercenter')
        live = _get_cookies(self.browser_id, 'lazada', 'live')
        if sc is None and live is None:
            return None
        return {'sellercenter': sc or {}, 'live': live or {}}

    def get_proxy(self) -> str | None:
        """通过 AdsPower API 获取账号对应的代理 IP。

        Lazada 采集强制要求使用代理，代理获取失败时抛出异常并终止采集。

        Returns:
            代理 URL 字符串（如 'socks5://user:pass@host:port'）

        Raises:
            RuntimeError: 代理获取失败时抛出
        """
        proxy_dict = get_proxy_for_account(self.browser_id)

        if proxy_dict is None:
            # 代理获取失败，发送告警并抛出异常
            error_msg = f'账号 {self.browser_id} 代理获取失败，终止采集'
            logger.error(error_msg)
            alert_manager.send_alert(
                alert_type='proxy_fetch_failed',
                title='Lazada 代理获取失败',
                content=(
                    f'账号: {self.browser_id}\n'
                    f'分组: {self.group_name}\n'
                    f'错误: 无法从 AdsPower 获取代理配置\n'
                    f'说明: Lazada 采集强制要求使用代理，代理获取失败将终止采集'
                ),
            )
            raise RuntimeError(error_msg)

        # 提取代理 URL（优先 http，其次 https）
        proxy_url = proxy_dict.get('http') or proxy_dict.get('https')

        if not proxy_url:
            # 代理配置为空，发送告警并抛出异常
            error_msg = f'账号 {self.browser_id} 代理配置为空，终止采集'
            logger.error(error_msg)
            alert_manager.send_alert(
                alert_type='proxy_config_empty',
                title='Lazada 代理配置为空',
                content=(
                    f'账号: {self.browser_id}\n'
                    f'分组: {self.group_name}\n'
                    f'错误: 代理配置字典为空\n'
                    f'代理配置: {proxy_dict}\n'
                    f'说明: Lazada 采集强制要求使用代理，代理配置为空将终止采集'
                ),
            )
            raise RuntimeError(error_msg)

        logger.info(f'账号 {self.browser_id} 使用代理: {proxy_url[:50]}...')
        return proxy_url

    @staticmethod
    def _calc_mtop_sign(token: str, t: str, app_key: str, data: str) -> str:
        """计算 mtop 签名。

        签名公式：md5(token + '&' + t + '&' + appKey + '&' + data)

        Args:
            token: _m_h5_tk 前 32 位
            t: 毫秒时间戳字符串
            app_key: 固定 '4272'
            data: 紧凑 JSON 字符串
        """
        raw = f'{token}&{t}&{app_key}&{data}'
        return hashlib.md5(raw.encode()).hexdigest()

    def _build_mtop_task(self, api: str, api_type: str, data: dict,
                         cookies: dict, page_num: int = 1,
                         page_size: int = 100,
                         extra_meta: dict | None = None,
                         method: str = 'GET') -> Task:
        """构造 mtop 接口 Task（自动计算签名，支持 GET/POST）。

        Args:
            api: mtop 接口名（如 'mtop.lazada.live.data.seller.metrics'）
            api_type: API 类型标识
            data: 请求数据字典
            cookies: live 端口 Cookie 字典
            page_num: 页码
            page_size: 每页条数
            extra_meta: 额外 meta 数据
            method: 请求方式，'GET' 或 'POST'
        """
        # 紧凑 JSON
        data_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

        # 从 _m_h5_tk 提取 token
        m_h5_tk = cookies.get('_m_h5_tk', '')
        token = m_h5_tk.split('_')[0] if m_h5_tk else ''

        # 时间戳（毫秒）
        t = str(int(time.time() * 1000))

        # 签名
        app_key = '4272'
        sign = self._calc_mtop_sign(token, t, app_key, data_str)

        # 国家代码映射
        region_map = {
            'co.th': 'LAZADA_TH',
            'com.my': 'LAZADA_MY',
            'co.id': 'LAZADA_ID',
            'vn': 'LAZADA_VN',
            'sg': 'LAZADA_SG',
            'com.ph': 'LAZADA_PH',
        }
        region_id = region_map.get(self.country_domain, 'LAZADA_TH')

        # 构造完整 URL（包含所有必需参数）
        url = f'{self.live_base}/{api}/1.0/'

        # 元数据参数（GET/POST 共用）
        params = {
            'jsv': '2.6.1',
            'appKey': app_key,
            't': t,
            'sign': sign,
            'v': '1.0',
            'timeout': '30000',
            'H5Request': 'true',
            'url': api,
            'x-i18n-language': 'zh',
            'api': api,
            'type': 'originaljson',
            'dataType': 'json',
            'valueType': 'original',
            'x-i18n-regionID': region_id,
        }

        # POST 请求：data 参数移到 body
        if method == 'POST':
            post_body = {'data': data_str}
        else:
            # GET 请求：data 参数放在 query string
            params['data'] = data_str
            post_body = None

        meta = {
            'api_type': api_type,
            'page_num': page_num,
            'page_size': page_size,
        }
        if extra_meta:
            meta.update(extra_meta)

        return Task(
            url=url,
            method=method,
            params=params,
            data=post_body,  # POST body（GET 时为 None）
            headers={'Cookie': self._cookie_header(cookies)},
            meta=meta,
        )

    # ------------------------------------------------------------------
    # 日期计算（任务 3.1~3.3）
    # ------------------------------------------------------------------

    def _get_country_today(self) -> datetime:
        """按国家时区获取当地日期。"""
        utc_offset = LAZADA_TIMEZONE_MAP.get(self.country_domain, 8)
        return datetime.utcnow() + timedelta(hours=utc_offset)

    def _get_date_range(self, is_full: bool) -> list[datetime]:
        """返回日期列表（增量 7 天 / 全量 30 天）。

        日期范围：T-N 到 T-1（不含今天）。
        """
        today = self._get_country_today().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        days = 30 if is_full else 7
        return [today - timedelta(days=i) for i in range(days, 0, -1)]

    @staticmethod
    def _format_date_mtop(date: datetime) -> str:
        """mtop 日期格式：YYYYMMDD"""
        return date.strftime('%Y%m%d')

    @staticmethod
    def _format_date_ba(date: datetime) -> str:
        """BA 日期格式：YYYY-MM-DD"""
        return date.strftime('%Y-%m-%d')

    # ------------------------------------------------------------------
    # Task 构造方法（任务 4.1~4.6）
    # ------------------------------------------------------------------

    def _build_seller_metrics_tasks(self, cookies: dict, is_full: bool) -> list[Task]:
        """构造 1.1 seller_metrics 逐日采集 Task。"""
        tasks = []
        dates = self._get_date_range(is_full)
        for date in dates:
            date_str = self._format_date_mtop(date)
            data = {
                'period': 'day',
                'dateRange': f'{date_str}|{date_str}',
            }
            task = self._build_mtop_task(
                api='mtop.lazada.live.data.seller.metrics',
                api_type=API_TYPE_SELLER_METRICS,
                data=data,
                cookies=cookies,
                extra_meta={'date': date_str},
            )
            tasks.append(task)
        return tasks

    def _build_lazlive_list_tasks(self, cookies: dict, is_full: bool) -> list[Task]:
        """构造 3.1 直播列表 Task（POST 请求，根据 crawl_type 设置 roomStatus）。"""
        # 1. 根据 crawl_type 选择 roomStatus
        if self.crawl_type == 'realtime':
            # 实时模式：只查询 Online 状态的直播间
            room_statuses = "Online"
            logger.info('实时模式：只查询 Online 状态的直播间')
        else:
            # 历史模式：查询所有状态的直播间
            room_statuses = "Notice,Online,End,History"
            logger.info('历史模式：查询 Notice,Online,End,History 状态的直播间')

        # 2. 计算时区偏移（注意取负值）
        utc_offset = LAZADA_TIMEZONE_MAP.get(self.country_domain, 8)
        timezone_offset = -utc_offset  # 文档中 -7 表示 UTC+7

        # 3. 构造 data 字典
        data = {
            '_timezone': timezone_offset,
            'roomStatus': room_statuses,
            'orderByRoomStatus': "Notice,Online,End,History",
            'pageNum': 1,
            'pageSize': 100,
        }

        # 4. 构造 POST 请求 Task
        task = self._build_mtop_task(
            api='mtop.lazada.live.querylivesbystatus',
            api_type=API_TYPE_LIVE_LIST,
            data=data,
            cookies=cookies,
            page_num=1,
            page_size=100,
            extra_meta={'room_statuses': room_statuses, 'timezone_offset': timezone_offset},
            method='POST',
        )

        return [task]

    def build_api_sequence(self, cookies: dict, is_full: bool) -> list[ApiSequence]:
        """构造 API 序列列表（按执行顺序）。

        实时模式只构建 3.1 + 3.2，历史模式构建全部 19 个接口。

        Args:
            cookies: {'sellercenter': {...}, 'live': {...}}
            is_full: 是否全量采集
        """
        self._resolved_is_full = is_full
        sequences: list[ApiSequence] = []
        sc_cookies = cookies.get('sellercenter')
        live_cookies = cookies.get('live')

        # 保存引用，Token 刷新时原地更新这些字典，闭包中的任务构造器自动使用新值
        self._sc_cookies = sc_cookies
        self._live_cookies = live_cookies

        if self.crawl_type == 'realtime':
            logger.info('实时模式：只构建 3.1 + 3.2 直播接口，跳过 1.x 和 2.x')
            self.skipped_api_types.extend(list(SELLERCENTER_API_TYPES))

            if live_cookies:
                sequences.append(self._seq_live_list(live_cookies, is_full))
            else:
                self.skipped_api_types.extend(list(LIVE_API_TYPES))
                logger.warning('live Cookie 缺失，跳过 3.1 和 3.2 接口')
        else:
            # 历史模式：按顺序构建所有接口
            if sc_cookies:
                # 1.1 seller_metrics（逐日，无分页）
                sequences.append(self._seq_seller_metrics(sc_cookies, is_full))
                # 1.2 productRooms（range，有分页）
                sequences.append(self._seq_seller_product_rooms(sc_cookies, is_full))
                # 1.3 products（range，有分页）
                sequences.append(self._seq_seller_products(sc_cookies, is_full))
                # 1.4~1.5 实时接口（无日期，无分页）
                sequences.append(self._seq_realtime_trend(sc_cookies))
                sequences.append(self._seq_realtime_detail(sc_cookies))
                # 2.1.x~2.4.x BA 逐日接口（12 个，全部无分页）
                sequences.extend(self._seq_ba_daily_all(sc_cookies, is_full))
            else:
                self.skipped_api_types.extend(list(SELLERCENTER_API_TYPES))
                logger.warning('sellercenter Cookie 缺失，跳过 1.x 和 2.x 接口')

            if live_cookies:
                sequences.append(self._seq_live_list(live_cookies, is_full))
            else:
                self.skipped_api_types.extend(list(LIVE_API_TYPES))
                logger.warning('live Cookie 缺失，跳过 3.1 和 3.2 接口')

        logger.info(f'构造 API 序列完成，共 {len(sequences)} 个')
        return sequences

    # ------------------------------------------------------------------
    # 序列构造器
    # ------------------------------------------------------------------

    def _seq_seller_metrics(self, cookies: dict, is_full: bool) -> ApiSequence:
        """1.1 seller_metrics 序列（逐日采集，无分页）。"""
        return ApiSequence(
            api_type=API_TYPE_SELLER_METRICS,
            build_initial_tasks=lambda: self._build_seller_metrics_tasks(cookies, is_full),
        )

    def _seq_seller_product_rooms(self, cookies: dict, is_full: bool) -> ApiSequence:
        """1.2 productRooms 序列（range 采集，有分页）。"""
        dates = self._get_date_range(is_full)
        start_date = self._format_date_mtop(dates[0])
        end_date = self._format_date_mtop(dates[-1])
        period = 'l30d' if is_full else 'l7d'

        def build_initial() -> list[Task]:
            data = {
                'period': period,
                'dateRange': f'{start_date}|{end_date}',
                'pageNum': 1,
                'pageSize': 100,
            }
            return [self._build_mtop_task(
                api='mtop.lazada.live.data.seller.productRooms',
                api_type=API_TYPE_SELLER_PRODUCT_ROOMS,
                data=data, cookies=cookies, page_num=1, page_size=100,
                extra_meta={'start_date': start_date, 'end_date': end_date, 'period': period},
            )]

        def build_next(last_results: list[dict], page: int) -> list[Task]:
            if not last_results:
                return []
            last = last_results[-1]
            if not self._needs_next_page_mtop(last, page - 1):
                return []
            data = {
                'period': period,
                'dateRange': f'{start_date}|{end_date}',
                'pageNum': page,
                'pageSize': 100,
            }
            return [self._build_mtop_task(
                api='mtop.lazada.live.data.seller.productRooms',
                api_type=API_TYPE_SELLER_PRODUCT_ROOMS,
                data=data, cookies=cookies, page_num=page, page_size=100,
                extra_meta={'start_date': start_date, 'end_date': end_date, 'period': period},
            )]

        return ApiSequence(
            api_type=API_TYPE_SELLER_PRODUCT_ROOMS,
            build_initial_tasks=build_initial,
            build_next_page=build_next,
            max_pages=10,
        )

    def _seq_seller_products(self, cookies: dict, is_full: bool) -> ApiSequence:
        """1.3 products 序列（range 采集，有分页）。"""
        dates = self._get_date_range(is_full)
        start_date = self._format_date_mtop(dates[0])
        end_date = self._format_date_mtop(dates[-1])
        period = 'l30d' if is_full else 'l7d'

        def build_initial() -> list[Task]:
            data = {
                'period': period,
                'dateRange': f'{start_date}|{end_date}',
                'pageNum': 1,
                'pageSize': 100,
            }
            return [self._build_mtop_task(
                api='mtop.lazada.live.data.seller.products',
                api_type=API_TYPE_SELLER_PRODUCTS,
                data=data, cookies=cookies, page_num=1, page_size=100,
                extra_meta={'start_date': start_date, 'end_date': end_date, 'period': period},
            )]

        def build_next(last_results: list[dict], page: int) -> list[Task]:
            if not last_results:
                return []
            last = last_results[-1]
            if not self._needs_next_page_mtop(last, page - 1):
                return []
            data = {
                'period': period,
                'dateRange': f'{start_date}|{end_date}',
                'pageNum': page,
                'pageSize': 100,
            }
            return [self._build_mtop_task(
                api='mtop.lazada.live.data.seller.products',
                api_type=API_TYPE_SELLER_PRODUCTS,
                data=data, cookies=cookies, page_num=page, page_size=100,
                extra_meta={'start_date': start_date, 'end_date': end_date, 'period': period},
            )]

        return ApiSequence(
            api_type=API_TYPE_SELLER_PRODUCTS,
            build_initial_tasks=build_initial,
            build_next_page=build_next,
            max_pages=10,
        )

    def _seq_realtime_trend(self, cookies: dict) -> ApiSequence:
        """1.4 realtime trend 序列（无日期，无分页）。"""
        headers = {
            'Cookie': self._cookie_header(cookies),
            'Accept': 'application/json',
        }

        def build_initial() -> list[Task]:
            return [Task(
                url=f'{self.sellercenter_base}/realtime/key/detail/trend/accumulationV2.json',
                headers=headers,
                meta={'api_type': API_TYPE_REALTIME_TREND},
            )]

        return ApiSequence(
            api_type=API_TYPE_REALTIME_TREND,
            build_initial_tasks=build_initial,
        )

    def _seq_realtime_detail(self, cookies: dict) -> ApiSequence:
        """1.5 realtime detail 序列（无日期，无分页）。"""
        headers = {
            'Cookie': self._cookie_header(cookies),
            'Accept': 'application/json',
        }

        def build_initial() -> list[Task]:
            return [Task(
                url=f'{self.sellercenter_base}/realtime/key/detailV2.json',
                headers=headers,
                meta={'api_type': API_TYPE_REALTIME_DETAIL},
            )]

        return ApiSequence(
            api_type=API_TYPE_REALTIME_DETAIL,
            build_initial_tasks=build_initial,
        )

    def _seq_ba_daily_all(self, cookies: dict, is_full: bool) -> list[ApiSequence]:
        """2.1.x~2.4.x 共 12 个 BA 逐日接口序列（全部无分页）。"""
        dates = self._get_date_range(is_full)
        headers = {
            'Cookie': self._cookie_header(cookies),
            'Accept': 'application/json',
        }

        # BA 接口定义：(路径, api_type, 额外参数)
        ba_apis = [
            ('dashboard/key/overviewV2', API_TYPE_BA_KEY_OVERVIEW, {}),
            ('dashboard/key/trendV2', API_TYPE_BA_KEY_TREND, {}),
            ('dashboard/traffic/overall', API_TYPE_BA_TRAFFIC_OVERALL, {}),
            ('dashboard/traffic/source/ranking', API_TYPE_BA_TRAFFIC_SOURCE, {}),
            ('dashboard/traffic/search/ranking', API_TYPE_BA_TRAFFIC_SEARCH, {}),
            ('dashboard/product/overview', API_TYPE_BA_PRODUCT_OVERVIEW, {}),
            ('product/diagnosis/overview', API_TYPE_BA_PRODUCT_DIAGNOSIS, {}),
            ('product/performance/batch/itemV2', API_TYPE_BA_PRODUCT_PERF_REVENUE,
             {'orderBy': 'productRevenue', 'cateId': '', 'brandId': '', 'searchStr': '', 'device': '1', 'order': 'desc', 'dashboard': 'true'}),
            ('product/performance/batch/itemV2', API_TYPE_BA_PRODUCT_PERF_VISITOR,
             {'orderBy': 'productIpvUv', 'cateId': '', 'brandId': '', 'searchStr': '', 'device': '1', 'order': 'desc', 'dashboard': 'true'}),
            ('dashboard/promotion/board/overview', API_TYPE_BA_PROMO_OVERVIEW, {}),
            ('dashboard/promotion/board/trend', API_TYPE_BA_PROMO_TREND, {}),
            ('dashboard/promotion/board/category/ratio', API_TYPE_BA_PROMO_CATEGORY, {}),
        ]

        sequences = []
        for path, api_type, extra_params in ba_apis:
            # 闭包捕获当前循环变量
            def make_builder(_path=path, _api_type=api_type, _extra=extra_params):
                def build_initial() -> list[Task]:
                    tasks = []
                    for date in dates:
                        date_str = self._format_date_ba(date)
                        date_range = f'{date_str}|{date_str}'
                        params = {'dateRange': date_range, 'dateType': 'day'}
                        params.update(_extra)
                        tasks.append(Task(
                            url=f'{self.sellercenter_base}/{_path}.json',
                            params=params,
                            headers=headers,
                            meta={'api_type': _api_type, 'date': date_str},
                        ))
                    return tasks
                return build_initial

            sequences.append(ApiSequence(
                api_type=api_type,
                build_initial_tasks=make_builder(),
            ))

        return sequences

    def _seq_live_list(self, cookies: dict, is_full: bool) -> ApiSequence:
        """3.1 直播列表 + 3.2 直播详情序列（有分页 + 依赖任务）。"""

        def build_initial() -> list[Task]:
            return self._build_lazlive_list_tasks(cookies, is_full)

        def build_next(last_results: list[dict], page: int) -> list[Task]:
            if not last_results:
                return []
            last = last_results[-1]
            if not self._needs_next_page_mtop(last, page - 1):
                return []
            # 增量模式早停
            if self._check_live_list_early_stop(last, is_full):
                return []
            # 从 meta 中恢复 roomStatus 和 timezone
            meta = last.get('_meta', {})
            room_statuses = meta.get('room_statuses', 'End,History,Online')
            timezone_offset = meta.get('timezone_offset', -8)
            data = {
                '_timezone': timezone_offset,
                'roomStatus': room_statuses,
                'orderByRoomStatus': room_statuses,
                'pageNum': page,
                'pageSize': 100,
            }
            return [self._build_mtop_task(
                api='mtop.lazada.live.querylivesbystatus',
                api_type=API_TYPE_LIVE_LIST,
                data=data, cookies=cookies, page_num=page, page_size=100,
                extra_meta={'room_statuses': room_statuses, 'timezone_offset': timezone_offset},
                method='POST',
            )]

        def on_completed(all_results: list[dict]) -> list[Task]:
            # 从 3.1 结果提取 liveUuid，构造 3.2 Task
            live_uuids = self._extract_live_uuids(all_results)
            if not live_uuids:
                return []
            logger.info(f'从 3.1 结果提取 {len(live_uuids)} 个 liveUuid，构造 3.2 Task')
            return [self._build_room_metrics_task(uuid, cookies) for uuid in live_uuids]

        return ApiSequence(
            api_type=API_TYPE_LIVE_LIST,
            build_initial_tasks=build_initial,
            build_next_page=build_next,
            on_completed=on_completed,
            max_pages=10,
        )

    # ------------------------------------------------------------------
    # 分页处理（任务 5.1~5.5）
    # ------------------------------------------------------------------

    def _needs_next_page_mtop(self, result: dict, page_num: int) -> bool:
        """检查 mtop 分页接口是否需要续页。

        Args:
            result: parse_response 返回的结果字典
            page_num: 当前页码

        Returns:
            True 表示需要续页
        """
        # 最大 10 页保护
        if page_num >= 10:
            logger.warning(f'mtop 分页达到最大页数 10，终止翻页: {result.get("api_type")}')
            return False

        data = result.get('data', {}) or {}
        api_type = result.get('api_type')

        # parse_response 返回的 data 是整个 JSON 响应，业务数据在 data['data'] 中
        inner = data.get('data', {}) or {}

        # 3.1 接口：totalCount 字段（字符串类型）
        if api_type == API_TYPE_LIVE_LIST:
            raw = inner.get('totalCount') if isinstance(inner, dict) else None
        else:
            # 1.2/1.3 接口：total 在外层 data 中
            raw = data.get('total')

        if raw is None:
            return False

        try:
            total = int(raw)
        except (ValueError, TypeError):
            return False

        return page_num * 100 < total

    def _check_live_list_early_stop(self, result: dict, is_full: bool) -> bool:
        """检查 3.1 增量模式是否需要提前终止。

        Args:
            result: parse_response 返回的结果字典
            is_full: 是否全量模式

        Returns:
            True 表示需要提前终止
        """
        # 实时模式不需要早停（Online 直播间数量少，无需提前终止）
        if self.crawl_type == 'realtime':
            return False

        if is_full:
            return False

        # 检查最后一条数据时间戳是否早于 T-7
        data = result.get('data', {})
        items = data.get('data', []) if isinstance(data, dict) else []
        if not items:
            return True

        last_item = items[-1]
        last_timestamp = last_item.get('startTime', 0)  # 毫秒时间戳
        if not last_timestamp:
            return False

        # 计算 T-7 的时间戳
        cutoff = self._get_country_today() - timedelta(days=7)
        cutoff_timestamp = int(cutoff.timestamp() * 1000)

        if last_timestamp < cutoff_timestamp:
            logger.info(f'3.1 增量模式提前终止：最后一条数据时间早于 T-7')
            return True

        return False

    # ------------------------------------------------------------------
    # 多阶段采集（任务 6.1~6.2）
    # ------------------------------------------------------------------

    def _build_room_metrics_task(self, live_uuid: str, cookies: dict) -> Task:
        """构造单个 3.2 直播详情 Task。

        Args:
            live_uuid: 直播 UUID
            cookies: live 端口 Cookie
        """
        data = {'liveUuid': live_uuid}
        return self._build_mtop_task(
            api='mtop.lazada.live.data.presenter.room.metrics',
            api_type=API_TYPE_ROOM_METRICS,
            data=data,
            cookies=cookies,
            extra_meta={'live_uuid': live_uuid},
        )

    def _extract_live_uuids(self, results: list[dict]) -> list[str]:
        """从 3.1 结果提取 liveUuid（根据 crawl_type 过滤）。

        Args:
            results: 3.1 API 的所有解析结果

        Returns:
            去重后的 liveUuid 列表
        """
        live_uuids = []
        for result in results:
            if result.get('api_type') != API_TYPE_LIVE_LIST:
                continue

            resp_data = result.get('data', {})
            inner = resp_data.get('data', {}) if isinstance(resp_data, dict) else {}
            inner2 = inner.get('data', {}) if isinstance(inner, dict) else {}
            live_info_dtos = inner2.get('liveInfoDTOs', {}) if isinstance(inner2, dict) else {}

            items = []
            if isinstance(live_info_dtos, dict):
                # 对象格式：按 roomStatus 提取
                if self.crawl_type == 'realtime':
                    items = live_info_dtos.get('Online', [])
                else:
                    items = live_info_dtos.get('End', []) + live_info_dtos.get('History', [])
            elif isinstance(live_info_dtos, list):
                # 数组格式：根据 crawl_type 过滤
                if self.crawl_type == 'realtime':
                    items = [item for item in live_info_dtos
                             if isinstance(item, dict) and item.get('roomStatus') == 'Online']
                else:
                    items = [item for item in live_info_dtos
                             if isinstance(item, dict) and item.get('roomStatus') in ('End', 'History')]

            # 提取 liveUuid
            for item in items:
                if isinstance(item, dict):
                    live_uuid = item.get('liveUuid')
                    if live_uuid and live_uuid not in live_uuids:
                        live_uuids.append(live_uuid)

        return live_uuids

    # ------------------------------------------------------------------
    # 数据上报格式化
    # ------------------------------------------------------------------

    def format_message(self, url: str, response_text: str,
                       cookies: dict | None = None,
                       extra: str | None = None,
                       task: Task | None = None) -> dict:
        """构造数据上报消息体（符合 Lazada 数仓对接文档格式，支持 GET/POST）。

        Args:
            url: 请求 URL
            response_text: 响应文本
            cookies: Cookie 字典（未使用，从 self.get_cookies() 获取）
            extra: 额外信息（未使用）
            task: Task 对象（用于获取 method 和 POST body）

        Returns:
            符合文档格式的消息体
        """
        from urllib.parse import urlparse, urlencode

        # params: 从 task.params 重建查询参数字符串
        if task and task.params:
            params = urlencode(task.params)
        else:
            parsed = urlparse(url)
            params = parsed.query

        # 拼接完整 URL（用于 request.url 和 fromUrl）
        if params and '?' not in url:
            full_url = f'{url}?{params}'
        else:
            full_url = url

        # method: 从 task 获取真实 method
        method = task.method if task else 'GET'

        # body: POST 请求时填充
        if method == 'POST' and task and task.data:
            if isinstance(task.data, dict):
                body = json.dumps(task.data, ensure_ascii=False)
            else:
                body = ''
        else:
            body = ''

        # cookies: 从当前采集器获取
        all_cookies = self.get_cookies() or {}
        sc_cookies = all_cookies.get('sellercenter', {})
        live_cookies = all_cookies.get('live', {})

        # 合并两端口 Cookie（优先 sellercenter）
        merged_cookies = {**live_cookies, **sc_cookies}
        cookies_str = json.dumps(merged_cookies, ensure_ascii=False)

        # fromUrl: 请求的页面 URL（使用完整 URL）
        from_url = full_url

        # extra.seller_id: 从数据库 extra 读取
        seller_id = _get_cookie_extra(self.browser_id, 'lazada', 'live').get('seller_id', '')

        # extra.venture: 从 country_domain 推导（co.th → TH）
        venture = self.country_domain.split('.')[-1].upper()

        extra_obj = {
            'seller_id': seller_id,
            'venture': venture,
        }

        # 构造消息体
        return {
            'params': params,
            'method': method,
            'body': body,
            'cookies': cookies_str,
            'fromUrl': from_url,
            'extra': extra_obj,
            'sign': Settings.DATA_SERVER_CONFIG['api_sign'],
            'socketUserId': self.socket_user_id,
            'userType': 6.0,
            'updateTime': int(time.time() * 1000),
            'request': {
                'response': response_text,
                'url': full_url,
            },
        }

    # ------------------------------------------------------------------
    # 响应解析（任务 7.1~7.2）
    # ------------------------------------------------------------------

    def parse_response(self, result: DownloadResult) -> dict | None:
        """解析 DownloadResult，返回含 api_type 字段的字典。

        响应校验规则：
        - sellercenter 接口（1.x、2.x）：code == 0 表示成功
        - mtop 接口（3.1、3.2）：ret 列表中包含 "SUCCESS::调用成功"

        Args:
            result: 下载结果

        Returns:
            解析成功返回字典（至少含 api_type），失败返回 None
        """
        api_type = result.task.meta.get('api_type', 'unknown')

        if not result.success:
            # HTTP 请求失败告警
            alert_manager.send_alert(
                alert_type='api_request_failed',
                title=f'Lazada 接口请求失败',
                content=(
                    f'账号: {self.browser_id}\n'
                    f'分组: {self.group_name}\n'
                    f'接口: {api_type}\n'
                    f'URL: {result.task.url}\n'
                    f'错误: {result.error or "HTTP 请求失败"}'
                ),
            )
            return None

        try:
            data = json.loads(result.text) if result.text else {}
        except json.JSONDecodeError:
            # JSON 解析失败告警
            alert_manager.send_alert(
                alert_type='json_parse_failed',
                title=f'Lazada 接口响应解析失败',
                content=(
                    f'账号: {self.browser_id}\n'
                    f'分组: {self.group_name}\n'
                    f'接口: {api_type}\n'
                    f'URL: {result.task.url}\n'
                    f'响应: {result.text[:200] if result.text else "空响应"}'
                ),
            )
            logger.error(f'JSON 解析失败: {result.task.url}')
            return None

        # 校验业务状态码
        code = data.get('code')
        ret = data.get('ret', [])
        has_success_ret = any('调用成功' in str(r) for r in ret) if ret else False

        if code != 0 and not has_success_ret:
            # Token 过期检测（仅 mtop 接口）
            # 注意：Lazada 实际返回的拼写是 EXOIRED（文档确认），同时兼容标准拼写
            if ret and any(
                'FAIL_SYS_TOKEN_EXOIRED' in str(r) or 'FAIL_SYS_TOKEN_EXPIRED' in str(r)
                for r in ret
            ):
                # 检查是否已经重试过（防止无限递归）
                retry_count = result.task.meta.get('_token_retry_count', 0) if result.task.meta else 0
                if retry_count >= 1:
                    # 已重试过，不再重试
                    logger.error(
                        f'Token 更新后仍失败，账号={self.browser_id}, '
                        f'分组={self.group_name}, api_type={api_type}'
                    )
                    alert_manager.send_alert(
                        'token_update_failed',
                        'Lazada Token 更新后仍失败',
                        f'账号: {self.browser_id}\n分组: {self.group_name}\n接口: {api_type}'
                    )
                    return None

                # Token 过期，尝试更新并重试
                logger.warning(
                    f'Token 过期，账号={self.browser_id}, 分组={self.group_name}, '
                    f'api_type={api_type}, url={result.task.url}'
                )
                return self._handle_token_expired_and_retry(result, api_type)

            # 其他业务错误
            if api_type not in (API_TYPE_REALTIME_TREND,API_TYPE_REALTIME_DETAIL):
                # 业务状态码异常告警
                alert_manager.send_alert(
                    alert_type='api_business_error',
                    title=f'Lazada 接口业务状态异常',
                    content=(
                        f'账号: {self.browser_id}\n'
                        f'分组: {self.group_name}\n'
                        f'接口: {api_type}\n'
                        f'URL: {result.task.url}\n'
                        f'code: {code}\n'
                        f'ret: {ret}\n'
                        f'响应: {json.dumps(data, ensure_ascii=False)[:300]}'
                    ),
                )
                logger.warning(
                    f'接口响应异常，账号={self.browser_id}, 分组={self.group_name}, '
                    f'api_type={api_type}, code={code}, ret={ret}, url={result.task.url}'
                )
            return None

        return {
            'api_type': api_type,
            'data': data,
            '_meta': result.task.meta,
        }

    # ------------------------------------------------------------------
    # Token 过期自动更新（从响应头 Set-Cookie 提取新 Token 并重试）
    # ------------------------------------------------------------------

    def _extract_token_from_headers(self, headers: dict) -> dict[str, str]:
        """从响应头 Set-Cookie 提取 _m_h5_tk 和 _m_h5_tk_enc"""
        set_cookie = headers.get('set-cookie', '') or headers.get('Set-Cookie', '')
        if not set_cookie:
            return {}

        import re
        tokens = {}
        for cookie_part in set_cookie.split(','):
            if '_m_h5_tk_enc=' in cookie_part:
                match = re.search(r'_m_h5_tk_enc=([^;]+)', cookie_part)
                if match:
                    tokens['_m_h5_tk_enc'] = match.group(1)
            elif '_m_h5_tk=' in cookie_part:
                match = re.search(r'_m_h5_tk=([^;]+)', cookie_part)
                if match:
                    tokens['_m_h5_tk'] = match.group(1)

        return tokens

    def _rebuild_task_with_new_tokens(self, task: Task,
                                      new_tokens: dict[str, str]) -> Task:
        """使用新 Token 重新构造请求任务（更新 Cookie + 重新签名）"""
        from copy import deepcopy
        import re

        new_task = deepcopy(task)

        # 更新 Cookie 头中的 Token
        old_cookie = task.headers.get('Cookie', '')
        new_cookie = old_cookie

        if '_m_h5_tk_enc=' in old_cookie:
            new_cookie = re.sub(
                r'_m_h5_tk_enc=[^;]+',
                f'_m_h5_tk_enc={new_tokens["_m_h5_tk_enc"]}',
                new_cookie,
            )
        else:
            new_cookie += f'; _m_h5_tk_enc={new_tokens["_m_h5_tk_enc"]}'

        if '_m_h5_tk=' in old_cookie:
            new_cookie = re.sub(
                r'(?<!enc=)_m_h5_tk=([^;]+)',
                f'_m_h5_tk={new_tokens["_m_h5_tk"]}',
                new_cookie,
            )
        else:
            new_cookie += f'; _m_h5_tk={new_tokens["_m_h5_tk"]}'

        new_task.headers['Cookie'] = new_cookie

        # 重新计算签名
        token = new_tokens['_m_h5_tk'].split('_')[0]
        t = str(int(time.time() * 1000))
        app_key = '4272'

        if task.method == 'GET':
            data_str = task.params.get('data', '')
        else:
            data_str = task.data.get('data', '') if task.data else ''

        sign = self._calc_mtop_sign(token, t, app_key, data_str)
        new_task.params['t'] = t
        new_task.params['sign'] = sign

        if not new_task.meta:
            new_task.meta = {}
        new_task.meta['_token_retry_count'] = 1

        return new_task

    def _handle_token_expired_and_retry(self, result: DownloadResult,
                                        api_type: str) -> dict | None:
        """处理 Token 过期：提取新 Token、更新双端口 Cookie、重试请求"""
        from downloader import Downloader
        from services.cookie_manager import save_cookies

        # 1. 提取新 Token
        new_tokens = self._extract_token_from_headers(result.headers)
        if '_m_h5_tk' not in new_tokens or '_m_h5_tk_enc' not in new_tokens:
            alert_manager.send_alert(
                'token_extract_failed',
                'Lazada Token 提取失败',
                f'账号: {self.browser_id}\n分组: {self.group_name}\n'
                f'接口: {api_type}\n响应头: {result.headers}',
            )
            logger.error(f'Token 提取失败，响应头: {result.headers}')
            return None

        # 2. 更新 Cookie（sellercenter + live 两个端口，同时更新数据库和内存）
        try:
            cookies = self.get_cookies()
            if cookies:
                for endpoint in ('sellercenter', 'live'):
                    ep_cookies = cookies.get(endpoint)
                    if ep_cookies:
                        updated = ep_cookies.copy()
                        updated.update(new_tokens)
                        save_cookies(self.browser_id, 'lazada', endpoint, updated)

            # 原地更新内存中的 Cookie 字典，后续闭包构造的任务自动使用新 Token
            for attr in ('_sc_cookies', '_live_cookies'):
                mem_cookies = getattr(self, attr, None)
                if mem_cookies is not None:
                    mem_cookies.update(new_tokens)

            logger.info(
                f'Token 更新成功，账号={self.browser_id}, '
                f'新 Token: {new_tokens["_m_h5_tk"][:20]}...'
            )
        except Exception as e:
            logger.error(f'Cookie 更新失败: {e}')

        # 3. 重新构造请求任务并重试
        new_task = self._rebuild_task_with_new_tokens(result.task, new_tokens)
        logger.info(f'Token 过期重试，账号={self.browser_id}, api_type={api_type}')

        dl = Downloader(proxy=self.get_proxy())
        retry_results = dl.run([new_task])

        if not retry_results or not retry_results[0].success:
            logger.error(f'Token 更新后重试请求失败，账号={self.browser_id}')
            return None

        # 4. 递归解析（retry_count=1，不会再次重试）
        retry_dr = retry_results[0]
        parsed = self.parse_response(retry_dr)
        if parsed is not None:
            # 附带重试后的响应体，供 _process_results 上报 Kafka 使用
            parsed['_retried_text'] = retry_dr.text
        return parsed

    # ------------------------------------------------------------------
    # 登录态检测（任务 8.1~8.3）
    # ------------------------------------------------------------------

    def _send_probe_request(self, task: Task) -> DownloadResult | None:
        """发送探测请求的通用方法。

        Args:
            task: Task 对象

        Returns:
            DownloadResult 对象，失败时返回 None
        """
        from downloader import Downloader

        try:
            proxy = self.get_proxy()
            dl = Downloader(proxy=proxy, timeout=10)
            results = dl.run([task])

            if results and results[0].success:
                return results[0]

            logger.warning(
                f'探测请求失败，账号={self.browser_id}，URL={task.url}，'
                f'错误={results[0].error if results else "无响应"}'
            )
            return None
        except Exception as e:
            logger.warning(f'探测请求异常，账号={self.browser_id}，URL={task.url}，错误={e}')
            return None

    def _probe_sellercenter_login(self, cookies: dict) -> tuple[bool, bool]:
        """探测 Sellercenter 登录态。

        Args:
            cookies: sellercenter Cookie 字典

        Returns:
            (is_valid, is_token_expired)
            - is_valid: True=登录有效, False=已登出
            - is_token_expired: 始终为 False（Sellercenter 无 Token 自动更新机制）
        """
        today = self._get_country_today()
        date_str = self._format_date_ba(today - timedelta(days=1))
        url = f'{self.sellercenter_base}/dashboard/key/overviewV2.json'
        params = {'dateRange': f'{date_str}|{date_str}', 'dateType': 'day'}
        headers = {'Cookie': self._cookie_header(cookies), 'Accept': 'application/json'}

        task = Task(url=url, params=params, headers=headers, meta={'api_type': 'probe_sellercenter'})
        result = self._send_probe_request(task)
        if not result:
            return (False, False)

        try:
            data = json.loads(result.text)
            return (data.get('code') == 0, False)
        except Exception:
            # 返回 HTML/text 或 JSON 解析失败，说明已登出
            return (False, False)

    def _probe_live_login(self, cookies: dict) -> tuple[bool, bool]:
        """探测 LazLive 登录态。

        Args:
            cookies: live Cookie 字典

        Returns:
            (is_valid, is_token_expired)
            - is_valid: True=登录有效, False=已登出
            - is_token_expired: True=仅 Token 过期（可自动更新）
        """
        utc_offset = LAZADA_TIMEZONE_MAP.get(self.country_domain, 8)
        data = {
            '_timezone': -utc_offset,
            'roomStatus': 'Online',
            'orderByRoomStatus': 'Online',
            'pageNum': 1,
            'pageSize': 1,
        }

        task = self._build_mtop_task(
            api='mtop.lazada.live.querylivesbystatus',
            api_type='probe_live',
            data=data,
            cookies=cookies,
            page_num=1,
            page_size=1,
            method='POST',
        )

        result = self._send_probe_request(task)
        if not result:
            return (False, False)

        try:
            resp_data = json.loads(result.text)
            ret = resp_data.get('ret', [])

            # 有效：ret 包含 "SUCCESS"
            if any('SUCCESS' in str(r) for r in ret):
                return (True, False)

            # Token 过期：检查响应头是否有新 Token
            if any('FAIL_SYS_TOKEN_EXOIRED' in str(r) or 'FAIL_SYS_TOKEN_EXPIRED' in str(r) for r in ret):
                new_tokens = self._extract_token_from_headers(result.headers)
                if '_m_h5_tk' in new_tokens and '_m_h5_tk_enc' in new_tokens:
                    logger.info(f'LazLive Token 过期，准备自动更新，账号={self.browser_id}')
                    self._update_token_from_response(result.headers)
                    return (True, True)

            # 其他失败情况（SESSION_EXPIRED / TOKEN_ILLEGAL）视为登出
            return (False, False)
        except (json.JSONDecodeError, KeyError):
            return (False, False)

    def _check_login_state(self, cookies: dict) -> dict:
        """检测登录态是否有效（采集前预检）。

        Args:
            cookies: {'sellercenter': {...}, 'live': {...}}

        Returns:
            {
                'sellercenter_valid': bool,  # Sellercenter 端是否有效
                'live_valid': bool,          # LazLive 端是否有效
                'needs_refresh': bool,       # 是否需要刷新 Cookie
                'error': str | None,         # 探测失败的错误信息
            }
        """
        result = {
            'sellercenter_valid': False,
            'live_valid': False,
            'needs_refresh': False,
            'error': None,
        }

        sc_cookies = cookies.get('sellercenter')
        live_cookies = cookies.get('live')

        # 实时模式：只检测 LazLive 端
        if self.crawl_type == 'realtime':
            if not live_cookies:
                result['error'] = 'live_cookie_missing'
                result['needs_refresh'] = True
                return result

            is_valid, is_token_expired = self._probe_live_login(live_cookies)
            result['live_valid'] = is_valid

            if not is_valid:
                result['needs_refresh'] = True
                result['error'] = 'live_login_invalid'
            elif is_token_expired:
                logger.info(f'LazLive Token 自动更新成功，跳过 Cookie 刷新，账号={self.browser_id}')

            return result

        # 历史模式：检测两端
        invalid_endpoints = []

        # 检测 Sellercenter
        if sc_cookies:
            is_valid, _ = self._probe_sellercenter_login(sc_cookies)
            result['sellercenter_valid'] = is_valid
            if not is_valid:
                invalid_endpoints.append('sellercenter')
        else:
            invalid_endpoints.append('sellercenter')

        # 检测 LazLive
        if live_cookies:
            is_valid, is_token_expired = self._probe_live_login(live_cookies)
            result['live_valid'] = is_valid
            if not is_valid:
                invalid_endpoints.append('live')
            elif is_token_expired:
                logger.info(f'LazLive Token 自动更新成功，账号={self.browser_id}')
        else:
            invalid_endpoints.append('live')

        # 设置刷新标记和错误信息
        if invalid_endpoints:
            result['needs_refresh'] = True
            if len(invalid_endpoints) == 2:
                result['error'] = 'both_endpoints_invalid'
            elif 'sellercenter' in invalid_endpoints:
                result['error'] = 'sellercenter_invalid'
            else:
                result['error'] = 'live_invalid'

        return result

    def _update_token_from_response(self, response_headers: dict) -> bool:
        """从响应头提取并更新 Token。

        Args:
            response_headers: HTTP 响应头

        Returns:
            True=更新成功, False=更新失败
        """
        # 1. 提取新 Token
        new_tokens = self._extract_token_from_headers(response_headers)
        if '_m_h5_tk' not in new_tokens or '_m_h5_tk_enc' not in new_tokens:
            logger.error(f'Token 提取失败，响应头: {response_headers}')
            return False

        # 2. 更新数据库中的 Cookie（sellercenter + live 两个端口）
        try:
            cookies = self.get_cookies()
            if cookies:
                for endpoint in ('sellercenter', 'live'):
                    ep_cookies = cookies.get(endpoint)
                    if ep_cookies:
                        updated = ep_cookies.copy()
                        updated.update(new_tokens)
                        cookie_manager.save_cookies(self.browser_id, 'lazada', endpoint, updated)

            # 3. 更新内存中的 Cookie 字典（后续任务自动使用新 Token）
            for attr in ('_sc_cookies', '_live_cookies'):
                mem_cookies = getattr(self, attr, None)
                if mem_cookies is not None:
                    mem_cookies.update(new_tokens)

            logger.info(
                f'Token 更新成功，账号={self.browser_id}, '
                f'新 Token: {new_tokens["_m_h5_tk"][:20]}...'
            )
            return True
        except Exception as e:
            logger.error(f'Token 更新失败，账号={self.browser_id}，错误={e}')
            return False

    def _refresh_cookies(self) -> bool:
        """刷新 Cookie（通过浏览器自动登录）"""
        logger.info(f'开始刷新 Cookie，账号={self.browser_id}')

        credentials = cookie_manager.get_account_credentials(
            self.browser_id, 'lazada', endpoint='sellercenter'
        )
        if not credentials:
            logger.error(f'无法刷新 Cookie：账号 {self.browser_id} 缺少凭证')
            return False

        from cookie_keeper.browser_refresher import BrowserRefresher
        refresher = BrowserRefresher()

        try:
            new_cookies = refresher.refresh_account(
                self.browser_id, credentials, self.group_name
            )
        except Exception as e:
            logger.error(f'Cookie 刷新失败，账号={self.browser_id}，错误={e}')
            return False

        failed_endpoints = []
        for endpoint, cookie_dict in new_cookies.items():
            if cookie_dict:
                cookie_manager.save_cookies(
                    self.browser_id, 'lazada', endpoint=endpoint, cookies=cookie_dict
                )
            else:
                failed_endpoints.append(endpoint)

        if failed_endpoints:
            logger.warning(f'Cookie 部分刷新失败，账号={self.browser_id}，失败端点={", ".join(failed_endpoints)}')
            return False

        logger.info(f'Cookie 刷新成功，账号={self.browser_id}')
        return True

    # ------------------------------------------------------------------
    # 单端口 Cookie 缺失的 partial 状态上报（任务 7.2）
    # ------------------------------------------------------------------

    def start_crawl(self) -> dict[str, Any]:
        """覆写基类方法，添加登录态预检 + Cookie 条件刷新 + 单端口缺失的 partial 状态上报。"""
        # 1. 获取 Cookie
        cookies = self.get_cookies()

        # 2. Cookie 不存在或为空，直接刷新
        if not cookies or (not cookies.get('sellercenter') and not cookies.get('live')):
            logger.warning(f'Cookie 不存在或为空，直接刷新，账号={self.browser_id}')
            if not self._refresh_cookies():
                logger.error(f'Cookie 刷新失败，终止采集，账号={self.browser_id}')
                return {'success': False, 'error': 'refresh_failed'}
        else:
            # 3. 预检登录态
            login_state = self._check_login_state(cookies)

            # 4. 根据检测结果决定是否刷新
            if login_state['needs_refresh']:
                logger.info(
                    f'登录态失效，开始刷新 Cookie，账号={self.browser_id}，'
                    f'原因={login_state.get("error")}'
                )
                if not self._refresh_cookies():
                    logger.error(f'Cookie 刷新失败，终止采集，账号={self.browser_id}')
                    return {'success': False, 'error': 'refresh_failed'}
            elif login_state.get('error') and not login_state['sellercenter_valid'] and not login_state['live_valid']:
                # 探测失败且两端都无效，降级策略：跳过刷新，直接采集（让被动检测处理）
                logger.warning(
                    f'登录态探测失败，跳过刷新直接采集，账号={self.browser_id}，'
                    f'错误={login_state["error"]}'
                )
            else:
                logger.info(f'登录态有效，跳过 Cookie 刷新，账号={self.browser_id}')

        # 5. 执行采集
        result = super().start_crawl()

        # 6. 处理跳过的 api_type（单端口 Cookie 缺失）
        if self.skipped_api_types and result.get('success'):
            if self.crawl_type == 'realtime':
                # 实时模式：主动跳过 sellercenter 接口，这是正常行为
                logger.info(f'实时模式：主动跳过 {len(self.skipped_api_types)} 个 sellercenter 接口')
            else:
                # 历史模式：Cookie 缺失导致跳过接口，这是异常情况
                logger.warning(
                    f'单端口 Cookie 缺失，跳过 {len(self.skipped_api_types)} 个接口: '
                    f'{", ".join(self.skipped_api_types)}'
                )
                result['status'] = 'partial'
                result['skipped_api_types'] = self.skipped_api_types

                # 发送告警
                alert_manager.send_alert(
                    alert_type='partial_collection',
                    title='Lazada 单端口 Cookie 缺失',
                    content=(
                        f'账号 {self.browser_id} 单端口 Cookie 缺失，'
                        f'跳过 {len(self.skipped_api_types)} 个接口：\n'
                        f'{", ".join(self.skipped_api_types)}'
                    ),
                )

            # 更新 monitor 状态为 partial
            if self.batch_id:
                from monitor import get_monitor
                monitor = get_monitor()
                try:
                    # 重新调用 finish_account 覆盖状态
                    monitor.finish_account(
                        self.batch_id, self.browser_id, status='partial'
                    )
                except Exception as e:
                    logger.error(f'更新 monitor partial 状态失败: {e}')

        return result


if __name__ == '__main__':
    LazadaHttpCrawler(browser_id="k1c0io17",group_name = '泰国团队-lazada',crawl_type='history').start_crawl()