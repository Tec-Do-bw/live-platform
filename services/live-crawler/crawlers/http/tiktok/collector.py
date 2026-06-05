"""TikTok HTTP 采集器纯函数实现。"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlencode

from crawlers.constants import DataSource
from core.config import Settings
from utils.credentials import Credentials, load_credentials
from utils.headers import build_headers
from utils.http_session import get_session, sync_retry
from utils.logger import logger
from utils.types import FatalError, FetchResult, LoginRequired


BASE_URL = "https://shop.tiktok.com"
REFERER_URL = f"{BASE_URL}/streamer/compass/livestream-analytics/view"

# 直播录像列表（webcast）：账号级接口，host/language 按区域变化，仅 count/offset 翻页变化
REPLAY_INFO_PATH = "/webcast/room/replay/info/"
LIVECENTER_URL = "https://livecenter.tiktok.com"
REPLAY_REFERER_URL = f"{LIVECENTER_URL}/replay"
# 固定 query 参数（不含 count/offset/webcast_language），与 livecenter 直播录像页原生下发一致
REPLAY_FIXED_PARAMS = {
    "aid": "304449",
    "app_name": "tiktok_live_center",
    "device_platform": "web_pc",
    "need_suffix": "true",
}
REPLAY_COUNT_INCREMENTAL = 6   # 增量：仅取最新一页
REPLAY_COUNT_FULL = 30         # 全量：单页拉满以减少翻页请求数
REPLAY_MAX_PAGES = 50          # has_more 异常时的翻页安全上限，防止死循环
LIVE_LIST_PAGE_SIZE = 500      # live/list 单页大小，页面原生请求同口径
LIVE_LIST_MAX_PAGES = 10       # live/list 全量翻页安全上限，防止异常时死循环

# LIVE_LIST_STATS_TYPES = [
#     10, 15, 11, 12, 13, 14, 80, 88, 95, 90, 72, 96, 70, 86,
#     20, 29, 25, 50, 41, 42, 21, 40, 100, 101, 62, 61,
# ]
LIVE_LIST_STATS_TYPES = [10, 15, 11, 12, 13, 14, 80, 95, 90, 86, 82, 119, 20, 100, 101, 110, 111, 22, 72, 112, 113, 87,
                         62, 64, 21, 118, 120, 50, 114, 115, 40, 117, 116, 41, 42, 201, 202, 200, 88, 96, 70, 29, 25,
                         61]
# live/stats 单日聚合 stats_types：与页面原生下发一致（详见防摸鱼T1数据接口文档 §2.1）
# 不可复用 LIVE_LIST_STATS_TYPES——两者字段集与含义不同，混用会导致上报字段错配 + classifier 误分类
LIVE_STATS_TYPES = [11, 115, 13, 200, 106, 81, 82, 201, 202, 70, 210, 211, 212, 213]
TREND_CHART_STATS_BASIC = [3]
TREND_CHART_STATS_FULL = [3, 20, 341, 21, 22, 12, 16, 23, 50, 51, 40]
CORE_STATS_TYPES = [
    23, 20, 325, 310, 39, 29, 312, 313, 332, 330, 10, 323,
    315, 314, 349, 241, 3, 2, 5, 18, 290, 291, 292,
    -23, -20, -39, -330, -10, -3, -2, -18,
]

# 接口英文标识 → 中文名，用于日志可读性（grep 仍可用英文标识，人读直接看中文）
API_DISPLAY_NAMES = {
    "account_info": "账号信息",
    "replay_info": "直播录像列表",
    "live_list": "直播间列表",
    "live_stats": "关键指标",
    "trend_chart": "直播间趋势图",
    "core_stats": "直播大屏-流量分析-流量转化",
}


def _api_label(api_name: str) -> str:
    """返回 'english 中文' 形式的接口标识，无映射时回退为纯英文。"""
    cn = API_DISPLAY_NAMES.get(api_name, "")
    return f"{api_name} {cn}" if cn else api_name


class TikTokRegionProfile(TypedDict):
    """TikTok 不同国家请求特征。"""

    timezone_offset: int
    webcast_base_url: str
    webcast_language: str


TIKTOK_REGION_PROFILES: dict[str, TikTokRegionProfile] = {
    # 覆盖 SCHEDULER_CONFIG.cron_config 的 UTC+9/+8/+7/-3/-6/-8 时区组
    "JP": {
        "timezone_offset": 32400,
        "webcast_base_url": "https://webcast.tiktok.com",
        "webcast_language": "ja-JP",
    },
    "SG": {
        "timezone_offset": 28800,
        "webcast_base_url": "https://webcast.tiktok.com",
        "webcast_language": "en",
    },
    "MY": {
        "timezone_offset": 28800,
        "webcast_base_url": "https://webcast.tiktok.com",
        "webcast_language": "en",
    },
    "CN": {
        "timezone_offset": 28800,
        "webcast_base_url": "https://webcast.tiktok.com",
        "webcast_language": "en",
    },
    "ID": {
        "timezone_offset": 25200,
        "webcast_base_url": "https://webcast.tiktok.com",
        "webcast_language": "en",
    },
    "TH": {
        "timezone_offset": 25200,
        "webcast_base_url": "https://webcast.tiktok.com",
        "webcast_language": "en",
    },
    "VN": {
        "timezone_offset": 25200,
        "webcast_base_url": "https://webcast.tiktok.com",
        "webcast_language": "vi-VN",
    },
    "PH": {
        # 存疑：依据历史 request_context 数据(carrier_region=ph 但 timezone_name=Asia/Bangkok)
        # 推断为 UTC+7=25200，未经活账号验证。PH 本土时区实际可能是 Asia/Manila(UTC+8=28800)。
        # 待有 PH 活账号投屏时核实，再据实修正。
        "timezone_offset": 25200,
        "webcast_base_url": "https://webcast.tiktok.com",
        "webcast_language": "en",
    },
    "BR": {
        "timezone_offset": -10800,
        "webcast_base_url": "https://webcast.tiktok.com",
        "webcast_language": "pt",
    },
    "MX": {
        "timezone_offset": -21600,
        "webcast_base_url": "https://webcast.tiktok.com",
        "webcast_language": "es-419",
    },
    "US": {
        "timezone_offset": -28800,
        "webcast_base_url": "https://webcast.us.tiktok.com",
        "webcast_language": "en",
    },
}
DEFAULT_REGION_PROFILE: TikTokRegionProfile = {
    "timezone_offset": 0,
    "webcast_base_url": "https://webcast.tiktok.com",
    "webcast_language": "en",
}
TIMEZONE_OFFSET_MAP = {
    region: profile["timezone_offset"]
    for region, profile in TIKTOK_REGION_PROFILES.items()
}


class RoomMeta(TypedDict):
    """直播间元数据。"""

    room_id: str
    room_name: str
    live_start_ts: int
    live_end_ts: int
    revenue: str
    currency_code: str


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _parse_ext(cred: Credentials) -> dict[str, Any]:
    """从 Credentials.ext_json 解析 TikTok 请求上下文。"""
    ext = cred.ext
    return {
        "query_string": ext.get("query_string", ""),
        "creator_id": ext.get("creator_id", ""),
        "user_agent": ext.get("user_agent", ""),
    }


def _region_profile(region: str) -> TikTokRegionProfile:
    """根据账号真实国家获取 TikTok 请求特征。

    region 缺失或未知时降级到 DEFAULT_REGION_PROFILE（UTC+0），并告警提示，
    避免静默按 UTC+0 推算时间窗导致采集日期错位却无迹可查。
    """
    if not region:
        logger.warning("TikTok 账号 region 缺失，降级使用 UTC+0 默认请求特征")
        return DEFAULT_REGION_PROFILE
    profile = TIKTOK_REGION_PROFILES.get(region.upper())
    if profile is None:
        logger.warning(f"TikTok 未知 region={region}，降级使用 UTC+0 默认请求特征")
        return DEFAULT_REGION_PROFILE
    return profile


def _build_url(path: str, query_string: str = "", extra_params: dict[str, Any] | None = None) -> str:
    """构造完整 URL，保留账号级 query string。"""
    params = parse_qs(query_string, keep_blank_values=True)
    if extra_params:
        for key, value in extra_params.items():
            params[key] = [str(value)]
    query = urlencode(params, doseq=True)
    return f"{BASE_URL}{path}?{query}" if query else f"{BASE_URL}{path}"


def _build_tiktok_headers(cred: Credentials, extra: dict[str, str] | None = None) -> dict[str, str]:
    """构造 TikTok API 请求头。"""
    region = cred.region.upper()
    headers_extra = {
        "content-type": "application/json",
    }
    if region:
        headers_extra["x-tt-store-region"] = region.lower()
    ext = _parse_ext(cred)
    if ext.get("user_agent"):
        headers_extra["user-agent"] = ext["user_agent"]
    if extra:
        headers_extra.update(extra)
    return build_headers(origin=BASE_URL, referer=REFERER_URL, cred=cred, extra=headers_extra)


def _build_webcast_headers(cred: Credentials) -> dict[str, str]:
    """构造 webcast 接口请求头（origin/referer 指向 livecenter 直播录像页）。"""
    extra: dict[str, str] = {}
    ext = _parse_ext(cred)
    if ext.get("user_agent"):
        extra["user-agent"] = ext["user_agent"]
    return build_headers(origin=LIVECENTER_URL, referer=REPLAY_REFERER_URL, cred=cred, extra=extra)


def _tiktok_http_config() -> dict[str, Any]:
    """读取 TikTok HTTP 采集配置。"""
    return getattr(Settings, "TIKTOK_HTTP_CONFIG", {}) or {}


def _full_window_days() -> int:
    """读取全量默认时间窗天数。"""
    raw_value = _tiktok_http_config().get("full_window_days", 60)
    try:
        days = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("TIKTOK_HTTP_FULL_WINDOW_DAYS 必须是正整数") from exc
    if days <= 0:
        raise ValueError("TIKTOK_HTTP_FULL_WINDOW_DAYS 必须是正整数")
    return days


def _full_window_bounds(region: str) -> tuple[int, int]:
    """计算全量时间窗起止 UTC 时间戳（基于账号当地时区）。

    默认起点 = 账号当地 today-N 00:00:00（N 默认 60）；
    配置 TIKTOK_HTTP_FULL_START_DATE 后，起点 = 指定日期当地 00:00:00；
    终点 = 账号当地 today 00:00:00（不含今天）。
    """
    offset = _region_profile(region)["timezone_offset"]
    tz_obj = timezone(timedelta(seconds=offset))
    now = datetime.now(tz_obj)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_date_text = str(_tiktok_http_config().get("full_start_date", "")).strip()
    if start_date_text:
        try:
            start_date = date.fromisoformat(start_date_text)
        except ValueError as exc:
            raise ValueError("TIKTOK_HTTP_FULL_START_DATE 必须使用 YYYY-MM-DD 格式") from exc
        start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=tz_obj)
    else:
        start = end - timedelta(days=_full_window_days())

    if start >= end:
        raise ValueError("TIKTOK_HTTP_FULL_START_DATE 必须早于账号当地今天")
    return int(start.timestamp()), int(end.timestamp())


def _time_window(region: str, full: bool) -> dict[str, int | str]:
    """计算 TikTok live/list 时间窗。"""
    offset = _region_profile(region)["timezone_offset"]
    tz_obj = timezone(timedelta(seconds=offset))
    now = datetime.now(tz_obj)
    if full:
        start_ts, end_ts = _full_window_bounds(region)
        return {
            "period": 2,
            "granularity": 1,
            "start_timestamp": str(start_ts),
            "end_timestamp": str(end_ts),
            "timezone_offset": offset,
        }
    return {
        "period": 33,
        "granularity": 32,
        "base_timestamp": str(int(now.timestamp())),
        "timezone_offset": offset,
        "days_back": 28 if full else 3,
    }


def _response_json(resp: Any) -> dict[str, Any]:
    """解析响应 JSON，失败时抛出普通异常给 sync_retry/collector 处理。"""
    data = resp.json()
    return data if isinstance(data, dict) else {"data": data}


def _check_code(data: dict[str, Any], endpoint: str, account_id: str) -> bool:
    """校验响应业务码，TikTok 全端点统一契约：code==0 表示成功。

    返回 True 表示业务成功；False 表示业务失败（HTTP 200 + code≠0），
    调用方应将其当作采集失败处理，避免脏数据上报下游。
    详见 docs/specs/防摸鱼T1数据接口说明文档.md
    """
    code = data.get("code")
    if code == 0:
        return True
    msg = data.get("message", "")
    logger.warning(f"[{account_id}/{endpoint}] 业务码异常 code={code} message={msg}")
    return False


def _check_webcast_code(data: dict[str, Any], endpoint: str, account_id: str) -> bool:
    """校验 webcast 接口业务码：webcast 用 status_code==0 表示成功（兼容 code）。"""
    code = data.get("status_code", data.get("code"))
    if code == 0:
        return True
    msg = data.get("message") or data.get("status_msg", "")
    logger.warning(f"[{account_id}/{endpoint}] webcast 业务码异常 status_code={code} message={msg}")
    return False


def _replay_has_more(data: dict[str, Any]) -> bool:
    """从 replay/info 响应解析 data.has_more，缺失时按 False 处理（停止翻页）。"""
    return bool(data.get("data", {}).get("has_more"))


def _local_yesterday(region: str) -> date:
    """根据账号区域时区推算当地 today-1（latest_available_date）。

    与浏览器版 browserapi._generate_daily_payloads 时区口径一致，
    避免 server 时区≠账号时区时日期窗口错位。
    """
    offset = _region_profile(region)["timezone_offset"]
    tz_obj = timezone(timedelta(seconds=offset))
    return (datetime.now(tz_obj) - timedelta(days=1)).date()


def _make_result(
    *,
    ok: bool,
    url: str,
    request_body: str | dict[str, Any] | None,
    response_body: str | dict[str, Any],
    data: dict[str, Any],
) -> FetchResult:
    return {
        "ok": ok,
        "url": url,
        "request_body": request_body,
        "response_body": response_body,
        "data": data,
    }


def _format_message(
    url: str,
    request_body: Any,
    response_body: Any,
    cookies: list[dict[str, Any]] | dict[str, Any],
    socket_user_id: str,
) -> dict[str, Any]:
    """格式化为与浏览器版 format_api_message 等价的上报消息。

    镜像浏览器版 `crawlers/browser/base.py:177-219`：
    - request_body 为 "No request body" 或 falsy 时 extra=None
    - request_body 是 str 时原样进入 extra，否则 json.dumps(request_body)
    - response_body 是 dict 时 json.dumps(..., ensure_ascii=False)，否则 str(...)
    - 字段固定为 params/cookies/fromUrl/extra/sign/userType/updateTime/request/socketUserId
    """
    if request_body == "No request body" or not request_body:
        extra = None
    else:
        extra = request_body if isinstance(request_body, str) else _json_dumps(request_body)

    if isinstance(response_body, dict):
        response_str = _json_dumps(response_body)
    else:
        response_str = str(response_body)

    return {
        "params": "",
        "cookies": _json_dumps(cookies),
        "fromUrl": url,
        "extra": extra,
        "sign": Settings.DATA_SERVER_CONFIG["api_sign"],
        "userType": 6.0,
        "dataSource": DataSource.TIKTOK,
        "updateTime": int(time.time() * 1000),
        "request": {
            "response": response_str,
            "url": url,
        },
        "socketUserId": socket_user_id,
    }


@sync_retry(retries=2, delay=1.0)
def fetch_account_info(session: Any, cred: Credentials) -> FetchResult:
    """获取账号信息并验证登录态。"""
    ext = _parse_ext(cred)
    url = _build_url(
        "/api/v1/streamer_desktop/account_info/get",
        ext["query_string"],
        {"version": "1"},
    )
    resp = session.get(url, headers=_build_tiktok_headers(cred), timeout=10)
    resp.raise_for_status()
    data = _response_json(resp)
    ok = _check_code(data, "account_info", cred.account_id) and bool(data.get("data", {}).get("user_id"))
    logger.info(f"[{cred.account_id}/{_api_label('account_info')}] HTTP {resp.status_code} ok={ok}")
    return _make_result(ok=ok, url=url, request_body=None, response_body=resp.text, data=data)


@sync_retry(retries=2, delay=1.0)
def fetch_replay_info(session: Any, cred: Credentials, count: int, offset: int) -> FetchResult:
    """获取直播录像回放列表分页（webcast 账号级接口）。

    GET https://webcast*.tiktok.com/webcast/room/replay/info/
    host/webcast_language 按 region 派生；翻页由调用方依据 data.has_more 推进。
    """
    profile = _region_profile(cred.region)
    params = {
        **REPLAY_FIXED_PARAMS,
        "count": str(count),
        "offset": str(offset),
        "webcast_language": profile["webcast_language"],
    }
    url = f"{profile['webcast_base_url']}{REPLAY_INFO_PATH}?{urlencode(params)}"
    resp = session.get(url, headers=_build_webcast_headers(cred), timeout=10)
    resp.raise_for_status()
    data = _response_json(resp)
    ok = _check_webcast_code(data, "replay_info", cred.account_id)
    logger.info(
        f"[{cred.account_id}/{_api_label('replay_info')}] offset={offset} count={count} "
        f"HTTP {resp.status_code} ok={ok} has_more={_replay_has_more(data)}"
    )
    return _make_result(ok=ok, url=url, request_body=None, response_body=resp.text, data=data)


@sync_retry(retries=2, delay=1.0)
def fetch_live_list(session: Any, cred: Credentials, full: bool = False, page: int = 0) -> FetchResult:
    """获取直播间列表，直接请求扩展 stats_types。"""
    ext = _parse_ext(cred)
    url = _build_url("/api/v2/insights/creator/live/list", ext["query_string"])
    tw = _time_window(cred.region, full)
    time_selector = {
        "period": tw["period"],
        "granularity": tw["granularity"],
        "timezone_offset": tw["timezone_offset"],
    }
    if full:
        time_selector["start_timestamp"] = tw["start_timestamp"]
        time_selector["end_timestamp"] = tw["end_timestamp"]
    else:
        time_selector["base_timestamp"] = tw["base_timestamp"]
    payload = {
        "request": {
            "params": [
                {
                    "time_selector": time_selector,
                    "list_control": {
                        "rules": [{"direction": 2, "field": "LIVE_LIST_LIVE_START_TIMESTAMP"}],
                        "pagination": {"size": LIVE_LIST_PAGE_SIZE, "page": page},
                    },
                    "stats_types": LIVE_LIST_STATS_TYPES,
                }
            ]
        },
        "version": "2",
    }
    resp = session.post(url, headers=_build_tiktok_headers(cred), json=payload, timeout=15)
    resp.raise_for_status()
    data = _response_json(resp)
    ok = _check_code(data, "live_list", cred.account_id)
    logger.info(
        f"[{cred.account_id}/{_api_label('live_list')}] page={page} "
        f"HTTP {resp.status_code} ok={ok} len={len(resp.text)}"
    )
    return _make_result(ok=ok, url=url, request_body=_json_dumps(payload), response_body=resp.text, data=data)


@sync_retry(retries=2, delay=1.0)
def fetch_live_stats(session: Any, cred: Credentials, target_date: date) -> FetchResult:
    """获取单日 live/stats 汇总。"""
    ext = _parse_ext(cred)
    url = _build_url("/api/v2/insights/creator/live/stats", ext["query_string"])
    start_ts = int(datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    end_ts = start_ts + 86400
    # 结构对齐页面原生 payload：params 数组包裹 + is_live_type，不可用扁平结构（详见接口文档 §2.1）
    payload = {
        "request": {
            "params": [
                {
                    "time_selector": {
                        "period": 2,
                        "granularity": 1,
                        "start_timestamp": str(start_ts),
                        "end_timestamp": str(end_ts),
                        "timezone_offset": "0",
                    },
                    "stats_types": LIVE_STATS_TYPES,
                    "is_live_type": True,
                }
            ],
            "version": "2",
        }
    }
    resp = session.post(url, headers=_build_tiktok_headers(cred), json=payload, timeout=10)
    resp.raise_for_status()
    data = _response_json(resp)
    ok = _check_code(data, "live_stats", cred.account_id)
    logger.info(f"[{cred.account_id}/{_api_label('live_stats')}] date={target_date} HTTP {resp.status_code} ok={ok}")
    return _make_result(ok=ok, url=url, request_body=_json_dumps(payload), response_body=resp.text, data=data)


@sync_retry(retries=2, delay=1.0)
def fetch_trend_chart(
    session: Any,
    cred: Credentials,
    room_id: str,
    stats_types: list[int] | None = None,
) -> FetchResult:
    """获取单房间趋势图。"""
    ext = _parse_ext(cred)
    url = _build_url("/api/v1/insights/creator/liveroom/recap/trend/chart", ext["query_string"])
    payload = {
        "request": {
            "room_filter": {"room_id": room_id, "query_online": True},
            "stats_types": stats_types or TREND_CHART_STATS_BASIC,
            "granularity": 1,
        }
    }
    resp = session.post(url, headers=_build_tiktok_headers(cred), json=payload, timeout=10)
    resp.raise_for_status()
    data = _response_json(resp)
    ok = _check_code(data, "trend_chart", cred.account_id)
    logger.info(f"[{cred.account_id}/{_api_label('trend_chart')}] room={room_id} HTTP {resp.status_code} ok={ok}")
    return _make_result(ok=ok, url=url, request_body=_json_dumps(payload), response_body=resp.text, data=data)


@sync_retry(retries=2, delay=1.0)
def fetch_core_stats(session: Any, cred: Credentials, room_id: str) -> FetchResult:
    """获取单房间核心统计。"""
    ext = _parse_ext(cred)
    keep_keys = {
        "device_id",
        "fp",
        "device_platform",
        "cookie_enabled",
        "screen_width",
        "screen_height",
        "browser_language",
        "browser_platform",
        "browser_name",
        "browser_version",
        "browser_online",
        "timezone_name",
    }
    raw_params = parse_qs(ext["query_string"], keep_blank_values=True)
    base_params = {key: values[0] for key, values in raw_params.items() if key in keep_keys}
    base_params["app_name"] = "i18n_ecom_shop"
    base_params["vertical"] = "3"
    url = f"{BASE_URL}/api/v1/insights/workbench/live/detail/core/stats?{urlencode(base_params)}"
    payload = {
        "request": {
            "room_filter": {
                "room_id": room_id,
                "is_content_type": 1,
                "creator_id": ext["creator_id"],
                "country": cred.region.upper(),
            },
            "stats_types": CORE_STATS_TYPES,
        }
    }
    resp = session.post(url, headers=_build_tiktok_headers(cred), json=payload, timeout=10)
    resp.raise_for_status()
    data = _response_json(resp)
    ok = _check_code(data, "core_stats", cred.account_id)
    logger.info(f"[{cred.account_id}/{_api_label('core_stats')}] room={room_id} HTTP {resp.status_code} ok={ok}")
    return _make_result(ok=ok, url=url, request_body=_json_dumps(payload), response_body=resp.text, data=data)


def parse_rooms(live_list_data: dict[str, Any]) -> tuple[list[RoomMeta], str]:
    """从 live/list 响应解析直播间列表和 creator_id。"""
    segments = live_list_data.get("data", {}).get("segments", [])
    first = segments[0] if segments else {}
    creator_ids = first.get("filter", {}).get("creator_id", [])
    creator_id = str(creator_ids[0]) if creator_ids else ""
    timed_lists = first.get("timed_lists", [])
    stats = timed_lists[0].get("stats", []) if timed_lists else []

    rooms: list[RoomMeta] = []
    for stat in stats:
        room_id = stat.get("live_id")
        live_end_ts = int(stat.get("live_end_timestamp") or 0)
        if not room_id or live_end_ts == 0:
            continue
        revenue = stat.get("revenue", {}) or {}
        rooms.append(
            {
                "room_id": str(room_id),
                "room_name": stat.get("live_name", ""),
                "live_start_ts": int(stat.get("live_start_timestamp") or 0),
                "live_end_ts": live_end_ts,
                "revenue": str(revenue.get("amount", "0")),
                "currency_code": revenue.get("currency_code", ""),
            }
        )
    return rooms, creator_id


def filter_rooms_by_window(rooms: list[RoomMeta], region: str, full: bool) -> list[RoomMeta]:
    """按采集窗口过滤直播间。"""
    if full:
        return rooms
    offset = _region_profile(region)["timezone_offset"]
    tz_obj = timezone(timedelta(seconds=offset))
    now = datetime.now(tz_obj)
    cutoff = now - timedelta(days=3)
    cutoff_dt = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=tz_obj)
    cutoff_ts = int(cutoff_dt.timestamp())
    return [room for room in rooms if room["live_end_ts"] >= cutoff_ts]


def _update_creator_id(cred: Credentials, creator_id: str) -> None:
    """creator_id 变化时回写 ext_json。"""
    ext = cred.ext
    if creator_id and ext.get("creator_id") != creator_id:
        ext["creator_id"] = creator_id
        cred.ext_json = _json_dumps(ext)
        cred.save()


def _cookie_dict_from_token(token: dict[str, Any] | list[dict[str, Any]]) -> dict[str, str]:
    """将浏览器 cookie list 或 dict 转成 Session 可接受的 cookie dict。"""
    if isinstance(token, dict):
        return {str(key): str(value) for key, value in token.items()}
    cookies: dict[str, str] = {}
    for item in token:
        name = item.get("name")
        if name:
            cookies[str(name)] = str(item.get("value", ""))
    return cookies


def _yield_fetch_result(item: FetchResult) -> tuple[bool, FetchResult | dict[str, Any]]:
    """把 FetchResult 转成 (ok, payload) 二元组。

    业务码异常（ok=False）时返回错误占位包，避免脏数据上报下游；
    业务成功时原样透传 FetchResult 给 adapter 走上报。
    """
    if item["ok"]:
        return True, item
    return False, {
        "url": item["url"],
        "request_body": item["request_body"],
        "response_body": item["response_body"],
        "data": {"error": "业务码异常 code≠0", "url": item["url"]},
    }


def _collect_replay_info(
    session: Any, cred: Credentials, full: bool
) -> Iterator[FetchResult]:
    """采集直播回放列表，按 has_more 翻页。

    增量：count=6 仅取最新一页（不翻页，最新直播覆盖增量窗口足矣）；
    全量：count=30 单页拉满，data.has_more 为 true 时 offset 累加 count 继续。
    """
    count = REPLAY_COUNT_FULL if full else REPLAY_COUNT_INCREMENTAL
    offset = 0
    for _ in range(REPLAY_MAX_PAGES):
        result = fetch_replay_info(session, cred, count, offset)
        yield result
        # 业务码异常或增量模式：不翻页
        if not result["ok"] or not full:
            return
        if not _replay_has_more(result["data"]):
            return
        offset += count


def _full_stats_days_range(region: str) -> range:
    """计算 live/stats 全量日聚合倒序天数范围。"""
    latest = _local_yesterday(region)
    start_ts, _ = _full_window_bounds(region)
    offset = _region_profile(region)["timezone_offset"]
    tz_obj = timezone(timedelta(seconds=offset))
    start_date = datetime.fromtimestamp(start_ts, tz_obj).date()
    days_count = (latest - start_date).days + 1
    if days_count <= 0:
        raise ValueError("TikTok HTTP 全量 live/stats 时间窗为空")
    return range(0, days_count)


def setup_session(account_id: str) -> tuple[Credentials, Any, FetchResult]:
    """加载凭据、建立会话并验证登录态。

    从 collect_tiktok 头部抽出，供 adapter 在进入数据采集前先验证登录态：
    验证通过才发 success 回调并决定本轮 full，验证失败抛 LoginRequired 走登出回调。

    Returns:
        (cred, session, login_result) 三元组；登录态失效时抛 LoginRequired。
        调用方负责在使用完毕后 session.close()。
    """
    cred = load_credentials(account_id, platform="tiktok")
    if not cred or not cred.token:
        raise FatalError(f"[{account_id}] 凭据缺失，需要刷新")

    # query_string 携带设备指纹（device_id/fp/browser_* 等），是所有 fetch_* 接口
    # 构造合法 URL 的前提；缺失时 TikTok 会返回 no login/invalid params。
    # 浏览器版从拦截请求动态提取可运行时容错，HTTP 版静态读库必须在采集前校验，
    # 否则会静默降级成无指纹请求。不可降级，抛 FatalError 走调度层重新刷新。
    if not _parse_ext(cred)["query_string"]:
        raise FatalError(
            f"[{account_id}] 凭据 ext_json.query_string 缺失（设备指纹），需要重新刷新"
        )

    session = get_session(cred.fingerprint_spec, proxy=cred.proxy)
    try:
        session.cookies.update(_cookie_dict_from_token(cred.token_data))
        login_result = fetch_account_info(session, cred)
    except Exception:
        session.close()
        raise
    if not login_result["ok"]:
        session.close()
        raise LoginRequired(f"[{account_id}] 登录态失效")
    return cred, session, login_result


def collect_tiktok(
    account_id: str,
    full: bool = False,
    *,
    cred: Credentials | None = None,
    session: Any | None = None,
    login_result: FetchResult | None = None,
) -> Iterator[tuple[bool, FetchResult | dict[str, Any]]]:
    """TikTok HTTP 采集编排生成器。

    三个 keyword 参数同时缺省时自动 setup_session（向后兼容旧调用）；
    adapter 已在外部完成验证与回调时，注入复用以避免重复请求 account_info。
    注入会话由调用方负责关闭；自建会话在 finally 中关闭。
    """
    owns_session = cred is None or session is None or login_result is None
    if owns_session:
        cred, session, login_result = setup_session(account_id)
    try:
        # 账号信息（个人资料）上报：自建会话时在此 yield；
        # 注入模式下 adapter 已在验证阶段上报过，跳过避免重复上报
        if owns_session:
            yield _yield_fetch_result(login_result)

        # 直播回放列表（webcast 账号级接口），按 has_more 翻页
        try:
            for replay_result in _collect_replay_info(session, cred, full):
                yield _yield_fetch_result(replay_result)
        except Exception as e:
            logger.exception(f"[{account_id}] replay_info 采集失败")
            yield False, {
                "url": "",
                "request_body": None,
                "response_body": "",
                "data": {"error": str(e), "endpoint": "replay_info"},
            }

        list_rooms: list[RoomMeta] = []
        creator_id = ""
        max_pages = LIVE_LIST_MAX_PAGES if full else 1
        for page in range(max_pages):
            list_result = fetch_live_list(session, cred, full, page=page)
            yield _yield_fetch_result(list_result)

            page_rooms, page_creator_id = parse_rooms(list_result["data"])
            list_rooms.extend(page_rooms)
            if page_creator_id and not creator_id:
                creator_id = page_creator_id
            if not list_result["ok"] or len(page_rooms) < LIVE_LIST_PAGE_SIZE:
                break
        else:
            logger.warning(
                f"[{account_id}/{_api_label('live_list')}] 已达到翻页上限 "
                f"max_pages={LIVE_LIST_MAX_PAGES}，请核对是否存在截断"
            )

        _update_creator_id(cred, creator_id)
        rooms = filter_rooms_by_window(list_rooms, cred.region, full)
        logger.info(f"[{account_id}] TikTok HTTP 找到 {len(rooms)} 个直播间 full={full}")

        for index, room in enumerate(rooms):
            room_id = room["room_id"]
            try:
                yield _yield_fetch_result(fetch_trend_chart(session, cred, room_id, TREND_CHART_STATS_BASIC))
                yield _yield_fetch_result(fetch_trend_chart(session, cred, room_id, TREND_CHART_STATS_FULL))
                yield _yield_fetch_result(fetch_core_stats(session, cred, room_id))
            except Exception as e:
                logger.exception(f"[{account_id}] room={room_id} 采集失败")
                yield False, {
                    "url": "",
                    "request_body": None,
                    "response_body": "",
                    "data": {"error": str(e), "room_id": room_id},
                }

            if index < len(rooms) - 1:
                time.sleep(random.uniform(0.5, 1.5))

        # live/stats 日聚合：增量取 T-1/T-2/T-3，全量跟随 TikTok HTTP 配置时间窗
        # 时区锚点统一用账号当地 today-1，与浏览器版 browserapi._generate_daily_payloads 对齐
        # 详见 .claude/rules/tiktok-collection-time.md
        latest = _local_yesterday(cred.region)
        days_range = _full_stats_days_range(cred.region) if full else range(0, 3)
        for days_back in days_range:
            target = latest - timedelta(days=days_back)
            try:
                yield _yield_fetch_result(fetch_live_stats(session, cred, target))
            except Exception as e:
                logger.exception(f"[{account_id}] live_stats {target} 失败")
                yield False, {
                    "url": "",
                    "request_body": None,
                    "response_body": "",
                    "data": {"error": str(e), "date": target.isoformat()},
                }
    finally:
        # 自建会话由本函数关闭；注入会话交回 adapter 在 finally 中关闭
        if owns_session:
            session.close()
