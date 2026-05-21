from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.state_machine import StateManager
from shared.models import MonitoredRoom, Status


class FakeMediaMTXClient:
    def __init__(self):
        self.added: list[str] = []
        self.removed: list[str] = []

    async def add_path(self, room_id: str, rtmp_source: str | None = None) -> dict:
        self.added.append(room_id)
        return {}

    async def remove_path(self, room_id: str) -> None:
        self.removed.append(room_id)


class FakeRelayController:
    def __init__(self):
        self.started: list[tuple[str, str]] = []
        self.stopped: list[int] = []
        self.next_pid = 100

    async def start_ffmpeg_relay(self, flv_url: str, mediamtx_path: str) -> int:
        self.started.append((flv_url, mediamtx_path))
        self.next_pid += 1
        return self.next_pid

    async def stop_ffmpeg_relay(self, pid: int | None) -> None:
        if pid is not None:
            self.stopped.append(pid)


@pytest.mark.asyncio
async def test_live_detected_starts_recording():
    mediamtx = FakeMediaMTXClient()
    relay = FakeRelayController()
    manager = StateManager(mediamtx_client=mediamtx, relay_controller=relay)
    room = MonitoredRoom(room_id="123", platform="tiktok", room_url="https://example.com/live")

    state = await manager.on_live_detected(room, "https://example.com/live.flv")

    assert state.status == Status.RECORDING
    assert state.ffmpeg_pid == 101
    assert mediamtx.added == ["tiktok-123"]
    assert relay.started == [("https://example.com/live.flv", "tiktok-123")]


@pytest.mark.asyncio
async def test_segment_callback_updates_last_active_by_path():
    manager = StateManager(mediamtx_client=FakeMediaMTXClient(), relay_controller=FakeRelayController())
    room = MonitoredRoom(room_id="123", platform="tiktok", room_url="https://example.com/live")
    await manager.on_live_detected(room, "https://example.com/live.flv")

    state = await manager.on_segment_received("tiktok-123")

    assert state.room_id == "123"
    assert state.status == Status.RECORDING
    assert state.last_active > 0


@pytest.mark.asyncio
async def test_health_check_moves_timeout_room_to_reconnecting():
    relay = FakeRelayController()
    manager = StateManager(
        mediamtx_client=FakeMediaMTXClient(),
        relay_controller=relay,
        timeout_seconds=1,
    )
    room = MonitoredRoom(room_id="123", platform="tiktok", room_url="https://example.com/live")
    state = await manager.on_live_detected(room, "https://example.com/live.flv")
    state.last_active = 0

    changed = await manager.run_health_check()

    assert changed[0].status == Status.RECONNECTING
    assert changed[0].retry_count == 1
    assert relay.stopped == [101]


@pytest.mark.asyncio
async def test_stream_ended_cleans_resources():
    mediamtx = FakeMediaMTXClient()
    relay = FakeRelayController()
    manager = StateManager(mediamtx_client=mediamtx, relay_controller=relay)
    room = MonitoredRoom(room_id="123", platform="tiktok", room_url="https://example.com/live")
    await manager.on_live_detected(room, "https://example.com/live.flv")

    state = await manager.on_stream_ended("123")

    assert state.status == Status.IDLE
    assert state.ffmpeg_pid is None
    assert relay.stopped == [101]
    assert mediamtx.removed == ["tiktok-123"]
