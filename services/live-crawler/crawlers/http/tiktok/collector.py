"""TikTok HTTP 采集器纯函数实现。"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlencode

from core.config import Settings
from utils.credentials import Credentials, load_credentials
from utils.headers import build_headers
from utils.http_session import get_session, sync_retry
from utils.logger import logger
from utils.types import FatalError, FetchResult, LoginRequired


BASE_URL = "https://shop.tiktok.com"
REFERER_URL = f"{BASE_URL}/streamer/compass/livestream-analytics/view"

LIVE_LIST_STATS_TYPES = [
    10, 15, 11, 12, 13, 14, 80, 88, 95, 90, 72, 96, 70, 86,
    20, 29, 25, 50, 41, 42, 21, 40, 100, 101, 62, 61,
]
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
TIMEZONE_OFFSET_MAP = {
    "US": -28800,
    "ID": 25200,
    "MY": 28800,
    "SG": 28800,
    "MX": -21600,
    "TH": 25200,
    "VN": 25200,
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


def _time_window(region: str, full: bool) -> dict[str, int | str]:
    """计算 TikTok live/list 时间窗。"""
    offset = TIMEZONE_OFFSET_MAP.get(region.upper(), 0)
    tz_obj = timezone(timedelta(seconds=offset))
    now = datetime.now(tz_obj)
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


def _local_yesterday(region: str) -> date:
    """根据账号区域时区推算当地 today-1（latest_available_date）。

    与浏览器版 browserapi._generate_daily_payloads 时区口径一致，
    避免 server 时区≠账号时区时日期窗口错位。
    """
    offset = TIMEZONE_OFFSET_MAP.get(region.upper(), 0)
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
    logger.info(f"[{cred.account_id}/account_info] HTTP {resp.status_code} ok={ok}")
    return _make_result(ok=ok, url=url, request_body=None, response_body=resp.text, data=data)


@sync_retry(retries=2, delay=1.0)
def fetch_live_list(session: Any, cred: Credentials, full: bool = False) -> FetchResult:
    """获取直播间列表，直接请求扩展 stats_types。"""
    ext = _parse_ext(cred)
    url = _build_url("/api/v2/insights/creator/live/list", ext["query_string"])
    tw = _time_window(cred.region, full)
    payload = {
        "request": {
            "params": [
                {
                    "time_selector": {
                        "period": tw["period"],
                        "granularity": tw["granularity"],
                        "base_timestamp": tw["base_timestamp"],
                        "timezone_offset": tw["timezone_offset"],
                    },
                    "list_control": {
                        "rules": [{"direction": 2, "field": "LIVE_LIST_LIVE_START_TIMESTAMP"}],
                        "pagination": {"size": 500, "page": 0},
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
    logger.info(f"[{cred.account_id}/live_list] HTTP {resp.status_code} ok={ok} len={len(resp.text)}")
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
                        "granularity": 11,
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
    logger.info(f"[{cred.account_id}/live_stats] date={target_date} HTTP {resp.status_code} ok={ok}")
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
    logger.info(f"[{cred.account_id}/trend_chart] room={room_id} HTTP {resp.status_code} ok={ok}")
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
    logger.info(f"[{cred.account_id}/core_stats] room={room_id} HTTP {resp.status_code} ok={ok}")
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
    offset = TIMEZONE_OFFSET_MAP.get(region.upper(), 0)
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


def collect_tiktok(account_id: str, full: bool = False) -> Iterator[tuple[bool, FetchResult | dict[str, Any]]]:
    """TikTok HTTP 采集编排生成器。"""
    cred = load_credentials(account_id, platform="tiktok")
    if not cred or not cred.token:
        raise FatalError(f"[{account_id}] 凭据缺失，需要刷新")

    session = get_session(cred.fingerprint_spec, proxy=cred.proxy)
    try:
        session.cookies.update(_cookie_dict_from_token(cred.token_data))

        login_result = fetch_account_info(session, cred)
        if not login_result["ok"]:
            raise LoginRequired(f"[{account_id}] 登录态失效")

        list_result = fetch_live_list(session, cred, full)
        yield _yield_fetch_result(list_result)

        rooms, creator_id = parse_rooms(list_result["data"])
        _update_creator_id(cred, creator_id)
        rooms = filter_rooms_by_window(rooms, cred.region, full)
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

        # live/stats 日聚合：增量取 T-1/T-2/T-3，全量取 T-1 ~ T-28
        # 时区锚点统一用账号当地 today-1，与浏览器版 browserapi._generate_daily_payloads 对齐
        # 详见 .claude/rules/tiktok-collection-time.md
        latest = _local_yesterday(cred.region)
        days_range = range(0, 28) if full else range(0, 3)
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
        session.close()
