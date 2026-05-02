#!/usr/bin/env python3
"""
批量更新 AdsPower 环境的 remark 字段

功能：
1. 从 Excel 文件读取 collection_id 和 validate_id
2. 更新 remark 为 vid:{validate_id} 格式（不保留 advertiser_name）
3. 失败请求自动重试
"""

import os
import sys
import logging
import time
from typing import Dict
import requests
import openpyxl

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('update_remarks.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# AdsPower API 配置
ADSPOWER_API_URL = os.getenv("ADSPOWER_API_URL", "http://localhost:50325")
REQUEST_TIMEOUT = 10
REQUEST_INTERVAL = 1.5
MAX_RETRIES = 3


def read_excel(file_path: str) -> Dict[str, str]:
    """读取 Excel 文件，提取 collection_id 和 validate_id"""
    logger.info(f"开始读取 Excel 文件: {file_path}")

    try:
        wb = openpyxl.load_workbook(file_path)
        ws = wb.active

        data = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            collection_id, validate_id = row[0], row[1]

            if collection_id and str(collection_id).strip():
                data[str(collection_id).strip()] = str(validate_id).strip() if validate_id else ""

        logger.info(f"成功读取 {len(data)} 条记录")
        return data

    except Exception as e:
        logger.error(f"读取 Excel 文件失败: {e}")
        raise


def update_remark_with_retry(profile_id: str, validate_id: str) -> bool:
    """更新 remark，失败自动重试"""
    new_remark = f"vid:{validate_id}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            url = f"{ADSPOWER_API_URL}/api/v1/user/update"
            payload = {
                "user_id": profile_id,
                "remark": new_remark
            }

            response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            result = response.json()
            if result.get("code") == 0:
                return True
            else:
                error_msg = result.get("msg", "未知错误")
                if attempt < MAX_RETRIES:
                    logger.warning(f"  第 {attempt} 次尝试失败: {error_msg}，{REQUEST_INTERVAL}秒后重试...")
                    time.sleep(REQUEST_INTERVAL)
                else:
                    logger.error(f"  第 {attempt} 次尝试失败: {error_msg}")
                    return False

        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning(f"  第 {attempt} 次尝试异常: {e}，{REQUEST_INTERVAL}秒后重试...")
                time.sleep(REQUEST_INTERVAL)
            else:
                logger.error(f"  第 {attempt} 次尝试异常: {e}")
                return False

    return False


def main():
    """主流程"""
    excel_file = "shopee_ids.xlsx"

    logger.info("=" * 60)
    logger.info("开始批量更新 AdsPower 环境 remark")
    logger.info(f"API 地址: {ADSPOWER_API_URL}")
    logger.info(f"remark 格式: vid:{{validate_id}} (不保留 advertiser_name)")
    logger.info("=" * 60)

    # 1. 读取 Excel 文件
    try:
        data = read_excel(excel_file)
    except Exception:
        logger.error("无法读取 Excel 文件，程序退出")
        return

    if not data:
        logger.warning("没有需要处理的数据")
        return

    # 2. 批量处理
    total = len(data)
    success_count = 0
    failed_count = 0

    for idx, (collection_id, validate_id) in enumerate(data.items(), start=1):
        logger.info(f"\n[{idx}/{total}] 处理环境: {collection_id}")
        logger.info(f"  目标 remark: vid:{validate_id}")

        if update_remark_with_retry(collection_id, validate_id):
            logger.info(f"  [OK] 更新成功")
            success_count += 1
        else:
            logger.error(f"  [FAIL] 更新失败")
            failed_count += 1

        # 添加请求间隔
        if idx < total:
            time.sleep(REQUEST_INTERVAL)

    # 3. 输出统计
    logger.info("\n" + "=" * 60)
    logger.info("处理完成")
    logger.info(f"总数: {total}, 成功: {success_count}, 失败: {failed_count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
