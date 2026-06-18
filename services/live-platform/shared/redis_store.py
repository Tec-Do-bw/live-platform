from __future__ import annotations

import inspect
import json
from collections.abc import Iterable
from time import time
from typing import Any

from shared.models import MonitoredRoom, RoomState, Status
from shared.config import settings

COLLECTIONS_KEY = "live:monitor:collections"
CONFIG_KEY_TEMPLATE = "live:collection:{collection_id}:config"
STATUS_KEY_TEMPLATE = "live:collection:{collection_id}:status"


def config_key(collection_id: str) -> str:
    return CONFIG_KEY_TEMPLATE.format(collection_id=collection_id)


def status_key(collection_id: str) -> str:
    return STATUS_KEY_TEMPLATE.format(collection_id=collection_id)


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _decode_hash(raw: dict[Any, Any]) -> dict[str, str]:
    return {_decode(key): _decode(value) for key, value in raw.items()}


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _is_enabled(raw: dict[str, str]) -> bool:
    return raw.get("enabled", "1").lower() not in {"0", "false", "no", "off"}


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


class RedisRoomRepository:
    """Redis 房间配置与状态仓储。"""

    def __init__(self, redis_client: Any | None = None):
        self.redis = redis_client or self._create_default_client()

    @staticmethod
    def _create_default_client() -> Any:
        try:
            from redis import asyncio as redis_asyncio
        except ImportError as exc:
            raise RuntimeError("缺少 redis 依赖，请安装 redis 或注入 redis_client") from exc
        config = settings.redis
        return redis_asyncio.Redis(
            host=config.host,
            port=config.port,
            password=config.password,
            db=config.db,
            decode_responses=True,
        )

    async def list_collection_ids(self) -> list[str]:
        raw_ids = await _maybe_await(self.redis.smembers(COLLECTIONS_KEY))
        return sorted(_decode(collection_id) for collection_id in raw_ids)

    async def list_monitored_rooms(self) -> list[MonitoredRoom]:
        return await self.get_monitored_rooms(await self.list_collection_ids())

    async def get_monitored_rooms(self, collection_ids: Iterable[str]) -> list[MonitoredRoom]:
        """按 collection_ids 输入顺序返回存在且启用的房间配置。"""
        rooms: list[MonitoredRoom] = []
        for collection_id in collection_ids:
            raw = _decode_hash(await _maybe_await(self.redis.hgetall(config_key(str(collection_id)))))
            if not raw or not _is_enabled(raw):
                continue
            platform = raw.get("platform", "").lower()
            room_url = raw.get("room_url") or raw.get("roomUrl") or ""
            if not platform or not room_url:
                continue
            rooms.append(
                MonitoredRoom(
                    collection_id=str(raw.get("collection_id") or raw.get("collectionId") or collection_id),
                    platform=platform,
                    room_url=room_url,
                )
            )
        return rooms

    async def upsert_monitored_room(self, room: MonitoredRoom) -> None:
        await _maybe_await(self.redis.sadd(COLLECTIONS_KEY, room.collection_id))
        await _maybe_await(
            self.redis.hset(
                config_key(room.collection_id),
                mapping={
                    "collection_id": room.collection_id,
                    "collectionId": room.collection_id,
                    "platform": room.platform,
                    "room_url": room.room_url,
                    "roomUrl": room.room_url,
                    "enabled": "1",
                },
            )
        )

    async def write_status(
        self,
        room: MonitoredRoom,
        *,
        stream_info: dict[str, Any] | None,
        state: RoomState,
        is_live: bool,
        recording_started: bool,
    ) -> dict[str, str]:
        payload = build_status_payload(
            room,
            stream_info=stream_info,
            state=state,
            is_live=is_live,
            recording_started=recording_started,
        )
        await _maybe_await(self.redis.hset(status_key(room.collection_id), mapping=payload))
        return payload

    async def save_room_status(
        self,
        room: MonitoredRoom,
        *,
        stream_info: dict[str, Any] | None = None,
        state: RoomState | None = None,
        error_message: str = "",
    ) -> dict[str, str]:
        """兼容旧调用名，直接按 stream_info/state 推导状态。"""
        if state is None:
            state = RoomState(
                collection_id=room.collection_id,
                platform=room.platform,
                room_url=room.room_url,
                error_message=error_message,
            )
        flv_url = (stream_info or {}).get("flv_url")
        is_live = bool(flv_url) and flv_url != "error"
        return await self.write_status(
            room,
            stream_info=stream_info,
            state=state,
            is_live=is_live,
            recording_started=False,
        )

    async def get_statuses(self, collection_ids: Iterable[str]) -> list[dict[str, Any] | None]:
        """按 collection_ids 输入顺序返回状态；不存在的位置返回 None。"""
        result: list[dict[str, Any] | None] = []
        for collection_id in collection_ids:
            raw = _decode_hash(await _maybe_await(self.redis.hgetall(status_key(str(collection_id)))))
            result.append(parse_status_payload(raw) if raw else None)
        return result

    async def list_live_status(self, collection_ids: Iterable[str]) -> list[dict[str, Any]]:
        """兼容下游读法，按 collection_ids 输入顺序返回直播状态。"""
        statuses = await self.get_statuses(collection_ids)
        result: list[dict[str, Any]] = []
        for collection_id, status in zip(collection_ids, statuses, strict=False):
            is_live = bool(status and status["isLive"])
            result.append(
                {
                    "collectionId": str(collection_id),
                    "isLive": is_live,
                    "roomId": str(status["roomId"]) if is_live and status else "",
                    "flvUrl": str(status["flvUrl"]) if is_live and status else "",
                }
            )
        return result


def build_status_payload(
    room: MonitoredRoom,
    *,
    stream_info: dict[str, Any] | None,
    state: RoomState,
    is_live: bool,
    recording_started: bool,
) -> dict[str, str]:
    info = stream_info or {}
    flv_url = str(info.get("flv_url") or "")
    live_room_id = str(info.get("roomId") or info.get("room_id") or state.live_room_id or "")
    now = str(int(time()))
    return {
        "collectionId": room.collection_id,
        "collection_id": room.collection_id,
        "isLive": "1" if is_live else "0",
        "roomId": live_room_id,
        "room_id": live_room_id,
        "flvUrl": flv_url if is_live else "",
        "flv_url": flv_url if is_live else "",
        "platform": room.platform,
        "roomUrl": room.room_url,
        "room_url": room.room_url,
        "status": state.status.value if isinstance(state.status, Status) else str(state.status),
        "mediamtxPath": state.mediamtx_path or "",
        "mediamtx_path": state.mediamtx_path or "",
        "recordingStarted": "1" if recording_started else "0",
        "recording_started": "1" if recording_started else "0",
        "updatedAt": now,
        "lastLiveStart": str(int(state.started_at)) if is_live and state.started_at else "",
        "lastLiveEnd": "" if is_live else now,
        "errorMessage": state.error_message,
        "error_message": state.error_message,
        "metadata": _json_dumps(info),
    }


def parse_status_payload(raw: dict[str, str]) -> dict[str, Any]:
    return {
        "collectionId": raw.get("collectionId") or raw.get("collection_id") or "",
        "isLive": raw.get("isLive") == "1",
        "roomId": raw.get("roomId") or raw.get("room_id") or "",
        "flvUrl": raw.get("flvUrl") or raw.get("flv_url") or "",
        "platform": raw.get("platform") or "",
        "roomUrl": raw.get("roomUrl") or raw.get("room_url") or "",
        "status": raw.get("status") or "",
        "mediamtxPath": raw.get("mediamtxPath") or raw.get("mediamtx_path") or "",
        "recordingStarted": raw.get("recordingStarted") == "1" or raw.get("recording_started") == "1",
        "updatedAt": raw.get("updatedAt") or "",
        "lastLiveStart": raw.get("lastLiveStart") or "",
        "lastLiveEnd": raw.get("lastLiveEnd") or "",
        "errorMessage": raw.get("errorMessage") or raw.get("error_message") or "",
        "metadata": _json_loads(raw.get("metadata")),
    }


class RedisStore(RedisRoomRepository):
    """兼容旧命名。"""


class RoomRepository(RedisRoomRepository):
    """兼容旧 scheduler 注入名。"""
