"""补采任务数据模型 — recrawl_tasks 和 request_context 的 CRUD 操作"""

import sqlite3

from utils.logger import logger


def create_task_auto(
    conn: sqlite3.Connection,
    batch_id: str, account_id: str, group_name: str,
    room_id: str, target_date: str, api_type: str, level: str,
) -> int | None:
    """创建自动补采任务（重复则忽略）"""
    try:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO recrawl_tasks
               (batch_id, account_id, group_name, room_id, target_date, api_type, level, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'auto')""",
            (batch_id, account_id, group_name, room_id, target_date, api_type, level),
        )
        conn.commit()
        return cursor.lastrowid if cursor.rowcount > 0 else None
    except sqlite3.IntegrityError:
        # 重复任务，正常忽略
        return None
    except Exception as e:
        logger.error(f'创建自动补采任务异常: {e}')
        return None


def create_task_manual(
    conn: sqlite3.Connection,
    batch_id: str, account_id: str, group_name: str,
    room_id: str, target_date: str, api_type: str, level: str,
) -> int:
    """创建或重置手动补采任务（无论当前状态均可重置）"""
    cursor = conn.execute(
        """INSERT INTO recrawl_tasks
           (batch_id, account_id, group_name, room_id, target_date, api_type, level, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'manual')
           ON CONFLICT(batch_id, account_id, room_id, target_date, api_type)
           DO UPDATE SET status='pending', retry_count=0, error_msg='',
                         source='manual', updated_at=CURRENT_TIMESTAMP""",
        (batch_id, account_id, group_name, room_id, target_date, api_type, level),
    )
    conn.commit()
    return cursor.lastrowid


def get_pending_tasks(conn: sqlite3.Connection, account_id: str | None = None) -> list[dict]:
    """获取 pending 状态的补采任务"""
    sql = "SELECT * FROM recrawl_tasks WHERE status = 'pending'"
    params: list = []
    if account_id:
        sql += " AND account_id = ?"
        params.append(account_id)
    sql += " ORDER BY created_at ASC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_tasks_by_account(
    conn: sqlite3.Connection, account_id: str, status: str | None = None,
) -> list[dict]:
    """获取指定账号的补采任务"""
    sql = "SELECT * FROM recrawl_tasks WHERE account_id = ?"
    params: list = [account_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def update_task_status(
    conn: sqlite3.Connection, task_id: int, status: str,
    retry_count: int | None = None, error_msg: str | None = None,
) -> None:
    """更新任务状态"""
    fields = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
    params: list = [status]
    if retry_count is not None:
        fields.append("retry_count = ?")
        params.append(retry_count)
    if error_msg is not None:
        fields.append("error_msg = ?")
        params.append(error_msg)
    params.append(task_id)
    conn.execute(f"UPDATE recrawl_tasks SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()


def save_request_context(
    conn: sqlite3.Connection, account_id: str, context_type: str,
    api_base_url: str = '', query_string: str = '',
    headers: str = '{}', cookies: str = '[]', payload_template: str = '{}',
) -> None:
    """保存或更新请求上下文（upsert）"""
    conn.execute(
        """INSERT INTO request_context
           (account_id, context_type, api_base_url, query_string, headers, cookies, payload_template)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(account_id, context_type)
           DO UPDATE SET api_base_url=excluded.api_base_url, query_string=excluded.query_string,
                         headers=excluded.headers, cookies=excluded.cookies,
                         payload_template=excluded.payload_template,
                         updated_at=CURRENT_TIMESTAMP""",
        (account_id, context_type, api_base_url, query_string, headers, cookies, payload_template),
    )
    conn.commit()


def get_request_context(
    conn: sqlite3.Connection, account_id: str, context_type: str,
) -> dict | None:
    """获取请求上下文"""
    row = conn.execute(
        "SELECT * FROM request_context WHERE account_id = ? AND context_type = ?",
        (account_id, context_type),
    ).fetchone()
    return dict(row) if row else None


def cleanup_old_tasks(conn: sqlite3.Connection, days: int = 30) -> int:
    """清理指定天数前的已完成/已失败任务"""
    cursor = conn.execute(
        """DELETE FROM recrawl_tasks
           WHERE status IN ('success', 'recrawl_failed')
             AND updated_at < datetime('now', ?)""",
        (f'-{days} days',),
    )
    conn.commit()
    return cursor.rowcount
