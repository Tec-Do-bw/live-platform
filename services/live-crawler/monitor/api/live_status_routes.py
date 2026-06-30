"""TikTok 批量开播状态 API。"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from monitor.api.auth import API_TOKEN, require_cookie_api_token
from utils.redis_bridge import LiveRedisRepository


router = APIRouter(tags=["live-status"])
_repository = None


class BatchLiveStatusRequest(BaseModel):
    collectionIds: list[object] = Field(default_factory=list)


def get_repository() -> LiveRedisRepository:
    global _repository
    if _repository is None:
        _repository = LiveRedisRepository()
    return _repository


@router.post("/api/v1/tiktok/live-status/batch")
def batch_live_status(req: BatchLiveStatusRequest, _: None = Depends(require_cookie_api_token)):
    collection_ids = [str(collection_id) for collection_id in req.collectionIds]

    try:
        data = get_repository().list_live_status(collection_ids)
    except Exception as e:
        return JSONResponse(content={"code": 5099, "message": f"Redis unavailable: {e}", "data": None})

    return JSONResponse(content={"code": 200, "message": "success", "data": data})
