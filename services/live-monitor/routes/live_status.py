from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from utils.redis_bridge import LiveRedisRepository


router = APIRouter(tags=["live-status"])
_repository = None


def get_repository():
    global _repository
    if _repository is None:
        _repository = LiveRedisRepository()
    return _repository


@router.post("/api/v1/tiktok/live-status/batch")
async def batch_live_status(request: Request):
    body = await request.json()
    collection_ids = body.get("collectionIds") or []

    try:
        repo = get_repository()
        data = repo.list_live_status([str(collection_id) for collection_id in collection_ids])
    except Exception as e:
        return JSONResponse(content={"code": 5099, "message": f"Redis unavailable: {e}", "data": None})

    return JSONResponse(content={"code": 200, "message": "success", "data": data})
