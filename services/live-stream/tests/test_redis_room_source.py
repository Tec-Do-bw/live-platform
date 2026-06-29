import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis_room_source as rrs
from redis_room_source import RedisRoomSource, COLLECTIONS_KEY, config_key, status_key, lease_key, recording_key


@pytest.fixture(autouse=True)
def _stub_lease_ttl(monkeypatch):
    # 隔离 Apollo: lease ttl 用固定值,避免测试触达配置中心
    monkeypatch.setattr(rrs.config, "stream_lease_ttl_seconds", lambda: 360)


class FakeRedis:
    def __init__(self):
        self.strings = {}
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

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.strings:
            return False
        self.strings[key] = str(value)
        if ex is not None:
            self.expirations[key] = int(ex)
        return True

    def get(self, key):
        return self.strings.get(key)

    def delete(self, key):
        existed = key in self.strings
        self.strings.pop(key, None)
        return 1 if existed else 0

    def eval(self, script, numkeys, key, worker_id, ttl_seconds=None):
        if "EXPIRE" in script:
            if self.get(key) == worker_id:
                self.expire(key, int(ttl_seconds))
                return 1
            return 0
        if "DEL" in script:
            if self.get(key) == worker_id:
                return self.delete(key)
            return 0
        return 0


def test_claim_allows_one_worker_only():
    redis = FakeRedis()
    source = RedisRoomSource(redis)

    assert source.claim("coll_1", "worker-a", ttl_seconds=360) is True
    assert source.claim("coll_1", "worker-b", ttl_seconds=360) is False
    assert redis.get(lease_key("coll_1")) == "worker-a"


def test_renew_requires_same_worker():
    redis = FakeRedis()
    source = RedisRoomSource(redis)
    source.claim("coll_1", "worker-a", ttl_seconds=100)

    assert source.renew("coll_1", "worker-b", ttl_seconds=360) is False
    assert source.renew("coll_1", "worker-a", ttl_seconds=360) is True
    assert redis.expirations[lease_key("coll_1")] == 360


def test_release_requires_same_worker():
    redis = FakeRedis()
    source = RedisRoomSource(redis)
    source.claim("coll_1", "worker-a", ttl_seconds=100)

    assert source.release("coll_1", "worker-b") is False
    assert redis.get(lease_key("coll_1")) == "worker-a"
    assert source.release("coll_1", "worker-a") is True
    assert redis.get(lease_key("coll_1")) is None


def test_live_candidates_skip_expired_status():
    redis = FakeRedis()
    source = RedisRoomSource(redis)
    redis.sadd(COLLECTIONS_KEY, "coll_expired")
    redis.sadd(COLLECTIONS_KEY, "coll_live")
    redis.hset(
        status_key("coll_expired"),
        mapping={
            "collectionId": "coll_expired",
            "isLive": "1",
            "roomId": "room-expired",
            "flvUrl": "https://pull/expired.flv",
            "expiresAt": "1000",
            "platform": "tiktok",
        },
    )
    redis.hset(
        status_key("coll_live"),
        mapping={
            "collectionId": "coll_live",
            "isLive": "1",
            "roomId": "room-live",
            "flvUrl": "https://pull/live.flv",
            "expiresAt": "2000",
            "platform": "tiktok",
            "roomUrl": "https://www.tiktok.com/@demo/live",
        },
    )

    rows = source.list_live_candidates(limit=10, now=1500)

    assert rows == [
        {
            "collectionId": "coll_live",
            "roomId": "room-live",
            "flvUrl": "https://pull/live.flv",
            "platform": "tiktok",
            "roomUrl": "https://www.tiktok.com/@demo/live",
        }
    ]


def test_get_status_returns_metadata_for_producer_task():
    redis = FakeRedis()
    source = RedisRoomSource(redis)
    redis.hset(
        status_key("coll_live"),
        mapping={
            "collectionId": "coll_live",
            "isLive": "1",
            "roomId": "room-live",
            "flvUrl": "https://pull/live.flv",
            "expiresAt": "2000",
            "platform": "tiktok",
            "roomUrl": "https://www.tiktok.com/@demo/live",
            "metadata": '{"id": "creator-1", "filePath": "demo", "startTime": "100"}',
        },
    )

    row = source.get_status("coll_live", now=1500)

    assert row["metadata"]["id"] == "creator-1"
    assert row["metadata"]["filePath"] == "demo"


def test_live_candidates_skip_disabled_config():
    redis = FakeRedis()
    source = RedisRoomSource(redis)
    redis.sadd(COLLECTIONS_KEY, "coll_disabled")
    redis.hset(config_key("coll_disabled"), mapping={"enabled": "0"})
    redis.hset(
        status_key("coll_disabled"),
        mapping={
            "collectionId": "coll_disabled",
            "isLive": "1",
            "roomId": "room-live",
            "flvUrl": "https://pull/live.flv",
            "expiresAt": "2000",
            "platform": "tiktok",
        },
    )

    assert source.list_live_candidates(limit=10, now=1500) == []
    assert source.get_status("coll_disabled", now=1500) is None


def test_write_recording_status_sets_hash_and_ttl():
    redis = FakeRedis()
    source = RedisRoomSource(redis)

    source.write_recording_status("coll_1", {"workerId": "worker-a", "status": "recording"}, ttl_seconds=360)

    assert redis.hgetall(recording_key("coll_1"))["status"] == "recording"
    assert redis.expirations[recording_key("coll_1")] == 360
