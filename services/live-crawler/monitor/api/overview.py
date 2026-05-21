"""账号总览 API — 跨批次聚合视角"""

import time
import sqlite3
from datetime import datetime, timedelta

from fastapi import APIRouter, Query

from monitor.db import get_connection
from monitor.registry import get_expected_account_types, get_expected_room_types, get_room_types_for_completion
from utils.adspower_client import get_adspower_client, AdsPowerRateLimitError, AdsPowerApiError
from utils.logger import logger

router = APIRouter(prefix='/api', tags=['overview'])

_conn: sqlite3.Connection | None = None

# AdsPower 账号名缓存：{account_id: account_name}
# 缓存 10 分钟，避免每次请求都查 AdsPower
_account_name_cache: dict[str, str] = {}
_cache_time: float = 0
_CACHE_TTL = 600  # 10 分钟


def set_db_connection(conn: sqlite3.Connection):
    """设置数据库连接（供测试注入）"""
    global _conn
    _conn = conn


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（生产环境每次创建新连接，测试环境用注入的连接）"""
    if _conn is not None:
        return _conn
    return get_connection()


def _get_account_names(account_ids: list[str]) -> dict[str, str]:
    """从 AdsPower API 批量获取账号名称（带缓存）"""
    global _account_name_cache, _cache_time

    now = time.time()
    # 缓存未过期，直接返回
    if now - _cache_time < _CACHE_TTL and _account_name_cache:
        return {aid: _account_name_cache.get(aid, aid) for aid in account_ids}

    try:
        client = get_adspower_client()

        # 查询所有分组的环境列表
        all_profiles: dict[str, str] = {}
        group_data = client.get('/api/v1/group/list', params={'page_size': 100})
        groups = group_data.get('data', {}).get('list', [])

        for group in groups:
            gid = group.get('group_id', '0')
            user_data = client.get('/api/v1/user/list', params={'group_id': gid, 'page_size': 100})
            for u in user_data.get('data', {}).get('list', []):
                uid = u.get('user_id', '')
                if uid:
                    all_profiles[uid] = u.get('name', '') or uid

        _account_name_cache = all_profiles
        _cache_time = now
        logger.info(f'已缓存 {len(all_profiles)} 个 AdsPower 账号名称')

    except (AdsPowerRateLimitError, AdsPowerApiError) as e:
        logger.warning(f'获取 AdsPower 账号名称失败（API 异常）: {e}')
    except Exception as e:
        logger.warning(f'获取 AdsPower 账号名称失败: {e}')

    return {aid: _account_name_cache.get(aid, aid) for aid in account_ids}


@router.get('/overview')
def get_overview(days: int = Query(default=3, ge=1, le=90), platform: str | None = Query(default=None)):
    """账号总览 — 返回时间窗口内所有账号的聚合完整率"""
    conn = _get_conn()
    cutoff_ts = int(time.time()) - days * 86400

    # 获取时间窗口内的所有账号
    accounts = conn.execute(
        """SELECT DISTINCT s.account_id, s.group_name, s.platform,
                  MAX(s.started_at) as last_collected_at,
                  (SELECT batch_id FROM account_sessions
                   WHERE account_id = s.account_id ORDER BY started_at DESC LIMIT 1) as last_batch_id
           FROM account_sessions s
           JOIN collection_batches b ON s.batch_id = b.batch_id
           WHERE b.started_at >= datetime(?, 'unixepoch')
           GROUP BY s.account_id""",
        (cutoff_ts,),
    ).fetchall()

    result = []

    for acc in accounts:
        account_id = acc['account_id']
        acc_platform = acc['platform'] or 'tiktok'

        # 按平台过滤
        if platform and acc_platform != platform:
            continue

        expected_account = get_expected_account_types(acc_platform)
        expected_room = get_expected_room_types(acc_platform)

        room_types_for_completion = get_room_types_for_completion(acc_platform)

        # 统计直播间数
        rooms = conn.execute(
            "SELECT DISTINCT room_id FROM room_sessions WHERE account_id = ? AND start_time >= ?",
            (account_id, cutoff_ts),
        ).fetchall()
        total_rooms = len(rooms)

        # 期望总数
        expected_total = len(expected_account) + total_rooms * len(room_types_for_completion)

        # 实际成功数（跨批次聚合）
        actual_account = conn.execute(
            """SELECT COUNT(DISTINCT api_type) FROM collection_records
               WHERE account_id = ? AND room_id = '' AND status = 'success'
                 AND batch_id IN (SELECT batch_id FROM collection_batches WHERE started_at >= datetime(?, 'unixepoch'))""",
            (account_id, cutoff_ts),
        ).fetchone()[0]

        actual_room = 0
        for room in rooms:
            cnt = conn.execute(
                """SELECT COUNT(DISTINCT api_type) FROM collection_records
                   WHERE account_id = ? AND room_id = ? AND status = 'success' AND api_type IN ({})""".format(
                    ','.join('?' * len(room_types_for_completion))
                ),
                (account_id, room['room_id'], *room_types_for_completion),
            ).fetchone()[0]
            actual_room += cnt

        actual_total = actual_account + actual_room
        missing_count = max(0, expected_total - actual_total)
        completeness = round(actual_total / expected_total * 100, 1) if expected_total > 0 else 100.0

        result.append({
            'account_id': account_id,
            'account_name': account_id,  # 后续会被 _get_account_names 覆盖
            'group_name': acc['group_name'],
            'completeness': completeness,
            'total_rooms': total_rooms,
            'missing_count': missing_count,
            'last_batch_id': acc['last_batch_id'],
            'last_collected_at': acc['last_collected_at'],
        })

    # 按完整率升序排列（最不完整的在前）
    result.sort(key=lambda x: x['completeness'])

    # 批量获取账号名称
    account_ids = [r['account_id'] for r in result]
    name_map = _get_account_names(account_ids)
    for r in result:
        r['account_name'] = name_map.get(r['account_id'], r['account_id'])

    today = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    return {
        'accounts': result,
        'time_range': {'start': start, 'end': today},
        'days': days,
    }


@router.get('/overview/{account_id}')
def get_account_overview(account_id: str, days: int = Query(default=3, ge=1, le=90)):
    """账号聚合详情 — 三级数据状态（跨批次合并）"""
    conn = _get_conn()
    cutoff_ts = int(time.time()) - days * 86400

    # 根据账号所属平台获取期望类型
    acc_row = conn.execute(
        "SELECT group_name, platform FROM account_sessions WHERE account_id = ? ORDER BY started_at DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    group_name = acc_row['group_name'] if acc_row else ''
    acc_platform = (acc_row['platform'] or 'tiktok') if acc_row else 'tiktok'

    expected_account_types = get_expected_account_types(acc_platform)
    expected_room_types = get_expected_room_types(acc_platform)

    # 1. 账号级
    account_level = []
    for api_type in expected_account_types:
        row = conn.execute(
            """SELECT batch_id FROM collection_records
               WHERE account_id = ? AND room_id = '' AND api_type = ? AND status = 'success'
               ORDER BY collected_at DESC LIMIT 1""",
            (account_id, api_type),
        ).fetchone()
        account_level.append({
            'api_type': api_type,
            'status': 'success' if row else 'missing',
            'last_batch': row['batch_id'] if row else None,
        })

    # 2. 日期级
    daily_records = conn.execute(
        """SELECT DISTINCT target_date, api_type, status FROM daily_collection_status
           WHERE account_id = ? AND target_date >= date(?, 'unixepoch')
           ORDER BY target_date DESC""",
        (account_id, cutoff_ts),
    ).fetchall()
    daily_level = [
        {'target_date': r['target_date'], 'api_type': r['api_type'], 'status': r['status']}
        for r in daily_records
    ]

    # 3. 直播间级
    room_types_for_completion = get_room_types_for_completion(acc_platform)

    rooms = conn.execute(
        """SELECT DISTINCT rs.room_id,
                  COALESCE(MAX(rs.start_time), 0) as start_time
           FROM room_sessions rs
           WHERE rs.account_id = ? AND rs.start_time >= ?
           GROUP BY rs.room_id
           ORDER BY start_time DESC""",
        (account_id, cutoff_ts),
    ).fetchall()

    room_level = []
    for room in rooms:
        room_id = room['room_id']
        apis = []
        for api_type in expected_room_types:
            row = conn.execute(
                """SELECT 1 FROM collection_records
                   WHERE account_id = ? AND room_id = ? AND api_type = ? AND status = 'success'
                   LIMIT 1""",
                (account_id, room_id, api_type),
            ).fetchone()
            apis.append({
                'api_type': api_type,
                'status': 'success' if row else 'missing',
            })
        room_level.append({'room_id': room_id, 'apis': apis})

    # 计算完整率
    total = len(expected_account_types) + len(rooms) * len(room_types_for_completion)
    success = sum(1 for a in account_level if a['status'] == 'success')
    success += sum(
        1 for r in room_level for a in r['apis']
        if a['status'] == 'success' and a['api_type'] in room_types_for_completion
    )
    completeness = round(success / total * 100, 1) if total > 0 else 100.0

    return {
        'account_level': account_level,
        'daily_level': daily_level,
        'room_level': room_level,
        'completeness': completeness,
    }
