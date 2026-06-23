from __future__ import annotations

import subprocess
from pathlib import Path

from utils.video import cut_long_segment


def test_cut_long_segment_invokes_ffmpeg_and_returns_split_files(monkeypatch, tmp_path):
    input_path = tmp_path / "segment.ts"
    input_path.write_bytes(b"video")
    captured_command = []

    def fake_run(command, stdout, stderr, check):
        captured_command.extend(command)
        assert stdout == subprocess.DEVNULL
        assert stderr == subprocess.DEVNULL
        assert check is True
        Path(command[-1].replace("%00005d", "00000")).write_bytes(b"part0")
        Path(command[-1].replace("%00005d", "00001")).write_bytes(b"part1")

    monkeypatch.setattr("utils.video.subprocess.run", fake_run)

    result = cut_long_segment(input_path, segment_duration=8)

    assert captured_command == [
        "ffmpeg",
        "-i",
        str(input_path),
        "-c",
        "copy",
        "-segment_time",
        "8",
        "-f",
        "segment",
        input_path.with_suffix("").as_posix() + ".%00005d.ts",
    ]
    assert result == [tmp_path / "segment.00000.ts", tmp_path / "segment.00001.ts"]
