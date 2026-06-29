"""一次性脚本: 把 live-stream 新点分 key 写入 Apollo DEV/dev01 并发布。

使用方式（本地运行,不会碰生产凭证）:
    set APOLLO_OPENAPI_TOKEN=<你的 Apollo OpenAPI token>
    cd services/live-stream
    python scripts/seed_apollo_config.py

约定:
- 只写 DEV/dev01,生产集群（PRO 等）请自行复核后再跑
- 新旧 key 并存,脚本不删除任何旧 key
- 通用 key 的 value 请从 Apollo 现有旧 key 抄过来,保持一致
- kafka.servers 用逗号分隔字符串,不要写成 list 字面量
"""
from __future__ import annotations

import os
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.apollo.openapi_writer import publish_namespace, update_apollo_item


PORTAL_URL = os.environ.get("APOLLO_PORTAL_URL", "http://apollo-portal.tec-develop.com")
ENV = "dev"
APP_ID = "live-spider"
CLUSTER = "dev01"
NAMESPACE = "application"
OPERATOR = os.environ.get("APOLLO_OPERATOR", "bw.xie")


# key -> (value, comment)
CONFIG_ITEMS: dict[str, tuple[str, str]] = {
    # ===== 通用 key（value 从对应旧 key 抄过来）=====
    "redis.host": ("", "Redis 主机（迁移自 redisHost）"),
    "redis.port": ("6379", "Redis 端口（迁移自 redisPort）"),
    "redis.password": ("", "Redis 密码（迁移自 redisPassword）"),
    "redis.db": ("0", "Redis DB（迁移自 redisDb）"),
    "kafka.servers": ("", "Kafka broker 逗号分隔（迁移自 kafkaPro，去掉 list 字面量）"),
    "kafka.topic": ("liveTs", "Kafka topic（迁移自 topic_name）"),
    "oss.endpoint": ("", "OSS endpoint（迁移自 endpoint）"),
    "oss.bucket_name": ("", "OSS bucket（迁移自 bucket_name）"),
    "oss.access_key_id": ("", "OSS AK ID（迁移自 access_key_id）"),
    "oss.access_key_secret": ("", "OSS AK Secret（迁移自 access_key_secret）"),
    "oss.region": ("", "OSS region（迁移自 oss_region）"),
    # ===== live-stream 特有 key =====
    "live_stream.primary_node_url": ("http://192.168.46.39:8080", "live-monitor 主节点"),
    "live_stream.backup_node_url": ("http://192.168.46.39:8080", "live-monitor 备节点"),
    "live_stream.room_source": ("http", "房间来源 http|redis"),
    "live_stream.worker_id": ("", "工作节点 ID,留空则自动生成"),
    "live_stream.max_retries": ("12", "FFmpeg 最大重试次数"),
    "live_stream.retry_interval_seconds": ("1", "重试初始间隔（秒）"),
    "live_stream.retry_backoff": ("1.5", "重试退避因子"),
    "live_stream.max_retry_interval_seconds": ("30", "最大重试间隔（秒）"),
    "live_stream.analyze_duration_us": ("5000000", "FFmpeg analyzeduration（微秒）"),
    "live_stream.probe_size_bytes": ("10000000", "FFmpeg probesize（字节）"),
    "live_stream.heartbeat_interval_seconds": ("10", "心跳检测间隔（秒）"),
    "live_stream.no_data_timeout_seconds": ("25", "无数据超时（秒）"),
    "live_stream.lease_ttl_seconds": ("360", "Redis 租约 TTL（秒）"),
}


def main() -> None:
    missing = [key for key, (value, _) in CONFIG_ITEMS.items() if not value.strip()]
    if missing:
        print("注意: 以下 key 仍为空, 请确认后再运行:")
        for key in missing:
            print(f"  - {key}")

    for key, (value, comment) in CONFIG_ITEMS.items():
        update_apollo_item(
            PORTAL_URL,
            ENV,
            APP_ID,
            CLUSTER,
            NAMESPACE,
            key=key,
            value=value,
            operator=OPERATOR,
            comment=comment,
        )
        print(f"写入 {key} = {value!r}")

    publish_namespace(
        PORTAL_URL,
        ENV,
        APP_ID,
        CLUSTER,
        NAMESPACE,
        operator=OPERATOR,
        release_title="live-stream 点分 key 迁移",
        release_comment="新增点分风格 key, 旧 key 保留",
    )
    print("发布完成。")


if __name__ == "__main__":
    main()
