from __future__ import annotations

import pytest

from shared.models import MonitoredRoom, RoomState, Status
from shared.redis_store import COLLECTIONS_KEY, RedisRoomRepository, config_key, status_key


class FakeRedis:
    def __init__(self):
        self.sets: dict[str, set[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    async def sadd(self, key: str, *values: str) -> int:
        target = self.sets.setdefault(key, set())
        before = len(target)
        target.update(str(value) for value in values)
        return len(target) - before

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(key, {}).update({str(k): str(v) for k, v in mapping.items()})
        return len(mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))


@pytest.mark.asyncio
async def test_upsert_room_writes_expected_keys():
    redis = FakeRedis()
    repo = RedisRoomRepository(redis)
    room = MonitoredRoom(collection_id="collection-a", platform="tiktok", room_url="https://example.com/live")

    await repo.upsert_monitored_room(room)

    assert redis.sets[COLLECTIONS_KEY] == {"collection-a"}
    assert redis.hashes[config_key("collection-a")]["platform"] == "tiktok"
    assert redis.hashes[config_key("collection-a")]["roomUrl"] == "https://example.com/live"


@pytest.mark.asyncio
async def test_get_monitored_rooms_keeps_requested_order():
    redis = FakeRedis()
    repo = RedisRoomRepository(redis)
    await repo.upsert_monitored_room(MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/1"))
    await repo.upsert_monitored_room(MonitoredRoom(collection_id="c2", platform="shopee", room_url="https://example.com/2"))

    rooms = await repo.get_monitored_rooms(["c2", "missing", "c1"])

    assert [room.collection_id for room in rooms] == ["c2", "c1"]
    assert [room.platform for room in rooms] == ["shopee", "tiktok"]


@pytest.mark.asyncio
async def test_write_and_read_statuses_keep_requested_order():
    redis = FakeRedis()
    repo = RedisRoomRepository(redis)
    room = MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/1")
    state = RoomState(
        collection_id="c1",
        live_room_id="actual-r1",
        platform="tiktok",
        room_url="https://example.com/1",
        status=Status.RECORDING,
        flv_url="https://stream.example.com/live.flv",
        mediamtx_path="tiktok-c1",
    )

    await repo.write_status(
        room,
        stream_info={"flv_url": "https://stream.example.com/live.flv", "roomId": "actual-r1"},
        state=state,
        is_live=True,
        recording_started=True,
    )
    statuses = await repo.get_statuses(["missing", "c1"])

    assert redis.hashes[status_key("c1")]["isLive"] == "1"
    assert statuses[0] is None
    assert statuses[1]["collectionId"] == "c1"
    assert statuses[1]["isLive"] is True
    assert statuses[1]["roomId"] == "actual-r1"
    assert statuses[1]["recordingStarted"] is True
