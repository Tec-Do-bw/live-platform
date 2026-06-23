from __future__ import annotations

from pathlib import Path


def test_mediamtx_records_mpegts_segments():
    config_text = Path("config/mediamtx.yml").read_text(encoding="utf-8")

    assert "recordFormat: mpegts" in config_text
    assert "recordSegmentDuration: 10s" in config_text
    assert "runOnRecordSegmentComplete" in config_text
