from __future__ import annotations

import httpx

from shared.config import MediaMTXConfig, settings
from shared.logger import get_logger

logger = get_logger(__name__)


class MediaMTXClient:
    """MediaMTX API 客户端。"""

    def __init__(self, config: MediaMTXConfig | None = None, client: httpx.AsyncClient | None = None):
        self.config = config or settings.mediamtx
        self._client = client

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        client = self._client or httpx.AsyncClient(timeout=5)
        should_close = self._client is None
        try:
            response = await client.request(method, f"{self.config.api_base_url}{path}", **kwargs)
            response.raise_for_status()
            return response
        finally:
            if should_close:
                await client.aclose()

    async def add_path(self, room_id: str, rtmp_source: str | None = None) -> dict:
        """添加或更新 MediaMTX path（幂等：先移除再添加）。"""
        # 幂等处理：先尝试移除已存在的 path（避免 400 Bad Request）
        await self.remove_path(room_id)

        payload = {"source": rtmp_source or "publisher"}
        response = await self._request("POST", f"/v3/config/paths/add/{room_id}", json=payload)
        logger.info("MediaMTX path 已添加 | room_id=%s", room_id)
        return response.json() if response.content else {}

    async def remove_path(self, room_id: str) -> None:
        """移除 MediaMTX path（幂等：404 视为成功）。"""
        try:
            await self._request("DELETE", f"/v3/config/paths/delete/{room_id}")
            logger.info("MediaMTX path 已移除 | room_id=%s", room_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.debug("MediaMTX path 不存在，跳过移除 | room_id=%s", room_id)
                return
            raise

    async def list_active_paths(self) -> dict:
        response = await self._request("GET", "/v3/paths/list")
        return response.json()

    async def get_path_info(self, room_id: str) -> dict:
        response = await self._request("GET", f"/v3/paths/get/{room_id}")
        return response.json()
