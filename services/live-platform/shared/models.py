from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import time


class Status(str, Enum):
    """直播间录制状态。"""

    IDLE = "idle"
    STARTING = "starting"
    RECORDING = "recording"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    COOLDOWN = "cooldown"


@dataclass
class RoomState:
    """单个直播间的运行态。"""

    room_id: str
    platform: str
    room_url: str
    status: Status = Status.IDLE
    flv_url: str | None = None
    mediamtx_path: str | None = None
    ffmpeg_pid: int | None = None
    retry_count: int = 0
    max_retries: int = 15
    last_active: float = 0
    started_at: float = 0
    error_message: str = ""
    metadata: dict = field(default_factory=dict)

    def is_healthy(self, timeout_seconds: int = 30, now: float | None = None) -> bool:
        """基于切片回调时间判断录制是否健康。"""
        if self.status != Status.RECORDING:
            return True
        current_time = now if now is not None else time()
        return current_time - self.last_active < timeout_seconds

    def mark_active(self, now: float | None = None) -> None:
        """记录最近一次收到切片的时间。"""
        self.last_active = now if now is not None else time()


@dataclass(frozen=True)
class MonitoredRoom:
    """待监控直播间配置。"""

    room_id: str
    platform: str
    room_url: str


@dataclass(frozen=True)
class SegmentTask:
    """MediaMTX 切片完成后的上传任务。"""

    room_id: str
    file_path: Path
    mediamtx_path: str | None = None
    duration: float | None = None
    created_at: float = field(default_factory=time)
