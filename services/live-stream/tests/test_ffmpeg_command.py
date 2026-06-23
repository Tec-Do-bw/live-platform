import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from TT_client import FFmpegStreamManager, build_live_url_candidates


def test_tiktok_ffmpeg_command_maps_only_first_video_and_audio_streams():
    manager = FFmpegStreamManager()

    command = manager.build_ffmpeg_command(
        "https://pull.example/live.flv",
        "/tmp/live_%05d.ts",
        segment_time=8,
        platform="tiktok",
    )

    assert "-copy_unknown" not in command
    assert not any(command[index:index + 2] == ["-map", "0"] for index in range(len(command) - 1))
    assert ["-map", "0:v:0?"] == command[command.index("-map"):command.index("-map") + 2]
    assert "0:a:0?" in command
    assert "-dn" in command
    assert "-sn" in command


def test_build_live_url_candidates_dedupes_and_skips_only_audio():
    candidates = build_live_url_candidates(
        {
            "flv_url": "https://pull.example/main.flv",
            "play_urls": [
                "https://pull.example/main.flv",
                "https://pull.example/main.flv?only_audio=1",
                "",
                "error",
                "https://pull.example/backup.flv",
            ],
        }
    )

    assert candidates == [
        "https://pull.example/main.flv",
        "https://pull.example/backup.flv",
    ]
