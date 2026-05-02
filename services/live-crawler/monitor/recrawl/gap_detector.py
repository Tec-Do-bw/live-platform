"""缺失检测器 — 对比注册表期望与实际采集记录，找出缺失的 API 调用

三级检测：
1. 账号级：各平台对应的 account-level API 是否采集
2. 日期级：daily_collection_status 中每天的日期级 API 是否采集
3. 直播间级：每个 room_id 的 room-level API 是否采集
"""

import sqlite3

from monitor.registry import (
    get_expected_account_types,
    get_expected_daily_types,
    get_expected_room_types,
    get_room_types_for_completion,
)
from monitor.recrawl.models import create_task_auto


def _make_gap(
    batch_id: str, account_id: str, group_name: str,
    room_id: str, target_date: str, api_type: str, level: str,
) -> dict:
    """构造缺失记录字典"""
    return {
        'batch_id': batch_id,
        'account_id': account_id,
        'group_name': group_name,
        'room_id': room_id,
        'target_date': target_date,
        'api_type': api_type,
        'level': level,
    }


def detect_account_gaps(conn: sqlite3.Connection, batch_id: str) -> list[dict]:
    """检测账号级缺失

    遍历该批次所有账号，根据平台检查每个期望的 account-level api_type 是否有成功记录。
    """
    rows = conn.execute(
        "SELECT account_id, group_name, platform FROM account_sessions WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()

    gaps = []
    for row in rows:
        account_id = row['account_id']
        group_name = row['group_name']
        platform = row['platform'] or 'tiktok'
        expected = get_expected_account_types(platform)

        collected = conn.execute(
            "SELECT DISTINCT api_type FROM collection_records "
            "WHERE batch_id = ? AND account_id = ? AND status = 'success' AND room_id = ''",
            (batch_id, account_id),
        ).fetchall()
        collected_types = {r['api_type'] for r in collected}

        for api_type in expected:
            if api_type not in collected_types:
                gaps.append(_make_gap(
                    batch_id, account_id, group_name,
                    room_id='', target_date='', api_type=api_type, level='account',
                ))
    return gaps


def detect_daily_gaps(conn: sqlite3.Connection, batch_id: str) -> list[dict]:
    """检测日期级缺失

    从 daily_collection_status 中获取该批次所有账号的日期级采集记录，
    找出 status != 'success' 或完全缺失的日期。
    """
    accounts = conn.execute(
        "SELECT account_id, group_name, platform FROM account_sessions WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()

    gaps = []
    for acc in accounts:
        account_id = acc['account_id']
        group_name = acc['group_name']
        platform = acc['platform'] or 'tiktok'
        expected = get_expected_daily_types(platform)

        daily_rows = conn.execute(
            "SELECT target_date, api_type, status FROM daily_collection_status "
            "WHERE batch_id = ? AND account_id = ?",
            (batch_id, account_id),
        ).fetchall()

        status_map: dict[tuple[str, str], str] = {}
        all_dates: set[str] = set()
        for dr in daily_rows:
            status_map[(dr['target_date'], dr['api_type'])] = dr['status']
            all_dates.add(dr['target_date'])

        for target_date in sorted(all_dates):
            for api_type in expected:
                if status_map.get((target_date, api_type)) != 'success':
                    gaps.append(_make_gap(
                        batch_id, account_id, group_name,
                        room_id='', target_date=target_date, api_type=api_type, level='daily',
                    ))
    return gaps


def detect_room_gaps(conn: sqlite3.Connection, batch_id: str) -> list[dict]:
    """检测直播间级缺失

    遍历 room_sessions 中每个 room_id，根据平台检查对应的 room-level API。
    """
    rooms = conn.execute(
        "SELECT rs.account_id, rs.room_id, a.group_name, a.platform "
        "FROM room_sessions rs "
        "JOIN account_sessions a ON rs.batch_id = a.batch_id AND rs.account_id = a.account_id "
        "WHERE rs.batch_id = ?",
        (batch_id,),
    ).fetchall()

    gaps = []
    for room in rooms:
        account_id = room['account_id']
        room_id = room['room_id']
        group_name = room['group_name']
        platform = room['platform'] or 'tiktok'
        expected = get_room_types_for_completion(platform)

        collected = conn.execute(
            "SELECT DISTINCT api_type FROM collection_records "
            "WHERE batch_id = ? AND account_id = ? AND room_id = ? AND status = 'success'",
            (batch_id, account_id, room_id),
        ).fetchall()
        collected_types = {r['api_type'] for r in collected}

        for api_type in expected:
            if api_type not in collected_types:
                gaps.append(_make_gap(
                    batch_id, account_id, group_name,
                    room_id=room_id, target_date='', api_type=api_type, level='room',
                ))
    return gaps


def detect_all_gaps(conn: sqlite3.Connection, batch_id: str) -> list[dict]:
    """执行全部三级检测，返回合并的缺失列表"""
    gaps = []
    gaps.extend(detect_account_gaps(conn, batch_id))
    gaps.extend(detect_daily_gaps(conn, batch_id))
    gaps.extend(detect_room_gaps(conn, batch_id))
    return gaps


def _is_shopee_gap(conn: sqlite3.Connection, gap: dict) -> bool:
    """判断缺口是否属于 Shopee 账号（Shopee 使用 JS 注入模式，不支持 HTTP 补采）"""
    row = conn.execute(
        "SELECT platform FROM account_sessions WHERE account_id = ? LIMIT 1",
        (gap['account_id'],),
    ).fetchone()
    return bool(row and row['platform'] == 'shopee')


def detect_and_create_tasks(conn: sqlite3.Connection, batch_id: str) -> int:
    """检测缺失并自动创建补采任务

    Returns:
        新创建的任务数量
    """
    gaps = detect_all_gaps(conn, batch_id)
    created = 0
    for gap in gaps:
        # Shopee 使用 JS 注入模式，HTTP 补采不适用，跳过
        if _is_shopee_gap(conn, gap):
            continue
        task_id = create_task_auto(conn, **gap)
        if task_id is not None:
            created += 1
    return created
