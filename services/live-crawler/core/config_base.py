#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Dict, Any
from .apollo.setting import KAFKA_HOSTS

class BaseConfig(BaseSettings):
    # 环境标识（子类中覆盖）
    ENVIRONMENT: str = "base"
    DEBUG: bool = False

    # 项目根目录
    ROOT_DIR: Path = Path(__file__).parents[1]  # 指向项目根目录
    
    # 日志配置（子类中覆盖）
    LOG_LEVEL: str = "INFO"
    LOG_DIR: Path = ROOT_DIR / "logs"

    # 异步请求配置
    ASYNC_CONFIG: Dict[str, Any] = {
        # 并发数控制
        "concurrency": 5,
        # 重试次数
        "retries": 3,
        # 请求超时时间（秒）
        "timeout": 30.0,
        # 重试延迟因子
        "backoff_factor": 0.3,
        # 需要重试的状态码
        "status_forcelist": (500, 502, 504)
    }

    # Kafka 配置
    KAFKA_CONFIG: Dict[str, Any] = {
        # 是否启用 Kafka 发送（可通过环境变量 KAFKA_ENABLED 覆盖）
        "enabled": True,
        # Broker 地址（从Apollo配置中心获取）
        # "bootstrap_servers": KAFKA_HOSTS,
        # Broker 地址 本地调式 直接写死
        # "bootstrap_servers": "10.206.2.154:9092, 10.206.2.109:9092, 10.206.2.63:9092",
        "bootstrap_servers": "172.25.0.11:9092,172.25.0.158:9092,172.25.0.237:9092",
        # 基础连接安全设置（无认证时保持 PLAINTEXT）
        "security_protocol": "PLAINTEXT",
        "sasl_mechanism": None,
        "sasl_username": None,
        "sasl_password": None,
        # 生产者参数
        "acks": "all",
        "retries": 3,
        "linger_ms": 5,
        "batch_size": 32768,
        "client_id": "xiaomi_ads_crawler",
        # 平台到 topic 的映射（支持未来扩展）
        "platform_topics": {
            "lazada": "streamer_lazada_relate_data",
            "tiktok": "",    # 预留
            "shopee": "",    # 预留
        }
    }


    # 数据存储配置
    DATA_SERVER_CONFIG: Dict[str, Any] = {
        # 是否启用数据存储
        'enabled': True,
        'api_url':'https://www.livelabstar.com/live/v1.0',
        # 数据存储API端点
        'endpoint':'/data/info/send',
        # 数据存储API访问令牌
        'access_token':'UhYtrOciOiJIUzI1NiJ0.eyJqdGkiOiIyOkuwt3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZYGkdF',
        # 数据存储API签名
        'api_sign':'4fk0050d4c9c2c7ba8efc59684acf',
     }

    # 平台采集配置
    PLATFORM_CONFIG: Dict[str, Any] = {
        "tiktok": {
            # 采集器类型：'browser' | 'http'
            # 优先级低于账号粒度的 credentials.crawler_mode，仅在账号未指定时生效
            "crawler_type": "browser",
            # 是否启用实时获取user_ids（从AdsPower分组中获取）
            "use_dynamic_users": False,

            # 动态按 platform 筛选分组
            # True: 自动查询所有分组，筛选名称包含 platform 的分组
            # False: 使用下方 group_names 列表
            "use_dynamic_groups": False,

            # adspower 用户组名称（当 use_dynamic_groups=False 时使用）
            "group_names": ['新加坡团队-tiktok'],

            # 需要采集的账号（当use_dynamic_users=False时使用）
            "user_ids": ['k19ly6f4', 'k1cvlr5b', 'k1cqlv5t'],
            # 美国：k19ly6f4
            # 墨西哥：k1cvlr5b
            # 越南： k1cqlv5t

            # TikTok平台需要访问的页面URL
            "page_urls": [
                "https://livecenter.tiktok.com/replay",
                "https://shop.tiktok.com/streamer/compass/livestream-analytics/view",
                # "https://shop.tiktok.com/streamer/compass/product-analysis/view",
                # "https://shop.tiktok.com/streamer/compass/data-overview/view",
            ],
            "wait_page_map": {
                "https://livecenter.tiktok.com/replay": ".replayListContent-jBlzCz",
                "https://shop.tiktok.com/streamer/compass/livestream-analytics/view": ".zep-table-content-inner",
                "https://shop.tiktok.com/streamer/compass/product-analysis/view": ".zep-table-body",
                "https://shop.tiktok.com/streamer/compass/data-overview/view": ".flex flex-row flex-wrap gap-16", 
            },
            # 需要监听拦截的API接口列表
            # 第一阶段：仅保留 live/list（触发 JS 注入采集趋势）+ replay/info，确保 100% 准确
            "listen_urls": [
                "api/v2/insights/creator/live/list",  # 直播间列表（触发 JS 注入采集趋势）
                "webcast/room/replay/info",  # 直播录像列表
                "api/v1/streamer_desktop/account_info/get",  # 账号信息
                # --- 以下接口暂时关闭，后续逐步放开 ---
                "api/v2/insights/creator/live/stats",  # 关键指标（含 JS 补充历史数据）
                "api/v1/streamer_desktop/account_info/get",  # 账号信息
                # "api/v1/insights/creator/liveroom/recap/core/stats",  # 直播间详情-关键指标
                # "api/v1/insights/creator/liveroom/recap/trend/chart",  # 已改为 JS 注入，不需监听 直播间详情-商品分析-成交趋势 \ 直播间详情-流量分析-流量趋势 \ 直播间详情-内容分析-直播趋势
                # "api/v1/insights/creator/liveroom/recap/product/list",  # 直播间详情-商品分析-商品列表
                # "api/v1/insights/workbench/live/detail/core/stats",  # 直播间详情-流量分析-流量转化
                # "api/v1/insights/creator/liveroom/recap/viewer/source/stats",  # 直播间详情-用户画像
                # "webcast/anchor/live_fragment/list",  # 直播录像高光
                # "api/v3/insights/creator/product/analytics/list",  # 商品分析接口
                # "api/v2/insights/creator/info",
                # "insights/workbench/live/detail/source/new",  # tk接口改为v3
                # "api/v1/insights/workbench/live/detail/room/info",
                # "api/v1/insights/workbench/live/detail/trend/chart",
            ],
            # 页面加载等待时间（秒）
            "wait_time": 8,
            # Tab切换选择器
            "tab_selector": ".zep-tabs-header-title-text",
            # Tab点击间隔时间（秒）
            "tab_click_interval": 3,
            # 直播详情页等待时间（秒）
            "detail_page_wait": 4,
        },
        "shopee": {
            # 是否启用实时获取user_ids（从AdsPower分组中获取）
            "use_dynamic_users": False,

            # 动态按 platform 筛选分组
            "use_dynamic_groups": False,

            # adspower 用户组名称（当 use_dynamic_groups=False 时使用）
            "group_names": [],

            # 需要采集的账号（当use_dynamic_users=False时使用）
            "user_ids": [],
            # Shopee 页面入口统一从 live/list 开始，后续请求由 sessionList 触发
            "page_urls": [
                "https://seller.shopee.com.my/creator-center/insight/live/list",  # 直播列表
                # "https://seller.shopee.com.my/creator-center/insight/live",  # 数据整体概览
                # "https://seller.shopee.com.my/creator-center/insight/live/cumulative-trend",  # 数据概览-累计趋势

                # "https://seller.shopee.com.my/creator-center/insight/live/user-demographics",
                # "https://seller.shopee.com.my/creator-center/insight/live/product-list",
                #
                # "https://seller.shopee.com.my/creator-center/insight/video",
                # 'https://seller.shopee.com.my/creator-center/insight/video/cumulative-trend',
                # 'https://seller.shopee.com.my/creator-center/insight/video/user-demographics',
                # 'https://seller.shopee.com.my/creator-center/insight/video/list',
                # 'https://seller.shopee.com.my/creator-center/insight/video/product-list'
            ],
            # Shopee 已全面改为 JS 主动注入模式，不再依赖网络拦截
            "listen_urls": [
                # "api/supply/lm/sellercenter/realtime/sessionList",  # 直播列表 - real-time 直播间列表基础信息
                #
                # "api/supply/lm/sellercenter/overview/v3",  # 数据整体概览 ： 数据概览-销售类核心指标，数据概览-流量表现类指标 该接口默认包含2种订单类型
                # "api/supply/lm/sellercenter/metricTrend/v2",  # 数据概览-累计趋势： 累计趋势全维度日度指标  该接口默认包含2种订单类型
                # # 7个直播间详情数据接口
                # 'api/supply/lm/sellercenter/realtime/dashboard/overview',
                # "api/supply/lm/sellercenter/realtime/dashboard/trends",
                # "api/supply/lm/sellercenter/realtime/dashboard/viewer-source",
                # "api/supply/lm/sellercenter/realtime/dashboard/viewer-profile",
                # "api/supply/lm/sellercenter/realtime/dashboard/buyer-profile",
                #
                # "api/v2/login"
                #
                #
                # "api/supply/lm/sellercenter/productsList/v2",
                #
                # "supply/lm/sellercenter/liveList/v2",  # 全量30天数据接口
                # "api/supply/lm/sellercenter/userDemographics",
                #
                # "api/supply/sellercenter/video/v2/overview",
                # "api/supply/sellercenter/video/v2/metricTrend",
                # "api/supply/sellercenter/video/v2/demographics",
                # "api/supply/sellercenter/video/v2/videolist",
                # "api/supply/sellercenter/video/v2/productlist",

            ],
            "wait_page_map": {
                "https://seller.shopee.com.my/creator-center/insight/live/list": ".eds-react-table-tbody"
            },
            "wait_time": 8,
            "tab_selector": "",
            "page_close_time": 25,
        },
        "lazada": {
            # Lazada HTTP 采集器配置
            "crawler_type": "http",  # 标识为 HTTP 采集
            "http_workers": 5,  # Downloader 并发线程数
            "realtime_interval_minutes": 10,  # 实时采集间隔（分钟）
            # 历史采集遵循 SCHEDULER_CONFIG 的时区分组调度规则
            "use_dynamic_users": True,
            "use_dynamic_groups": True,
            "group_names": [],
            "user_ids": ['k1bx0kof'],
            "page_urls": [],  # HTTP 采集器不需要页面 URL
            "listen_urls": [],  # HTTP 采集器不需要监听 URL
        }
    }

    # 定时任务配置
    SCHEDULER_CONFIG: Dict[str, Any] = {
        # 是否启用定时任务
        "enabled": True,
        # 定时任务执行时间配置（支持多个时间点）
        # 每个时间点对应一个定时任务，按列表顺序添加
        "cron_config": [
            # UTC+9 日本（本地 04:00 / 16:00）
            {"hour": "3",  "minute": "0", "timezone_group": "UTC+9"},
            {"hour": "15", "minute": "0", "timezone_group": "UTC+9"},

            # UTC+8 中国/马来/新加坡（本地 04:00 / 16:00）
            {"hour": "4",  "minute": "0", "timezone_group": "UTC+8"},
            {"hour": "16", "minute": "0", "timezone_group": "UTC+8"},

            # UTC+7 印尼/泰国/越南（本地 04:00 / 16:00）
            {"hour": "5",  "minute": "0", "timezone_group": "UTC+7"},
            {"hour": "17", "minute": "0", "timezone_group": "UTC+7"},

            # UTC-3 巴西（本地 02:00 / 16:00）
            {"hour": "13", "minute": "0", "timezone_group": "UTC-3"},
            {"hour": "3",  "minute": "5", "timezone_group": "UTC-3"},

            # UTC-6 墨西哥（本地 02:00 / 16:00）
            {"hour": "16", "minute": "5", "timezone_group": "UTC-6"},
            {"hour": "6",  "minute": "0", "timezone_group": "UTC-6"},

            # UTC-8 美国（本地 00:00 / 16:00）
            {"hour": "16", "minute": "10", "timezone_group": "UTC-8"},
            {"hour": "8",  "minute": "0", "timezone_group": "UTC-8"},
        ],
        # 任务超时时间（小时）
        "task_timeout": 2,
        # 最大重试次数
        "max_retries": 3,
        # 重试延迟（秒）
        "retry_delay": 300,
    }

    # 告警配置
    ALERT_CONFIG: Dict[str, Any] = {
        # 是否启用告警
        "enabled": True,
        # 飞书机器人 Webhook URL，启用告警前请配置
        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/51079d39-c0ba-4a83-803e-04d22017ac5f",
        # 告警类型配置
        "alert_types": {
            "login_failed": True,  # 账号登出告警
            "crawl_failed": True,  # 采集失败告警
            "task_timeout": True,  # 任务超时告警
        }
    }

    # OpenAI 配置（日报生成，scripts/openai_client.py 使用）
    # 取值优先级：环境变量 > 此处默认值，未配置 api_key 时日报自动降级为纯文本
    OPENAI_CONFIG: Dict[str, Any] = {
        # 模型名称（可通过环境变量 OPENAI_MODEL 覆盖）
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        # 请求超时时间（秒，可通过环境变量 OPENAI_TIMEOUT_SECONDS 覆盖）
        "timeout_seconds": int(os.getenv("OPENAI_TIMEOUT_SECONDS", "30")),
        # API 密钥（可通过环境变量 OPENAI_API_KEY 覆盖；为空则日报降级为纯文本）
        "api_key": os.getenv("OPENAI_API_KEY", ""),
    }

    # AdsPower指纹浏览器配置
    ADSPOWER_CONFIG: Dict[str, Any] = {
        # AdsPower API地址
        "api_url": "http://127.0.0.1:50325",
        # 按平台筛选分组时，排除以下前缀开头的分组名称
        "exclude_group_prefixes": [],
    }

    # Cookie 管理 API 配置（monitor/api/cookie_routes.py 使用）
    # 供 adspower-server 远程写入 Cookie 时做身份校验
    COOKIE_API_CONFIG: Dict[str, Any] = {
        # 访问令牌（请求头 X-API-Token 必须与此一致才放行）
        "token": "sk-5eajkJEpzRQL4pvMpqxxoffm3hgFi7FCNDs2OXfWIJuOipvx",
    }

    # 补采配置
    RECRAWL_CONFIG: Dict[str, Any] = {
        "enabled": True,              # 自动补采开关
        "max_retry": 3,               # 最大重试次数
        "retry_delays": [1, 3, 10],   # 重试间隔（秒）
        "request_interval": 2,        # 同账号请求间隔（秒）
        "max_concurrent": 2,          # 最大并发账号数
        "default_days": 3,            # 默认检测时间窗口（天）
    }

    # 登录回调配置
    LOGIN_CALLBACK_CONFIG: Dict[str, Any] = {
        # 是否启用登录回调
        "enabled": True,

        # pro 回调接口地址（可通过环境变量 LOGIN_CALLBACK_URL 覆盖）
        "url": "https://www.livelabstar.com/live/v1.0/live/room/account/login/callback",  # pro
        # pro|pre  访问令牌（可通过环境变量 LOGIN_CALLBACK_ACCESS_TOKEN 覆盖）
        "access_token": "UhYtrOciOiJIUzI1NiJ0.eyJqdGkiOiIyOkuwt3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZYGkdF",

        # test01
        # "url": "https://test01-patrick-star.tec-develop.cn/live/v1.0/live/room/account/login/callback",
        # "access_token": "eyHhbGciOiJIUzI1NiJ0.eyJqdGkiOiIyIiwic3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZHy8NE8",

        # 请求超时时间（秒）
        "timeout": 10,
    }


_BASE_CONFIG = BaseConfig()


class DevConfig(BaseConfig):
    # 环境标识（开发环境）
    ENVIRONMENT: str = "dev"
    DEBUG: bool = True

    # 日志配置（开发环境）
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")

    # Kafka 配置
    KAFKA_CONFIG: Dict[str, Any] = {
        **_BASE_CONFIG.KAFKA_CONFIG,
        # Broker 地址（从Apollo配置中心获取）
        # "bootstrap_servers": KAFKA_HOSTS,
        # Broker 地址 本地调式 直接写死
        # "bootstrap_servers": "10.206.2.154:9092, 10.206.2.109:9092, 10.206.2.63:9092",
        "bootstrap_servers": os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "172.25.0.11:9092,172.25.0.158:9092,172.25.0.237:9092",
        ),
    }

    # 数据存储配置
    DATA_SERVER_CONFIG: Dict[str, Any] = {
        **_BASE_CONFIG.DATA_SERVER_CONFIG,
        'api_url': os.getenv('DATA_SERVER_API_URL', 'https://test01-patrick-star.tec-develop.cn/live/v1.0'),
        'access_token': os.getenv(
            'DATA_SERVER_ACCESS_TOKEN',
            'eyHhbGciOiJIUzI1NiJ0.eyJqdGkiOiIyIiwic3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZHy8NE8'
        ),
    }

    # 登录回调配置
    LOGIN_CALLBACK_CONFIG: Dict[str, Any] = {
        **_BASE_CONFIG.LOGIN_CALLBACK_CONFIG,
        'url': os.getenv('LOGIN_CALLBACK_URL', 'https://test01-patrick-star.tec-develop.cn/live/v1.0/live/room/account/login/callback'),
        'access_token': os.getenv(
            'LOGIN_CALLBACK_ACCESS_TOKEN',
            'eyHhbGciOiJIUzI1NiJ0.eyJqdGkiOiIyIiwic3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZHy8NE8'
        ),
    }


class ProConfig(BaseConfig):
    # 环境标识（生产环境）
    ENVIRONMENT: str = "pro"
    DEBUG: bool = False

    # 日志配置（生产环境）
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Kafka 配置
    KAFKA_CONFIG: Dict[str, Any] = {
        **_BASE_CONFIG.KAFKA_CONFIG,
        # Broker 地址（从Apollo配置中心获取）
        # "bootstrap_servers": KAFKA_HOSTS,
        # Broker 地址 本地调式 直接写死
        # "bootstrap_servers": "10.206.2.154:9092, 10.206.2.109:9092, 10.206.2.63:9092",
        "bootstrap_servers": os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "alikafka-pre-cn-jmp41wn79001-1-vpc.alikafka.aliyuncs.com:9092,alikafka-pre-cn-jmp41wn79001-2-vpc.alikafka.aliyuncs.com:9092,alikafka-pre-cn-jmp41wn79001-3-vpc.alikafka.aliyuncs.com:9092",
        ),
    }


    PLATFORM_CONFIG: Dict[str, Any] = {
        "tiktok": {
            # 采集器类型：'browser' | 'http'
            # 优先级低于账号粒度的 credentials.crawler_mode，仅在账号未指定时生效
            "crawler_type": "browser",
            # 是否启用实时获取user_ids（从AdsPower分组中获取）
            "use_dynamic_users": True,

            # 动态按 platform 筛选分组
            # True: 自动查询所有分组，筛选名称包含 platform 的分组
            # False: 使用下方 group_names 列表
            "use_dynamic_groups": True,

            # adspower 用户组名称（当 use_dynamic_groups=False 时使用）
            "group_names": ['新加坡团队-tiktok'],

            # 需要采集的账号（当use_dynamic_users=False时使用）
            "user_ids": [],

            # TikTok平台需要访问的页面URL
            "page_urls": [
                "https://livecenter.tiktok.com/replay",
                "https://shop.tiktok.com/streamer/compass/livestream-analytics/view",
                # "https://shop.tiktok.com/streamer/compass/product-analysis/view",
                # "https://shop.tiktok.com/streamer/compass/data-overview/view",
            ],
            "wait_page_map": {
                "https://livecenter.tiktok.com/replay": ".replayListContent-jBlzCz",
                "https://shop.tiktok.com/streamer/compass/livestream-analytics/view": ".zep-table-content-inner",
                "https://shop.tiktok.com/streamer/compass/product-analysis/view": ".zep-table-body",
                "https://shop.tiktok.com/streamer/compass/data-overview/view": ".flex flex-row flex-wrap gap-16",
            },
            # 需要监听拦截的API接口列表
            # 第一阶段：仅保留 live/list（触发 JS 注入采集趋势）+ replay/info，确保 100% 准确
            "listen_urls": [
                "api/v2/insights/creator/live/list",  # 直播间列表（触发 JS 注入采集趋势）
                "webcast/room/replay/info",  # 直播录像列表
                "api/v1/streamer_desktop/account_info/get",  # 账号信息
                # --- 以下接口暂时关闭，后续逐步放开 ---
                "api/v2/insights/creator/live/stats",  # 关键指标（含 JS 补充历史数据）
                "api/v1/streamer_desktop/account_info/get",  # 账号信息
                # "api/v1/insights/creator/liveroom/recap/core/stats",  # 直播间详情-关键指标
                # "api/v1/insights/creator/liveroom/recap/trend/chart",  # 已改为 JS 注入，不需监听 直播间详情-商品分析-成交趋势 \ 直播间详情-流量分析-流量趋势 \ 直播间详情-内容分析-直播趋势
                # "api/v1/insights/creator/liveroom/recap/product/list",  # 直播间详情-商品分析-商品列表
                # "api/v1/insights/workbench/live/detail/core/stats",  # 直播间详情-流量分析-流量转化
                # "api/v1/insights/creator/liveroom/recap/viewer/source/stats",  # 直播间详情-用户画像
                # "webcast/anchor/live_fragment/list",  # 直播录像高光
                # "api/v3/insights/creator/product/analytics/list",  # 商品分析接口
                # "api/v2/insights/creator/info",
                # "insights/workbench/live/detail/source/new",  # tk接口改为v3
                # "api/v1/insights/workbench/live/detail/room/info",
                # "api/v1/insights/workbench/live/detail/trend/chart",
            ],
            # 页面加载等待时间（秒）
            "wait_time": 8,
            # Tab切换选择器
            "tab_selector": ".zep-tabs-header-title-text",
            # Tab点击间隔时间（秒）
            "tab_click_interval": 3,
            # 直播详情页等待时间（秒）
            "detail_page_wait": 4,
        },
        "shopee": {
            # 是否启用实时获取user_ids（从AdsPower分组中获取）
            "use_dynamic_users": True,

            # 动态按 platform 筛选分组
            "use_dynamic_groups": True,

            # adspower 用户组名称（当 use_dynamic_groups=False 时使用）
            "group_names": [],

            # 需要采集的账号（当use_dynamic_users=False时使用）
            "user_ids": [],
            # Shopee 页面入口统一从 live/list 开始，后续请求由 sessionList 触发
            "page_urls": [
                "https://seller.shopee.com.my/creator-center/insight/live/list",  # 直播列表
                # "https://seller.shopee.com.my/creator-center/insight/live",  # 数据整体概览
                # "https://seller.shopee.com.my/creator-center/insight/live/cumulative-trend",  # 数据概览-累计趋势

                # "https://seller.shopee.com.my/creator-center/insight/live/user-demographics",
                # "https://seller.shopee.com.my/creator-center/insight/live/product-list",
                #
                # "https://seller.shopee.com.my/creator-center/insight/video",
                # 'https://seller.shopee.com.my/creator-center/insight/video/cumulative-trend',
                # 'https://seller.shopee.com.my/creator-center/insight/video/user-demographics',
                # 'https://seller.shopee.com.my/creator-center/insight/video/list',
                # 'https://seller.shopee.com.my/creator-center/insight/video/product-list'
            ],
            # Shopee 已全面改为 JS 主动注入模式，不再依赖网络拦截
            "listen_urls": [
                # "api/supply/lm/sellercenter/realtime/sessionList",  # 直播列表 - real-time 直播间列表基础信息
                #
                # "api/supply/lm/sellercenter/overview/v3",  # 数据整体概览 ： 数据概览-销售类核心指标，数据概览-流量表现类指标 该接口默认包含2种订单类型
                # "api/supply/lm/sellercenter/metricTrend/v2",  # 数据概览-累计趋势： 累计趋势全维度日度指标  该接口默认包含2种订单类型
                # # 7个直播间详情数据接口
                # 'api/supply/lm/sellercenter/realtime/dashboard/overview',
                # "api/supply/lm/sellercenter/realtime/dashboard/trends",
                # "api/supply/lm/sellercenter/realtime/dashboard/viewer-source",
                # "api/supply/lm/sellercenter/realtime/dashboard/viewer-profile",
                # "api/supply/lm/sellercenter/realtime/dashboard/buyer-profile",
                #
                # "api/v2/login"
                #
                #
                # "api/supply/lm/sellercenter/productsList/v2",
                #
                # "supply/lm/sellercenter/liveList/v2",  # 全量30天数据接口
                # "api/supply/lm/sellercenter/userDemographics",
                #
                # "api/supply/sellercenter/video/v2/overview",
                # "api/supply/sellercenter/video/v2/metricTrend",
                # "api/supply/sellercenter/video/v2/demographics",
                # "api/supply/sellercenter/video/v2/videolist",
                # "api/supply/sellercenter/video/v2/productlist",

            ],
            "wait_page_map": {
                "https://seller.shopee.com.my/creator-center/insight/live/list": ".eds-react-table-tbody"
            },
            "wait_time": 8,
            "tab_selector": "",
            "page_close_time": 25,
        },
        "lazada": {
            # Lazada HTTP 采集器配置
            "crawler_type": "http",  # 标识为 HTTP 采集
            "http_workers": 5,  # Downloader 并发线程数
            "realtime_interval_minutes": 10,  # 实时采集间隔（分钟）
            # 历史采集遵循 SCHEDULER_CONFIG 的时区分组调度规则
            "use_dynamic_users": True,
            "use_dynamic_groups": True,
            "group_names": [],
            "user_ids": ['k1bx0kof'],
            "page_urls": [],  # HTTP 采集器不需要页面 URL
            "listen_urls": [],  # HTTP 采集器不需要监听 URL
        }
    }


    # 数据存储配置
    DATA_SERVER_CONFIG: Dict[str, Any] = {
        **_BASE_CONFIG.DATA_SERVER_CONFIG,
        'api_url': os.getenv('DATA_SERVER_API_URL', 'https://www.livelabstar.com/live/v1.0'),
        'access_token': os.getenv(
            'DATA_SERVER_ACCESS_TOKEN',
            'UhYtrOciOiJIUzI1NiJ0.eyJqdGkiOiIyOkuwt3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZYGkdF'
        ),
    }

    # 登录回调配置
    LOGIN_CALLBACK_CONFIG: Dict[str, Any] = {
        **_BASE_CONFIG.LOGIN_CALLBACK_CONFIG,
        'url': os.getenv('LOGIN_CALLBACK_URL', 'https://www.livelabstar.com/live/v1.0/live/room/account/login/callback'),
        'access_token': os.getenv(
            'LOGIN_CALLBACK_ACCESS_TOKEN',
            'UhYtrOciOiJIUzI1NiJ0.eyJqdGkiOiIyOkuwt3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZYGkdF'
        ),
    }
