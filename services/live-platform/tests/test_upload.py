from __future__ import annotations

from pathlib import Path

import pytest

from shared.config import settings
from shared.models import SegmentTask
from tests.test_config import full_settings
from upload.coordinator import UploadCoordinator


class FakeOSSWorker:
    def __init__(self):
        self.calls: list[dict] = []

    async def upload_segment(
        self,
        file_path: Path,
        object_name: str,
        retry_count: int = 3,
    ) -> str:
        self.calls.append(
            {
                "file_path": file_path,
                "object_name": object_name,
            }
        )
        return f"https://oss.example.com/{object_name}"


class FakeKafkaWorker:
    def __init__(self):
        self.payloads: list[dict] = []

    async def send_segment_metadata(
        self,
        task: SegmentTask,
        video_url: str,
        legacy_name,
        file_stat,
        retry_count: int = 3,
    ) -> dict:
        payload = {
            "room_id": task.room_id,
            "videoUrl": video_url,
            "legacy_basename": legacy_name.basename,
            "object_name": legacy_name.object_name,
            "videoIndex": legacy_name.video_index,
            "metadata": task.metadata,
            "st_size": file_stat.st_size,
        }
        self.payloads.append(payload)
        return payload


@pytest.mark.asyncio
async def test_upload_coordinator_runs_oss_then_kafka(tmp_path):
    settings.override(full_settings(ossPrefix="realtime-video/"))
    oss = FakeOSSWorker()
    kafka = FakeKafkaWorker()
    coordinator = UploadCoordinator(oss_worker=oss, kafka_worker=kafka)
    file_path = tmp_path / "2026-06-23_10-25-01-092478.mp4"
    file_path.write_bytes(b"video")

    payload = await coordinator.process_one(
        SegmentTask(
            room_id="123",
            file_path=file_path,
            duration=10,
            platform="tiktok",
            live_room_id="actual-123",
            legacy_file_path="testuser",
            creat_time="1752982646",
            segment_sequence=0,
            metadata={"roomName": "测试直播间", "filePath": "testuser", "CreatTime": "1752982646"},
            created_at=1782216005,
        )
    )

    assert payload["videoUrl"] == "https://oss.example.com/realtime-video/testuser_1752982646_00000.ts"
    assert payload["legacy_basename"] == "testuser_1752982646_00000.ts"
    assert payload["object_name"] == "realtime-video/testuser_1752982646_00000.ts"
    assert payload["videoIndex"] == "0"
    assert payload["metadata"] == {"roomName": "测试直播间", "filePath": "testuser", "CreatTime": "1752982646"}
    assert oss.calls == [
        {
            "file_path": file_path,
            "object_name": "realtime-video/testuser_1752982646_00000.ts",
        }
    ]
    assert kafka.payloads == [payload]


@pytest.mark.asyncio
async def test_upload_coordinator_splits_long_segment_with_legacy_names(tmp_path):
    settings.override(full_settings(ossPrefix="realtime-video/"))
    oss = FakeOSSWorker()
    kafka = FakeKafkaWorker()
    original = tmp_path / "long-segment.ts"
    split_0 = tmp_path / "long-segment.00000.ts"
    split_1 = tmp_path / "long-segment.00001.ts"
    original.write_bytes(b"original")
    split_0.write_bytes(b"split0")
    split_1.write_bytes(b"split1")

    def fake_cutter(file_path: Path) -> list[Path]:
        assert file_path == original
        return [split_0, split_1]

    coordinator = UploadCoordinator(
        oss_worker=oss,
        kafka_worker=kafka,
        long_segment_cutter=fake_cutter,
    )

    await coordinator.process_one(
        SegmentTask(
            room_id="123",
            file_path=original,
            duration=20,
            platform="tiktok",
            legacy_file_path="testuser",
            creat_time="1752982646",
            segment_sequence=0,
            metadata={"filePath": "testuser", "CreatTime": "1752982646"},
        )
    )

    assert [call["object_name"] for call in oss.calls] == [
        "realtime-video/testuser_1752982646_00000.00000.ts",
        "realtime-video/testuser_1752982646_00000.00001.ts",
    ]
    assert [payload["videoIndex"] for payload in kafka.payloads] == ["0.0", "0.1"]
    assert not original.exists()
