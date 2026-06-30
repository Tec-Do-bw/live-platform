import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.api_response import ApiOutcome, ErrorReason
from utils.redis_bridge import (
    COLLECTIONS_KEY,
    LiveRedisRepository,
    build_status_payload,
    config_key,
    normalize_seed_row,
    status_key,
)


class FakeRedis:
    def __init__(self):
        self.sets = {}
        self.hashes = {}
        self.expirations = {}

    def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(str(value))
        return 1

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def hset(self, key, mapping=None, **kwargs):
        values = mapping or kwargs
        self.hashes.setdefault(key, {}).update({str(k): str(v) for k, v in values.items()})
        return len(values)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def expire(self, key, seconds):
        self.expirations[key] = int(seconds)
        return True


def test_upsert_config_writes_collection_set_and_hash():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)

    repo.upsert_config(
        collection_id="coll_1001",
        room_url="https://www.tiktok.com/@demo/live",
        platform="tiktok",
        legacy_room_id="legacy_1",
        enabled=True,
        source_node="node-a",
    )

    assert "coll_1001" in redis.smembers(COLLECTIONS_KEY)
    raw = redis.hgetall(config_key("coll_1001"))
    assert raw["collectionId"] == "coll_1001"
    assert raw["collection_id"] == "coll_1001"
    assert raw["legacyRoomId"] == "legacy_1"
    assert raw["roomUrl"] == "https://www.tiktok.com/@demo/live"
    assert raw["room_url"] == "https://www.tiktok.com/@demo/live"
    assert raw["platform"] == "tiktok"
    assert raw["enabled"] == "1"
    assert raw["sourceNode"] == "node-a"


def test_normalize_seed_row_prefers_collection_id_and_platform():
    row = ("legacy_1", "https://www.tiktok.com/@demo/live", "0", "coll_1001", "tiktok")

    normalized = normalize_seed_row(row)

    assert normalized["collection_id"] == "coll_1001"
    assert normalized["legacy_room_id"] == "legacy_1"
    assert normalized["room_url"] == "https://www.tiktok.com/@demo/live"
    assert normalized["platform"] == "tiktok"


def test_normalize_seed_row_falls_back_to_legacy_room_id_and_infers_platform():
    row = ("legacy_2", "https://ph.shp.ee/DT7Tpev", "0")

    normalized = normalize_seed_row(row)

    assert normalized["collection_id"] == "legacy_2"
    assert normalized["legacy_room_id"] == "legacy_2"
    assert normalized["platform"] == "shopee"


def test_build_status_payload_live_success_keeps_flv_url():
    outcome = ApiOutcome(
        code=200,
        port_info={
            "roomId": "7544720840995162887",
            "flv_url": "https://pull-flv.example/live.flv",
            "play_urls": ["https://pull-flv.example/live.flv"],
        },
        error_reason=None,
        error_detail=None,
    )

    payload = build_status_payload(
        collection_id="coll_1001",
        platform="tiktok",
        room_url="https://www.tiktok.com/@demo/live",
        outcome=outcome,
        port_info=outcome.port_info,
        source_node="node-a",
        now=1000,
        ttl_seconds=900,
    )

    assert payload["isLive"] == "1"
    assert payload["status"] == "live"
    assert payload["roomId"] == "7544720840995162887"
    assert payload["room_id"] == "7544720840995162887"
    assert payload["flvUrl"] == "https://pull-flv.example/live.flv"
    assert payload["flv_url"] == "https://pull-flv.example/live.flv"
    assert payload["expiresAt"] == "1900"
    assert payload["code"] == "200"


def test_build_status_payload_offline_clears_flv_url():
    outcome = ApiOutcome(
        code=2001,
        port_info={"roomId": "7544720840995162887", "uniqueId": "demo"},
        error_reason=None,
        error_detail=None,
    )

    payload = build_status_payload(
        collection_id="coll_1002",
        platform="tiktok",
        room_url="https://www.tiktok.com/@demo/live",
        outcome=outcome,
        port_info=outcome.port_info,
        source_node="node-a",
        now=1000,
        ttl_seconds=900,
    )

    assert payload["isLive"] == "0"
    assert payload["status"] == "offline"
    assert payload["roomId"] == "7544720840995162887"
    assert payload["flvUrl"] == ""
    assert payload["flv_url"] == ""
    assert payload["code"] == "2001"


def test_write_status_detection_error_without_previous_status_is_not_assignable():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    outcome = ApiOutcome(
        code=5099,
        port_info=None,
        error_reason=ErrorReason.INTERNAL_ERROR,
        error_detail="直播状态检测失败",
    )

    payload = repo.write_status(
        collection_id="coll_1003",
        platform="tiktok",
        room_url="https://www.tiktok.com/@demo/live",
        outcome=outcome,
        port_info=None,
        source_node="node-a",
        now=1000,
    )

    assert payload["isLive"] == "0"
    assert payload["flvUrl"] == ""
    assert payload["expiresAt"] == "0"
    assert payload["status"] == "internal_error"
    assert payload["lastDetectCode"] == "5099"
    assert payload["lastDetectReason"] == ErrorReason.INTERNAL_ERROR
    assert payload["lastDetectMessage"] == "直播状态检测失败"
    assert payload["detectFailCount"] == "1"
    assert repo.list_live_status(["coll_1003"], now=1001) == [
        {"collectionId": "coll_1003", "isLive": False, "roomId": "", "flvUrl": ""}
    ]


def test_write_status_detection_error_preserves_previous_live_until_expiry():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    live_outcome = ApiOutcome(
        code=200,
        port_info={"roomId": "room-1", "flv_url": "https://pull/live.flv"},
        error_reason=None,
        error_detail=None,
    )
    error_outcome = ApiOutcome(
        code=5001,
        port_info=None,
        error_reason=ErrorReason.UPSTREAM_REQUEST_FAILED,
        error_detail="timeout",
    )

    repo.write_status(
        collection_id="coll_live",
        platform="tiktok",
        room_url="https://www.tiktok.com/@live/live",
        outcome=live_outcome,
        port_info=live_outcome.port_info,
        source_node="node-a",
        now=1000,
        ttl_seconds=900,
    )
    payload = repo.write_status(
        collection_id="coll_live",
        platform="tiktok",
        room_url="https://www.tiktok.com/@live/live",
        outcome=error_outcome,
        port_info=None,
        source_node="node-a",
        now=1100,
        ttl_seconds=1200,
    )

    assert payload["isLive"] == "1"
    assert payload["status"] == "live"
    assert payload["code"] == "200"
    assert payload["flvUrl"] == "https://pull/live.flv"
    assert payload["expiresAt"] == "1900"
    assert payload["lastDetectCode"] == "5001"
    assert payload["lastDetectReason"] == ErrorReason.UPSTREAM_REQUEST_FAILED
    assert payload["lastDetectMessage"] == "timeout"
    assert payload["detectFailCount"] == "1"
    assert redis.expirations[status_key("coll_live")] == 900
    assert repo.list_live_status(["coll_live"], now=1101) == [
        {"collectionId": "coll_live", "isLive": True, "roomId": "room-1", "flvUrl": "https://pull/live.flv"}
    ]
    assert repo.list_live_status(["coll_live"], now=1901) == [
        {"collectionId": "coll_live", "isLive": False, "roomId": "", "flvUrl": ""}
    ]


def test_write_status_detection_error_increments_fail_count_without_extending_expires_at():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    live_outcome = ApiOutcome(
        code=200,
        port_info={"roomId": "room-1", "flv_url": "https://pull/live.flv"},
        error_reason=None,
        error_detail=None,
    )
    error_outcome = ApiOutcome(
        code=5002,
        port_info=None,
        error_reason=ErrorReason.PARSE_FAILED,
        error_detail="页面解析失败",
    )

    repo.write_status(
        collection_id="coll_live",
        platform="tiktok",
        room_url="https://www.tiktok.com/@live/live",
        outcome=live_outcome,
        port_info=live_outcome.port_info,
        source_node="node-a",
        now=1000,
        ttl_seconds=900,
    )
    repo.write_status(
        collection_id="coll_live",
        platform="tiktok",
        room_url="https://www.tiktok.com/@live/live",
        outcome=error_outcome,
        port_info=None,
        source_node="node-a",
        now=1100,
    )
    payload = repo.write_status(
        collection_id="coll_live",
        platform="tiktok",
        room_url="https://www.tiktok.com/@live/live",
        outcome=error_outcome,
        port_info=None,
        source_node="node-a",
        now=1200,
    )

    assert payload["flvUrl"] == "https://pull/live.flv"
    assert payload["expiresAt"] == "1900"
    assert payload["lastDetectCode"] == "5002"
    assert payload["detectFailCount"] == "2"


def test_write_status_confirmed_offline_clears_previous_flv_url():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    live_outcome = ApiOutcome(
        code=200,
        port_info={"roomId": "room-1", "flv_url": "https://pull/live.flv"},
        error_reason=None,
        error_detail=None,
    )
    offline_outcome = ApiOutcome(
        code=2001,
        port_info={"roomId": "room-1", "uniqueId": "demo"},
        error_reason=None,
        error_detail=None,
    )

    repo.write_status(
        collection_id="coll_live",
        platform="tiktok",
        room_url="https://www.tiktok.com/@live/live",
        outcome=live_outcome,
        port_info=live_outcome.port_info,
        source_node="node-a",
        now=1000,
    )
    payload = repo.write_status(
        collection_id="coll_live",
        platform="tiktok",
        room_url="https://www.tiktok.com/@live/live",
        outcome=offline_outcome,
        port_info=offline_outcome.port_info,
        source_node="node-a",
        now=1100,
    )

    assert payload["isLive"] == "0"
    assert payload["status"] == "offline"
    assert payload["flvUrl"] == ""
    assert payload["detectFailCount"] == "0"


def test_list_live_status_keeps_requested_order_and_missing_is_offline():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    live_outcome = ApiOutcome(
        code=200,
        port_info={"roomId": "room-1", "flv_url": "https://pull/live.flv"},
        error_reason=None,
        error_detail=None,
    )
    repo.write_status(
        collection_id="coll_live",
        platform="tiktok",
        room_url="https://www.tiktok.com/@live/live",
        outcome=live_outcome,
        port_info=live_outcome.port_info,
        source_node="node-a",
        now=1000,
    )

    rows = repo.list_live_status(["coll_missing", "coll_live"], now=1001)

    assert rows == [
        {"collectionId": "coll_missing", "isLive": False, "roomId": "", "flvUrl": ""},
        {"collectionId": "coll_live", "isLive": True, "roomId": "room-1", "flvUrl": "https://pull/live.flv"},
    ]


def test_list_live_status_treats_expired_status_as_offline():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    live_outcome = ApiOutcome(
        code=200,
        port_info={"roomId": "room-1", "flv_url": "https://pull/live.flv"},
        error_reason=None,
        error_detail=None,
    )
    repo.write_status(
        collection_id="coll_live",
        platform="tiktok",
        room_url="https://www.tiktok.com/@live/live",
        outcome=live_outcome,
        port_info=live_outcome.port_info,
        source_node="node-a",
        now=1000,
        ttl_seconds=10,
    )

    rows = repo.list_live_status(["coll_live"], now=1011)

    assert rows == [{"collectionId": "coll_live", "isLive": False, "roomId": "", "flvUrl": ""}]
    assert redis.expirations[status_key("coll_live")] == 10


def test_list_live_status_treats_disabled_config_as_offline():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    redis.hset(config_key("coll_live"), mapping={"enabled": "0"})
    redis.hset(
        status_key("coll_live"),
        mapping={
            "collectionId": "coll_live",
            "isLive": "1",
            "roomId": "room-1",
            "flvUrl": "https://pull/live.flv",
            "expiresAt": "2000",
        },
    )

    rows = repo.list_live_status(["coll_live"], now=1000)

    assert rows == [{"collectionId": "coll_live", "isLive": False, "roomId": "", "flvUrl": ""}]


def test_list_live_status_treats_dirty_expires_at_as_offline():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    redis.hset(
        status_key("coll_live"),
        mapping={
            "collectionId": "coll_live",
            "isLive": "1",
            "roomId": "room-1",
            "flvUrl": "https://pull/live.flv",
            "expiresAt": "dirty",
        },
    )

    rows = repo.list_live_status(["coll_live"], now=1000)

    assert rows == [{"collectionId": "coll_live", "isLive": False, "roomId": "", "flvUrl": ""}]
