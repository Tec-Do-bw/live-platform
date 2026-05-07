from __future__ import annotations

import sqlite3
from pathlib import Path

from shared.models import MonitoredRoom


class RoomRepository:
    """直播间配置读取仓储。"""

    def __init__(self, sqlite_path: Path):
        self.sqlite_path = sqlite_path

    def init_schema(self) -> None:
        """初始化本地开发表结构。"""
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS live_streaming_room (
                    room_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    room_url TEXT NOT NULL,
                    local_status INTEGER NOT NULL DEFAULT 1
                )
                """
            )

    async def list_monitored_rooms(self) -> list[MonitoredRoom]:
        """查询待监控直播间。"""
        self.init_schema()
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT room_id, platform, room_url
                FROM live_streaming_room
                WHERE local_status = 1
                """
            ).fetchall()
        return [
            MonitoredRoom(
                room_id=str(row["room_id"]),
                platform=str(row["platform"]).lower(),
                room_url=str(row["room_url"]),
            )
            for row in rows
        ]
