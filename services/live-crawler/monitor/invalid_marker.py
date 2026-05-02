"""登出期间数据标记模块

标记登出期间的采集记录为 invalid，区分 invalid（登出）和 failed（其他错误）。
"""

import sqlite3
from datetime import datetime

from utils.logger import logger


def mark_invalid_records(
    conn: sqlite3.Connection,
    batch_id: str,
    account_id: str,
    logout_at: datetime,
) -> int:
    """标记登出期间的采集记录为 invalid

    Args:
        conn: 数据库连接
        batch_id: 批次ID
        account_id: 账号ID
        logout_at: 登出时间戳

    Returns:
        标记的记录数

    逻辑：
    1. 查询 collection_records 中该账号在 logout_at 之后的记录
    2. 检查 response_size == 0 或 extra_data 中数据为空/零值
    3. 更新 status = 'invalid'
    """
    try:
        logout_at_str = logout_at.isoformat()

        # 查询登出时间之后的采集记录，且 response_size == 0
        cursor = conn.execute(
            """UPDATE collection_records
               SET status = 'invalid'
               WHERE batch_id = ?
                 AND account_id = ?
                 AND collected_at >= ?
                 AND response_size = 0
                 AND status != 'invalid'""",
            (batch_id, account_id, logout_at_str),
        )
        conn.commit()

        marked_count = cursor.rowcount
        logger.info(
            f'标记了 {marked_count} 条登出期间的采集记录为 invalid '
            f'(batch_id={batch_id}, account_id={account_id})'
        )
        return marked_count

    except Exception as e:
        logger.error(f'标记 invalid 记录失败: {e}')
        return 0
