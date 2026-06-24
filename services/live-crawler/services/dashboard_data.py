"""TikTok 直播大屏数据服务。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from crawlers.http.tiktok.collector import _format_message, setup_session
from crawlers.http.tiktok.real_collector import (
    fetch_dashboard_core_stats,
    fetch_dashboard_product_list,
    fetch_dashboard_room_info,
    fetch_dashboard_source_new,
    fetch_dashboard_trend_chart,
    fetch_dashboard_user_portrait,
)
from monitor.schemas.dashboard import DashboardDataRequest, DashboardDataType, DashboardTimeRange
from utils.http_session import DEFAULT_RETRY_EXCEPTIONS
from utils.types import FatalError, LoginRequired


class DashboardApiError(Exception):
    """直播大屏 API 错误，供 route 层转成统一响应。"""

    def __init__(self, code: int, reason: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.reason = reason
        self.detail = detail


DASHBOARD_FETCHERS: dict[DashboardDataType, Callable[..., dict[str, Any]]] = {
    DashboardDataType.core_stats: fetch_dashboard_core_stats,
    DashboardDataType.trend_chart: fetch_dashboard_trend_chart,
    DashboardDataType.source_new: fetch_dashboard_source_new,
    DashboardDataType.user_portrait: fetch_dashboard_user_portrait,
    DashboardDataType.product_list: fetch_dashboard_product_list,
    DashboardDataType.room_info: fetch_dashboard_room_info,
}


def _start_time_for(time_range: DashboardTimeRange, now_func: Callable[[], float]) -> int | None:
    """按请求窗口计算趋势图 start_time。"""
    now = int(now_func())
    if time_range == DashboardTimeRange.last_5m:
        return now - 300
    if time_range == DashboardTimeRange.last_30m:
        return now - 1800
    return None


def _upstream_reason(exc: BaseException) -> str:
    """区分上游超时与其他请求错误。"""
    if isinstance(exc, TimeoutError):
        return "upstream_timeout"
    return "upstream_error"


def fetch_dashboard_data(
    req: DashboardDataRequest,
    *,
    now_func: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """查询单个 TikTok 直播大屏接口并包装成上报消息 envelope。"""
    session = None
    try:
        cred, session, _login_result = setup_session(req.collectionId)
        fetcher = DASHBOARD_FETCHERS[req.dataType]
        if req.dataType == DashboardDataType.trend_chart:
            result = fetcher(session, cred, req.roomId, _start_time_for(req.timeRange, now_func))
        else:
            result = fetcher(session, cred, req.roomId)

        message = _format_message(
            result["url"],
            result["request_body"],
            result["response_body"],
            cred.token_data,
            req.collectionId,
        )
        message.pop("cookies", None)
        message["dataSource"] = "live_crawler_tiktok_http"
        message["dataType"] = req.dataType.value
        message["roomId"] = req.roomId
        message["socketUserId"] = req.collectionId
        return {"code": 200, "message": "success", "data": message}
    except LoginRequired as e:
        raise DashboardApiError(5001, "login_required", str(e)) from e
    except FatalError as e:
        raise DashboardApiError(4041, "session_not_found", str(e)) from e
    except DEFAULT_RETRY_EXCEPTIONS as e:
        raise DashboardApiError(5001, _upstream_reason(e), str(e)) from e
    except ValueError as e:
        raise DashboardApiError(5001, "upstream_error", str(e)) from e
    except Exception as e:
        raise DashboardApiError(5099, "internal_error", str(e)) from e
    finally:
        if session is not None:
            session.close()
