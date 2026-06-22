from __future__ import annotations

import asyncio

from shared.logger import get_logger
from shared.models import SegmentTask
from upload.kafka_worker import KafkaWorker
from upload.oss_worker import OSSWorker

logger = get_logger(__name__)


class UploadCoordinator:
    """串联 OSS 上传与 Kafka 推送。"""

    def __init__(self, oss_worker: OSSWorker | None = None, kafka_worker: KafkaWorker | None = None):
        self.oss_worker = oss_worker or OSSWorker()
        self.kafka_worker = kafka_worker or KafkaWorker()
        self.queue: asyncio.Queue[SegmentTask] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._stopping = False

    async def enqueue(self, task: SegmentTask) -> None:
        await self.queue.put(task)

    async def process_one(self, task: SegmentTask) -> dict:
        """处理单个切片任务：OSS 上传 → Kafka 推送（串行）"""
        video_url = None
        try:
            # 1. OSS 上传（成功后本地文件被删除）
            video_url = await self.oss_worker.upload_segment(task.file_path)

            # 2. Kafka 推送（OSS 成功后才推送，避免状态漂移）
            payload = await self.kafka_worker.send_segment_metadata(
                room_id=task.room_id,
                file_path=task.file_path,
                duration=task.duration,
                video_url=video_url,
                platform=task.platform,  # P2-5: 透传 platform 供 Kafka 拼 dataSource
            )
            return payload

        except Exception as e:
            # Kafka 推送失败但 OSS 已成功 → 记录死信（后续可扩展为死信队列）
            if video_url:
                logger.error(
                    f"Kafka 推送失败但 OSS 已成功（数据漂移风险） | "
                    f"room_id={task.room_id} video_url={video_url} error={e}",
                    exc_info=True,
                )
            raise

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
