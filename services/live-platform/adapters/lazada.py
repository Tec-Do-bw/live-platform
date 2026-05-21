from __future__ import annotations

from adapters.legacy import run_legacy_call


async def get_lazada_stream_info(room_url: str) -> dict | None:
    """获取 Lazada 直播流信息。"""
    return await run_legacy_call("lazada", "get_lazada_live_info", room_url)
