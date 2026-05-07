from __future__ import annotations

from adapters.legacy import run_legacy_call


async def get_shopee_stream_info(room_url: str) -> dict | None:
    """获取 Shopee 直播流信息。"""
    return await run_legacy_call("shopee", "get_shopee_live_info", room_url)
