"""采集模式解析器。

负责判断账号本轮应执行全量还是增量采集。
"""

from core.collection_tracker import CollectionTracker
from monitor.login_status_manager import LoginStatusManager


def resolve_collection_mode(
    platform: str,
    user_id: str,
    tracker: CollectionTracker,
    status_mgr: LoginStatusManager,
    force_full_collection: bool = False,
) -> tuple[bool, str]:
    """计算账号本轮采集模式及原因。"""
    if force_full_collection:
        return True, '手动全量'

    if tracker.is_new_account(platform, user_id):
        return True, '新账号全量'

    events = status_mgr.get_recent_events(user_id, limit=2)
    if (
        len(events) >= 2
        and events[0]['event_type'] == 'login'
        and events[1]['event_type'] == 'logout'
    ):
        return True, '登出恢复全量'

    return False, '增量'
