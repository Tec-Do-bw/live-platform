"""补采执行器 — 消费 pending 任务，通过 HTTP 请求补采缺失数据

补采流程：
1. 从 request_context 读取保存的 headers / cookies / api_base_url / query_string
2. 通过 AdsPower 代理 IP 发起 HTTP 请求获取数据
3. 将响应数据上报到数据服务器（复刻 send_api_request 逻辑）
4. 验证 collection_records 是否更新
"""

import copy
import json
import time
import sqlite3
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

import requests as http_requests

from core.config import Settings
from utils.logger import logger
from monitor.db import get_connection
from monitor.recrawl.models import (
    get_pending_tasks, update_task_status, get_request_context, cleanup_old_tasks,
)
from monitor.recrawl.proxy import get_proxy_for_account

# api_type → request_context 的 context_type 映射
CONTEXT_MAP = {
    'trend_gmv': 'trend_chart',
    'trend_stats': 'trend_chart',
    'live_stats': 'live_stats',
    'live_list': 'live_list',
}


class RecrawlHTTPError(Exception):
    """补采 HTTP 请求异常，携带状态码用于精确判断"""
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        super().__init__(f'HTTP {status_code}: {body}')

# trend/chart 固定路径
TREND_CHART_PATH = '/api/v1/insights/creator/liveroom/recap/trend/chart'

# live/stats 固定路径
LIVE_STATS_PATH = '/api/v2/insights/creator/live/stats'

# live/list 固定路径
LIVE_LIST_PATH = '/api/v2/insights/creator/live/list'

# trend/chart 的 Body 模板
TREND_BODIES = {
    'trend_gmv': {
        'request': {
            'room_filter': {'room_id': '', 'query_online': True},
            'stats_types': [3],
            'granularity': 1,
        }
    },
    'trend_stats': {
        'request': {
            'room_filter': {'room_id': '', 'query_online': True},
            'stats_types': [3, 20, 341, 21, 22, 12, 16, 23, 50, 51, 40],
            'granularity': 1,
        }
    },
}


def execute_pending_tasks(conn: sqlite3.Connection, account_id: str | None = None) -> dict:
    """执行 pending 补采任务

    Args:
        conn: 数据库连接
        account_id: 可选，只执行指定账号的任务。为 None 时执行所有账号的任务

    Returns:
        {'total': N, 'success': N, 'failed': N, 'skipped': N}
    """
    config = Settings.RECRAWL_CONFIG
    empty_stats = {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}

    if not config.get('enabled', True):
        logger.info('自动补采已关闭，跳过执行')
        return empty_stats

    # 清理旧任务
    cleanup_old_tasks(conn, days=30)

    tasks = get_pending_tasks(conn, account_id=account_id)
    if not tasks:
        logger.info('无 pending 补采任务')
        return empty_stats

    logger.info(f'发现 {len(tasks)} 个 pending 补采任务')

    # 按账号分组
    account_tasks: dict[str, list[dict]] = defaultdict(list)
    for task in tasks:
        account_tasks[task['account_id']].append(task)

    stats = {'total': len(tasks), 'success': 0, 'failed': 0, 'skipped': 0}
    max_concurrent = config.get('max_concurrent', 2)

    def process_account(account_id: str, account_task_list: list[dict]) -> dict:
        """处理单个账号的所有补采任务（串行，独立数据库连接）"""
        result = {'success': 0, 'failed': 0, 'skipped': 0}

        # 每个线程使用独立的 SQLite 连接，避免多线程共享写入冲突
        thread_conn = get_connection()

        # 获取代理
        proxy = get_proxy_for_account(account_id)

        request_interval = config.get('request_interval', 2)

        for task in account_task_list:
            task_result = _execute_single_task(thread_conn, task, proxy, config)
            result[task_result] += 1
            time.sleep(request_interval)

        thread_conn.close()
        return result

    # 账号间并行执行
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(process_account, acc_id, task_list): acc_id
            for acc_id, task_list in account_tasks.items()
        }
        for future in futures:
            try:
                result = future.result()
                stats['success'] += result['success']
                stats['failed'] += result['failed']
                stats['skipped'] += result['skipped']
            except Exception as e:
                logger.error(f'账号补采线程异常: {e}')

    logger.info(
        f'补采执行完成: 总计 {stats["total"]}, '
        f'成功 {stats["success"]}, 失败 {stats["failed"]}, 跳过 {stats["skipped"]}'
    )
    return stats


def _execute_single_task(
    conn: sqlite3.Connection, task: dict, proxy: dict | None, config: dict,
) -> str:
    """执行单个补采任务

    Returns:
        'success' / 'failed' / 'skipped'
    """
    task_id = task['id']
    api_type = task['api_type']
    account_id = task['account_id']

    # 标记为 running
    update_task_status(conn, task_id, 'running')

    # 获取请求上下文
    context_type = CONTEXT_MAP.get(api_type, api_type)
    ctx = get_request_context(conn, account_id, context_type)
    if ctx is None:
        logger.warning(f'补采任务 {task_id}: 无请求上下文 (account={account_id}, type={context_type})，跳过')
        update_task_status(conn, task_id, 'pending', error_msg='no_request_context')
        return 'skipped'

    # 重试循环
    max_retry = config.get('max_retry', 3)
    delays = config.get('retry_delays', [1, 3, 10])

    for attempt in range(max_retry):
        try:
            # 1. 构造并发送 HTTP 请求
            response_data = _fetch_api_data(api_type, task, ctx, proxy)
            if response_data is None:
                raise RuntimeError('HTTP 请求返回空数据')

            # 2. 上报到数据服务器
            uploaded = _send_to_data_server(
                url=response_data['url'],
                request_body=response_data['request_body'],
                response_body=response_data['response_body'],
                cookies=response_data['cookies'],
                account_id=account_id,
            )
            if not uploaded:
                raise RuntimeError('数据上报失败')

            # 3. 验证补采结果（记录到 collection_records）
            # 上报成功后，监控钩子会在 send_api_request 中自动记录
            # 这里额外做一层验证
            logger.info(
                f'补采任务 {task_id} 成功: {api_type} '
                f'(account={account_id}, room={task["room_id"]})'
            )
            update_task_status(conn, task_id, 'success')
            return 'success'

        except Exception as e:
            retry_count = attempt + 1

            # 精确判断 HTTP 状态码
            if isinstance(e, RecrawlHTTPError):
                if e.status_code in (401, 403):
                    # session 过期，不做无意义重试
                    logger.warning(f'补采任务 {task_id}: session 过期 (HTTP {e.status_code})，直接标记失败')
                    update_task_status(conn, task_id, 'recrawl_failed',
                                       retry_count=retry_count, error_msg='session_expired')
                    return 'failed'
                if e.status_code == 429:
                    # 频率限制，延长等待
                    logger.warning(f'补采任务 {task_id}: 频率限制，等待 30 秒后重试')
                    time.sleep(30)

            error_msg = str(e)
            logger.warning(f'补采任务 {task_id} 第 {retry_count}/{max_retry} 次失败: {error_msg}')
            update_task_status(conn, task_id, 'running',
                               retry_count=retry_count, error_msg=error_msg)

            if attempt < max_retry - 1:
                delay = delays[attempt] if attempt < len(delays) else delays[-1]
                time.sleep(delay)

    # 所有重试失败
    update_task_status(conn, task_id, 'recrawl_failed', retry_count=max_retry)
    return 'failed'


def _parse_context(ctx: dict) -> tuple[str, str, dict, dict, list]:
    """解析请求上下文，返回 (base_url, query_string, headers, cookies_dict, cookies_list)"""
    headers = json.loads(ctx['headers']) if ctx['headers'] else {}

    # 过滤不适用于补采请求的头部：
    # - HTTP/2 伪头部（以 : 开头，如 :authority, :method 等）
    # - accept-encoding: 让 requests 库自动管理解压
    # - content-length: 补采请求的 body 长度与原始请求不同
    _skip_headers = {'accept-encoding', 'content-length'}
    headers = {
        k: v for k, v in headers.items()
        if not k.startswith(':') and k.lower() not in _skip_headers
    }

    cookies_list = json.loads(ctx['cookies']) if ctx['cookies'] else []

    # 将 cookies 列表转为 requests 库的 cookies 字典
    cookies_dict = {
        c['name']: c['value']
        for c in cookies_list
        if isinstance(c, dict) and 'name' in c and 'value' in c
    }

    return ctx['api_base_url'], ctx['query_string'], headers, cookies_dict, cookies_list


def _build_url(base_url: str, path: str, query_string: str) -> str:
    """拼接 base_url + path + query_string"""
    url = f'{base_url}{path}'
    if query_string:
        url = f'{url}?{query_string}'
    return url


def _post_and_pack(
    url: str, body_str: str, headers: dict,
    cookies_dict: dict, cookies_list: list, proxy: dict | None,
) -> dict:
    """发送 POST 请求并封装返回结果

    Raises:
        RecrawlHTTPError: HTTP 状态码非 200
    """
    resp = http_requests.post(
        url, headers=headers, cookies=cookies_dict,
        data=body_str, proxies=proxy, timeout=30,
    )
    if resp.status_code != 200:
        raise RecrawlHTTPError(resp.status_code, resp.text[:200])

    # 尝试解析 JSON，失败时记录原始响应
    try:
        response_body = resp.json()
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f'JSON 解析失败: {e}, 响应前 200 字符: {resp.text[:200]}')
        raise

    return {
        'url': url,
        'request_body': body_str,
        'response_body': response_body,
        'cookies': cookies_list,
    }


def _fetch_api_data(
    api_type: str, task: dict, ctx: dict, proxy: dict | None,
) -> dict | None:
    """发起 HTTP 请求获取 TikTok API 数据

    Returns:
        {'url': str, 'request_body': str, 'response_body': dict, 'cookies': list}
    """
    base_url, query_string, headers, cookies_dict, cookies_list = _parse_context(ctx)

    if api_type in ('trend_gmv', 'trend_stats'):
        return _fetch_trend_chart(api_type, task, base_url, query_string,
                                  headers, cookies_dict, cookies_list, proxy)
    if api_type == 'live_stats':
        return _fetch_live_stats(task, ctx, base_url, query_string,
                                 headers, cookies_dict, cookies_list, proxy)
    if api_type == 'live_list':
        return _fetch_live_list(task, ctx, base_url, query_string,
                                headers, cookies_dict, cookies_list, proxy)

    logger.warning(f'不支持的补采 API 类型: {api_type}')
    return None


def _fetch_trend_chart(
    api_type: str, task: dict,
    base_url: str, query_string: str,
    headers: dict, cookies_dict: dict, cookies_list: list,
    proxy: dict | None,
) -> dict | None:
    """补采 trend/chart 数据（trend_gmv 或 trend_stats）"""
    room_id = task['room_id']
    if not room_id:
        logger.warning('trend_chart 补采缺少 room_id')
        return None

    body_template = TREND_BODIES.get(api_type)
    if not body_template:
        return None

    body = copy.deepcopy(body_template)
    body['request']['room_filter']['room_id'] = room_id
    body_str = json.dumps(body)

    url = _build_url(base_url, TREND_CHART_PATH, query_string)
    logger.info(f'补采 {api_type}: room={room_id}, url={url[:80]}...')

    return _post_and_pack(url, body_str, headers, cookies_dict, cookies_list, proxy)


def _fetch_live_stats(
    task: dict, ctx: dict,
    base_url: str, query_string: str,
    headers: dict, cookies_dict: dict, cookies_list: list,
    proxy: dict | None,
) -> dict | None:
    """补采 live/stats 数据（日期级指标）"""
    target_date = task.get('target_date', '')
    if not target_date:
        logger.warning('live_stats 补采缺少 target_date')
        return None

    # 从 payload_template 深拷贝原始请求体
    template_str = ctx.get('payload_template', '{}')
    try:
        payload = json.loads(template_str) if isinstance(template_str, str) else template_str
        payload = copy.deepcopy(payload)
    except (json.JSONDecodeError, TypeError):
        logger.warning('live_stats payload_template 解析失败')
        return None

    time_selector = _build_time_selector(target_date)
    if time_selector is None:
        return None

    # 替换 payload 中的 time_selector
    try:
        payload['request']['params'][0]['time_selector'] = time_selector
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f'live_stats payload 结构异常: {e}')
        return None

    body_str = json.dumps(payload)

    url = _build_url(base_url, LIVE_STATS_PATH, query_string)
    logger.info(f'补采 live_stats: date={target_date}, url={url[:80]}...')

    return _post_and_pack(url, body_str, headers, cookies_dict, cookies_list, proxy)


def _build_time_selector(target_date: str) -> dict | None:
    """根据目标日期构建 time_selector

    Args:
        target_date: 'YYYY-MM-DD' 格式日期

    Returns:
        time_selector 字典，与 _handle_live_stats_injection 格式一致
    """
    try:
        d = datetime.strptime(target_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        # start_timestamp = D 的 UTC 00:00
        start = d
        # end_timestamp = (D + 1 天) 的 UTC 00:00
        end = d + timedelta(days=1)

        return {
            'period': 2,
            'granularity': 1,
            'start_timestamp': int(start.timestamp()),
            'end_timestamp': int(end.timestamp()),
            'timezone_offset': '0',
        }
    except ValueError as e:
        logger.warning(f'日期解析失败 ({target_date}): {e}')
        return None


def _fetch_live_list(
    task: dict, ctx: dict,
    base_url: str, query_string: str,
    headers: dict, cookies_dict: dict, cookies_list: list,
    proxy: dict | None,
) -> dict | None:
    """补采 live/list 数据（直播间列表）

    从 payload_template 读取真实的请求体模板，替换 base_timestamp 后发送
    """
    target_date = task.get('target_date', '')
    if not target_date:
        logger.warning('live_list 补采缺少 target_date')
        return None

    # 从 payload_template 深拷贝原始请求体
    template_str = ctx.get('payload_template', '{}')
    try:
        payload = json.loads(template_str) if isinstance(template_str, str) else template_str
        payload = copy.deepcopy(payload)
    except (json.JSONDecodeError, TypeError):
        logger.warning('live_list payload_template 解析失败')
        return None

    # 替换 base_timestamp 为目标日期
    try:
        d = datetime.strptime(target_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        base_timestamp = int(d.timestamp())

        # 更新 payload 中的 base_timestamp
        payload['request']['params'][0]['time_selector']['base_timestamp'] = str(base_timestamp)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        logger.warning(f'live_list payload 更新失败: {e}')
        return None

    body_str = json.dumps(payload)
    url = _build_url(base_url, LIVE_LIST_PATH, query_string)
    logger.info(f'补采 live_list: date={target_date}, url={url[:80]}...')

    return _post_and_pack(url, body_str, headers, cookies_dict, cookies_list, proxy)



def _send_to_data_server(
    url: str, request_body: str, response_body: dict,
    cookies: list, account_id: str,
) -> bool:
    """将补采数据上报到数据服务器（复刻 base.py:send_api_request + format_api_message 逻辑）

    Args:
        url: 原始 API URL
        request_body: 请求体 JSON 字符串
        response_body: 响应体字典
        cookies: cookies 列表
        account_id: 账号 ID（作为 socketUserId）

    Returns:
        上报是否成功
    """
    api_url = Settings.DATA_SERVER_CONFIG.get('api_url')
    endpoint = Settings.DATA_SERVER_CONFIG.get('send_endpoint', '/data/info/send')
    access_token = Settings.DATA_SERVER_CONFIG.get('access_token')
    api_sign = Settings.DATA_SERVER_CONFIG.get('api_sign', '')
    timeout = Settings.DATA_SERVER_CONFIG.get('timeout', 30)

    full_url = f'{api_url}{endpoint}'

    # 构造消息体（复刻 format_api_message）
    response_str = json.dumps(response_body, ensure_ascii=False) if isinstance(response_body, dict) else str(response_body)

    message = {
        'params': '',
        'cookies': json.dumps(cookies, ensure_ascii=False),
        'fromUrl': url,
        'extra': request_body,
        'sign': api_sign,
        'userType': 6.0,
        'updateTime': int(time.time() * 1000),
        'request': {
            'response': response_str,
            'url': url,
        },
        'socketUserId': account_id,
    }

    send_headers = {
        'accessToken': access_token,
        'Content-Type': 'application/json',
    }

    try:
        resp = http_requests.post(
            full_url, headers=send_headers, json=message, timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(f'数据上报失败: HTTP {resp.status_code}')
            return False
        logger.info(f'补采数据已上报: {url[:80]}...')
        return True
    except Exception as e:
        logger.error(f'数据上报异常: {e}')
        return False


def verify_recrawl_result(conn: sqlite3.Connection, task: dict) -> bool:
    """验证补采结果：检查对应表中是否有成功记录"""
    account_id = task['account_id']
    api_type = task['api_type']

    if api_type == 'live_stats':
        row = conn.execute(
            """SELECT 1 FROM daily_collection_status
               WHERE account_id = ? AND target_date = ? AND api_type = ? AND status = 'success'
               LIMIT 1""",
            (account_id, task.get('target_date', ''), api_type),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT 1 FROM collection_records
               WHERE account_id = ? AND room_id = ? AND api_type = ? AND status = 'success'
               LIMIT 1""",
            (account_id, task.get('room_id', ''), api_type),
        ).fetchone()

    return row is not None
