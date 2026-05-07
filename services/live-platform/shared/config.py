from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    detect_interval_seconds: int = 60
    access_token: str = "AFDD0B4AD2EC172C586E2150770FBF9E"


@dataclass(frozen=True)
class MediaMTXConfig:
    api_base_url: str = "http://127.0.0.1:9997"
    rtmp_base_url: str = "rtmp://127.0.0.1:1935/live"
    record_root: Path = Path("/data/recordings")
    segment_timeout_seconds: int = 30


@dataclass(frozen=True)
class DatabaseConfig:
    sqlite_path: Path = Path("data/live-platform.sqlite3")


@dataclass(frozen=True)
class OSSConfig:
    endpoint: str = ""
    bucket_name: str = ""
    access_key_id: str = ""
    access_key_secret: str = ""
    prefix: str = "realtime-video/"
    signed_url_ttl_seconds: int = 86400 * 180


@dataclass(frozen=True)
class KafkaConfig:
    bootstrap_servers: str = ""
    topic_name: str = "liveTs"


@dataclass(frozen=True)
class Settings:
    server: ServerConfig
    mediamtx: MediaMTXConfig
    database: DatabaseConfig
    oss: OSSConfig
    kafka: KafkaConfig
    log_dir: Path


def load_settings() -> Settings:
    """从环境变量加载运行配置。"""
    return Settings(
        server=ServerConfig(
            host=_env("LIVE_PLATFORM_HOST", "0.0.0.0"),
            port=int(_env("LIVE_PLATFORM_PORT", "8080")),
            detect_interval_seconds=int(_env("LIVE_DETECT_INTERVAL_SECONDS", "60")),
            access_token=_env("LIVE_PLATFORM_ACCESS_TOKEN", "AFDD0B4AD2EC172C586E2150770FBF9E"),
        ),
        mediamtx=MediaMTXConfig(
            api_base_url=_env("MEDIAMTX_API_BASE_URL", "http://127.0.0.1:9997").rstrip("/"),
            rtmp_base_url=_env("MEDIAMTX_RTMP_BASE_URL", "rtmp://127.0.0.1:1935/live").rstrip("/"),
            record_root=Path(_env("MEDIAMTX_RECORD_ROOT", "/data/recordings")),
            segment_timeout_seconds=int(_env("SEGMENT_TIMEOUT_SECONDS", "30")),
        ),
        database=DatabaseConfig(
            sqlite_path=Path(_env("LIVE_PLATFORM_SQLITE_PATH", "data/live-platform.sqlite3")),
        ),
        oss=OSSConfig(
            endpoint=_env("OSS_ENDPOINT", ""),
            bucket_name=_env("OSS_BUCKET_NAME", ""),
            access_key_id=_env("OSS_ACCESS_KEY_ID", ""),
            access_key_secret=_env("OSS_ACCESS_KEY_SECRET", ""),
            prefix=_env("OSS_PREFIX", "realtime-video/"),
            signed_url_ttl_seconds=int(_env("OSS_SIGNED_URL_TTL_SECONDS", str(86400 * 180))),
        ),
        kafka=KafkaConfig(
            bootstrap_servers=_env("KAFKA_BOOTSTRAP_SERVERS", ""),
            topic_name=_env("KAFKA_TOPIC_NAME", "liveTs"),
        ),
        log_dir=Path(_env("LIVE_PLATFORM_LOG_DIR", "logs")),
    )


settings = load_settings()
