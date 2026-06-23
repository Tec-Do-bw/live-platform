from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from shared.config import KafkaConfig, settings
from shared.logger import get_logger

logger = get_logger(__name__)


def _format_timestamp(timestamp: float | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _build_segment_file_name(
    file_path: Path,
    platform: str = "",
    live_room_id: str = "",
    record_start_time: str = "",
) -> str:
    parts = [platform, live_room_id, record_start_time, file_path.name]
    return "_".join(part for part in parts if part)


class KafkaWorker:
    """Kafka 元数据推送 worker。"""

    def __init__(self, config: KafkaConfig | None = None, producer=None):
        self.config = config
        self._producer = producer

    def _get_producer(self):
        if self._producer is not None:
            return self._producer
        config = self.config or settings.kafka
        if not config.bootstrap_servers:
            raise RuntimeError("Kafka 配置不完整")
        from kafka import KafkaProducer

        servers = [server.strip() for server in config.bootstrap_servers.split(",") if server.strip()]
        self._producer = KafkaProducer(
            bootstrap_servers=servers,
            value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
        )
        return self._producer

    async def send_segment_metadata(
        self,
        room_id: str,
        file_path: Path,
        duration: float | None,
        video_url: str,
        platform: str = "",  # P2-5: 用于拼接 dataSource 字段
        live_room_id: str = "",
        record_start_time: str = "",
        metadata: dict | None = None,
        created_at: float | None = None,
        retry_count: int = 3,
    ) -> dict:
        """推送切片元数据到 Kafka。"""
        segment_file_name = _build_segment_file_name(file_path, platform, live_room_id or room_id, record_start_time)
        end_time = created_at if created_at is not None else None
        start_time = (created_at - duration) if (created_at is not None and duration is not None) else None
        payload = dict(metadata or {})
        payload.update(
            {
                "room_id": room_id,
                "roomID": payload.get("roomID") or payload.get("roomId") or room_id,
                "local_file_name": segment_file_name,
                "duration": duration,
                "videoUrl": video_url,
                "dataSource": f"live_crawler_{platform}_http" if platform else "",
                "createTime": payload.get("createTime") or _format_timestamp(created_at),
                "videoStartTime": payload.get("videoStartTime") or _format_timestamp(start_time),
                "videoEndTime": payload.get("videoEndTime") or _format_timestamp(end_time),
            }
        )
        last_error: Exception | None = None
        for attempt in range(1, retry_count + 1):
            try:
                producer = self._get_producer()
                config = self.config or settings.kafka
                producer.send(config.topic_name, value=payload)
                producer.flush()
                return payload
            except Exception as exc:
                last_error = exc
                logger.warning(f"Kafka 推送失败，准备重试 | room_id={room_id} attempt={attempt} error={exc}")
                await asyncio.sleep(min(attempt, 3))
        raise RuntimeError(f"Kafka 推送失败: {room_id}") from last_error
