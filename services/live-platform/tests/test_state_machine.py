from __future__ import annotations

import pytest

from orchestrator.state_machine import StateManager
from shared.models import MonitoredRoom, Status


class FakeMediaMTXClient:
    def __init__(self):
        self.added: list[str] = []
        self.removed: list[str] = []
        self.events: list[tuple[str, str]] = []

    async def add_path(self, room_id: str, rtmp_source: str | None = None) -> dict:
        self.added.append(room_id)
        self.events.append(("add", room_id))
        return {}

    async def remove_path(self, room_id: str) -> None:
        self.removed.append(room_id)
        self.events.append(("remove", room_id))


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
    room = MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/live")

    state = await manager.on_live_detected(room, "https://example.com/live.flv", {"roomId": "123"})

    assert state.status == Status.RECORDING
    assert state.collection_id == "c1"
    assert state.live_room_id == "123"
    assert state.ffmpeg_pid == 101
    assert state.segment_sequence == 0
    assert state.last_segment_sequence == -1
    assert state.metadata["CreatTime"].isdigit()
    assert mediamtx.added == ["tiktok-c1"]
    assert relay.started == [("https://example.com/live.flv", "tiktok-c1")]


@pytest.mark.asyncio
async def test_segment_callback_updates_last_active_by_path():
    manager = StateManager(mediamtx_client=FakeMediaMTXClient(), relay_controller=FakeRelayController())
    room = MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/live")
    await manager.on_live_detected(room, "https://example.com/live.flv", {"roomId": "123"})

    state = await manager.on_segment_received("tiktok-c1")

    assert state.room_id == "123"
    assert state.collection_id == "c1"
    assert state.status == Status.RECORDING
    assert state.last_active > 0
    assert state.last_segment_sequence == 0
    assert state.segment_sequence == 1

    state = await manager.on_segment_received("tiktok-c1")

    assert state.last_segment_sequence == 1
    assert state.segment_sequence == 2


@pytest.mark.asyncio
async def test_health_check_moves_timeout_room_to_reconnecting():
    relay = FakeRelayController()
    manager = StateManager(
        mediamtx_client=FakeMediaMTXClient(),
        relay_controller=relay,
        timeout_seconds=1,
    )
    room = MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/live")
    state = await manager.on_live_detected(room, "https://example.com/live.flv", {"roomId": "123"})
    state.last_active = 0

    changed = await manager.run_health_check()

    assert changed[0].status == Status.RECONNECTING
    assert changed[0].retry_count == 1
    assert relay.stopped == [101]


@pytest.mark.asyncio
async def test_timeout_removes_path_before_reconnect_success():
    mediamtx = FakeMediaMTXClient()
    relay = FakeRelayController()

    async def stream_resolver(platform: str, room_url: str) -> str:
        assert platform == "tiktok"
        assert room_url == "https://example.com/live"
        return "https://example.com/live-new.flv"

    manager = StateManager(
        mediamtx_client=mediamtx,
        relay_controller=relay,
        stream_resolver=stream_resolver,
        timeout_seconds=1,
    )
    room = MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/live")
    state = await manager.on_live_detected(room, "https://example.com/live.flv", {"roomId": "123"})
    state.last_active = 0

    await manager.run_health_check()
    assert state.mediamtx_path == "tiktok-c1"
    changed = await manager.retry_reconnecting()

    assert changed[0].status == Status.RECORDING
    assert mediamtx.added == ["tiktok-c1", "tiktok-c1"]
    assert mediamtx.removed == ["tiktok-c1"]
    assert mediamtx.events == [
        ("add", "tiktok-c1"),
        ("remove", "tiktok-c1"),
        ("add", "tiktok-c1"),
    ]
    assert relay.stopped == [101]
    assert relay.started == [
        ("https://example.com/live.flv", "tiktok-c1"),
        ("https://example.com/live-new.flv", "tiktok-c1"),
    ]


@pytest.mark.asyncio
async def test_stale_segment_callback_does_not_revive_reconnecting_room():
    mediamtx = FakeMediaMTXClient()
    relay = FakeRelayController()
    manager = StateManager(
        mediamtx_client=mediamtx,
        relay_controller=relay,
        timeout_seconds=1,
    )
    room = MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/live")
    state = await manager.on_live_detected(room, "https://example.com/live.flv", {"roomId": "123"})
    state.last_active = 0

    await manager.run_health_check()
    callback_state = await manager.on_segment_received("tiktok-c1")

    assert callback_state.status == Status.RECONNECTING
    assert callback_state.ffmpeg_pid is None
    assert mediamtx.events == [("add", "tiktok-c1"), ("remove", "tiktok-c1")]


@pytest.mark.asyncio
async def test_stream_ended_cleans_resources():
    mediamtx = FakeMediaMTXClient()
    relay = FakeRelayController()
    manager = StateManager(mediamtx_client=mediamtx, relay_controller=relay)
    room = MonitoredRoom(collection_id="c1", platform="tiktok", room_url="https://example.com/live")
    await manager.on_live_detected(room, "https://example.com/live.flv", {"roomId": "123"})

    state = await manager.on_stream_ended("c1")

    assert state.status == Status.IDLE
    assert state.ffmpeg_pid is None
    assert relay.stopped == [101]
    assert mediamtx.removed == ["tiktok-c1"]
