from __future__ import annotations

import pytest

from orchestrator.scheduler import detect_rooms
from orchestrator.state_machine import StateManager
from shared.models import MonitoredRoom, Status
from tests.test_state_machine import FakeMediaMTXClient, FakeRelayController


class FakeRepository:
    def __init__(self, rooms: list[MonitoredRoom] | None = None):
        self.rooms = rooms or [
            MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/live")
        ]
        self.status_writes = []

    async def list_monitored_rooms(self):
        return self.rooms

    async def write_status(self, room, *, stream_info, state, is_live, recording_started):
        self.status_writes.append(
            {
                "collection_id": room.collection_id,
                "stream_info": stream_info,
                "status": state.status,
                "is_live": is_live,
                "recording_started": recording_started,
            }
        )


@pytest.mark.asyncio
async def test_scheduler_starts_idle_room(monkeypatch):
    async def fake_get_stream_info(platform: str, room_url: str):
        return {"flv_url": "https://example.com/live.flv", "roomId": "actual-123"}

    monkeypatch.setattr("orchestrator.scheduler.get_stream_info", fake_get_stream_info)
    monkeypatch.setattr("orchestrator.scheduler._max_active_recordings", lambda: 4)
    manager = StateManager(
        mediamtx_client=FakeMediaMTXClient(),
        relay_controller=FakeRelayController(),
    )
    repo = FakeRepository()

    started_count = await detect_rooms(repository=repo, manager=manager)
    state = await manager.get("c1")

    assert started_count == 1
    assert state is not None
    assert state.status == Status.RECORDING
    assert state.collection_id == "c1"
    assert state.live_room_id == "actual-123"
    assert repo.status_writes[0]["is_live"] is True


@pytest.mark.asyncio
async def test_scheduler_ignores_offline_room(monkeypatch):
    async def fake_get_stream_info(platform: str, room_url: str):
        return {"flv_url": "error"}

    monkeypatch.setattr("orchestrator.scheduler.get_stream_info", fake_get_stream_info)
    monkeypatch.setattr("orchestrator.scheduler._max_active_recordings", lambda: 4)
    manager = StateManager(
        mediamtx_client=FakeMediaMTXClient(),
        relay_controller=FakeRelayController(),
    )
    repo = FakeRepository()

    started_count = await detect_rooms(repository=repo, manager=manager)
    state = await manager.get("c1")

    assert started_count == 0
    assert state is not None
    assert state.status == Status.IDLE
    assert repo.status_writes[0]["is_live"] is False


@pytest.mark.asyncio
async def test_scheduler_limits_recording_start_but_writes_all_statuses(monkeypatch):
    rooms = [
        MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/1"),
        MonitoredRoom(collection_id="c2", platform="tiktok", room_url="https://example.com/2"),
    ]
    repo = FakeRepository(rooms)

    async def fake_get_stream_info(platform: str, room_url: str):
        return {"flv_url": f"{room_url}.flv"}

    monkeypatch.setattr("orchestrator.scheduler.get_stream_info", fake_get_stream_info)
    monkeypatch.setattr("orchestrator.scheduler._max_active_recordings", lambda: 1)
    relay = FakeRelayController()
    manager = StateManager(mediamtx_client=FakeMediaMTXClient(), relay_controller=relay)

    started_count = await detect_rooms(repository=repo, manager=manager)

    assert started_count == 1
    assert len(relay.started) == 1
    assert [write["collection_id"] for write in repo.status_writes] == ["c1", "c2"]
    assert [write["is_live"] for write in repo.status_writes] == [True, True]
    assert [write["recording_started"] for write in repo.status_writes] == [True, False]
