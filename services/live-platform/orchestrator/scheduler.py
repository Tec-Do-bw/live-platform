from __future__ import annotations

from adapters import get_stream_url
from orchestrator.state_machine import StateManager, state_manager
from shared.config import settings
from shared.db import RoomRepository
from shared.logger import get_logger
from shared.models import Status

logger = get_logger(__name__)


async def detect_rooms(
    repository: RoomRepository | None = None,
    manager: StateManager | None = None,
) -> int:
    """扫描待监控房间，检测开播并推进状态机。"""
    repo = repository or RoomRepository(settings.database.sqlite_path)
    manager = manager or state_manager
    rooms = await repo.list_monitored_rooms()
    started_count = 0

    await manager.run_health_check()
    await manager.retry_reconnecting()

    for room in rooms:
        state = await manager.ensure_room(room)
        if state.status != Status.IDLE:
            continue
        stream_info = await get_stream_url(room.platform, room.room_url)
        if stream_info:
            await manager.on_live_detected(room, stream_info)
            started_count += 1

    logger.info("房间检测完成 | total=%s started=%s", len(rooms), started_count)
    return started_count
