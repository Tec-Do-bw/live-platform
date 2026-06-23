from __future__ import annotations

import asyncio
from pathlib import Path

from shared.config import OSSConfig, settings
from shared.logger import get_logger

logger = get_logger(__name__)


class OSSWorker:
    """OSS 上传 worker。"""

    def __init__(self, config: OSSConfig | None = None, bucket=None):
        self.config = config
        self._bucket = bucket

    def _get_bucket(self):
        if self._bucket is not None:
            return self._bucket
        config = self.config or settings.oss
        if not all(
            [
                config.endpoint,
                config.bucket_name,
                config.access_key_id,
                config.access_key_secret,
            ]
        ):
            raise RuntimeError("OSS 配置不完整")
        import oss2

        auth = oss2.Auth(config.access_key_id, config.access_key_secret)
        self._bucket = oss2.Bucket(auth, config.endpoint, config.bucket_name)
        return self._bucket

    async def upload_segment(
        self,
        file_path: Path,
        object_name: str,
        retry_count: int = 3,
    ) -> str:
        """上传切片文件，成功后删除本地文件。"""
        last_error: Exception | None = None
        for attempt in range(1, retry_count + 1):
            try:
                return await asyncio.to_thread(
                    self._upload_sync,
                    file_path,
                    object_name,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(f"OSS 上传失败，准备重试 | file={file_path} attempt={attempt} error={exc}")
                await asyncio.sleep(min(attempt, 3))
        raise RuntimeError(f"OSS 上传失败: {file_path}") from last_error

    def _upload_sync(
        self,
        file_path: Path,
        object_name: str,
    ) -> str:
        bucket = self._get_bucket()
        config = self.config or settings.oss
        bucket.put_object_from_file(object_name, str(file_path))
        url = bucket.sign_url("GET", object_name, config.signed_url_ttl_seconds)
        try:
            file_path.unlink()
        except FileNotFoundError:
            pass
        return str(url)
