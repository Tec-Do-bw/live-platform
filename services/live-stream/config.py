"""live-stream 配置访问层（门面）。

所有业务配置统一从 Apollo 读取（唯一权威源）。
- 流控参数/节点 URL: 读取点实时调用,享热更新,禁止存模块级常量
- 连接类配置（Redis/Kafka/OSS）: 由调用方启动时读一次
仅 APOLLO_URL/APOLLOID/DEPLOY_ENV 走环境变量（见 core/apollo/__init__.py）。
"""
from __future__ import annotations

import os
import socket

from core.apollo import APOLLO


def _get_str(key: str, default: str = "") -> str:
    val = APOLLO.get_value(key, default_val=default)
    return default if val is None else str(val)


def _get_int(key: str, default: int, minimum: int | None = None) -> int:
    raw = APOLLO.get_value(key, default_val=str(default))
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = default
    return max(val, minimum) if minimum is not None else val


def _get_float(key: str, default: float, minimum: float | None = None) -> float:
    raw = APOLLO.get_value(key, default_val=str(default))
    try:
        val = float(raw)
    except (TypeError, ValueError):
        val = default
    return max(val, minimum) if minimum is not None else val


# ========== 连接类配置（启动读一次）==========
def redis_config() -> dict[str, object]:
    """Redis 连接参数。"""
    return {
        "host": _get_str("redis.host"),
        "port": _get_int("redis.port", 6379),
        "password": _get_str("redis.password") or None,
        "db": _get_int("redis.db", 0),
    }


def kafka_servers() -> list[str]:
    """Kafka broker 列表。值为逗号分隔字符串,取出即用,不再 eval。"""
    raw = _get_str("kafka.servers")
    return [s.strip() for s in raw.split(",") if s.strip()]


def kafka_topic() -> str:
    return _get_str("kafka.topic", "liveTs")


def oss_config() -> dict[str, str]:
    """阿里云 OSS 连接参数。"""
    return {
        "endpoint": _get_str("oss.endpoint"),
        "bucket_name": _get_str("oss.bucket_name"),
        "access_key_id": _get_str("oss.access_key_id"),
        "access_key_secret": _get_str("oss.access_key_secret"),
    }


def cut_live_number() -> int:
    """单房间切片积压阈值（原 cutliveNumber 通用 key,保留原名）。"""
    return _get_int("cutliveNumber", 4)


# ========== 主备节点（实时,热更新）==========
def primary_node_url() -> str:
    return _get_str("live_stream.primary_node_url", "http://192.168.46.39:8080")


def backup_node_url() -> str:
    return _get_str("live_stream.backup_node_url", "http://192.168.46.39:8080")


# ========== 房间来源 / worker（实时）==========
def is_redis_room_source() -> bool:
    return _get_str("live_stream.room_source", "http").lower() == "redis"


def worker_id() -> str:
    configured = _get_str("live_stream.worker_id")
    if configured:
        return configured
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "unknown"
    return f"{socket.gethostname()}:{local_ip}:{os.getpid()}"


def stream_lease_ttl_seconds() -> int:
    return _get_int("live_stream.lease_ttl_seconds", 360)


# ========== FFmpeg 流控参数（实时,热更新）==========
def stream_max_retries() -> int:
    return _get_int("live_stream.max_retries", 12, minimum=1)


def stream_retry_interval_seconds() -> int:
    return _get_int("live_stream.retry_interval_seconds", 1, minimum=1)


def stream_retry_backoff() -> float:
    return _get_float("live_stream.retry_backoff", 1.5, minimum=1.0)


def stream_max_retry_interval_seconds() -> int:
    return _get_int("live_stream.max_retry_interval_seconds", 30, minimum=1)


def stream_analyze_duration_us() -> int:
    return _get_int("live_stream.analyze_duration_us", 5000000, minimum=1000000)


def stream_probe_size_bytes() -> int:
    return _get_int("live_stream.probe_size_bytes", 10000000, minimum=1000000)


def stream_heartbeat_interval_seconds() -> int:
    return _get_int("live_stream.heartbeat_interval_seconds", 10, minimum=5)


def stream_no_data_timeout_seconds() -> int:
    return _get_int("live_stream.no_data_timeout_seconds", 25, minimum=10)
