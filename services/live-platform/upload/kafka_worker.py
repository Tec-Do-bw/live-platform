from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from shared.config import KafkaConfig, settings
from shared.logger import get_logger
from shared.models import SegmentTask
from upload.legacy_naming import LegacySegmentName

logger = get_logger(__name__)


def md5_encrypt(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def _video_time_fields(file_stat: Any, duration: float | None) -> tuple[str, str, int]:
    start_time = str(int(getattr(file_stat, "st_ctime", 0) or 0))
    end_time = str(int(getattr(file_stat, "st_mtime", 0) or 0))
    fallback_duration = int(duration or 8)
    if end_time == start_time:
        end_time = str(int(start_time) + fallback_duration)
    interval_time = int(end_time) - int(start_time)
    return start_time, end_time, interval_time


def _is_shopee_task(task: SegmentTask) -> bool:
    if task.platform.lower() == "shopee":
        return True
    session = task.metadata.get("session")
    return isinstance(session, dict) and ("shop_id" in session or "session_id" in session)


def _build_tiktok_payload(
    *,
    task: SegmentTask,
    video_url: str,
    legacy_name: LegacySegmentName,
    file_stat: Any,
) -> dict:
    video_start_time, video_end_time, interval_time = _video_time_fields(file_stat, task.duration)
    metadata = dict(task.metadata or {})
    return {
        "roomID": task.room_id,
        "roomName": task.legacy_file_path,
        "intervalTime": interval_time,
        "createTime": task.creat_time,
        "videoStartTime": video_start_time,
        "videoEndTime": video_end_time,
        "batchID": str(metadata.get("roomId") or metadata.get("roomID") or metadata.get("batchID") or task.room_id),
        "UserID": str(metadata.get("id") or metadata.get("UserID") or ""),
        "videoIndex": legacy_name.video_index,
        "videoUrl": video_url,
        "uniID": md5_encrypt(video_url),
    }


def _build_shopee_payload(
    *,
    task: SegmentTask,
    video_url: str,
    legacy_name: LegacySegmentName,
    file_stat: Any,
) -> dict:
    video_start_time, video_end_time, interval_time = _video_time_fields(file_stat, task.duration)
    metadata = dict(task.metadata or {})
    session = metadata.get("session") if isinstance(metadata.get("session"), dict) else {}
    return {
        "roomID": task.room_id,
        "room_id": str(session.get("room_id") or metadata.get("room_id") or ""),
        "roomName": str(session.get("username") or task.legacy_file_path),
        "intervalTime": interval_time,
        "createTime": task.creat_time,
        "init_startTime": str(metadata.get("startTime") or metadata.get("init_startTime") or ""),
        "st_size": round(getattr(file_stat, "st_size", 0) / (1024 * 1024), 2),
        "videoStartTime": video_start_time,
        "videoEndTime": video_end_time,
        "batchID": str(session.get("session_id") or metadata.get("session_id") or ""),
        "UserID": str(session.get("uid") or metadata.get("UserID") or ""),
        "shop_id": str(session.get("shop_id") or metadata.get("shop_id") or ""),
        "nickname": str(session.get("nickname") or metadata.get("nickname") or ""),
        "member_cnt": session.get("member_cnt") or metadata.get("member_cnt") or "",
        "like_cnt": session.get("like_cnt") or metadata.get("like_cnt") or "",
        "start_time": session.get("start_time") or metadata.get("start_time") or "",
        "viewer_count": session.get("viewer_count") or metadata.get("viewer_count") or "",
        "chatroom_id": session.get("chatroom_id") or metadata.get("chatroom_id") or "",
        "videoIndex": legacy_name.video_index,
        "videoUrl": video_url,
        "uniID": md5_encrypt(video_url),
    }


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
        *,
        task: SegmentTask,
        video_url: str,
        legacy_name: LegacySegmentName,
        file_stat: Any,
        retry_count: int = 3,
    ) -> dict:
        """推送切片元数据到 Kafka。"""
        if _is_shopee_task(task):
            payload = _build_shopee_payload(
                task=task,
                video_url=video_url,
                legacy_name=legacy_name,
                file_stat=file_stat,
            )
        else:
            payload = _build_tiktok_payload(
                task=task,
                video_url=video_url,
                legacy_name=legacy_name,
                file_stat=file_stat,
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
                logger.warning(f"Kafka 推送失败，准备重试 | room_id={task.room_id} attempt={attempt} error={exc}")
                await asyncio.sleep(min(attempt, 3))
        raise RuntimeError(f"Kafka 推送失败: {task.room_id}") from last_error
