"""恢复补采任务生成器

检测登出期间的缺失数据，生成恢复补采任务。
"""

import sqlite3
from datetime import datetime

from utils.logger import logger
from monitor.recrawl.models import create_task_auto


def detect_logout_gaps(
    conn: sqlite3.Connection,
    account_id: str,
    group_name: str,
    logout_at: datetime,
    login_at: datetime,
) -> list[dict]:
    """检测登出期间的缺失数据

    Args:
        conn: 数据库连接
        account_id: 账号ID
        group_name: 分组名称
        logout_at: 登出时间戳
        login_at: 登录恢复时间戳

    Returns:
        缺失记录列表，格式：[{
            'batch_id': str,
            'account_id': str,
            'room_id': str,
            'target_date': str,
            'api_type': str,
            'level': str  # account/daily/room
        }]
    """
    try:
        logout_at_str = logout_at.isoformat()
        login_at_str = login_at.isoformat()

        # 查询登出期间 status=invalid 的采集记录
        rows = conn.execute(
            """SELECT DISTINCT batch_id, account_id, room_id, api_type
               FROM collection_records
               WHERE account_id = ?
                 AND status = 'invalid'
                 AND collected_at >= ?
                 AND collected_at <= ?""",
            (account_id, logout_at_str, login_at_str),
        ).fetchall()

        gaps = []
        for row in rows:
            gap = {
                'batch_id': row['batch_id'],
                'account_id': row['account_id'],
                'room_id': row['room_id'] or '',
                'target_date': '',  # 从 daily_collection_status 获取
                'api_type': row['api_type'],
                'level': 'room' if row['room_id'] else 'account',
            }
            gaps.append(gap)

        logger.info(f'检测到账号 {account_id} 登出期间有 {len(gaps)} 条缺失数据')
        return gaps

    except Exception as e:
        logger.error(f'检测登出期间缺失数据失败: {e}')
        return []


def create_recovery_tasks(
    conn: sqlite3.Connection,
    gaps: list[dict],
    recovery_batch_id: str,
) -> int:
    """创建恢复补采任务

    Args:
        conn: 数据库连接
        gaps: 缺失记录列表
        recovery_batch_id: 恢复补采批次ID

    Returns:
        创建的任务数
    """
    try:
        tasks_created = 0
        for gap in gaps:
            task_id = create_task_auto(
                conn,
                batch_id=gap['batch_id'],
                account_id=gap['account_id'],
                group_name='',  # 从 account_sessions 获取
                room_id=gap['room_id'],
                target_date=gap['target_date'],
                api_type=gap['api_type'],
                level=gap['level'],
            )
            if task_id:
                tasks_created += 1

                # 更新 source 为 logout_recovery
                conn.execute(
                    "UPDATE recrawl_tasks SET source='logout_recovery' WHERE id=?",
                    (task_id,),
                )

        conn.commit()
        logger.info(f'创建了 {tasks_created} 个恢复补采任务 (batch_id={recovery_batch_id})')
        return tasks_created

    except Exception as e:
        logger.error(f'创建恢复补采任务失败: {e}')
        return 0
