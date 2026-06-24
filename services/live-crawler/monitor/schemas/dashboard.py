"""TikTok 直播大屏 API 请求模型。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DashboardDataType(StrEnum):
    """直播大屏支持的数据类型。"""

    core_stats = "core_stats"
    trend_chart = "trend_chart"
    source_new = "source_new"
    user_portrait = "user_portrait"
    product_list = "product_list"
    room_info = "room_info"


class DashboardTimeRange(StrEnum):
    """趋势图支持的时间窗口。"""

    full = "full"
    last_5m = "last_5m"
    last_30m = "last_30m"


class DashboardDataRequest(BaseModel):
    """直播大屏单接口查询请求。"""

    dataType: DashboardDataType
    roomId: str = Field(min_length=1)
    collectionId: str = Field(min_length=1)
    timeRange: DashboardTimeRange = DashboardTimeRange.full
