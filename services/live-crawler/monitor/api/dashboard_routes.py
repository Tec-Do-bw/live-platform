"""TikTok 直播大屏实时查询 API。"""

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from monitor.api.auth import require_cookie_api_token
from monitor.schemas.dashboard import DashboardDataRequest
from services.dashboard_data import DashboardApiError, fetch_dashboard_data


router = APIRouter(tags=["tiktok-dashboard"])


@router.post("/api/v1/tiktok/dashboard/data")
async def tiktok_dashboard_data(
    req: DashboardDataRequest,
    _: None = Depends(require_cookie_api_token),
):
    """查询 TikTok 直播大屏单项数据。"""
    try:
        return await run_in_threadpool(fetch_dashboard_data, req)
    except DashboardApiError as e:
        message = "上游请求失败" if e.code == 5001 else "API request failed"
        return JSONResponse(
            content={
                "code": e.code,
                "message": message,
                "dataType": req.dataType.value,
                "roomId": req.roomId,
                "error": {"reason": e.reason, "detail": e.detail},
            }
        )
