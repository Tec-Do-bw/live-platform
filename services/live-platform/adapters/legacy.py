from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from shared.logger import get_logger

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
LEGACY_MONITOR_DIR = ROOT_DIR / "live-monitor"


def _ensure_legacy_path() -> None:
    legacy_path = str(LEGACY_MONITOR_DIR)
    if legacy_path not in sys.path:
        sys.path.insert(0, legacy_path)


async def run_legacy_call(factory: str, method: str, room_url: str, *args: Any) -> dict | None:
    """在线程中调用旧 live-monitor 取流逻辑。"""
    return await asyncio.to_thread(_run_legacy_call_sync, factory, method, room_url, *args)


def _run_legacy_call_sync(factory: str, method: str, room_url: str, *args: Any) -> dict | None:
    _ensure_legacy_path()
    try:
        if factory == "tiktok":
            from utils.TiktokTool import TiktokTool

            tool = TiktokTool()
            cookie_list = tool.get_cookie_list()
            return tool.getLiveStreamInfo_requests(room_url, cookie_list, None)
        if factory == "shopee":
            from utils.ShopeeTool import ShopeeTool

            return ShopeeTool().get_shopee_live_info(room_url, proxy=False)
        if factory == "lazada":
            from utils.LazadaTool import LazadaTool

            return LazadaTool().get_lazada_live_info(room_url, proxy=False)
    except Exception as exc:
        logger.warning("旧取流适配调用失败 | platform=%s url=%s error=%s", factory, room_url, exc)
        return None
    return None
