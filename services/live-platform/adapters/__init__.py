from __future__ import annotations

from adapters.lazada import get_lazada_stream_info
from adapters.shopee import get_shopee_stream_info
from adapters.tiktok import get_tiktok_stream_info


async def get_stream_info(platform: str, room_url: str) -> dict | None:
    """按平台获取直播间信息。"""
    normalized = platform.lower()
    if normalized == "tiktok":
        return await get_tiktok_stream_info(room_url)
    if normalized == "shopee":
        return await get_shopee_stream_info(room_url)
    if normalized == "lazada":
        return await get_lazada_stream_info(room_url)
    raise ValueError(f"不支持的平台: {platform}")


async def get_stream_url(platform: str, room_url: str) -> str | None:
    info = await get_stream_info(platform, room_url)
    if not info:
        return None
    flv_url = info.get("flv_url")
    if not flv_url or flv_url == "error":
        return None
    return str(flv_url)
