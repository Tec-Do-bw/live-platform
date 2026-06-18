from __future__ import annotations

from fastapi import BackgroundTasks
import pytest

from api import internal
from api.internal import SegmentReadyRequest, segment_ready
from shared.models import RoomState, Status


@pytest.mark.asyncio
async def test_segment_ready_uses_actual_room_id_for_upload(monkeypatch, tmp_path):
    captured = []

    async def fake_on_segment_received(key: str):
        assert key == "tiktok-c1"
        return RoomState(
            collection_id="c1",
            live_room_id="actual-room-1",
            platform="tiktok",
            room_url="https://example.com/live",
            status=Status.RECORDING,
            mediamtx_path="tiktok-c1",
        )

    async def fake_enqueue(task):
        captured.append(task)

    monkeypatch.setattr(internal.state_manager, "on_segment_received", fake_on_segment_received)
    monkeypatch.setattr(internal.upload_coordinator, "enqueue", fake_enqueue)
    background_tasks = BackgroundTasks()

    response = await segment_ready(
        SegmentReadyRequest(path="tiktok-c1", filePath=str(tmp_path / "segment.mp4"), duration=10),
        background_tasks,
    )
    for task in background_tasks.tasks:
        await task()

    assert response == {"code": 200, "message": "accepted"}
    assert captured[0].room_id == "actual-room-1"
    assert captured[0].mediamtx_path == "tiktok-c1"
    assert captured[0].platform == "tiktok"
