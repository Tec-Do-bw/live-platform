from __future__ import annotations

import json
from pathlib import Path

from shared.config import KafkaConfig, settings
from shared.logger import get_logger

logger = get_logger(__name__)


class KafkaWorker:
    """Kafka 元数据推送 worker。"""

    def __init__(self, config: KafkaConfig | None = None, producer=None):
        self.config = config or settings.kafka
        self._producer = producer

    def _get_producer(self):
        if self._producer is not None:
            return self._producer
        if not self.config.bootstrap_servers:
            raise RuntimeError("Kafka 配置不完整")
        from kafka import KafkaProducer

        servers = [server.strip() for server in self.config.bootstrap_servers.split(",") if server.strip()]
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
        retry_count: int = 3,
    ) -> dict:
        """推送切片元数据到 Kafka。"""
        payload = {
            "room_id": room_id,
            "local_file_name": file_path.name,
            "duration": duration,
            "videoUrl": video_url,
        }
        last_error: Exception | None = None
        for attempt in range(1, retry_count + 1):
            try:
                producer = self._get_producer()
                producer.send(self.config.topic_name, value=payload)
                producer.flush()
                return payload
            except Exception as exc:
                last_error = exc
                logger.warning("Kafka 推送失败，准备重试 | room_id=%s attempt=%s error=%s", room_id, attempt, exc)
        raise RuntimeError(f"Kafka 推送失败: {room_id}") from last_error
