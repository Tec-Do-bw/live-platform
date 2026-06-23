from __future__ import annotations

import pytest

from upload.legacy_naming import (
    LegacySegmentName,
    build_legacy_segment_name,
    build_split_segment_name,
)


def test_build_legacy_segment_name_uses_file_path_creat_time_and_zero_based_index():
    result = build_legacy_segment_name(
        oss_prefix="realtime-video/",
        file_path="corollashoes_th",
        creat_time="1752982646",
        sequence=0,
    )

    assert result == LegacySegmentName(
        basename="corollashoes_th_1752982646_00000.ts",
        object_name="realtime-video/corollashoes_th_1752982646_00000.ts",
        video_index="0",
    )


def test_build_split_segment_name_matches_legacy_cut_big_file_pattern():
    result = build_split_segment_name(
        oss_prefix="realtime-video/",
        file_path="corollashoes_th",
        creat_time="1752982646",
        sequence=0,
        sub_sequence=2,
    )

    assert result.basename == "corollashoes_th_1752982646_00000.00002.ts"
    assert result.object_name == "realtime-video/corollashoes_th_1752982646_00000.00002.ts"
    assert result.video_index == "0.2"


def test_build_legacy_segment_name_rejects_missing_file_path():
    with pytest.raises(ValueError, match="filePath"):
        build_legacy_segment_name(
            oss_prefix="realtime-video/",
            file_path="",
            creat_time="1752982646",
            sequence=0,
        )
