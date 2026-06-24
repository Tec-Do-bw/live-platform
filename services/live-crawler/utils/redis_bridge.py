"""读取 live-monitor 写入的 Redis 直播状态。"""

from __future__ import annotations

import os
import time
from typing import Any

import redis

from core.apollo import APOLLO


COLLECTIONS_KEY = "live:monitor:collections"
CONFIG_KEY_TEMPLATE = "live:collection:{collection_id}:config"
STATUS_KEY_TEMPLATE = "live:collection:{collection_id}:status"
DEFAULT_LIVE_STATUS_TTL_SECONDS = 900


def config_key(collection_id: str) -> str:
    return CONFIG_KEY_TEMPLATE.format(collection_id=collection_id)


def status_key(collection_id: str) -> str:
    return STATUS_KEY_TEMPLATE.format(collection_id=collection_id)


def _redis_config() -> dict[str, str]:
    return {
        "redisHost": APOLLO.get_value("redisHost", ""),
        "redisPort": APOLLO.get_value("redisPort", "6379"),
        "redisPassword": APOLLO.get_value("redisPassword", ""),
        "redisDb": APOLLO.get_value("redisDb", "0"),
    }


def _decode(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _decode_hash(raw: dict[Any, Any]) -> dict[str, str]:
    return {_decode(key): _decode(value) for key, value in raw.items()}


def _offline_row(collection_id: str) -> dict[str, Any]:
    return {"collectionId": collection_id, "isLive": False, "roomId": "", "flvUrl": ""}


def _status_to_batch_item(collection_id: str, raw: dict[str, str], now: int) -> dict[str, Any]:
    is_live = raw.get("isLive") == "1"
    flv_url = raw.get("flvUrl") or raw.get("flv_url") or ""
    try:
        expires_at = int(raw.get("expiresAt") or "0")
    except ValueError:
        expires_at = 0
    if not is_live or not flv_url or flv_url == "error" or expires_at <= now:
        return _offline_row(collection_id)
    return {
        "collectionId": collection_id,
        "isLive": True,
        "roomId": raw.get("roomId") or raw.get("room_id") or "",
        "flvUrl": flv_url,
    }


def _is_config_enabled(raw: dict[str, str]) -> bool:
    if not raw:
        return True
    return raw.get("enabled", "1").lower() not in {"0", "false", "no", "off"}


class LiveRedisRepository:
    """Redis 直播状态只读仓储。"""

    def __init__(
        self,
        redis_client: object | None = None,
        *,
        status_ttl_seconds: int | None = None,
    ):
        self.redis = redis_client or self._create_default_client()
        self.status_ttl_seconds = int(
            status_ttl_seconds or os.environ.get("LIVE_STATUS_TTL_SECONDS", DEFAULT_LIVE_STATUS_TTL_SECONDS)
        )

    @staticmethod
    def _create_default_client() -> redis.Redis:
        cfg = _redis_config()
        return redis.Redis(
            host=cfg.get("redisHost"),
            port=int(cfg.get("redisPort") or 6379),
            password=cfg.get("redisPassword") or None,
            db=int(cfg.get("redisDb") or 0),
            decode_responses=True,
        )

    def list_live_status(self, collection_ids: list[str], *, now: int | None = None) -> list[dict[str, object]]:
        current_time = int(now if now is not None else time.time())
        rows = []
        for collection_id in collection_ids:
            config = _decode_hash(self.redis.hgetall(config_key(collection_id)))
            if not _is_config_enabled(config):
                rows.append(_offline_row(collection_id))
                continue
            raw = _decode_hash(self.redis.hgetall(status_key(collection_id)))
            if not raw:
                rows.append(_offline_row(collection_id))
                continue
            rows.append(_status_to_batch_item(collection_id, raw, current_time))
        return rows
