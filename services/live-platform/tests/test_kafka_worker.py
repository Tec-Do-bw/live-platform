from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from shared.config import KafkaConfig
from upload.kafka_worker import KafkaWorker


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
async def test_kafka_payload_completeness():
    producer = FakeProducer()
    worker = KafkaWorker(
        config=KafkaConfig(bootstrap_servers="localhost:9092", topic_name="liveTs"),
        producer=producer,
    )
    created_at = datetime(2026, 6, 23, 12, 5, 40).timestamp()

    payload = await worker.send_segment_metadata(
        room_id="room123",
        file_path=Path("00001.ts"),
        duration=10,
        video_url="https://oss.example.com/video.ts",
        platform="tiktok",
        live_room_id="room123",
        record_start_time="20260623120000",
        metadata={
            "roomID": "room123",
            "roomName": "测试直播间",
            "UserID": "user_123",
            "batchID": "batch_001",
        },
        created_at=created_at,
    )

    assert payload["room_id"] == "room123"
    assert payload["roomID"] == "room123"
    assert payload["roomName"] == "测试直播间"
    assert payload["UserID"] == "user_123"
    assert payload["batchID"] == "batch_001"
    assert payload["local_file_name"] == "tiktok_room123_20260623120000_00001.ts"
    assert payload["videoStartTime"] == "2026-06-23 12:05:30"
    assert payload["videoEndTime"] == "2026-06-23 12:05:40"
    assert payload["videoUrl"] == "https://oss.example.com/video.ts"
    assert payload["duration"] == 10
    assert payload["dataSource"] == "live_crawler_tiktok_http"
    assert producer.sent == [("liveTs", payload)]
    assert producer.flush_count == 1


@pytest.mark.asyncio
async def test_data_source_format():
    producer = FakeProducer()
    worker = KafkaWorker(
        config=KafkaConfig(bootstrap_servers="localhost:9092", topic_name="liveTs"),
        producer=producer,
    )

    payload = await worker.send_segment_metadata(
        room_id="shop456",
        file_path=Path("00001.ts"),
        duration=10,
        video_url="https://oss.example.com/video.ts",
        platform="shopee",
    )

    assert payload["dataSource"] == "live_crawler_shopee_http"


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
        room_id="room123",
        file_path=Path("00001.ts"),
        duration=10,
        video_url="https://oss.example.com/video.ts",
        platform="tiktok",
        retry_count=3,
    )

    assert sleeps == [1, 2]
    assert len(producer.sent) == 1
