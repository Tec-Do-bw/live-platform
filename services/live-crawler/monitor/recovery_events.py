"""恢复全量事件写入辅助方法。"""

from monitor.login_status_manager import LoginStatusManager
from utils.logger import logger


def append_full_recovery_event_if_needed(
    status_mgr: LoginStatusManager,
    user_id: str,
    platform: str,
    group_name: str,
    batch_id: str,
    mode_label: str,
    event_type: str,
    detail: dict | None = None,
) -> None:
    """仅在登出恢复全量模式下写入恢复事件。"""
    if mode_label not in ('登出恢复全量', '登出即时恢复全量'):
        return

    try:
        status_mgr.append_event(
            account_id=user_id,
            platform=platform,
            group_name=group_name,
            event_type=event_type,
            batch_id=batch_id,
            detail=detail,
        )
    except Exception as e:
        logger.error(f'写入恢复事件失败 account={user_id} event={event_type}: {e}')
