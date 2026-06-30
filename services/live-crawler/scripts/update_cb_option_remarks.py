#!/usr/bin/env python3
"""
批量更新 AdsPower 环境的 remark，追加 cb_option（本土/跨境标记）

数据来源：docs/shopee直播_多站点标记结果.csv
remark 格式：vid:{validate_id}|country:{code}|cb:{0|1}

注意：AdsPower API 有限流，使用退避重试机制处理。
"""

import csv
import os
import sys
import time
import logging
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('update_cb_option.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 默认值与 core/config_base.py 的 ADSPOWER_CONFIG['api_url'] 对齐
ADSPOWER_API_URL = os.getenv("ADSPOWER_API_URL", "http://127.0.0.1:50325")
REQUEST_TIMEOUT = 10
REQUEST_INTERVAL = 1.5
MAX_RETRIES = 3
RETRY_DELAY = 3
RETRY_BACKOFF = 1.5

# CSV shop_type 到 cb_option 的映射
SHOP_TYPE_TO_CB = {
    "本土 (Local)": 0,
    "跨境 (Cross-Border)": 1,
}

# 国家代码映射（CSV 中的 region 转小写即可）
REGION_TO_COUNTRY = {
    "MY": "my",
    "ID": "id",
    "TH": "th",
    "SG": "sg",
    "PH": "ph",
    "VN": "vn",
    "BR": "br",
    "MX": "mx",
}


def parse_remark(remark: str) -> dict:
    """解析 remark 字符串"""
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


def build_new_remark(parsed: dict, cb_option: int) -> str:
    """构建新的 remark，保留 vid 和 country（如果有），添加/更新 cb"""
    vid = parsed.get('vid') or ''
    if not vid:
        return ''

    parts = [f"vid:{vid}"]

    # 保留原有的 country（如果有）
    existing_country = parsed.get('country')
    if existing_country:
        parts.append(f"country:{existing_country}")

    # 添加/更新 cb
    parts.append(f"cb:{cb_option}")

    return "|".join(parts)


def api_request_with_retry(method: str, url: str, **kwargs) -> dict | None:
    """带限流重试的 API 请求"""
    current_delay = RETRY_DELAY

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if method == 'GET':
                resp = requests.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
            else:
                resp = requests.post(url, timeout=REQUEST_TIMEOUT, **kwargs)
            resp.raise_for_status()
            data = resp.json()

            if data.get('code') == 0:
                return data
            # AdsPower 限流返回 code=-1 且 msg 包含 "Too many request"
            msg = data.get('msg', '')
            if 'too many' in msg.lower() or 'rate' in msg.lower():
                if attempt < MAX_RETRIES:
                    logger.warning(f"  限流，{current_delay}秒后重试（第{attempt}次）...")
                    time.sleep(current_delay)
                    current_delay *= RETRY_BACKOFF
                    continue
            # 其他错误
            if attempt < MAX_RETRIES:
                logger.warning(f"  API 错误: {msg}，{current_delay}秒后重试...")
                time.sleep(current_delay)
                current_delay *= RETRY_BACKOFF
            else:
                logger.error(f"  API 错误: {msg}")
                return None

        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"  请求异常: {e}，{current_delay}秒后重试...")
                time.sleep(current_delay)
                current_delay *= RETRY_BACKOFF
            else:
                logger.error(f"  请求异常: {e}")
                return None

    return None


def get_current_remark(profile_id: str) -> str:
    """获取环境当前的 remark"""
    url = f"{ADSPOWER_API_URL}/api/v1/user/list"
    data = api_request_with_retry('GET', url, params={"user_id": profile_id})
    if not data:
        return ''
    users = data.get('data', {}).get('list', [])
    if not users:
        return ''
    return users[0].get('remark', '')


def update_remark(profile_id: str, new_remark: str) -> bool:
    """更新环境的 remark"""
    url = f"{ADSPOWER_API_URL}/api/v1/user/update"
    data = api_request_with_retry('POST', url, json={
        "user_id": profile_id,
        "remark": new_remark
    })
    return data is not None


def read_csv(file_path: str) -> list[dict]:
    """读取 CSV 文件"""
    records = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    return records


def main():
    # CSV 文件路径
    project_root = Path(__file__).resolve().parent.parent.parent
    csv_path = project_root / "docs" / "shopee直播_多站点标记结果.csv"

    if not csv_path.exists():
        logger.error(f"CSV 文件不存在: {csv_path}")
        return

    logger.info("=" * 60)
    logger.info("批量更新 AdsPower 环境 remark（追加 cb_option）")
    logger.info(f"API 地址: {ADSPOWER_API_URL}")
    logger.info(f"CSV 文件: {csv_path}")
    logger.info("=" * 60)

    records = read_csv(str(csv_path))
    logger.info(f"CSV 共 {len(records)} 条记录")

    # 过滤：有 collection_id 且 shop_type 可映射
    valid_records = []
    for row in records:
        collection_id = row.get('collection_id', '').strip()
        shop_type = row.get('shop_type', '').strip()
        if not collection_id:
            continue
        if shop_type not in SHOP_TYPE_TO_CB:
            logger.info(f"  跳过 {collection_id}：shop_type={shop_type}")
            continue
        valid_records.append(row)

    logger.info(f"有效记录: {len(valid_records)} 条（已过滤无 collection_id 和无效 shop_type）")

    if not valid_records:
        logger.warning("没有需要处理的数据")
        return

    total = len(valid_records)
    success_count = 0
    skip_count = 0
    failed_count = 0

    for idx, row in enumerate(valid_records, start=1):
        collection_id = row['collection_id'].strip()
        shop_type = row['shop_type'].strip()
        region = row.get('region', '').strip().upper()
        room_name = row.get('room_name', '')
        cb_option = SHOP_TYPE_TO_CB[shop_type]
        country = REGION_TO_COUNTRY.get(region, region.lower())

        logger.info(f"\n[{idx}/{total}] {room_name} ({collection_id}) region={region} type={shop_type}")

        # 获取当前 remark
        current_remark = get_current_remark(collection_id)
        if not current_remark:
            logger.warning(f"  无法获取当前 remark，跳过")
            failed_count += 1
            time.sleep(REQUEST_INTERVAL)
            continue

        parsed = parse_remark(current_remark)
        logger.info(f"  当前 remark: {current_remark}")

        # 检查是否已经有正确的 cb 值（不检查 country，因为我们要保留原值）
        if parsed.get('cb') == cb_option:
            logger.info(f"  已是最新，跳过")
            skip_count += 1
            time.sleep(REQUEST_INTERVAL)
            continue

        # 构建新 remark（保留原有的 country，只添加/更新 cb）
        new_remark = build_new_remark(parsed, cb_option)
        if not new_remark:
            logger.warning(f"  remark 中无 vid，跳过")
            skip_count += 1
            time.sleep(REQUEST_INTERVAL)
            continue

        logger.info(f"  新 remark: {new_remark}")

        if update_remark(collection_id, new_remark):
            logger.info(f"  ✓ 更新成功")
            success_count += 1
        else:
            logger.error(f"  ✗ 更新失败")
            failed_count += 1

        time.sleep(REQUEST_INTERVAL)

    logger.info("\n" + "=" * 60)
    logger.info("处理完成")
    logger.info(f"总数: {total}, 成功: {success_count}, 跳过: {skip_count}, 失败: {failed_count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
