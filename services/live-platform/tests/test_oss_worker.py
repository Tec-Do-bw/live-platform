from __future__ import annotations

from pathlib import Path

from shared.config import OSSConfig
from upload.oss_worker import OSSWorker, _build_object_name


class FakeBucket:
    def __init__(self):
        self.put_calls: list[tuple[str, str]] = []
        self.sign_calls: list[tuple[str, str, int]] = []

    def put_object_from_file(self, object_name: str, file_path: str) -> None:
        self.put_calls.append((object_name, file_path))

    def sign_url(self, method: str, object_name: str, ttl_seconds: int) -> str:
        self.sign_calls.append((method, object_name, ttl_seconds))
        return f"https://oss.example.com/{object_name}"


def test_object_name_format(tmp_path):
    file_path = tmp_path / "00001.ts"
    file_path.write_bytes(b"video")
    config = OSSConfig(
        endpoint="https://oss.example.com",
        bucket_name="bucket",
        access_key_id="ak",
        access_key_secret="sk",
        prefix="realtime-video/",
        signed_url_ttl_seconds=15552000,
    )
    bucket = FakeBucket()
    worker = OSSWorker(config=config, bucket=bucket)

    url = worker._upload_sync(
        file_path,
        platform="tiktok",
        live_room_id="room123",
        record_start_time="20260623120000",
    )

    assert url == "https://oss.example.com/realtime-video/tiktok_room123_20260623120000_00001.ts"
    assert bucket.put_calls == [
        ("realtime-video/tiktok_room123_20260623120000_00001.ts", str(file_path)),
    ]
    assert bucket.sign_calls == [
        ("GET", "realtime-video/tiktok_room123_20260623120000_00001.ts", 15552000),
    ]
    assert not file_path.exists()


def test_build_object_name_helper():
    assert _build_object_name(
        "realtime-video/",
        Path("00001.ts"),
        platform="shopee",
        live_room_id="shop456",
        record_start_time="20260623120000",
    ) == "realtime-video/shopee_shop456_20260623120000_00001.ts"
