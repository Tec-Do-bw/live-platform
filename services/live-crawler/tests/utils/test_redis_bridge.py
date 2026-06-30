import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.redis_bridge import LiveRedisRepository, config_key, status_key


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.expirations = {}

    def hset(self, key, mapping=None, **kwargs):
        values = mapping or kwargs
        self.hashes.setdefault(key, {}).update({str(k): str(v) for k, v in values.items()})
        return len(values)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def expire(self, key, seconds):
        self.expirations[key] = int(seconds)
        return True


def test_list_live_status_keeps_requested_order_and_missing_is_offline():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
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

    rows = repo.list_live_status(["coll_missing", "coll_live"], now=1001)

    assert rows == [
        {"collectionId": "coll_missing", "isLive": False, "roomId": "", "flvUrl": ""},
        {"collectionId": "coll_live", "isLive": True, "roomId": "room-1", "flvUrl": "https://pull/live.flv"},
    ]


def test_list_live_status_treats_expired_status_as_offline():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    redis.hset(
        status_key("coll_live"),
        mapping={
            "collectionId": "coll_live",
            "isLive": "1",
            "roomId": "room-1",
            "flvUrl": "https://pull/live.flv",
            "expiresAt": "1010",
        },
    )

    rows = repo.list_live_status(["coll_live"], now=1011)

    assert rows == [{"collectionId": "coll_live", "isLive": False, "roomId": "", "flvUrl": ""}]


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
