from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from shared.config import settings
from shared.logger import get_logger
from shared.models import SegmentTask
from upload.kafka_worker import KafkaWorker
from upload.legacy_naming import (
    LegacySegmentName,
    build_legacy_segment_name,
    build_split_segment_name,
)
from upload.oss_worker import OSSWorker
from utils.video import cut_long_segment

logger = get_logger(__name__)


class UploadCoordinator:
    """串联 OSS 上传与 Kafka 推送。"""

    def __init__(
        self,
        oss_worker: OSSWorker | None = None,
        kafka_worker: KafkaWorker | None = None,
        long_segment_cutter: Callable[[Path], list[Path]] | None = None,
    ):
        self.oss_worker = oss_worker or OSSWorker()
        self.kafka_worker = kafka_worker or KafkaWorker()
        self.queue: asyncio.Queue[SegmentTask] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._stopping = False
        self.long_segment_cutter = long_segment_cutter or cut_long_segment

    async def enqueue(self, task: SegmentTask) -> None:
        await self.queue.put(task)

    async def process_one(self, task: SegmentTask) -> dict:
        """处理单个切片任务：OSS 上传 → Kafka 推送（串行）"""
        if task.duration is not None and task.duration > 12:
            return await self._process_long_segment(task)
        legacy_name = self._build_legacy_name(task)
        return await self._upload_and_send(task, task.file_path, legacy_name)

    def _build_legacy_name(self, task: SegmentTask, *, sub_sequence: int | None = None) -> LegacySegmentName:
        oss_prefix = settings.oss.prefix
        file_path = task.legacy_file_path or str(task.metadata.get("filePath") or "")
        creat_time = task.creat_time or str(task.metadata.get("CreatTime") or "")
        if sub_sequence is None:
            return build_legacy_segment_name(
                oss_prefix=oss_prefix,
                file_path=file_path,
                creat_time=creat_time,
                sequence=task.segment_sequence,
            )
        return build_split_segment_name(
            oss_prefix=oss_prefix,
            file_path=file_path,
            creat_time=creat_time,
            sequence=task.segment_sequence,
            sub_sequence=sub_sequence,
        )

    async def _upload_and_send(self, task: SegmentTask, file_path: Path, legacy_name: LegacySegmentName) -> dict:
        file_stat = file_path.stat()
        video_url = await self.oss_worker.upload_segment(file_path, object_name=legacy_name.object_name)
        try:
            payload = await self.kafka_worker.send_segment_metadata(
                task=replace(task, file_path=file_path),
                video_url=video_url,
                legacy_name=legacy_name,
                file_stat=file_stat,
            )
            return payload
        except Exception as exc:
            logger.error(
                f"Kafka 推送失败但 OSS 已成功（数据漂移风险） | "
                f"room_id={task.room_id} video_url={video_url} error={exc}",
                exc_info=True,
            )
            raise

    async def _process_long_segment(self, task: SegmentTask) -> dict:
        split_paths = self.long_segment_cutter(task.file_path)
        if not split_paths:
            raise RuntimeError(f"长切片拆分失败: {task.file_path}")
        payload: dict = {}
        for sub_sequence, split_path in enumerate(split_paths):
            split_task = replace(task, file_path=split_path, duration=8, segment_sequence=task.segment_sequence)
            legacy_name = self._build_legacy_name(split_task, sub_sequence=sub_sequence)
            payload = await self._upload_and_send(split_task, split_path, legacy_name)
        if task.file_path.exists():
            task.file_path.unlink()
        return payload

    async def start(self, worker_count: int = 2) -> None:
        self._stopping = False
        for index in range(worker_count):
            self._workers.append(asyncio.create_task(self._worker_loop(index)))

    async def stop(self) -> None:
        self._stopping = True
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _worker_loop(self, index: int) -> None:
        while not self._stopping:
            task = await self.queue.get()
            try:
                await self.process_one(task)
                logger.info(f"切片处理完成 | room_id={task.room_id} file={task.file_path} worker={index}")
            except Exception:
                logger.exception(f"切片处理失败 | room_id={task.room_id} file={task.file_path}")
            finally:
                self.queue.task_done()


upload_coordinator = UploadCoordinator()
