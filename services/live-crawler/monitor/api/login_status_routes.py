"""登录状态 API 路由。

提供账号登录状态查询、登出账号列表、事件历史和手动恢复请求事件接口。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from monitor.db import get_connection
from monitor.login_status_manager import LoginStatusManager
from utils.logger import logger


router = APIRouter(prefix='/api', tags=['login_status'])


class TriggerRecoveryRequest(BaseModel):
    """触发恢复全量请求"""
    platform: str
    group_name: str


@router.get('/accounts/{account_id}/login-status')
def get_account_login_status(account_id: str):
    """获取账号登录状态

    Args:
        account_id: 账号ID

    Returns:
        账号状态信息
    """
    try:
        conn = get_connection()
        status_mgr = LoginStatusManager(conn)
        status = status_mgr.get_account_status(account_id)

        if not status:
            raise HTTPException(status_code=404, detail='账号状态不存在')

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'获取账号登录状态失败: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/accounts/{account_id}/login-events')
def get_account_login_events(account_id: str, limit: int = 100):
    """获取账号登录状态历史事件。"""
    try:
        conn = get_connection()
        status_mgr = LoginStatusManager(conn)
        events = status_mgr.list_events(account_id, limit=limit)
        return {
            'account_id': account_id,
            'events': events,
        }
    except Exception as e:
        logger.error(f'获取账号登录状态历史事件失败: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/accounts/logout-list')
def list_logout_accounts(platform: str | None = None):
    """列出所有登出状态的账号

    Args:
        platform: 可选，筛选平台

    Returns:
        登出账号列表
    """
    try:
        conn = get_connection()
        status_mgr = LoginStatusManager(conn)
        accounts = status_mgr.list_logout_accounts(platform)

        return {'accounts': accounts}

    except Exception as e:
        logger.error(f'列出登出账号失败: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/accounts/{account_id}/trigger-recovery')
def trigger_recovery(account_id: str, request: TriggerRecoveryRequest):
    """记录手动恢复请求事件。

    Args:
        account_id: 账号ID
        request: 请求体

    Returns:
        事件记录结果
    """
    try:
        if request.platform != 'tiktok':
            raise HTTPException(status_code=400, detail='当前版本仅支持 TikTok 恢复全量')

        conn = get_connection()
        status_mgr = LoginStatusManager(conn)
        status_mgr.mark_full_recovery_pending(
            account_id=account_id,
            platform=request.platform,
            group_name=request.group_name,
        )

        return {
            'success': True,
            'event_recorded': True,
            'message': '已记录手动恢复请求事件'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'触发恢复全量失败: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/recrawl/tasks/recovery')
def list_recovery_tasks(account_id: str | None = None, status: str | None = None):
    """列出恢复补采任务

    Args:
        account_id: 可选，筛选账号
        status: 可选，筛选状态

    Returns:
        恢复补采任务列表
    """
    try:
        conn = get_connection()

        sql = "SELECT * FROM recrawl_tasks WHERE source = 'logout_recovery'"
        params: list = []

        if account_id:
            sql += " AND account_id = ?"
            params.append(account_id)

        if status:
            sql += " AND status = ?"
            params.append(status)

        sql += " ORDER BY created_at DESC"

        rows = conn.execute(sql, params).fetchall()
        tasks = [dict(r) for r in rows]

        return {'tasks': tasks}

    except Exception as e:
        logger.error(f'列出恢复补采任务失败: {e}')
        raise HTTPException(status_code=500, detail=str(e))
