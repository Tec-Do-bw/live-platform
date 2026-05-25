from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from adapters import get_stream_info
from orchestrator.state_machine import state_manager
from shared.config import settings

# 复用 live-monitor 的翻译层
_LEGACY_DIR = str(Path(__file__).resolve().parents[2] / "live-monitor")
if _LEGACY_DIR not in sys.path:
    sys.path.insert(0, _LEGACY_DIR)

from utils.api_response import (
    classify_tiktok_result,
    classify_shopee_result,
    classify_lazada_result,
    success_response,
    error_response,
    ErrorReason,
)

router = APIRouter()

PLATFORM_CLASSIFIERS = {
    "tiktok": classify_tiktok_result,
    "shopee": classify_shopee_result,
    "lazada": classify_lazada_result,
}


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

    mate_url = request.mateUrl
    if not mate_url:
        return error_response(
            code=4001, reason=ErrorReason.INVALID_PARAM,
            detail="mateUrl 为空", platform=platform, mate_url=""
        )

    raw = await get_stream_info(platform, mate_url)

    classifier = PLATFORM_CLASSIFIERS[platform]
    outcome = classifier(raw, mate_url)

    if outcome.code == 200 or 2000 <= outcome.code < 3000:
        return success_response(outcome.code, outcome.port_info, mate_url)
    return error_response(
        outcome.code, outcome.error_reason, outcome.error_detail,
        platform=platform, mate_url=mate_url
    )


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
