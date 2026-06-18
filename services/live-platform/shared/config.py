from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.apollo_config import fetch_apollo_config


class ConfigError(RuntimeError):
    """Apollo 配置缺失或格式错误。"""


def _raw_value(apollo_config: dict[str, Any], name: str, *aliases: str) -> str:
    for key in (name, *aliases):
        value = apollo_config.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    key_list = ", ".join((name, *aliases))
    raise ConfigError(f"Apollo 缺少必填配置: {key_list}")


def _config_int(apollo_config: dict[str, Any], name: str, *aliases: str) -> int:
    raw = _raw_value(apollo_config, name, *aliases)
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Apollo 配置必须是整数: {name}") from exc


def _kafka_servers(apollo_config: dict[str, Any]) -> str:
    raw = _raw_value(apollo_config, "kafkaPro", "kafkaAddress")
    try:
        parsed = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return raw
    if isinstance(parsed, (list, tuple)):
        servers = [str(server).strip() for server in parsed if str(server).strip()]
        if servers:
            return ",".join(servers)
        raise ConfigError("Apollo 配置 kafkaPro/kafkaAddress 为空列表")
    return str(parsed)


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    detect_interval_seconds: int
    access_token: str
    max_active_recordings: int


@dataclass(frozen=True)
class MediaMTXConfig:
    api_base_url: str = ""
    rtmp_base_url: str = ""
    record_root: Path = Path("/data/recordings")
    segment_timeout_seconds: int = 30


@dataclass(frozen=True)
class RedisConfig:
    host: str
    port: int
    password: str
    db: int


@dataclass(frozen=True)
class OSSConfig:
    endpoint: str
    bucket_name: str
    access_key_id: str
    access_key_secret: str
    prefix: str
    signed_url_ttl_seconds: int


@dataclass(frozen=True)
class KafkaConfig:
    bootstrap_servers: str
    topic_name: str


@dataclass(frozen=True)
class UploadConfig:
    worker_count: int


@dataclass(frozen=True)
class Settings:
    server: ServerConfig
    mediamtx: MediaMTXConfig
    redis: RedisConfig
    oss: OSSConfig
    kafka: KafkaConfig
    upload: UploadConfig
    log_dir: Path


def load_settings(apollo_config: dict[str, Any] | None = None) -> Settings:
    """只从 Apollo 配置加载运行参数。"""
    config = fetch_apollo_config() if apollo_config is None else apollo_config
    return Settings(
        server=ServerConfig(
            host=_raw_value(config, "livePlatformHost"),
            port=_config_int(config, "livePlatformPort"),
            detect_interval_seconds=_config_int(config, "livePlatformDetectIntervalSeconds"),
            access_token=_raw_value(config, "livePlatformAccessToken"),
            max_active_recordings=_config_int(config, "cutliveNumber"),
        ),
        mediamtx=MediaMTXConfig(
            api_base_url=_raw_value(config, "mediaMtxApiBaseUrl").rstrip("/"),
            rtmp_base_url=_raw_value(config, "mediaMtxRtmpBaseUrl").rstrip("/"),
            record_root=Path(_raw_value(config, "mediaMtxRecordRoot")),
            segment_timeout_seconds=_config_int(config, "segmentTimeoutSeconds"),
        ),
        redis=RedisConfig(
            host=_raw_value(config, "redisHost"),
            port=_config_int(config, "redisPort"),
            password=_raw_value(config, "redisPassword"),
            db=_config_int(config, "redisDb"),
        ),
        oss=OSSConfig(
            endpoint=_raw_value(config, "endpoint"),
            bucket_name=_raw_value(config, "bucket_name"),
            access_key_id=_raw_value(config, "access_key_id"),
            access_key_secret=_raw_value(config, "access_key_secret"),
            prefix=_raw_value(config, "ossPrefix"),
            signed_url_ttl_seconds=_config_int(config, "ossSignedUrlTtlSeconds"),
        ),
        kafka=KafkaConfig(
            bootstrap_servers=_kafka_servers(config),
            topic_name=_raw_value(config, "topic_name"),
        ),
        upload=UploadConfig(
            worker_count=_config_int(config, "uploadWorkerCount"),
        ),
        log_dir=Path(_raw_value(config, "livePlatformLogDir")),
    )


class LazySettings:
    """延迟加载 Apollo 配置，避免 import 阶段访问网络。"""

    def __init__(self) -> None:
        self._settings: Settings | None = None

    def load(self) -> Settings:
        if self._settings is None:
            self._settings = load_settings()
        return self._settings

    def override(self, value: Settings | None) -> None:
        self._settings = value

    def __getattr__(self, name: str) -> Any:
        return getattr(self.load(), name)


settings = LazySettings()
