"""批次相关 API 路由"""

from fastapi import APIRouter, Query
from monitor.db import get_connection, init_db
from monitor.registry import get_expected_account_types, get_expected_room_types, get_room_types_for_completion

router = APIRouter(prefix="/api", tags=["batches"])


def _get_conn():
    conn = get_connection()
    init_db(conn)
    return conn


@router.get("/batches")
def list_batches(limit: int = Query(20, ge=1, le=100)):
    """获取采集批次列表"""
    conn = _get_conn()
    batches = conn.execute(
        "SELECT * FROM collection_batches ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()

    result = []
    for b in batches:
        batch_id = b['batch_id']

        # 计算完整率
        sessions = conn.execute(
            "SELECT account_id, group_name, platform, crawl_type, total_rooms FROM account_sessions WHERE batch_id=?",
            (batch_id,)
        ).fetchall()

        total_expected = 0
        total_actual = 0
        for s in sessions:
            # 按账号所属平台和采集类型获取期望类型
            acc_platform = s['platform'] or 'tiktok'
            crawl_type = s['crawl_type'] or ''
            expected_account = get_expected_account_types(acc_platform, crawl_type)
            expected_room = get_expected_room_types(acc_platform, crawl_type)

            room_types_for_completion = get_room_types_for_completion(acc_platform, crawl_type)

            # 账号级
            total_expected += len(expected_account)
            account_records = conn.execute(
                "SELECT api_type FROM collection_records "
                "WHERE batch_id=? AND account_id=? AND room_id='' AND status='success'",
                (batch_id, s['account_id'])
            ).fetchall()
            actual_account = sum(1 for r in account_records if r['api_type'] in expected_account)
            total_actual += actual_account

            # 直播间级
            rooms = conn.execute(
                "SELECT DISTINCT room_id FROM collection_records "
                "WHERE batch_id=? AND account_id=? AND room_id != ''",
                (batch_id, s['account_id'])
            ).fetchall()
            for room in rooms:
                total_expected += len(room_types_for_completion)
                room_records = conn.execute(
                    "SELECT api_type FROM collection_records "
                    "WHERE batch_id=? AND account_id=? AND room_id=? AND status='success'",
                    (batch_id, s['account_id'], room['room_id'])
                ).fetchall()
                actual_room = sum(1 for r in room_records if r['api_type'] in room_types_for_completion)
                total_actual += actual_room

        completeness = round(total_actual / total_expected * 100, 1) if total_expected > 0 else 0

        result.append({
            'batch_id': batch_id,
            'mode': b['mode'],
            'total_accounts': b['total_accounts'],
            'success_accounts': b['success_accounts'],
            'completeness': completeness,
            'started_at': b['started_at'],
            'finished_at': b['finished_at'],
        })

    return {'batches': result}
