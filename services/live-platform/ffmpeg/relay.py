from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass

from shared.config import MediaMTXConfig, settings
from shared.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RelayProcess:
    pid: int
    process: asyncio.subprocess.Process
    mediamtx_path: str


class FFmpegRelayController:
    """管理 HTTP-FLV 到 MediaMTX RTMP 的 FFmpeg relay。"""

    def __init__(self, config: MediaMTXConfig | None = None):
        self.config = config or settings.mediamtx
        self._processes: dict[int, RelayProcess] = {}

    def build_command(self, flv_url: str, mediamtx_path: str) -> list[str]:
        output_url = f"{self.config.rtmp_base_url}/{mediamtx_path}"
        return [
            "ffmpeg",
            "-y",
            "-loglevel",
            "warning",
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-i",
            flv_url,
            "-c",
            "copy",
            "-f",
            "flv",
            output_url,
        ]

    async def start_ffmpeg_relay(self, flv_url: str, mediamtx_path: str) -> int:
        """启动 FFmpeg relay 并返回 PID。"""
        command = self.build_command(flv_url, mediamtx_path)
        logger.info("启动 FFmpeg relay | path=%s", mediamtx_path)
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._processes[process.pid] = RelayProcess(
            pid=process.pid,
            process=process,
            mediamtx_path=mediamtx_path,
        )
        return process.pid

    async def stop_ffmpeg_relay(self, pid: int | None) -> None:
        """停止 FFmpeg relay。"""
        if pid is None:
            return
        relay_process = self._processes.pop(pid, None)
        if relay_process is None:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            return

        process = relay_process.process
        if process.returncode is not None:
            return

        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("FFmpeg 停止超时，强制结束 | pid=%s", pid)
            process.kill()
            await process.wait()

    def is_ffmpeg_alive(self, pid: int | None) -> bool:
        """判断 relay 进程是否仍在运行。"""
        if pid is None:
            return False
        relay_process = self._processes.get(pid)
        if relay_process is not None:
            return relay_process.process.returncode is None
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    async def cleanup_finished(self) -> int:
        """清理已退出的进程记录。"""
        finished = [
            pid
            for pid, relay_process in self._processes.items()
            if relay_process.process.returncode is not None
        ]
        for pid in finished:
            self._processes.pop(pid, None)
        return len(finished)
