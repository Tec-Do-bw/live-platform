from __future__ import annotations

import subprocess
from pathlib import Path


def cut_long_segment(input_path: Path, segment_duration: int = 8) -> list[Path]:
    output_pattern = input_path.with_suffix("").as_posix() + ".%00005d.ts"
    command = [
        "ffmpeg",
        "-i",
        str(input_path),
        "-c",
        "copy",
        "-segment_time",
        str(segment_duration),
        "-f",
        "segment",
        output_pattern,
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return sorted(input_path.parent.glob(f"{input_path.stem}.*.ts"))
