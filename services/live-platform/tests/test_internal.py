from __future__ import annotations

from datetime import datetime
from fastapi import BackgroundTasks
import pytest

from api import internal
from api.internal import SegmentReadyRequest, segment_ready
from shared.models import RoomState, Status


@pytest.mark.asyncio
async def test_segment_ready_uses_actual_room_id_for_upload(monkeypatch, tmp_path):
    captured = []
    sequences = iter([0, 1])

    async def fake_on_segment_received(key: str):
        assert key == "tiktok-c1"
        sequence = next(sequences)
        return RoomState(
            collection_id="c1",
            live_room_id="actual-room-1",
            platform="tiktok",
            room_url="https://example.com/live",
            status=Status.RECORDING,
            mediamtx_path="tiktok-c1",
            started_at=datetime(2026, 6, 23, 12, 0, 0).timestamp(),
            metadata={"roomID": "actual-room-1", "filePath": "testuser", "CreatTime": "1782216000"},
            last_segment_sequence=sequence,
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
    assert captured[0].live_room_id == "actual-room-1"
    assert captured[0].record_start_time == "1782216000"
    assert captured[0].legacy_file_path == "testuser"
    assert captured[0].creat_time == "1782216000"
    assert captured[0].segment_sequence == 0
    assert captured[0].metadata == {"roomID": "actual-room-1", "filePath": "testuser", "CreatTime": "1782216000"}

    second_background_tasks = BackgroundTasks()
    response = await segment_ready(
        SegmentReadyRequest(path="tiktok-c1", filePath=str(tmp_path / "segment2.ts"), duration=10),
        second_background_tasks,
    )
    for task in second_background_tasks.tasks:
        await task()

    assert response == {"code": 200, "message": "accepted"}
    assert captured[1].segment_sequence == 1


@pytest.mark.asyncio
async def test_segment_ready_rejects_missing_legacy_file_path(monkeypatch, tmp_path):
    async def fake_on_segment_received(key: str):
        return RoomState(
            collection_id="c1",
            live_room_id="actual-room-1",
            platform="tiktok",
            room_url="https://example.com/live",
            status=Status.RECORDING,
            mediamtx_path=key,
            started_at=datetime(2026, 6, 23, 12, 0, 0).timestamp(),
            metadata={"roomID": "actual-room-1", "CreatTime": "1782216000"},
            last_segment_sequence=0,
        )

    monkeypatch.setattr(internal.state_manager, "on_segment_received", fake_on_segment_received)

    with pytest.raises(RuntimeError, match="filePath"):
        await segment_ready(
            SegmentReadyRequest(path="tiktok-c1", filePath=str(tmp_path / "2026-06-23_10-25-01-092478.mp4")),
            BackgroundTasks(),
        )
