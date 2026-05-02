"""账号 + 直播间相关 API 路由"""

import json
from fastapi import APIRouter, Query
from monitor.db import get_connection, init_db
from monitor.registry import (
    get_expected_account_types,
    get_expected_room_types,
    get_expected_daily_types,
    get_room_types_for_completion,
)

router = APIRouter(prefix="/api", tags=["accounts"])


def _get_conn():
    conn = get_connection()
    init_db(conn)
    return conn


@router.get("/batches/{batch_id}/accounts")
def list_accounts(batch_id: str, platform: str | None = Query(default=None)):
    """获取批次下的账号列表及采集状态"""
    conn = _get_conn()

    sessions = conn.execute(
        "SELECT * FROM account_sessions WHERE batch_id=? ORDER BY started_at",
        (batch_id,)
    ).fetchall()

    result = []
    for s in sessions:
        account_id = s['account_id']
        acc_platform = s['platform'] or 'tiktok'
        crawl_type = s['crawl_type'] or ''

        # 按平台过滤
        if platform and acc_platform != platform:
            continue

        expected_account = get_expected_account_types(acc_platform, crawl_type)
        expected_room = get_expected_room_types(acc_platform, crawl_type)

        room_types_for_completion = get_room_types_for_completion(acc_platform, crawl_type)

        # 账号级 API 状态
        account_records = conn.execute(
            "SELECT api_type, status FROM collection_records "
            "WHERE batch_id=? AND account_id=? AND room_id=''",
            (batch_id, account_id)
        ).fetchall()
        api_status = {r['api_type']: r['status'] for r in account_records}

        # 直播间级统计
        rooms = conn.execute(
            "SELECT DISTINCT room_id FROM collection_records "
            "WHERE batch_id=? AND account_id=? AND room_id != ''",
            (batch_id, account_id)
        ).fetchall()
        room_success = 0
        for room in rooms:
            room_records = conn.execute(
                "SELECT api_type, status FROM collection_records "
                "WHERE batch_id=? AND account_id=? AND room_id=? AND status='success'",
                (batch_id, account_id, room['room_id'])
            ).fetchall()
            if all(any(r['api_type'] == t for r in room_records) for t in room_types_for_completion):
                room_success += 1

        result.append({
            'account_id': account_id,
            'group_name': s['group_name'],
            'platform': acc_platform,
            'total_rooms': s['total_rooms'],
            'room_success': room_success,
            'status': s['status'],
            'api_status': {t: api_status.get(t, 'missing') for t in expected_account},
            'started_at': s['started_at'],
            'finished_at': s['finished_at'],
        })

    return {'accounts': result}


@router.get("/accounts/{account_id}/rooms")
def list_rooms(account_id: str, batch_id: str = Query(...)):
    """获取账号下的直播间列表 + GMV + 采集状态"""
    conn = _get_conn()

    # 根据账号所属平台获取期望类型
    acc_row = conn.execute(
        "SELECT group_name, platform, crawl_type FROM account_sessions WHERE account_id=? ORDER BY started_at DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    acc_platform = (acc_row['platform'] or 'tiktok') if acc_row else 'tiktok'
    crawl_type = (acc_row['crawl_type'] or '') if acc_row else ''
    expected_room = get_expected_room_types(acc_platform, crawl_type)

    # 从 live_list 的 extra_data 中提取 rooms GMV 数据
    live_list_row = conn.execute(
        "SELECT extra_data FROM collection_records "
        "WHERE batch_id=? AND account_id=? AND api_type='live_list'",
        (batch_id, account_id)
    ).fetchone()

    rooms_gmv = {}
    if live_list_row and live_list_row['extra_data']:
        try:
            data = json.loads(live_list_row['extra_data'])
            for r in data.get('rooms', []):
                rooms_gmv[str(r.get('room_id', ''))] = r
        except (json.JSONDecodeError, TypeError):
            pass

    # 获取所有 room 的采集记录
    room_records = conn.execute(
        "SELECT room_id, api_type, status FROM collection_records "
        "WHERE batch_id=? AND account_id=? AND room_id != ''",
        (batch_id, account_id)
    ).fetchall()

    # 按 room_id 分组
    rooms_status: dict[str, dict[str, str]] = {}
    for r in room_records:
        rid = r['room_id']
        if rid not in rooms_status:
            rooms_status[rid] = {}
        rooms_status[rid][r['api_type']] = r['status']

    # 合并 GMV 数据 + 采集状态
    all_room_ids = set(rooms_gmv.keys()) | set(rooms_status.keys())
    result = []
    for rid in sorted(all_room_ids):
        gmv = rooms_gmv.get(rid, {})
        status = rooms_status.get(rid, {})
        result.append({
            'room_id': rid,
            'room_name': gmv.get('room_name', ''),
            'live_start_ts': gmv.get('live_start_ts', 0),
            'live_end_ts': gmv.get('live_end_ts', 0),
            'duration': gmv.get('duration', 0),
            'revenue': gmv.get('revenue', '0'),
            'currency_code': gmv.get('currency_code', ''),
            'item_sold_cnt': gmv.get('item_sold_cnt', 0),
            'view_cnt': gmv.get('view_cnt', 0),
            'api_status': {t: status.get(t, 'missing') for t in expected_room},
        })

    # 按开播时间倒序
    result.sort(key=lambda x: x['live_start_ts'], reverse=True)
    return {'rooms': result, 'expected_room_types': expected_room}


@router.get("/batches/{batch_id}/accounts/{account_id}")
def get_account_detail(batch_id: str, account_id: str):
    """获取账号的三级采集详情：账号级 + 日期级 + 直播间级"""
    conn = _get_conn()

    # 根据账号所属平台获取期望类型
    acc_row = conn.execute(
        "SELECT group_name, platform, crawl_type FROM account_sessions WHERE batch_id=? AND account_id=?",
        (batch_id, account_id)
    ).fetchone()
    group_name = acc_row['group_name'] if acc_row else ''
    acc_platform = (acc_row['platform'] or 'tiktok') if acc_row else 'tiktok'
    crawl_type = (acc_row['crawl_type'] or '') if acc_row else ''

    expected_account = get_expected_account_types(acc_platform, crawl_type)
    expected_daily = get_expected_daily_types(acc_platform, crawl_type)
    expected_room = get_expected_room_types(acc_platform, crawl_type)

    # 1. 账号级指标：从 collection_records 中读取 room_id='' 的记录
    account_records = conn.execute(
        "SELECT api_type, status, collected_at FROM collection_records "
        "WHERE batch_id=? AND account_id=? AND room_id=''",
        (batch_id, account_id)
    ).fetchall()
    api_map = {r['api_type']: {'status': r['status'], 'collected_at': r['collected_at']}
               for r in account_records}
    account_indicators = {
        t: api_map.get(t, {'status': None, 'collected_at': None})
        for t in expected_account
    }

    # 2. 日期级指标：从 daily_collection_status 读取按天记录
    daily_records = conn.execute(
        "SELECT target_date, api_type, status FROM daily_collection_status "
        "WHERE batch_id=? AND account_id=? ORDER BY target_date",
        (batch_id, account_id)
    ).fetchall()
    daily_map: dict[str, dict[str, dict]] = {}
    for r in daily_records:
        date = r['target_date']
        if date not in daily_map:
            daily_map[date] = {}
        daily_map[date][r['api_type']] = {'status': r['status']}
    daily_stats = []
    for date in sorted(daily_map.keys()):
        entry: dict = {'target_date': date}
        for t in expected_daily:
            entry[t] = daily_map[date].get(t, {'status': None})
        daily_stats.append(entry)

    # 3. 直播间级指标：从 room_sessions 获取应采列表，从 collection_records 获取采集状态
    room_sessions = conn.execute(
        "SELECT room_id, start_time, end_time FROM room_sessions "
        "WHERE batch_id=? AND account_id=? ORDER BY start_time DESC",
        (batch_id, account_id)
    ).fetchall()

    room_records = conn.execute(
        "SELECT room_id, api_type, status FROM collection_records "
        "WHERE batch_id=? AND account_id=? AND room_id != ''",
        (batch_id, account_id)
    ).fetchall()
    room_api_map: dict[str, dict[str, str]] = {}
    for r in room_records:
        rid = r['room_id']
        if rid not in room_api_map:
            room_api_map[rid] = {}
        room_api_map[rid][r['api_type']] = r['status']

    # 从 live_list 的 extra_data 中提取直播间 GMV 信息
    live_list_row = conn.execute(
        "SELECT extra_data FROM collection_records "
        "WHERE batch_id=? AND account_id=? AND api_type='live_list'",
        (batch_id, account_id)
    ).fetchone()
    rooms_gmv: dict[str, dict] = {}
    if live_list_row and live_list_row['extra_data']:
        try:
            data = json.loads(live_list_row['extra_data'])
            for r in data.get('rooms', []):
                rooms_gmv[str(r.get('room_id', ''))] = r
        except (json.JSONDecodeError, TypeError):
            pass

    # 遍历 room_sessions，组装每个直播间的指标和完整率
    rooms = []
    completeness_list = []

    room_types_for_completion = get_room_types_for_completion(acc_platform, crawl_type)

    for rs in room_sessions:
        rid = rs['room_id']
        apis = room_api_map.get(rid, {})
        gmv = rooms_gmv.get(rid, {})
        indicators = {}
        hit = 0
        for t in expected_room:
            status = apis.get(t)
            indicators[t] = {'status': status}
            # 只统计用于完成率计算的 API 类型
            if status == 'success' and t in room_types_for_completion:
                hit += 1
        # 计算单个直播间完整率
        comp = hit / len(room_types_for_completion) if room_types_for_completion else 1.0
        completeness_list.append(comp)
        rooms.append({
            'room_id': rid,
            'start_time': rs['start_time'],
            'end_time': rs['end_time'],
            'room_name': gmv.get('room_name', ''),
            'revenue': gmv.get('revenue', '0'),
            'currency_code': gmv.get('currency_code', ''),
            'item_sold_cnt': gmv.get('item_sold_cnt', 0),
            'view_cnt': gmv.get('view_cnt', 0),
            'indicators': indicators,
            'completeness': comp,
        })

    # 4. 总完整率：综合账号级 + 直播间级
    total = len(expected_account) + len(room_sessions) * len(room_types_for_completion)
    success = sum(1 for t in expected_account if account_indicators[t]['status'] == 'success')
    success += sum(
        1 for r in rooms for t in room_types_for_completion
        if r['indicators'].get(t, {}).get('status') == 'success'
    )
    overall = success / total if total > 0 else 1.0

    return {
        'account_id': account_id,
        'batch_id': batch_id,
        'group_name': group_name,
        'platform': acc_platform,
        'account_indicators': account_indicators,
        'daily_stats': daily_stats,
        'rooms': rooms,
        'overall_completeness': overall,
    }
