from __future__ import annotations

import pytest

from orchestrator.state_machine import StateManager
from shared.config import settings
from shared.models import MonitoredRoom, SegmentTask, Status
from tests.test_config import full_settings
from tests.test_state_machine import FakeMediaMTXClient, FakeRelayController
from tests.test_upload import FakeKafkaWorker, FakeOSSWorker
from upload.coordinator import UploadCoordinator


@pytest.mark.asyncio
async def test_recording_to_upload_chain(tmp_path):
    settings.override(full_settings(ossPrefix="realtime-video/"))
    manager = StateManager(
        mediamtx_client=FakeMediaMTXClient(),
        relay_controller=FakeRelayController(),
    )
    room = MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/live")

    state = await manager.on_live_detected(
        room,
        "https://example.com/live.flv",
        {"roomId": "123", "filePath": "testuser", "id": "user_123"},
    )
    await manager.on_segment_received("tiktok-c1")

    file_path = tmp_path / "2026-06-23_10-25-01-092478.mp4"
    file_path.write_bytes(b"video")
    oss = FakeOSSWorker()
    kafka = FakeKafkaWorker()
    coordinator = UploadCoordinator(oss_worker=oss, kafka_worker=kafka)
    payload = await coordinator.process_one(
        SegmentTask(
            room_id=state.room_id,
            file_path=file_path,
            duration=10,
            platform=state.platform,
            live_room_id=state.live_room_id,
            legacy_file_path=state.metadata["filePath"],
            creat_time=state.metadata["CreatTime"],
            segment_sequence=state.last_segment_sequence,
            metadata=dict(state.metadata),
        )
    )

    assert state.status == Status.RECORDING
    assert payload["videoUrl"] == "https://oss.example.com/realtime-video/testuser_" + state.metadata["CreatTime"] + "_00000.ts"
    assert oss.calls[0]["object_name"] == f"realtime-video/testuser_{state.metadata['CreatTime']}_00000.ts"
    assert "2026-06-23_10-25-01-092478.mp4" not in str(payload)
