from __future__ import annotations

from datetime import datetime

from adapters.legacy import run_legacy_call


async def get_shopee_stream_info(room_url: str) -> dict | None:
    """获取 Shopee 直播流信息。"""
    info = await run_legacy_call("shopee", "get_shopee_live_info", room_url)
    if not info:
        return info

    normalized = dict(info)
    session = normalized.get("session") if isinstance(normalized.get("session"), dict) else {}
    if not normalized.get("shop_id"):
        normalized["shop_id"] = str(session.get("shop_id") or session.get("uid") or "")
    if not normalized.get("nickname"):
        normalized["nickname"] = str(session.get("nickname") or session.get("username") or "")
    if not normalized.get("member_cnt"):
        normalized["member_cnt"] = normalized.get("memberCount") or ""
    if not normalized.get("like_cnt"):
        normalized["like_cnt"] = normalized.get("likeCount") or ""
    if not normalized.get("session_id"):
        normalized["session_id"] = str(session.get("session_id") or session.get("sessionId") or normalized.get("sessionId") or "")
    if not normalized.get("createTime"):
        normalized["createTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return normalized
