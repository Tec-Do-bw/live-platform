from __future__ import annotations

import os
import json
import time
from typing import Any

import redis
import requests


COLLECTIONS_KEY = "live:monitor:collections"
STATUS_KEY_TEMPLATE = "live:collection:{collection_id}:status"
LEASE_KEY_TEMPLATE = "live:collection:{collection_id}:lease"
RECORDING_KEY_TEMPLATE = "live:collection:{collection_id}:recording"
CONFIG_KEY_TEMPLATE = "live:collection:{collection_id}:config"
DEFAULT_STREAM_LEASE_TTL_SECONDS = 360

RENEW_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("EXPIRE", KEYS[1], tonumber(ARGV[2]))
end
return 0
"""

RELEASE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
end
return 0
"""


def status_key(collection_id: str) -> str:
    return STATUS_KEY_TEMPLATE.format(collection_id=collection_id)


def config_key(collection_id: str) -> str:
    return CONFIG_KEY_TEMPLATE.format(collection_id=collection_id)


def lease_key(collection_id: str) -> str:
    return LEASE_KEY_TEMPLATE.format(collection_id=collection_id)


def recording_key(collection_id: str) -> str:
    return RECORDING_KEY_TEMPLATE.format(collection_id=collection_id)


def _decode(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _decode_hash(raw: dict[Any, Any]) -> dict[str, str]:
    return {_decode(key): _decode(value) for key, value in raw.items()}


def _json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _is_config_enabled(raw: dict[str, str]) -> bool:
    if not raw:
        return True
    return raw.get("enabled", "1").lower() not in {"0", "false", "no", "off"}


def _fetch_apollo_config(istest: int = 0) -> dict:
    apollo_url = str(os.environ.get("APOLLO_URL", "")).strip()
    apollo_id = "live-spider"

    if "develop" in apollo_url:
        istest = 1
    if istest != 1 and os.name == "nt":
        apollo_url = "http://10.225.17.67:30080"

    env_name = "dev01" if istest == 1 else "PRO"
    url = f"{apollo_url}/configs/{apollo_id}/{env_name}/application"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json().get("configurations", {})
    except Exception:
        return {}


def _redis_config_from_env_or_apollo() -> dict:
    host = os.environ.get("REDIS_HOST") or os.environ.get("redisHost")
    port = os.environ.get("REDIS_PORT") or os.environ.get("redisPort")
    password = os.environ.get("REDIS_PASSWORD") or os.environ.get("redisPassword")
    db = os.environ.get("REDIS_DB") or os.environ.get("redisDb")
    if not host or not port or db is None:
        cfg = _fetch_apollo_config(int(os.environ.get("ISTEST", "1")))
        host = host or cfg.get("redisHost")
        port = port or cfg.get("redisPort")
        password = password or cfg.get("redisPassword")
        db = db if db is not None else cfg.get("redisDb")
    return {"host": host, "port": int(port), "password": password, "db": int(db)}


class RedisRoomSource:
    def __init__(self, redis_client: Any | None = None):
        self.redis = redis_client or self._create_default_client()
        self.lease_ttl_seconds = int(
            os.environ.get("STREAM_LEASE_TTL_SECONDS", DEFAULT_STREAM_LEASE_TTL_SECONDS)
        )

    @staticmethod
    def _create_default_client() -> redis.Redis:
        cfg = _redis_config_from_env_or_apollo()
        return redis.Redis(
            host=cfg["host"],
            port=cfg["port"],
            password=cfg["password"],
            db=cfg["db"],
            decode_responses=True,
        )

    def list_live_candidates(self, limit: int, *, now: int | None = None) -> list[dict[str, str]]:
        current_time = int(now if now is not None else time.time())
        candidates = []
        collection_ids = sorted(_decode(value) for value in self.redis.smembers(COLLECTIONS_KEY))
        for collection_id in collection_ids:
            if not self._is_enabled_collection(collection_id):
                continue
            raw = _decode_hash(self.redis.hgetall(status_key(collection_id)))
            if not self._is_fresh_live_status(raw, current_time):
                continue
            candidates.append(
                {
                    "collectionId": collection_id,
                    "roomId": raw.get("roomId") or raw.get("room_id") or "",
                    "flvUrl": raw.get("flvUrl") or raw.get("flv_url") or "",
                    "platform": raw.get("platform") or "",
                    "roomUrl": raw.get("roomUrl") or raw.get("room_url") or "",
                }
            )
            if len(candidates) >= limit:
                break
        return candidates

    def get_status(self, collection_id: str, *, now: int | None = None) -> dict[str, str] | None:
        current_time = int(now if now is not None else time.time())
        if not self._is_enabled_collection(collection_id):
            return None
        raw = _decode_hash(self.redis.hgetall(status_key(collection_id)))
        if not self._is_fresh_live_status(raw, current_time):
            return None
        return {
            "collectionId": collection_id,
            "roomId": raw.get("roomId") or raw.get("room_id") or "",
            "flvUrl": raw.get("flvUrl") or raw.get("flv_url") or "",
            "platform": raw.get("platform") or "",
            "roomUrl": raw.get("roomUrl") or raw.get("room_url") or "",
            "metadata": _json_loads(raw.get("metadata")),
        }

    def claim(self, collection_id: str, worker_id: str, ttl_seconds: int | None = None) -> bool:
        ttl = int(ttl_seconds or self.lease_ttl_seconds)
        return bool(self.redis.set(lease_key(collection_id), worker_id, nx=True, ex=ttl))

    def renew(self, collection_id: str, worker_id: str, ttl_seconds: int | None = None) -> bool:
        ttl = int(ttl_seconds or self.lease_ttl_seconds)
        return bool(self.redis.eval(RENEW_SCRIPT, 1, lease_key(collection_id), worker_id, ttl))

    def release(self, collection_id: str, worker_id: str) -> bool:
        return bool(self.redis.eval(RELEASE_SCRIPT, 1, lease_key(collection_id), worker_id))

    def write_recording_status(self, collection_id: str, mapping: dict, ttl_seconds: int | None = None) -> None:
        ttl = int(ttl_seconds or self.lease_ttl_seconds)
        key = recording_key(collection_id)
        self.redis.hset(key, mapping={str(k): str(v) for k, v in mapping.items()})
        self.redis.expire(key, ttl)

    @staticmethod
    def _is_fresh_live_status(raw: dict[str, str], now: int) -> bool:
        if not raw:
            return False
        flv_url = raw.get("flvUrl") or raw.get("flv_url") or ""
        try:
            expires_at = int(raw.get("expiresAt") or "0")
        except ValueError:
            expires_at = 0
        return raw.get("isLive") == "1" and bool(flv_url) and flv_url != "error" and expires_at > now

    def _is_enabled_collection(self, collection_id: str) -> bool:
        return _is_config_enabled(_decode_hash(self.redis.hgetall(config_key(collection_id))))
