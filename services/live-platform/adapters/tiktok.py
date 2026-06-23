from __future__ import annotations

from datetime import datetime

from adapters.legacy import run_legacy_call


async def get_tiktok_stream_info(room_url: str) -> dict | None:
    """获取 TikTok 直播流信息。"""
    info = await run_legacy_call("tiktok", "getLiveStreamInfo_requests", room_url)
    if not info:
        return info

    normalized = dict(info)
    room_id = str(normalized.get("roomID") or normalized.get("roomId") or normalized.get("room_id") or "")
    room_name = str(normalized.get("roomName") or normalized.get("nickname") or normalized.get("title") or "")
    user_id = str(normalized.get("UserID") or normalized.get("id") or normalized.get("uniqueId") or normalized.get("secUid") or "")

    if not normalized.get("roomID"):
        normalized["roomID"] = room_id
    if not normalized.get("roomId"):
        normalized["roomId"] = room_id
    if not normalized.get("roomName"):
        normalized["roomName"] = room_name
    if not normalized.get("UserID"):
        normalized["UserID"] = user_id
    if not normalized.get("batchID"):
        normalized["batchID"] = str(normalized.get("batch_id") or "")
    if not normalized.get("createTime"):
        normalized["createTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return normalized
