#!/usr/bin/env python3
"""
获取 AdsPower 中 Shopee 相关环境信息

筛选逻辑：分组名包含 "shopee"（不区分大小写）
输出字段：采集ID、分组名、名称、country、symbol
country 从 remark 解析（格式：vid:xxx|country:xx|cb:x）
symbol 由 CURRENCY_MAPPING 映射

用法：python scripts/list_shopee_accounts.py
"""

import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

import requests
from openpyxl import Workbook

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 默认值与 core/config_base.py 的 ADSPOWER_CONFIG['api_url'] 对齐
ADSPOWER_API_URL = os.getenv("ADSPOWER_API_URL", "http://127.0.0.1:50325")
REQUEST_TIMEOUT = 10
REQUEST_INTERVAL = 1.5
MAX_RETRIES = 3
RETRY_DELAY = 3
RETRY_BACKOFF = 1.5
PAGE_SIZE = 100

CURRENCY_MAPPING = {
    "id": {"currency": "IDR", "symbol": "Rp"},
    "my": {"currency": "MYR", "symbol": "RM"},
    "th": {"currency": "THB", "symbol": "฿"},
    "vn": {"currency": "VND", "symbol": "₫"},
    "ph": {"currency": "PHP", "symbol": "₱"},
    "sg": {"currency": "SGD", "symbol": "$"},
    "tw": {"currency": "TWD", "symbol": "NT$"},
    "br": {"currency": "BRL", "symbol": "R$"},
    "mx": {"currency": "MXN", "symbol": "$"},
}


def api_get_with_retry(url: str, params: dict = None) -> dict | None:
    """带限流退避重试的 GET 请求"""
    current_delay = RETRY_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get('code') == 0:
                return data
            msg = data.get('msg', '')
            if 'too many' in msg.lower() or 'rate' in msg.lower():
                if attempt < MAX_RETRIES:
                    logger.warning(f"限流，{current_delay:.1f}秒后重试（第{attempt}次）...")
                    time.sleep(current_delay)
                    current_delay *= RETRY_BACKOFF
                    continue
            if attempt < MAX_RETRIES:
                logger.warning(f"API 错误: {msg}，{current_delay:.1f}秒后重试...")
                time.sleep(current_delay)
                current_delay *= RETRY_BACKOFF
            else:
                logger.error(f"API 错误: {msg}")
                return None
        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"请求异常: {e}，{current_delay:.1f}秒后重试...")
                time.sleep(current_delay)
                current_delay *= RETRY_BACKOFF
            else:
                logger.error(f"请求异常: {e}")
                return None
    return None


def parse_remark(remark: str) -> dict:
    """解析 remark 字符串，提取 country"""
    result = {'vid': None, 'country': None, 'cb': None}
    if not remark or not remark.startswith('vid:'):
        return result
    for part in remark.split('|'):
        part = part.strip()
        if part.startswith('vid:'):
            result['vid'] = part[4:].strip()
        elif part.startswith('country:'):
            result['country'] = part[8:].strip().lower()
        elif part.startswith('cb:'):
            try:
                result['cb'] = int(part[3:].strip())
            except ValueError:
                pass
    return result


def get_shopee_groups() -> list[dict]:
    """分页获取所有分组，筛选名称包含 shopee 的"""
    matched = []
    page = 1
    while True:
        data = api_get_with_retry(
            f"{ADSPOWER_API_URL}/api/v1/group/list",
            params={"page": page, "page_size": PAGE_SIZE}
        )
        if not data:
            break
        groups = data.get('data', {}).get('list', [])
        if not groups:
            break
        for g in groups:
            name = g.get('group_name', '')
            if 'shopee' in name.lower():
                matched.append({'group_id': g['group_id'], 'group_name': name})
        if len(groups) < PAGE_SIZE:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL)
    return matched


def get_users_in_group(group_id: str, group_name: str) -> list[dict]:
    """分页获取指定分组下的所有环境"""
    users = []
    page = 1
    while True:
        data = api_get_with_retry(
            f"{ADSPOWER_API_URL}/api/v1/user/list",
            params={"group_id": group_id, "page": page, "page_size": PAGE_SIZE}
        )
        if not data:
            break
        user_list = data.get('data', {}).get('list', [])
        if not user_list:
            break
        for u in user_list:
            remark = u.get('remark', '')
            parsed = parse_remark(remark)
            country = parsed['country'] or ''
            symbol = CURRENCY_MAPPING.get(country, {}).get('symbol', '')
            users.append({
                'id': u.get('user_id', ''),
                'group': group_name,
                'name': u.get('name', ''),
                'country': country,
                'symbol': symbol,
            })
        if len(user_list) < PAGE_SIZE:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL)
    return users


def main():
    logger.info(f"AdsPower API: {ADSPOWER_API_URL}")
    logger.info("正在获取 Shopee 相关分组...")

    groups = get_shopee_groups()
    if not groups:
        logger.warning("未找到包含 shopee 的分组")
        return

    logger.info(f"找到 {len(groups)} 个 Shopee 分组: {[g['group_name'] for g in groups]}")

    all_accounts = []
    for g in groups:
        time.sleep(REQUEST_INTERVAL)
        accounts = get_users_in_group(g['group_id'], g['group_name'])
        logger.info(f"  分组 [{g['group_name']}] 下 {len(accounts)} 个环境")
        all_accounts.extend(accounts)

    if not all_accounts:
        logger.warning("未找到任何 Shopee 环境")
        return

    # 保存为 Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Shopee Accounts"
    ws.append(["采集ID", "分组", "名称", "Country", "Symbol"])
    for acc in all_accounts:
        ws.append([acc['id'], acc['group'], acc['name'], acc['country'], acc['symbol']])

    # 自动调整列宽
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    output_dir = Path(__file__).resolve().parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    filename = f"shopee_accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    output_path = output_dir / filename
    wb.save(str(output_path))

    logger.info(f"共 {len(all_accounts)} 个 Shopee 环境，已保存至: {output_path}")


if __name__ == "__main__":
    main()
