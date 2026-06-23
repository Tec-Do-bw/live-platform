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

    collection_id: str
    platform: str
    room_url: str
    live_room_id: str = ""
    status: Status = Status.IDLE
    flv_url: str | None = None
    mediamtx_path: str | None = None
    ffmpeg_pid: int | None = None
    retry_count: int = 0
    max_retries: int = 15
    last_active: float = 0
    started_at: float = 0
    segment_sequence: int = 0
    last_segment_sequence: int = -1
    error_message: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def room_id(self) -> str:
        """兼容旧调用方，返回实际直播间 ID。"""
        return self.live_room_id

    def is_healthy(self, timeout_seconds: int = 30, now: float | None = None) -> bool:
        """基于切片回调时间判断录制是否健康。"""
        if self.status != Status.RECORDING:
            return True
        current_time = now if now is not None else time()
        return current_time - self.last_active < timeout_seconds

    def mark_active(self, now: float | None = None) -> None:
        """记录最近一次收到切片的时间。"""
        self.last_active = now if now is not None else time()


@dataclass(frozen=True, init=False)
class MonitoredRoom:
    """待监控直播间配置。"""

    collection_id: str
    platform: str
    room_url: str

    def __init__(
        self,
        collection_id: str | None = None,
        platform: str = "",
        room_url: str = "",
        room_id: str | None = None,
    ):
        object.__setattr__(self, "collection_id", collection_id or room_id or "")
        object.__setattr__(self, "platform", platform)
        object.__setattr__(self, "room_url", room_url)

    @property
    def room_id(self) -> str:
        """兼容旧调用方，返回 collection_id。"""
        return self.collection_id


@dataclass(frozen=True)
class SegmentTask:
    """MediaMTX 切片完成后的上传任务。"""

    room_id: str
    file_path: Path
    mediamtx_path: str | None = None
    duration: float | None = None
    platform: str = ""
    live_room_id: str = ""
    legacy_file_path: str = ""
    creat_time: str = ""
    segment_sequence: int = 0
    record_start_time: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time)
