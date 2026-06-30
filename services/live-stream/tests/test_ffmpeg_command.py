import os
import sys
import types
import importlib

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeApollo:
    def get_value(self, key, default_val=None, namespace="application"):
        return default_val


@pytest.fixture
def tt_module(monkeypatch):
    fake_module = types.ModuleType("core.apollo")
    fake_module.APOLLO = FakeApollo()

    previous_tt = sys.modules.pop("TT_client", None)
    previous_config = sys.modules.pop("config", None)

    monkeypatch.setitem(sys.modules, "core.apollo", fake_module)

    tt_client = importlib.import_module("TT_client")

    try:
        yield tt_client
    finally:
        sys.modules.pop("TT_client", None)
        sys.modules.pop("config", None)
        if previous_tt is not None:
            sys.modules["TT_client"] = previous_tt
        if previous_config is not None:
            sys.modules["config"] = previous_config


def test_tiktok_ffmpeg_command_maps_only_first_video_and_audio_streams(tt_module):
    manager = tt_module.FFmpegStreamManager()

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


def test_build_live_url_candidates_dedupes_and_skips_only_audio(tt_module):
    candidates = tt_module.build_live_url_candidates(
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
