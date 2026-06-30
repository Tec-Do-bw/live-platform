"""TikTok 直播大屏实时查询 fetcher。"""

from __future__ import annotations

from typing import Any

from crawlers.http.tiktok.collector import (
    CORE_STATS_QUERY_KEYS,
    _api_label,
    _build_filtered_url,
    _build_tiktok_headers,
    _json_dumps,
    _make_result,
    _parse_ext,
    _response_json,
)
from utils.credentials import Credentials
from utils.http_session import DEFAULT_RETRY_EXCEPTIONS, sync_retry
from utils.logger import logger
from utils.types import FetchResult


DASHBOARD_QUERY_KEYS = CORE_STATS_QUERY_KEYS
DASHBOARD_FIXED_QUERY = {"app_name": "i18n_ecom_shop", "vertical": "3"}
DASHBOARD_CORE_STATS_TYPES = [
    15, 27, 7, 344, 50, 346, 348, 71, 10, 20, 330, 29, 70, 11, 39, 43, 343, 23, 310, 325, 130, 30,
    332, 323, 349, 62, 61, 60, 331, 312, 313, 314, 315, 241, 283, 3, 2, 5, 18, 17, 290, 291,
    292, -3, -2, -7, -344, -23, -20, -18, -39, -10, -11, -70, -71,
]
DASHBOARD_TREND_CHART_TYPES = [
    3, 52, 82, 41, 344, 20, 11, 50, 14, 84, 51, 92, 23, 13, 12, 16, 312, 313, 314, 315, 401,
    15, 91, 343, 350, 81, 323,
]
USER_PORTRAIT_TYPES = [80, 81, 82, 83, 90, 85, 86, 87, 88, 350, 351, 352, 353, 92, 93, 95]
PRODUCT_LIST_TYPES = [4, 5, 6, 7, 10, 15, 17, 18, 21, 30, 35, 41, 48, 51, 55, 64, 120, 301, 345]


def _dashboard_url(path: str, cred: Credentials) -> str:
    """构造直播大屏接口 URL，过滤动态签名脏参数。"""
    ext = _parse_ext(cred)
    return _build_filtered_url(path, ext["query_string"], DASHBOARD_QUERY_KEYS, DASHBOARD_FIXED_QUERY)


@sync_retry(retries=2, delay=1.0, retry_exceptions=DEFAULT_RETRY_EXCEPTIONS)
def _post_dashboard_api(session: Any, cred: Credentials, api_name: str, path: str, payload: dict[str, Any]) -> FetchResult:
    """发送直播大屏实时查询请求，HTTP 成功即保留原始业务响应。"""
    url = _dashboard_url(path, cred)
    resp = session.post(url, headers=_build_tiktok_headers(cred), json=payload, timeout=15)
    resp.raise_for_status()
    data = _response_json(resp)
    logger.info(
        f"[{cred.account_id}/{_api_label(api_name)}] HTTP {resp.status_code} "
        f"code={data.get('code')} len={len(resp.text)}"
    )
    return _make_result(ok=True, url=url, request_body=_json_dumps(payload), response_body=resp.text, data=data)


def fetch_dashboard_core_stats(session: Any, cred: Credentials, room_id: str) -> FetchResult:
    """获取直播大屏核心指标。"""
    ext = _parse_ext(cred)
    creator_id = ext.get("creator_id", "")
    if not creator_id:
        logger.warning(f"[{cred.account_id}/dashboard_core_stats] 缺少 creator_id，仍继续请求")
    payload = {
        "request": {
            "room_filter": {
                "room_id": room_id,
                "is_content_type": 1,
                "creator_id": creator_id,
                "country": cred.region.upper(),
            },
            "stats_types": DASHBOARD_CORE_STATS_TYPES,
        }
    }
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_core_stats",
        "/api/v1/insights/workbench/live/detail/core/stats",
        payload,
    )


def fetch_dashboard_trend_chart(
    session: Any,
    cred: Credentials,
    room_id: str,
    start_time: int | None = None,
) -> FetchResult:
    """获取直播大屏趋势图。"""
    request: dict[str, Any] = {
        "room_filter": {"room_id": room_id, "is_content_type": 1},
        "stats_types": DASHBOARD_TREND_CHART_TYPES,
    }
    if start_time is not None:
        request["start_time"] = start_time
    payload = {"request": request}
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_trend_chart",
        "/api/v1/insights/workbench/live/detail/trend/chart",
        payload,
    )


def fetch_dashboard_source_new(session: Any, cred: Credentials, room_id: str) -> FetchResult:
    """获取直播大屏流量来源。"""
    payload = {
        "request": {
            "stats_types": [100],
            "room_filter": {"room_id": room_id, "is_content_type": 1},
        },
        "version": 3,
    }
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_source_new",
        "/api/v3/insights/workbench/live/detail/source/new",
        payload,
    )


def fetch_dashboard_user_portrait(session: Any, cred: Credentials, room_id: str) -> FetchResult:
    """获取直播大屏用户画像。"""
    payload = {
        "request": {
            "room_filter": {"room_id": room_id, "is_content_type": 1},
            "stats_types": USER_PORTRAIT_TYPES,
        }
    }
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_user_portrait",
        "/api/v1/insights/workbench/live/detail/user/portrait",
        payload,
    )


def fetch_dashboard_product_list(
    session: Any,
    cred: Credentials,
    room_id: str,
    granularity: int | None = None,
) -> FetchResult:
    """获取直播大屏商品列表。"""
    request: dict[str, Any] = {
        "room_filter": {"room_id": room_id, "is_content_type": 1},
        "sorting_type": 1,
        "stats_types": PRODUCT_LIST_TYPES,
    }
    if granularity is not None:
        request["granularity"] = granularity
    payload = {"request": request}
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_product_list",
        "/api/v1/insights/workbench/live/detail/product/list",
        payload,
    )


def fetch_dashboard_room_info(session: Any, cred: Credentials, room_id: str) -> FetchResult:
    """获取直播大屏房间信息。"""
    payload = {"request": {"room_filter": {"room_id": room_id, "is_content_type": 1}}}
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_room_info",
        "/api/v1/insights/workbench/live/detail/room/info",
        payload,
    )
