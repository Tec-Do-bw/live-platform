from __future__ import annotations

from ffmpeg.relay import FFmpegRelayController
from shared.config import MediaMTXConfig


def test_build_ffmpeg_command_targets_mediamtx():
    controller = FFmpegRelayController(MediaMTXConfig(rtmp_base_url="rtmp://localhost:1935/live"))

    command = controller.build_command("https://example.com/live.flv", "tiktok-123")

    assert command[-1] == "rtmp://localhost:1935/live/tiktok-123"
    assert "-i" in command
    assert "https://example.com/live.flv" in command
    assert command[-3:] == ["-f", "flv", "rtmp://localhost:1935/live/tiktok-123"]
