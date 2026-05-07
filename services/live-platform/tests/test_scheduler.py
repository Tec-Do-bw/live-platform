from __future__ import annotations

import pytest

from orchestrator.scheduler import detect_rooms
from orchestrator.state_machine import StateManager
from shared.models import MonitoredRoom, Status
from tests.test_state_machine import FakeMediaMTXClient, FakeRelayController


class FakeRepository:
    async def list_monitored_rooms(self):
        return [MonitoredRoom(room_id="123", platform="tiktok", room_url="https://example.com/live")]


@pytest.mark.asyncio
async def test_scheduler_starts_idle_room(monkeypatch):
    async def fake_get_stream_url(platform: str, room_url: str):
        return "https://example.com/live.flv"

    monkeypatch.setattr("orchestrator.scheduler.get_stream_url", fake_get_stream_url)
    manager = StateManager(
        mediamtx_client=FakeMediaMTXClient(),
        relay_controller=FakeRelayController(),
    )

    started_count = await detect_rooms(repository=FakeRepository(), manager=manager)
    state = await manager.get("123")

    assert started_count == 1
    assert state is not None
    assert state.status == Status.RECORDING


@pytest.mark.asyncio
async def test_scheduler_ignores_offline_room(monkeypatch):
    async def fake_get_stream_url(platform: str, room_url: str):
        return None

    monkeypatch.setattr("orchestrator.scheduler.get_stream_url", fake_get_stream_url)
    manager = StateManager(
        mediamtx_client=FakeMediaMTXClient(),
        relay_controller=FakeRelayController(),
    )

    started_count = await detect_rooms(repository=FakeRepository(), manager=manager)
    state = await manager.get("123")

    assert started_count == 0
    assert state is not None
    assert state.status == Status.IDLE
