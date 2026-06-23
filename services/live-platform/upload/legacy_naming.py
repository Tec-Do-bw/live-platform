from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegacySegmentName:
    basename: str
    object_name: str
    video_index: str


def _normalize_component(value: str, field_name: str) -> str:
    normalized = str(value or "").replace("\\", "/").split("/")[-1].strip()
    if not normalized:
        raise ValueError(f"legacy segment naming requires {field_name}")
    return normalized


def _normalize_prefix(prefix: str) -> str:
    if not prefix:
        raise ValueError("legacy segment naming requires ossPrefix")
    return prefix if prefix.endswith("/") else f"{prefix}/"


def build_legacy_segment_name(
    *,
    oss_prefix: str,
    file_path: str,
    creat_time: str,
    sequence: int,
) -> LegacySegmentName:
    safe_file_path = _normalize_component(file_path, "filePath")
    safe_creat_time = _normalize_component(creat_time, "CreatTime")
    basename = f"{safe_file_path}_{safe_creat_time}_{sequence:05d}.ts"
    return LegacySegmentName(
        basename=basename,
        object_name=f"{_normalize_prefix(oss_prefix)}{basename}",
        video_index=str(sequence),
    )


def build_split_segment_name(
    *,
    oss_prefix: str,
    file_path: str,
    creat_time: str,
    sequence: int,
    sub_sequence: int,
) -> LegacySegmentName:
    safe_file_path = _normalize_component(file_path, "filePath")
    safe_creat_time = _normalize_component(creat_time, "CreatTime")
    basename = f"{safe_file_path}_{safe_creat_time}_{sequence:05d}.{sub_sequence:05d}.ts"
    return LegacySegmentName(
        basename=basename,
        object_name=f"{_normalize_prefix(oss_prefix)}{basename}",
        video_index=f"{sequence}.{sub_sequence}",
    )
