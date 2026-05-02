"""补采任务 API — 手动触发 + 任务列表查询"""

import sqlite3
import threading
from fastapi import APIRouter, Query
from pydantic import BaseModel
from monitor.db import get_connection
from monitor.recrawl.models import create_task_manual, get_tasks_by_account
from utils.logger import logger

router = APIRouter(prefix='/api', tags=['recrawl'])

_conn: sqlite3.Connection | None = None

# 补采执行锁：防止多次点击触发并发补采
_recrawl_lock = threading.Lock()


def set_db_connection(conn: sqlite3.Connection):
    """设置数据库连接（供测试注入）"""
    global _conn
    _conn = conn


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（生产环境每次创建新连接，测试环境用注入的连接）"""
    if _conn is not None:
        return _conn
    return get_connection()


class RecrawlTriggerRequest(BaseModel):
    """补采触发请求模型"""
    account_id: str
    level: str
    room_id: str = ''
    api_type: str = ''
    target_date: str = ''
    batch_id: str = ''
    group_name: str = ''


@router.post('/recrawl/trigger')
def trigger_recrawl(req: RecrawlTriggerRequest):
    """手动触发补采任务，创建后在后台线程异步执行"""
    conn = _get_conn()

    # batch_id 为空时，自动查找该账号最新的批次
    batch_id = req.batch_id
    if not batch_id:
        row = conn.execute(
            "SELECT batch_id FROM account_sessions WHERE account_id = ? ORDER BY started_at DESC LIMIT 1",
            (req.account_id,),
        ).fetchone()
        batch_id = row['batch_id'] if row else 'manual'

    task_id = create_task_manual(
        conn, batch_id=batch_id, account_id=req.account_id,
        group_name=req.group_name, room_id=req.room_id,
        target_date=req.target_date, api_type=req.api_type, level=req.level,
    )

    # 在后台线程异步执行补采（加锁防止并发）
    def _run_recrawl():
        if not _recrawl_lock.acquire(blocking=False):
            logger.info('已有补采任务在执行中，跳过本次触发')
            return
        try:
            from monitor.recrawl.executor import execute_pending_tasks
            bg_conn = get_connection()
            # 只执行当前账号的补采任务，避免触发其他账号的 AdsPower 查询
            execute_pending_tasks(bg_conn, account_id=req.account_id)
            bg_conn.close()
        except Exception as e:
            logger.error(f'后台补采执行失败: {e}')
        finally:
            _recrawl_lock.release()

    threading.Thread(target=_run_recrawl, daemon=True).start()

    return {'status': 'created', 'task_id': task_id}


@router.get('/recrawl/tasks')
def list_tasks(
    account_id: str = Query(default=None),
    status: str = Query(default=None),
):
    """查询补采任务列表"""
    conn = _get_conn()
    if account_id:
        tasks = get_tasks_by_account(conn, account_id, status=status)
    else:
        # 无 account_id 时返回所有任务（限制 100 条）
        sql = "SELECT * FROM recrawl_tasks"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT 100"
        rows = conn.execute(sql, params).fetchall()
        tasks = [dict(r) for r in rows]

    return {'tasks': tasks, 'total': len(tasks)}
