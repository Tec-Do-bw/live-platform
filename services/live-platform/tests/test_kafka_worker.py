from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from shared.config import KafkaConfig
from shared.models import SegmentTask
from upload.kafka_worker import KafkaWorker, md5_encrypt
from upload.legacy_naming import LegacySegmentName


class FakeProducer:
    def __init__(self, failures: int = 0):
        self.failures = failures
        self.sent: list[tuple[str, dict]] = []
        self.flush_count = 0

    def send(self, topic: str, value: dict) -> None:
        if self.failures:
            self.failures -= 1
            raise RuntimeError("Kafka 暂时不可用")
        self.sent.append((topic, value))

    def flush(self) -> None:
        self.flush_count += 1


@pytest.mark.asyncio
async def test_kafka_payload_matches_legacy_tiktok_contract():
    producer = FakeProducer()
    worker = KafkaWorker(
        config=KafkaConfig(bootstrap_servers="localhost:9092", topic_name="liveTs"),
        producer=producer,
    )

    payload = await worker.send_segment_metadata(
        task=SegmentTask(
            room_id="collection-123",
            file_path=Path("2026-06-23_10-25-01-092478.mp4"),
            duration=10,
            platform="tiktok",
            live_room_id="platform-room-999",
            legacy_file_path="testuser",
            creat_time="1752982646",
            segment_sequence=0,
            metadata={"roomId": "platform-room-999", "id": "user_123"},
        ),
        video_url="https://oss.example.com/video.ts",
        legacy_name=LegacySegmentName(
            basename="testuser_1752982646_00000.ts",
            object_name="realtime-video/testuser_1752982646_00000.ts",
            video_index="0",
        ),
        file_stat=SimpleNamespace(st_ctime=1752982650, st_mtime=1752982660, st_size=1024),
    )

    assert payload == {
        "roomID": "collection-123",
        "roomName": "testuser",
        "intervalTime": 10,
        "createTime": "1752982646",
        "videoStartTime": "1752982650",
        "videoEndTime": "1752982660",
        "batchID": "platform-room-999",
        "UserID": "user_123",
        "videoIndex": "0",
        "videoUrl": "https://oss.example.com/video.ts",
        "uniID": md5_encrypt("https://oss.example.com/video.ts"),
    }
    assert "local_file_name" not in payload
    assert "2026-06-23_10-25-01-092478.mp4" not in str(payload)
    assert producer.sent == [("liveTs", payload)]
    assert producer.flush_count == 1


@pytest.mark.asyncio
async def test_kafka_payload_matches_legacy_shopee_contract():
    producer = FakeProducer()
    worker = KafkaWorker(
        config=KafkaConfig(bootstrap_servers="localhost:9092", topic_name="liveTs"),
        producer=producer,
    )

    payload = await worker.send_segment_metadata(
        task=SegmentTask(
            room_id="collection-456",
            file_path=Path("segment.ts"),
            duration=10,
            platform="shopee",
            legacy_file_path="shopuser",
            creat_time="1752982646",
            segment_sequence=0,
            metadata={
                "startTime": "1752980000",
                "session": {
                    "room_id": "session-room-1",
                    "username": "shopuser",
                    "session_id": "session-1",
                    "uid": "uid-1",
                    "shop_id": "shop-1",
                    "nickname": "nick",
                    "member_cnt": 123,
                    "like_cnt": 456,
                    "start_time": 1752980000,
                    "viewer_count": 10,
                    "chatroom_id": "chat-1",
                },
            },
        ),
        video_url="https://oss.example.com/video.ts",
        legacy_name=LegacySegmentName(
            basename="shopuser_1752982646_00000.ts",
            object_name="realtime-video/shopuser_1752982646_00000.ts",
            video_index="0",
        ),
        file_stat=SimpleNamespace(st_ctime=1752982650, st_mtime=1752982650, st_size=1536 * 1024),
    )

    assert payload["roomID"] == "collection-456"
    assert payload["room_id"] == "session-room-1"
    assert payload["roomName"] == "shopuser"
    assert payload["intervalTime"] == 10
    assert payload["init_startTime"] == "1752980000"
    assert payload["st_size"] == 1.5
    assert payload["videoStartTime"] == "1752982650"
    assert payload["videoEndTime"] == "1752982660"
    assert payload["batchID"] == "session-1"
    assert payload["UserID"] == "uid-1"
    assert payload["shop_id"] == "shop-1"
    assert payload["nickname"] == "nick"
    assert payload["member_cnt"] == 123
    assert payload["like_cnt"] == 456
    assert payload["start_time"] == 1752980000
    assert payload["viewer_count"] == 10
    assert payload["chatroom_id"] == "chat-1"
    assert payload["videoIndex"] == "0"
    assert payload["uniID"] == md5_encrypt("https://oss.example.com/video.ts")


@pytest.mark.asyncio
async def test_retry_backoff(monkeypatch):
    producer = FakeProducer(failures=2)
    worker = KafkaWorker(
        config=KafkaConfig(bootstrap_servers="localhost:9092", topic_name="liveTs"),
        producer=producer,
    )
    sleeps = []

    async def fake_sleep(delay: int) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("upload.kafka_worker.asyncio.sleep", fake_sleep)

    await worker.send_segment_metadata(
        task=SegmentTask(
            room_id="room123",
            file_path=Path("00001.ts"),
            duration=10,
            platform="tiktok",
            legacy_file_path="testuser",
            creat_time="1752982646",
            metadata={"roomId": "room123"},
        ),
        video_url="https://oss.example.com/video.ts",
        legacy_name=LegacySegmentName(
            basename="testuser_1752982646_00000.ts",
            object_name="realtime-video/testuser_1752982646_00000.ts",
            video_index="0",
        ),
        file_stat=SimpleNamespace(st_ctime=1752982650, st_mtime=1752982660, st_size=1024),
        retry_count=3,
    )

    assert sleeps == [1, 2]
    assert len(producer.sent) == 1
