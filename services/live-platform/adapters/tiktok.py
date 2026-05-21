from __future__ import annotations

from adapters.legacy import run_legacy_call


async def get_tiktok_stream_info(room_url: str) -> dict | None:
    """获取 TikTok 直播流信息。"""
    return await run_legacy_call("tiktok", "getLiveStreamInfo_requests", room_url)
