#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手动发送登录状态回调 + 更新监控系统登录状态。

从 base.py:send_login_callback() 中拆分出来的独立脚本，
用于在不启动爬虫的情况下手动更改账号登录状态。

用法:
    # 标记账号登录成功
    python -m scripts.login_callback <collection_id> success --platform tiktok --group "TK-马来"

    # 标记账号登出
    python -m scripts.login_callback <collection_id> logout --platform tiktok --reason "cookie过期"

    # 批量操作（逗号分隔多个 ID）
    python -m scripts.login_callback id1,id2,id3 success --platform shopee

    # 仅发送 HTTP 回调，不更新本地监控
    python -m scripts.login_callback <collection_id> logout --only-callback

    # 仅更新本地监控，不发送 HTTP 回调
    python -m scripts.login_callback <collection_id> success --only-monitor
"""

import sys
import argparse
import requests
from pathlib import Path

# 将项目根目录加入 sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from core.config import Settings
from utils.logger import logger


def send_http_callback(collection_id: str, login_status: str, platform: str,
                       reason: str = "") -> bool:
    """发送登录状态 HTTP 回调到后端服务器。

    Args:
        collection_id: 采集ID（browser_id）
        login_status: 登录状态，"success" 或 "logout"
        platform: 平台标识（tiktok / shopee）
        reason: 登出原因（可选）

    Returns:
        bool: 是否发送成功
    """
    callback_config = Settings.LOGIN_CALLBACK_CONFIG
    if not callback_config.get("enabled", True):
        logger.warning('登录回调已禁用（配置 enabled=False），跳过 HTTP 回调')
        return False

    callback_url = callback_config.get("url")
    access_token = callback_config.get("access_token", "")
    timeout = callback_config.get("timeout", 10)

    if not callback_url:
        logger.error('未配置登录回调URL，无法发送回调')
        return False

    payload = {
        "login_status": login_status,
        "media": platform,
        "collection_id": collection_id,
        "reason": reason,
    }

    headers = {"Content-Type": "application/json"}
    if access_token:
        headers["accessToken"] = access_token

    try:
        logger.info(f'发送登录回调: status={login_status}, platform={platform}, '
                    f'collection_id={collection_id}, url={callback_url}')
        response = requests.post(callback_url, headers=headers, json=payload,
                                 timeout=timeout)

        if response.status_code == 200:
            logger.info(f'登录回调发送成功: {login_status}')
            return True
        else:
            logger.warning(f'登录回调响应异常 {response.status_code}: '
                           f'{response.text[:200]}')
            return False

    except requests.Timeout:
        logger.warning('登录回调请求超时')
    except requests.ConnectionError as e:
        logger.warning(f'登录回调连接失败: {e}')
    except Exception as e:
        logger.error(f'发送登录回调异常: {e}')

    return False


def update_monitor_status(collection_id: str, login_status: str, platform: str,
                          group_name: str = "", reason: str = "") -> bool:
    """更新本地监控系统的登录状态（SQLite）。

    Args:
        collection_id: 采集ID（browser_id）
        login_status: 登录状态，"success" 或 "logout"
        platform: 平台标识
        group_name: 分组名称
        reason: 登出原因（可选）

    Returns:
        bool: 是否更新成功
    """
    try:
        from monitor import get_monitor
        from monitor.login_status_manager import LoginStatusManager

        monitor = get_monitor()
        status_mgr = LoginStatusManager(monitor.conn)

        status_mgr.record_login_status(
            account_id=collection_id,
            platform=platform,
            group_name=group_name,
            login_status=login_status,
            reason=reason,
        )
        logger.info(f'监控系统登录状态已更新: {collection_id} -> {login_status}')
        return True

    except Exception as e:
        logger.error(f'更新监控系统登录状态失败: {e}')
        return False


def process_single(collection_id: str, login_status: str, platform: str,
                   group_name: str, reason: str,
                   do_callback: bool, do_monitor: bool) -> dict:
    """处理单个账号的登录状态变更。

    Returns:
        dict: {'callback': bool|None, 'monitor': bool|None}
    """
    result = {'callback': None, 'monitor': None}

    if do_callback:
        result['callback'] = send_http_callback(
            collection_id, login_status, platform, reason)

    if do_monitor:
        result['monitor'] = update_monitor_status(
            collection_id, login_status, platform, group_name, reason)

    return result


def main():
    parser = argparse.ArgumentParser(
        description='手动发送登录状态回调并更新监控系统')
    parser.add_argument('collection_ids',
                        help='采集ID（browser_id），多个用逗号分隔')
    parser.add_argument('status', choices=['success', 'logout'],
                        help='登录状态')
    parser.add_argument('--platform', default='tiktok',
                        help='平台标识（默认 tiktok）')
    parser.add_argument('--group', default='',
                        help='AdsPower 分组名称')
    parser.add_argument('--reason', default='',
                        help='登出原因（仅 logout 时有意义）')
    parser.add_argument('--only-callback', action='store_true',
                        help='仅发送 HTTP 回调，不更新本地监控')
    parser.add_argument('--only-monitor', action='store_true',
                        help='仅更新本地监控，不发送 HTTP 回调')

    args = parser.parse_args()

    # 确定执行哪些操作
    do_callback = True
    do_monitor = True
    if args.only_callback:
        do_monitor = False
    elif args.only_monitor:
        do_callback = False

    # 解析多个 ID
    ids = [cid.strip() for cid in args.collection_ids.split(',') if cid.strip()]

    if not ids:
        logger.error('未提供有效的 collection_id')
        sys.exit(1)

    logger.info(f'开始处理 {len(ids)} 个账号，'
                f'状态={args.status}, 平台={args.platform}')

    success_count = 0
    fail_count = 0

    for cid in ids:
        logger.info(f'--- 处理账号: {cid} ---')
        result = process_single(
            collection_id=cid,
            login_status=args.status,
            platform=args.platform,
            group_name=args.group,
            reason=args.reason,
            do_callback=do_callback,
            do_monitor=do_monitor,
        )

        # 判断是否全部成功
        outcomes = [v for v in result.values() if v is not None]
        if outcomes and all(outcomes):
            success_count += 1
        else:
            fail_count += 1

    logger.info(f'处理完成: 成功 {success_count}, 失败 {fail_count}, 共 {len(ids)}')

    if fail_count > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
