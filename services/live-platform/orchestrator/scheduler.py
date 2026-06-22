from __future__ import annotations

from typing import Any

from adapters import get_stream_info
from orchestrator.state_machine import StateManager, state_manager
from shared.config import settings
from shared.redis_store import RoomRepository
from shared.logger import get_logger
from shared.models import MonitoredRoom, Status

logger = get_logger(__name__)


async def detect_rooms(
    repository: RoomRepository | None = None,
    manager: StateManager | None = None,
) -> int:
    """扫描待监控房间，检测开播并推进状态机。"""
    repo = repository or RoomRepository()
    manager = manager or state_manager
    rooms = await repo.list_monitored_rooms()
    started_count = 0
    await manager.run_health_check()
    await manager.retry_reconnecting()
    active_recordings = _count_active_recordings(manager.snapshot())
    max_active_recordings = _max_active_recordings()

    for room in rooms:
        try:
            state = await manager.ensure_room(room)
            stream_info = await get_stream_info(room.platform, room.room_url)
            is_live = _is_live(stream_info)
            recording_started = False

            if is_live and state.status == Status.IDLE and active_recordings < max_active_recordings:
                state = await manager.on_live_detected(room, str(stream_info["flv_url"]), stream_info)
                started_count += 1
                active_recordings += 1
                recording_started = True
            elif not is_live and state.status in {Status.RECORDING, Status.STARTING, Status.RECONNECTING}:
                state = await manager.on_stream_ended(room.collection_id)

            await _write_status(repo, room, stream_info, state, is_live, recording_started)

        except Exception as e:
            # 单个房间异常不中断整轮检测
            logger.error(
                f"房间检测失败（跳过） | collection_id={room.collection_id} "
                f"platform={room.platform} error={e}",
                exc_info=True,
            )
            continue

    logger.info(f"房间检测完成 | total={len(rooms)} started={started_count}")
    return started_count


def _is_live(stream_info: dict[str, Any] | None) -> bool:
    if not stream_info:
        return False
    flv_url = stream_info.get("flv_url")
    return bool(flv_url) and flv_url != "error"


def _count_active_recordings(states: dict[str, Any]) -> int:
    return sum(1 for state in states.values() if state.status in {Status.STARTING, Status.RECORDING, Status.RECONNECTING})


def _max_active_recordings() -> int:
    return int(settings.server.max_active_recordings)


async def _write_status(
    repository: RoomRepository,
    room: MonitoredRoom,
    stream_info: dict[str, Any] | None,
    state: Any,
    is_live: bool,
    recording_started: bool,
) -> None:
    writer = getattr(repository, "write_status", None)
    if writer is None:
        return
    await writer(
        room,
        stream_info=stream_info,
        state=state,
        is_live=is_live,
        recording_started=recording_started,
    )
