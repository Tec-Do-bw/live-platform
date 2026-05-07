from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import time
from typing import Optional

from ffmpeg.relay import FFmpegRelayController
from orchestrator.mediamtx_client import MediaMTXClient
from shared.config import settings
from shared.logger import get_logger
from shared.models import MonitoredRoom, RoomState, Status

logger = get_logger(__name__)

StreamResolver = Callable[[str, str], Awaitable[Optional[str]]]


class StateManager:
    """管理所有房间状态与状态转换。"""

    def __init__(
        self,
        mediamtx_client: MediaMTXClient | None = None,
        relay_controller: FFmpegRelayController | None = None,
        stream_resolver: StreamResolver | None = None,
        timeout_seconds: int | None = None,
        cooldown_seconds: int = 60,
    ):
        self.mediamtx_client = mediamtx_client or MediaMTXClient()
        self.relay_controller = relay_controller or FFmpegRelayController()
        self.stream_resolver = stream_resolver
        self.timeout_seconds = timeout_seconds or settings.mediamtx.segment_timeout_seconds
        self.cooldown_seconds = cooldown_seconds
        self._states: dict[str, RoomState] = {}
        self._lock = asyncio.Lock()

    def snapshot(self) -> dict[str, RoomState]:
        return dict(self._states)

    async def ensure_room(self, room: MonitoredRoom) -> RoomState:
        async with self._lock:
            state = self._states.get(room.room_id)
            if state is None:
                state = RoomState(
                    room_id=room.room_id,
                    platform=room.platform,
                    room_url=room.room_url,
                    last_active=time(),
                )
                self._states[room.room_id] = state
            return state

    async def get(self, room_id: str) -> RoomState | None:
        async with self._lock:
            return self._states.get(room_id)

    async def get_by_room_or_path(self, key: str) -> RoomState | None:
        async with self._lock:
            state = self._states.get(key)
            if state is not None:
                return state
            for candidate in self._states.values():
                if candidate.mediamtx_path == key:
                    return candidate
            return None

    async def on_live_detected(self, room: MonitoredRoom, flv_url: str, metadata: dict | None = None) -> RoomState:
        """检测到开播后启动 MediaMTX path 与 FFmpeg relay。"""
        state = await self.ensure_room(room)
        if state.status not in {Status.IDLE, Status.RECONNECTING, Status.COOLDOWN, Status.FAILED}:
            return state

        state.status = Status.STARTING
        state.flv_url = flv_url
        state.mediamtx_path = self._build_path(room)
        state.started_at = time()
        state.error_message = ""
        state.metadata = metadata or {}

        try:
            await self.mediamtx_client.add_path(state.mediamtx_path)
            state.ffmpeg_pid = await self.relay_controller.start_ffmpeg_relay(
                flv_url=flv_url,
                mediamtx_path=state.mediamtx_path,
            )
        except Exception as exc:
            logger.exception("启动录制失败 | room_id=%s", room.room_id)
            state.status = Status.FAILED
            state.error_message = str(exc)
            await self._cleanup_state(state)
            return state

        return await self.on_recording_started(room.room_id)

    async def on_recording_started(self, room_id: str) -> RoomState:
        state = await self._require_state(room_id)
        state.status = Status.RECORDING
        state.retry_count = 0
        state.mark_active()
        logger.info("录制已开始 | room_id=%s", room_id)
        return state

    async def on_segment_received(self, room_id: str) -> RoomState:
        state = await self._require_state(room_id)
        state.mark_active()
        if state.status in {Status.STARTING, Status.RECONNECTING}:
            state.status = Status.RECORDING
        logger.info("收到切片回调 | room_id=%s", room_id)
        return state

    async def on_stream_timeout(self, room_id: str) -> RoomState:
        state = await self._require_state(room_id)
        if state.status != Status.RECORDING:
            return state
        state.status = Status.RECONNECTING
        state.retry_count += 1
        logger.warning("录制切片超时，进入重连 | room_id=%s retry=%s", room_id, state.retry_count)
        await self.relay_controller.stop_ffmpeg_relay(state.ffmpeg_pid)
        state.ffmpeg_pid = None
        return state

    async def on_reconnect_success(self, room_id: str, flv_url: str) -> RoomState:
        state = await self._require_state(room_id)
        if state.status != Status.RECONNECTING:
            return state
        room = MonitoredRoom(room_id=state.room_id, platform=state.platform, room_url=state.room_url)
        return await self.on_live_detected(room, flv_url, state.metadata)

    async def on_reconnect_failed(self, room_id: str, message: str = "") -> RoomState:
        state = await self._require_state(room_id)
        state.status = Status.FAILED
        state.error_message = message
        await self._cleanup_state(state)
        return state

    async def on_stream_ended(self, room_id: str) -> RoomState:
        state = await self._require_state(room_id)
        await self._cleanup_state(state)
        state.status = Status.IDLE
        state.flv_url = None
        state.retry_count = 0
        state.error_message = ""
        logger.info("录制已结束 | room_id=%s", room_id)
        return state

    async def run_health_check(self) -> list[RoomState]:
        """检查所有录制中的房间，返回发生状态变化的房间。"""
        changed: list[RoomState] = []
        for room_id, state in list(self.snapshot().items()):
            if not state.is_healthy(self.timeout_seconds):
                changed.append(await self.on_stream_timeout(room_id))
        return changed

    async def retry_reconnecting(self) -> list[RoomState]:
        """对重连中的房间重新获取流地址并尝试恢复。"""
        changed: list[RoomState] = []
        if self.stream_resolver is None:
            return changed

        for state in list(self.snapshot().values()):
            if state.status != Status.RECONNECTING:
                continue
            if state.retry_count > state.max_retries:
                changed.append(await self.on_reconnect_failed(state.room_id, "超过最大重试次数"))
                continue
            flv_url = await self.stream_resolver(state.platform, state.room_url)
            if flv_url:
                changed.append(await self.on_reconnect_success(state.room_id, flv_url))
        return changed

    async def _cleanup_state(self, state: RoomState) -> None:
        await self.relay_controller.stop_ffmpeg_relay(state.ffmpeg_pid)
        state.ffmpeg_pid = None
        if state.mediamtx_path:
            await self.mediamtx_client.remove_path(state.mediamtx_path)

    async def _require_state(self, room_id: str) -> RoomState:
        state = await self.get_by_room_or_path(room_id)
        if state is None:
            raise KeyError(f"房间状态不存在: {room_id}")
        return state

    @staticmethod
    def _build_path(room: MonitoredRoom) -> str:
        safe_platform = "".join(ch for ch in room.platform.lower() if ch.isalnum() or ch in {"-", "_"})
        safe_room_id = "".join(ch for ch in room.room_id if ch.isalnum() or ch in {"-", "_"})
        return f"{safe_platform}-{safe_room_id}"


state_manager = StateManager()
