from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from adapters import get_stream_info
from orchestrator.state_machine import state_manager
from shared.config import settings

router = APIRouter()


class LiveRoomRequest(BaseModel):
    mateUrl: str


def _unauthorized(access_token: Optional[str]) -> Optional[dict]:
    if access_token != settings.server.access_token:
        return {"code": 401, "message": "Unauthorized"}
    return None


async def _platform_response(platform: str, request: LiveRoomRequest, access_token: Optional[str]) -> dict:
    auth_error = _unauthorized(access_token)
    if auth_error:
        return auth_error
    info = await get_stream_info(platform, request.mateUrl)
    if info is None:
        info = {"flv_url": "error", "roomId": "", "message": f"{platform}采集异常", "filePath": ""}
    return {"code": 200, "message": "success", "data": {"port_info": info, "mateUrl": request.mateUrl}}


@router.get("/health")
async def health() -> dict:
    return {
        "code": 200,
        "message": "live-platform is running",
        "rooms": {room_id: state.status.value for room_id, state in state_manager.snapshot().items()},
    }


@router.post("/liveRoom/portInfo")
async def tiktok_info(request: LiveRoomRequest, access_token: Optional[str] = Header(default=None)) -> dict:
    return await _platform_response("tiktok", request, access_token)


@router.post("/liveRoom/shopeeInfo")
async def shopee_info(request: LiveRoomRequest, access_token: Optional[str] = Header(default=None)) -> dict:
    return await _platform_response("shopee", request, access_token)


@router.post("/liveRoom/lazadaInfo")
async def lazada_info(request: LiveRoomRequest, access_token: Optional[str] = Header(default=None)) -> dict:
    return await _platform_response("lazada", request, access_token)


@router.get("/docs/doc", response_class=HTMLResponse)
async def docs_doc() -> str:
    return "<html><body><h1>live-platform API</h1></body></html>"


@router.get("/docs/getConfig")
async def docs_config() -> dict:
    return {
        "code": 200,
        "data": {
            "health": "/health",
            "tiktok": "/liveRoom/portInfo",
            "shopee": "/liveRoom/shopeeInfo",
            "lazada": "/liveRoom/lazadaInfo",
        },
    }
