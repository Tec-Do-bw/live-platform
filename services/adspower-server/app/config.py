import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union


# 国家代理映射（按国家配置，值可以是单个代理字符串或列表，列表时随机选择）
_PROXY_MAP: Dict[str, Union[str, List[str]]] = {
    "MY": "socks5://my130.kookeey.info:24828:c822ee15:2169010a", # 家宽住宅
    "ID": "socks5://80.kookeey.info:32583:c822ee15:2169010a",
    "TH": "socks5://75.kookeey.info:27240:c822ee15:2169010a",
    "VN": "socks5://83.kookeey.info:27006:c822ee15:2169010a",
    "BR": "socks5://br293.kookeey.info:25552:c822ee15:2169010a",
    "JP": "socks5://81.kookeey.info:21696:c822ee15:2169010a",
    "US": "socks5://us178.kookeey.info:25539:c822ee15:2169010a", # 家宽住宅
    "MX": ["socks5://mx565.kookeey.info:30067:c822ee15:2169010a",  # 家宽住宅
            "socks5://mx351.kookeey.info:29961:c822ee15:2169010a", # 静态IDCIP
           ],
    "SG": "socks5://57.kookeey.info:24317:c822ee15:2169010a",
}

# 国家代码到中文名称映射
_COUNTRY_NAME_MAP: Dict[str, str] = {
    "MY": "马来",
    "ID": "印尼",
    "TH": "泰国",
    "VN": "越南",
    "BR": "巴西",
    "JP": "日本",
    "US": "美国",
    "MX": "墨西哥",
    "SG": "新加坡",
    "PH": "菲律宾",
    "TW": "台湾",
}

# Shopee 卖家中心域名映射（按国家配置）
_SHOPEE_SELLER_DOMAIN_MAP: Dict[str, str] = {
    "MY": "seller.shopee.com.my",
    "ID": "seller.shopee.co.id",
    "TH": "seller.shopee.co.th",
    "VN": "seller.shopee.vn",
    "BR": "seller.shopee.com.br",
    "MX": "seller.shopee.com.mx",
    "PH": "seller.shopee.ph",      # 菲律宾（预留）
    "SG": "seller.shopee.sg",      # 新加坡（预留）
    "TW": "seller.shopee.tw",      # 台湾（预留）
}

# Lazada 国家域名映射（按国家配置）
_LAZADA_COUNTRY_DOMAIN: Dict[str, str] = {
    "TH": "co.th",
    "VN": "vn",
    "MY": "com.my",
    "ID": "co.id",
    "PH": "com.ph",
    "SG": "sg",
}

# 国家/媒体组合配置（group_id 可选，没有则懒加载）
_GROUP_CONFIG_MAP: Dict[Tuple[str, str], Dict] = {
    # 已有 group_id 的配置
    ("TH", "tiktok"): {"group_id": 8559980},
    ("VN", "tiktok"): {"group_id": 8293559},
    ("MY", "shopee"): {"group_id": 7860758},
    ("ID", "shopee"): {"group_id": 7860756},
    ("MY", "tiktok"): {"group_id": 7860751},
    ("ID", "tiktok"): {"group_id": 7849620},
    # 新增配置（无 group_id，运行时懒加载）
    ("TH", "shopee"): {},
    ("VN", "shopee"): {},
    ("BR", "tiktok"): {},
    ("BR", "shopee"): {},
    ("JP", "tiktok"): {},
    ("JP", "shopee"): {},
    ("US", "tiktok"): {},
    ("US", "shopee"): {},
    ("MX", "tiktok"): {},
    ("MX", "shopee"): {},
}


@dataclass(frozen=True)
class Settings:
    ADSPOWER_API_URL: str = os.getenv("ADSPOWER_API_URL", "http://localhost:50325")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8080"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOGIN_TIMEOUT_SECONDS: int = int(os.getenv("LOGIN_TIMEOUT_SECONDS", "900"))
    MONITOR_API_URL: str = os.getenv("MONITOR_API_URL", "http://localhost:8777")
    COOKIE_API_TOKEN: str = os.getenv("COOKIE_API_TOKEN", "sk-5eajkJEpzRQL4pvMpqxxoffm3hgFi7FCNDs2OXfWIJuOipvx")
    LOGIN_CALLBACK_URL: str = os.getenv(
        "LOGIN_CALLBACK_URL",
        # "https://test01-patrick-star.tec-develop.cn/live/v1.0/live/room/account/login/callback"
        "https://www.livelabstar.com/live/v1.0/live/room/account/login/callback"
    )
    LOGIN_CALLBACK_ACCESS_TOKEN: str = os.getenv(
        "LOGIN_CALLBACK_ACCESS_TOKEN",
        # test
        # "eyHhbGciOiJIUzI1NiJ0.eyJqdGkiOiIyIiwic3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZHy8NE8"
        # pre| pro
        "UhYtrOciOiJIUzI1NiJ0.eyJqdGkiOiIyOkuwt3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZYGkdF"
    )
    LOGIN_SUCCESS_CLOSE_DELAY_SECONDS: int = int(os.getenv("LOGIN_SUCCESS_CLOSE_DELAY_SECONDS", "5"))
    LOGIN_FAILED_CLOSE_DELAY_SECONDS: int = int(os.getenv("LOGIN_FAILED_CLOSE_DELAY_SECONDS", "3"))
    LOGIN_TIMEOUT_CLOSE_DELAY_SECONDS: int = int(os.getenv("LOGIN_TIMEOUT_CLOSE_DELAY_SECONDS", "3"))
    SHOPEE_LOGIN_URL: str = "https://accounts.shopee.co.id/seller/login"
    TIKTOK_LOGIN_URL: str = "https://www.tiktok.com/login"
    LAZADA_LOGIN_URL: str = "https://live.lazada.co.th/app/login"  # 默认泰国
    GROUP_CONFIG_MAP: Dict[Tuple[str, str], Dict] = field(default_factory=lambda: _GROUP_CONFIG_MAP)
    # 飞书通知配置
    FEISHU_WEBHOOK_URL: str = os.getenv(
        "FEISHU_WEBHOOK_URL",
        "https://open.feishu.cn/open-apis/bot/v2/hook/51079d39-c0ba-4a83-803e-04d22017ac5f"
    )
    # 动态代理配置
    DYNAMIC_PROXY_API_URL: str = os.getenv(
        "DYNAMIC_PROXY_API_URL",
        "https://www.kkoip.com/pickdynamicips"
    )
    DYNAMIC_PROXY_SIGN: str = os.getenv("DYNAMIC_PROXY_SIGN", "d14379c4d98fc1247618ef21ce6394cb")
    DYNAMIC_PROXY_ACCESS_ID: str = os.getenv("DYNAMIC_PROXY_ACCESS_ID", "7758105")
    # 环境清理配置
    PROFILE_CLEANUP_THRESHOLD: int = int(os.getenv("PROFILE_CLEANUP_THRESHOLD", "60"))  # 触发清理的环境数量阈值
    PROFILE_CLEANUP_COUNT: int = int(os.getenv("PROFILE_CLEANUP_COUNT", "10"))  # 每次清理的环境数量
    # 浏览器分辨率配置
    BROWSER_WIDTH: int = int(os.getenv("BROWSER_WIDTH", "1920"))
    BROWSER_HEIGHT: int = int(os.getenv("BROWSER_HEIGHT", "1080"))


def get_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "dev").lower()

    if app_env == "pro":
        return Settings(
            LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
            LOGIN_CALLBACK_URL=os.getenv(
                "LOGIN_CALLBACK_URL",
                "https://www.livelabstar.com/live/v1.0/live/room/account/login/callback"
            ),
            LOGIN_CALLBACK_ACCESS_TOKEN=os.getenv(
                "LOGIN_CALLBACK_ACCESS_TOKEN",
                # test
                # "eyHhbGciOiJIUzI1NiJ0.eyJqdGkiOiIyIiwic3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZHy8NE8"
                # pre| pro
                "UhYtrOciOiJIUzI1NiJ0.eyJqdGkiOiIyOkuwt3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZYGkdF"
            ),
        )

    return Settings(
        LOG_LEVEL=os.getenv("LOG_LEVEL", "DEBUG"),
        LOGIN_CALLBACK_URL=os.getenv(
            "LOGIN_CALLBACK_URL",
            # "https://test01-patrick-star.tec-develop.cn/live/v1.0/live/room/account/login/callback"
            "https://test01-patrick-star.tec-develop.cn/live/v1.0/live/room/account/login/callback"
        ),
        LOGIN_CALLBACK_ACCESS_TOKEN=os.getenv(
            "LOGIN_CALLBACK_ACCESS_TOKEN",
            # test
            "eyHhbGciOiJIUzI1NiJ0.eyJqdGkiOiIyIiwic3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZHy8NE8"
            # pre| pro
            # "UhYtrOciOiJIUzI1NiJ0.eyJqdGkiOiIyOkuwt3ViIjoie1widXNlcklkXCI6MixcImNvbXBhbnlJZFwiOjIsXCJuaWNrbmFtZVwiOlwibHlkb25cIixcImVtYWlsXCI6XCJseWRvbi5saW5AdGVjLWRvLmNvbVwifSIsImlzcyI6InBob2VuaXgiLCJhdWQiOiJ1c2VyIiwiaWF0IjoxNzMzMTQ4Nzk4LCJleHAiOjE3MzU3NDA3OTh9.hPWRuY988rsJDGiGnY5QKj4mNQf_S6V2K9J0ZYGkdF"
        ),
    )


settings = get_settings()


def get_group_config(country: str, media: str) -> Optional[Dict]:
    if not country or not media:
        return None
    key = (country.upper(), media.lower())
    return settings.GROUP_CONFIG_MAP.get(key)


def get_login_url(media: str, country: str = "", cb_option: int = None) -> str:
    """根据媒体类型和国家获取登录URL，Shopee/Lazada 登录域名按国家区分"""
    if not media:
        return ""
    media_lower = media.lower()
    if media_lower == "shopee":
        # 跨境店统一使用 seller.shopee.cn 登录
        if cb_option == 1:
            return "https://seller.shopee.cn/seller/login"
        if country:
            seller_domain = _SHOPEE_SELLER_DOMAIN_MAP.get(country.upper())
            if seller_domain:
                # seller.shopee.xx -> accounts.shopee.xx
                accounts_domain = seller_domain.replace("seller.", "accounts.", 1)
                return f"https://{accounts_domain}/seller/login"
        # 未配置的国家，回退到默认
        return settings.SHOPEE_LOGIN_URL
    if media_lower == "lazada":
        country_domain = _LAZADA_COUNTRY_DOMAIN.get(country.upper(), "co.th") if country else "co.th"
        return f"https://live.lazada.{country_domain}/app/login"
    url_map = {
        "shopee": settings.SHOPEE_LOGIN_URL,
        "tiktok": settings.TIKTOK_LOGIN_URL,
    }
    return url_map.get(media_lower, "")


def get_proxy_by_country(country: str) -> Optional[str]:
    """根据国家获取代理，若配置为列表则随机选择一个"""
    if not country:
        return None
    proxy = _PROXY_MAP.get(country.upper())
    if isinstance(proxy, list):
        return random.choice(proxy)
    return proxy


def get_country_name(country: str) -> str:
    """根据国家代码获取中文名称，未找到则返回原代码"""
    if not country:
        return ""
    return _COUNTRY_NAME_MAP.get(country.upper(), country.upper())


def get_group_name(country: str, media: str) -> str:
    """生成标准 group_name：{中文名称}团队-{媒体}，如 印尼团队-tiktok"""
    country_name = get_country_name(country)
    return f"{country_name}团队-{media.lower()}"


def get_shopee_seller_domain(country: str) -> str:
    """根据国家获取 Shopee 卖家中心域名，未找到返回马来西亚域名"""
    if not country:
        return "seller.shopee.com.my"
    return _SHOPEE_SELLER_DOMAIN_MAP.get(country.upper(), "seller.shopee.com.my")
