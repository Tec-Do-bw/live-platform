from __future__ import annotations

import pytest

from orchestrator.state_machine import StateManager
from shared.models import MonitoredRoom, SegmentTask, Status
from tests.test_state_machine import FakeMediaMTXClient, FakeRelayController
from tests.test_upload import FakeKafkaWorker, FakeOSSWorker
from upload.coordinator import UploadCoordinator


@pytest.mark.asyncio
async def test_recording_to_upload_chain(tmp_path):
    manager = StateManager(
        mediamtx_client=FakeMediaMTXClient(),
        relay_controller=FakeRelayController(),
    )
    room = MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/live")

    state = await manager.on_live_detected(room, "https://example.com/live.flv", {"roomId": "123"})
    await manager.on_segment_received("tiktok-c1")

    file_path = tmp_path / "segment.mp4"
    file_path.write_bytes(b"video")
    coordinator = UploadCoordinator(oss_worker=FakeOSSWorker(), kafka_worker=FakeKafkaWorker())
    payload = await coordinator.process_one(SegmentTask(room_id=state.room_id, file_path=file_path, duration=10))

    assert state.status == Status.RECORDING
    assert payload["videoUrl"] == "https://oss.example.com/segment.mp4"
