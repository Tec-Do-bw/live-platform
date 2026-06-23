from __future__ import annotations

from pathlib import Path

import pytest

from shared.models import SegmentTask
from upload.coordinator import UploadCoordinator


class FakeOSSWorker:
    def __init__(self):
        self.calls: list[dict] = []

    async def upload_segment(
        self,
        file_path: Path,
        retry_count: int = 3,
        *,
        platform: str = "",
        live_room_id: str = "",
        record_start_time: str = "",
    ) -> str:
        self.calls.append(
            {
                "file_path": file_path,
                "platform": platform,
                "live_room_id": live_room_id,
                "record_start_time": record_start_time,
            }
        )
        return f"https://oss.example.com/{file_path.name}"


class FakeKafkaWorker:
    def __init__(self):
        self.payloads: list[dict] = []

    async def send_segment_metadata(
        self,
        room_id: str,
        file_path: Path,
        duration: float | None,
        video_url: str,
        platform: str = "",
        live_room_id: str = "",
        record_start_time: str = "",
        metadata: dict | None = None,
        created_at: float | None = None,
        retry_count: int = 3,
    ) -> dict:
        payload = {
            "room_id": room_id,
            "file_name": file_path.name,
            "duration": duration,
            "videoUrl": video_url,
            "platform": platform,
            "live_room_id": live_room_id,
            "record_start_time": record_start_time,
            "metadata": metadata or {},
            "created_at": created_at,
        }
        self.payloads.append(payload)
        return payload


@pytest.mark.asyncio
async def test_upload_coordinator_runs_oss_then_kafka(tmp_path):
    oss = FakeOSSWorker()
    kafka = FakeKafkaWorker()
    coordinator = UploadCoordinator(oss_worker=oss, kafka_worker=kafka)
    file_path = tmp_path / "segment.mp4"
    file_path.write_bytes(b"video")

    payload = await coordinator.process_one(
        SegmentTask(
            room_id="123",
            file_path=file_path,
            duration=10,
            platform="tiktok",
            live_room_id="actual-123",
            record_start_time="20260623120000",
            metadata={"roomName": "测试直播间"},
            created_at=1782216005,
        )
    )

    assert payload["videoUrl"] == "https://oss.example.com/segment.mp4"
    assert payload["platform"] == "tiktok"
    assert payload["live_room_id"] == "actual-123"
    assert payload["record_start_time"] == "20260623120000"
    assert payload["metadata"] == {"roomName": "测试直播间"}
    assert oss.calls == [
        {
            "file_path": file_path,
            "platform": "tiktok",
            "live_room_id": "actual-123",
            "record_start_time": "20260623120000",
        }
    ]
    assert kafka.payloads == [payload]
