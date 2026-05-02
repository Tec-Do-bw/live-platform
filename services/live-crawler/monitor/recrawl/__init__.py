"""补采闭环模块

提供 auto_detect_and_recrawl 入口函数，在每轮采集结束后自动检测缺失并执行补采。
"""

from core.config import Settings
from utils.logger import logger


def auto_detect_and_recrawl(batch_id: str, mode: str = 'once') -> dict | None:
    """自动检测缺失 + 执行补采（在 finish_batch 之后调用）

    Args:
        batch_id: 当前采集批次 ID
        mode: 采集模式（'once' / 'full'），full 模式跳过自动补采

    Returns:
        补采统计 dict 或 None（跳过时返回 None）
    """
    # 全量模式跳过自动补采（全量采集本身会覆盖所有数据）
    if mode == 'full':
        logger.info('全量采集模式，跳过自动补采')
        return None

    # 检查补采开关
    recrawl_config = Settings.RECRAWL_CONFIG
    if not recrawl_config.get('enabled', True):
        logger.info('自动补采已关闭（RECRAWL_CONFIG.enabled=False），跳过')
        return None

    try:
        from monitor import get_monitor
        from monitor.recrawl.gap_detector import detect_and_create_tasks
        from monitor.recrawl.executor import execute_pending_tasks

        conn = get_monitor().conn

        # 1. 检测缺失并创建补采任务
        created = detect_and_create_tasks(conn, batch_id)
        logger.info(f'缺失检测完成：新建 {created} 个补采任务')

        if created == 0:
            logger.info('无缺失，跳过补采执行')
            return {'created': 0, 'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}

        # 2. 执行 pending 补采任务
        stats = execute_pending_tasks(conn)
        stats['created'] = created
        logger.info(
            f'自动补采完成: 新建 {created} 任务, '
            f'执行 {stats["total"]}, 成功 {stats["success"]}, '
            f'失败 {stats["failed"]}, 跳过 {stats["skipped"]}'
        )
        return stats

    except Exception as e:
        logger.error(f'自动补采异常: {e}')
        return None
