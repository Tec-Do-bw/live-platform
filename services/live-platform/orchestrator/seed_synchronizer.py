"""MySQL → Redis 种子同步器

定期从 MySQL 表 live_streaming_room 同步种子房间到 Redis，
对齐 live-monitor 生产逻辑（main.py:select_Info）。
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from shared.config import settings
from shared.logger import get_logger
from shared.redis_store import RedisRoomRepository
from shared.models import MonitoredRoom
from utils.db_pool import db_pool

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class SeedSynchronizer:
    """MySQL → Redis 种子同步器"""

    def __init__(self, repository: RedisRoomRepository | None = None):
        self.repository = repository or RedisRoomRepository()
        self._last_collection_ids: set[str] = set()

    async def sync_once(self) -> dict[str, int]:
        """
        执行一次全量同步

        Returns:
            dict: {'added': 新增数, 'removed': 移除数, 'total': 总数}
        """
        try:
            # 1. 从 MySQL 读取种子（对齐 live-monitor SQL）
            seeds = await asyncio.to_thread(self._fetch_seeds_from_mysql)
            current_collection_ids = {seed.collection_id for seed in seeds}

            # 2. 识别新增和下线房间
            added_ids = current_collection_ids - self._last_collection_ids
            removed_ids = self._last_collection_ids - current_collection_ids

            # 3. 写入 Redis（新增 + 更新）
            for seed in seeds:
                if seed.collection_id in added_ids:
                    # 新增房间：重置 allocation_status = "0"（对齐 live-monitor:646）
                    await self.repository.upsert_monitored_room(
                        MonitoredRoom(
                            collection_id=seed.collection_id,
                            platform=seed.platform,
                            room_url=seed.room_url,
                            enabled=True,
                        )
                    )
                    logger.info(
                        f"种子同步-新增 | collection_id={seed.collection_id} "
                        f"platform={seed.platform} url={seed.room_url}"
                    )

            # 4. 从 Redis 删除下线房间（软删除：直接删投影，对齐 live-monitor:656-664）
            for removed_id in removed_ids:
                await self._remove_from_redis(removed_id)
                logger.info(f"种子同步-下线 | collection_id={removed_id}")

            # 5. 更新内存快照
            self._last_collection_ids = current_collection_ids

            logger.info(
                f"种子同步完成 | total={len(seeds)} added={len(added_ids)} removed={len(removed_ids)}"
            )
            return {
                "added": len(added_ids),
                "removed": len(removed_ids),
                "total": len(seeds),
            }

        except Exception as e:
            logger.error(f"种子同步失败: {e}", exc_info=True)
            return {"added": 0, "removed": 0, "total": 0}

    def _fetch_seeds_from_mysql(self) -> list[MonitoredRoom]:
        """
        从 MySQL 读取种子房间（同步调用，经 asyncio.to_thread 包装）

        SQL 对齐 live-monitor main.py:628，补充 collection_id + platform 列
        """
        sql = """
            SELECT room_id, room_url, allocation_status, collection_id, platform
            FROM live_streaming_room
            WHERE local_status = 1
        """
        try:
            rows = db_pool.execute_query(sql)
            if not rows:
                logger.warning("MySQL 种子表为空（local_status=1 无数据）")
                return []

            seeds = []
            for row in rows:
                # db_pool 默认返回元组，按列序解包
                room_id, room_url, allocation_status, collection_id, platform = row
                seeds.append(
                    MonitoredRoom(
                        collection_id=collection_id,
                        platform=platform.lower() if platform else "unknown",
                        room_url=room_url,
                        enabled=True,
                    )
                )

            logger.debug(f"MySQL 种子查询成功 | count={len(seeds)}")
            return seeds

        except Exception as e:
            logger.error(f"MySQL 种子查询失败: {e}", exc_info=True)
            # 查询失败时返回空列表，避免误删 Redis 已有数据
            return []

    async def _remove_from_redis(self, collection_id: str) -> None:
        """从 Redis 删除下线房间的 seed + config + status"""
        try:
            client = self.repository._client
            # 从种子 Set 删除
            await client.srem("live:monitor:collections", collection_id)
            # 删除 config 和 status key
            await client.delete(
                f"live:collection:{collection_id}:config",
                f"live:collection:{collection_id}:status",
            )
        except Exception as e:
            logger.warning(f"Redis 删除失败 | collection_id={collection_id} error={e}")


# 全局单例
seed_synchronizer = SeedSynchronizer()
