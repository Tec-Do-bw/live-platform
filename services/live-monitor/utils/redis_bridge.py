"""live-monitor 与 live-stream 之间的 Redis 桥接仓储。"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import redis

from utils.serverTool import fetch_apollo_config


COLLECTIONS_KEY = "live:monitor:collections"
CONFIG_KEY_TEMPLATE = "live:collection:{collection_id}:config"
STATUS_KEY_TEMPLATE = "live:collection:{collection_id}:status"
LEASE_KEY_TEMPLATE = "live:collection:{collection_id}:lease"
RECORDING_KEY_TEMPLATE = "live:collection:{collection_id}:recording"
DEFAULT_LIVE_STATUS_TTL_SECONDS = 900
DETECTION_ERROR_CODES = {5001, 5002, 5003, 5099}


def config_key(collection_id: str) -> str:
    return CONFIG_KEY_TEMPLATE.format(collection_id=collection_id)


def status_key(collection_id: str) -> str:
    return STATUS_KEY_TEMPLATE.format(collection_id=collection_id)


def lease_key(collection_id: str) -> str:
    return LEASE_KEY_TEMPLATE.format(collection_id=collection_id)


def recording_key(collection_id: str) -> str:
    return RECORDING_KEY_TEMPLATE.format(collection_id=collection_id)


def infer_platform(room_url: str) -> str:
    normalized = (room_url or "").lower()
    if "tiktok" in normalized:
        return "tiktok"
    if "shp" in normalized or "shopee" in normalized:
        return "shopee"
    if "lazada" in normalized:
        return "lazada"
    return "unknown"


def normalize_seed_row(row: Any) -> dict[str, str]:
    """兼容新旧 SQL 结果，统一成 Redis config 入参。"""
    if isinstance(row, dict):
        legacy_room_id = _decode(row.get("room_id"))
        room_url = _decode(row.get("room_url"))
        allocation_status = _decode(row.get("allocation_status", "0") or "0")
        raw_collection_id = _decode(row.get("collection_id"))
        raw_platform = _decode(row.get("platform"))
    else:
        legacy_room_id = _decode(row[0]) if len(row) > 0 else ""
        room_url = _decode(row[1]) if len(row) > 1 else ""
        allocation_status = _decode(row[2]) if len(row) > 2 else "0"
        raw_collection_id = _decode(row[3]) if len(row) > 3 else ""
        raw_platform = _decode(row[4]) if len(row) > 4 else ""

    collection_id = raw_collection_id or legacy_room_id
    platform = raw_platform.lower() if raw_platform else infer_platform(room_url)
    return {
        "collection_id": collection_id,
        "legacy_room_id": legacy_room_id,
        "room_id": legacy_room_id,
        "room_url": room_url,
        "allocation_status": allocation_status,
        "platform": platform,
    }


def _decode(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _decode_hash(raw: dict[Any, Any]) -> dict[str, str]:
    return {_decode(key): _decode(value) for key, value in raw.items()}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_array(value: Any) -> str:
    if value is None or value == "":
        return "[]"
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return _json_dumps([value])
        return _json_dumps(loaded if isinstance(loaded, list) else [loaded])
    if isinstance(value, list):
        return _json_dumps(value)
    return _json_dumps([value])


def _outcome_attr(outcome: Any, name: str, default: Any = None) -> Any:
    if outcome is None:
        return default
    if isinstance(outcome, dict):
        return outcome.get(name, default)
    return getattr(outcome, name, default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _status_for_code(code: int, is_live: bool) -> str:
    if is_live:
        return "live"
    if code in {2001, 2002}:
        return "offline"
    if code in {5001, 5003}:
        return "upstream_error"
    if code in {4041, 4042, 5002}:
        return "parse_error"
    return "internal_error"


def _is_detection_error_code(code: int) -> bool:
    return code in DETECTION_ERROR_CODES


def build_status_payload(
    *,
    collection_id: str,
    platform: str,
    room_url: str,
    outcome: Any,
    port_info: dict[str, Any] | None,
    source_node: str,
    now: int | None = None,
    ttl_seconds: int = DEFAULT_LIVE_STATUS_TTL_SECONDS,
) -> dict[str, str]:
    """根据 API 翻译结果构造 Redis status hash。"""
    info = port_info or _outcome_attr(outcome, "port_info", None) or {}
    code = int(_outcome_attr(outcome, "code", 5099) or 5099)
    flv_url = _decode(info.get("flv_url") or info.get("flvUrl") or "")
    room_id = _decode(info.get("roomId") or info.get("room_id") or "")
    current_time = int(now if now is not None else time.time())
    is_live = code == 200 and bool(flv_url) and flv_url != "error"
    status = _status_for_code(code, is_live)
    error_reason = _decode(_outcome_attr(outcome, "error_reason", "") or "")
    error_message = _decode(_outcome_attr(outcome, "error_detail", "") or "")
    play_urls = info.get("play_urls") or info.get("playUrls")
    is_detection_error = _is_detection_error_code(code)

    return {
        "collectionId": collection_id,
        "collection_id": collection_id,
        "isLive": "1" if is_live else "0",
        "roomId": room_id,
        "room_id": room_id,
        "flvUrl": flv_url if is_live else "",
        "flv_url": flv_url if is_live else "",
        "playUrls": _json_array(play_urls),
        "platform": platform,
        "roomUrl": room_url,
        "room_url": room_url,
        "status": status,
        "code": str(code),
        "errorReason": error_reason,
        "error_reason": error_reason,
        "errorMessage": error_message,
        "error_message": error_message,
        "updatedAt": str(current_time),
        "expiresAt": "0" if is_detection_error else str(current_time + int(ttl_seconds)),
        "sourceNode": source_node,
        "metadata": _json_dumps(info),
        "lastDetectCode": str(code),
        "lastDetectReason": error_reason,
        "lastDetectMessage": error_message,
        "lastDetectAt": str(current_time),
        "detectFailCount": "1" if is_detection_error else "0",
    }


def build_detection_error_payload(
    *,
    collection_id: str,
    platform: str,
    room_url: str,
    outcome: Any,
    port_info: dict[str, Any] | None,
    source_node: str,
    existing_status: dict[str, str],
    now: int | None = None,
) -> dict[str, str]:
    """构造检测异常写入字段；有旧状态时不刷新旧直播地址有效期。"""
    info = port_info or _outcome_attr(outcome, "port_info", None) or {}
    code = int(_outcome_attr(outcome, "code", 5099) or 5099)
    current_time = int(now if now is not None else time.time())
    error_reason = _decode(_outcome_attr(outcome, "error_reason", "") or "")
    error_message = _decode(_outcome_attr(outcome, "error_detail", "") or "")
    fail_count = _safe_int(existing_status.get("detectFailCount"), 0) + 1

    payload = {
        "lastDetectCode": str(code),
        "lastDetectReason": error_reason,
        "lastDetectMessage": error_message,
        "lastDetectAt": str(current_time),
        "detectFailCount": str(fail_count),
    }

    if existing_status:
        return payload

    payload.update(
        {
            "collectionId": collection_id,
            "collection_id": collection_id,
            "isLive": "0",
            "roomId": "",
            "room_id": "",
            "flvUrl": "",
            "flv_url": "",
            "playUrls": "[]",
            "platform": platform,
            "roomUrl": room_url,
            "room_url": room_url,
            "status": _status_for_code(code, False),
            "code": str(code),
            "errorReason": error_reason,
            "error_reason": error_reason,
            "errorMessage": error_message,
            "error_message": error_message,
            "updatedAt": str(current_time),
            "expiresAt": "0",
            "sourceNode": source_node,
            "metadata": _json_dumps(info),
        }
    )
    return payload


def _status_to_batch_item(collection_id: str, raw: dict[str, str], now: int) -> dict[str, Any]:
    is_live = raw.get("isLive") == "1"
    flv_url = raw.get("flvUrl") or raw.get("flv_url") or ""
    try:
        expires_at = int(raw.get("expiresAt") or "0")
    except ValueError:
        expires_at = 0
    if not is_live or not flv_url or flv_url == "error" or expires_at <= now:
        return {"collectionId": collection_id, "isLive": False, "roomId": "", "flvUrl": ""}
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
    """Redis 房间配置与直播状态仓储。"""

    def __init__(
        self,
        redis_client: Any | None = None,
        *,
        status_ttl_seconds: int | None = None,
    ):
        self.redis = redis_client or self._create_default_client()
        self.status_ttl_seconds = int(
            status_ttl_seconds
            or os.environ.get("LIVE_STATUS_TTL_SECONDS", DEFAULT_LIVE_STATUS_TTL_SECONDS)
        )

    @staticmethod
    def _create_default_client() -> redis.Redis:
        cfg = fetch_apollo_config(int(os.environ.get("ISTEST", "1")))
        return redis.Redis(
            host=cfg.get("redisHost"),
            port=int(cfg.get("redisPort")),
            password=cfg.get("redisPassword"),
            db=int(cfg.get("redisDb")),
            decode_responses=True,
        )

    def upsert_config(
        self,
        *,
        collection_id: str,
        room_url: str,
        platform: str,
        legacy_room_id: str = "",
        enabled: bool = True,
        source_node: str = "",
        now: int | None = None,
    ) -> None:
        current_time = int(now if now is not None else time.time())
        mapping = {
            "collectionId": collection_id,
            "collection_id": collection_id,
            "legacyRoomId": legacy_room_id,
            "room_id": legacy_room_id,
            "platform": platform,
            "roomUrl": room_url,
            "room_url": room_url,
            "enabled": "1" if enabled else "0",
            "updatedAt": str(current_time),
            "sourceNode": source_node,
        }
        self.redis.sadd(COLLECTIONS_KEY, collection_id)
        self.redis.hset(config_key(collection_id), mapping=mapping)

    def write_status(
        self,
        *,
        collection_id: str,
        platform: str,
        room_url: str,
        outcome: Any,
        port_info: dict[str, Any] | None,
        source_node: str,
        now: int | None = None,
        ttl_seconds: int | None = None,
    ) -> dict[str, str]:
        ttl = int(ttl_seconds or self.status_ttl_seconds)
        code = int(_outcome_attr(outcome, "code", 5099) or 5099)
        key = status_key(collection_id)

        if _is_detection_error_code(code):
            existing_status = _decode_hash(self.redis.hgetall(key))
            payload = build_detection_error_payload(
                collection_id=collection_id,
                platform=platform,
                room_url=room_url,
                outcome=outcome,
                port_info=port_info,
                source_node=source_node,
                existing_status=existing_status,
                now=now,
            )
            self.redis.hset(key, mapping=payload)
            if not existing_status:
                self.redis.expire(key, ttl)
            merged = dict(existing_status)
            merged.update(payload)
            return merged

        payload = build_status_payload(
            collection_id=collection_id,
            platform=platform,
            room_url=room_url,
            outcome=outcome,
            port_info=port_info,
            source_node=source_node,
            now=now,
            ttl_seconds=ttl,
        )
        self.redis.hset(key, mapping=payload)
        self.redis.expire(key, ttl)
        return payload

    def list_live_status(self, collection_ids: list[str], *, now: int | None = None) -> list[dict[str, Any]]:
        current_time = int(now if now is not None else time.time())
        rows = []
        for collection_id in collection_ids:
            config = _decode_hash(self.redis.hgetall(config_key(collection_id)))
            if not _is_config_enabled(config):
                rows.append({"collectionId": collection_id, "isLive": False, "roomId": "", "flvUrl": ""})
                continue
            raw = _decode_hash(self.redis.hgetall(status_key(collection_id)))
            if not raw:
                rows.append({"collectionId": collection_id, "isLive": False, "roomId": "", "flvUrl": ""})
                continue
            rows.append(_status_to_batch_item(collection_id, raw, current_time))
        return rows
