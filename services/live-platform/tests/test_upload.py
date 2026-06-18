from __future__ import annotations

from pathlib import Path

import pytest

from shared.models import SegmentTask
from upload.coordinator import UploadCoordinator


class FakeOSSWorker:
    async def upload_segment(self, file_path: Path, retry_count: int = 3) -> str:
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
        retry_count: int = 3,
    ) -> dict:
        payload = {
            "room_id": room_id,
            "file_name": file_path.name,
            "duration": duration,
            "videoUrl": video_url,
            "platform": platform,
        }
        self.payloads.append(payload)
        return payload


@pytest.mark.asyncio
async def test_upload_coordinator_runs_oss_then_kafka(tmp_path):
    kafka = FakeKafkaWorker()
    coordinator = UploadCoordinator(oss_worker=FakeOSSWorker(), kafka_worker=kafka)
    file_path = tmp_path / "segment.mp4"
    file_path.write_bytes(b"video")

    payload = await coordinator.process_one(
        SegmentTask(room_id="123", file_path=file_path, duration=10, platform="tiktok")
    )

    assert payload["videoUrl"] == "https://oss.example.com/segment.mp4"
    assert payload["platform"] == "tiktok"
    assert kafka.payloads == [payload]
