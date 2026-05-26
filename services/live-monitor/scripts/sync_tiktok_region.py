"""TikTok 主播国家信息对比脚本

用途：
    - 读取 Excel 中的 TikTok 直播间数据
    - 调用 /liveRoom/portInfo 接口获取 publish_region 和 live_region
    - 对比 API 返回的国家信息与原始 country_code
    - 生成包含对比结果的新 Excel 文件

使用：
    python scripts/sync_tiktok_region.py --dry-run  # 试运行（前 5 条）
    python scripts/sync_tiktok_region.py            # 完整运行
    python scripts/sync_tiktok_region.py --input data.xlsx --output result.xlsx

API 规范：
    详见 docs/specs/live-room-api.md
"""

import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from tqdm import tqdm

# 添加父目录到 sys.path 以导入 utils
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import Logings


@dataclass
class ApiConfig:
    """API 配置"""
    endpoint: str
    access_token: str
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


def load_api_config() -> ApiConfig:
    """从 config.py 读取 TikTok API 配置

    Returns:
        ApiConfig 实例
    """
    from config import requests_config

    tiktok_config = requests_config["TiktokLive"]["LiveRoomLink"]["doc"]
    return ApiConfig(
        endpoint=tiktok_config["endpoint"],
        access_token=tiktok_config["headers"]["access-token"],
        timeout=30,
        max_retries=3,
        retry_delay=1.0
    )


def load_excel_data(file_path: Path, logger) -> pd.DataFrame:
    """读取 Excel 文件并返回 DataFrame

    Args:
        file_path: Excel 文件路径
        logger: 日志对象

    Returns:
        包含所有列的 DataFrame

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: Excel 格式错误
    """
    if not file_path.exists():
        logger.error(f"文件不存在: {file_path}")
        raise FileNotFoundError(f"文件不存在: {file_path}")

    try:
        df = pd.read_excel(file_path, engine="openpyxl")
        logger.info(f"成功读取 Excel | 总行数={len(df)} | 列数={len(df.columns)}")
        return df
    except Exception as e:
        logger.error(f"Excel 读取失败: {e}")
        raise ValueError(f"Excel 格式错误: {e}")


def call_api_with_retry(
    room_url: str,
    config: ApiConfig,
    logger
) -> tuple[int, dict | None, str, float]:
    """调用 /liveRoom/portInfo 接口（带重试）

    Args:
        room_url: 直播间 URL
        config: API 配置
        logger: 日志对象

    Returns:
        (code, port_info, error_msg, elapsed_time) 四元组
        - code: 业务码（200/2001/4xxx/5xxx）
        - port_info: 成功时的 port_info 字典，失败时为 None
        - error_msg: 失败时的错误摘要，成功时为空字符串
        - elapsed_time: 请求耗时（秒，包含重试）

    重试策略:
        - 5xxx 错误：最多重试 3 次，指数退避（1s, 2s, 4s）
        - 4xxx 错误：不重试（资源不存在/入参错误）
        - 网络异常：最多重试 3 次，固定间隔 2s
    """
    start_time = time.time()

    for attempt in range(config.max_retries):
        try:
            response = requests.post(
                config.endpoint,
                json={"mateUrl": room_url},
                headers={"access-token": config.access_token},
                timeout=config.timeout
            )
            data = response.json()
            code = data.get("code", 5099)

            # 成功或不可重试错误：直接返回
            if code in (200, 2001) or 4000 <= code < 5000:
                port_info = data.get("data", {}).get("port_info") if code in (200, 2001) else None
                elapsed = time.time() - start_time
                return code, port_info, "", elapsed

            # 5xxx 错误：重试
            if 5000 <= code < 6000:
                error_msg = data.get("error", {}).get("detail", "未知错误")
                if attempt < config.max_retries - 1:
                    delay = 2 ** attempt  # 指数退避：1s, 2s, 4s
                    logger.warning(
                        f"API 返回 {code}，{delay}s 后重试 "
                        f"({attempt + 1}/{config.max_retries}) | {room_url}"
                    )
                    time.sleep(delay)
                    continue
                elapsed = time.time() - start_time
                return code, None, error_msg, elapsed

        except requests.RequestException as e:
            if attempt < config.max_retries - 1:
                logger.warning(
                    f"网络异常，2s 后重试 ({attempt + 1}/{config.max_retries}) | "
                    f"{room_url} | {e}"
                )
                time.sleep(2)
                continue
            elapsed = time.time() - start_time
            return 5001, None, f"网络异常: {e}", elapsed

    elapsed = time.time() - start_time
    return 5099, None, "达到最大重试次数", elapsed


def extract_region_fields(
    code: int,
    port_info: dict | None,
    original_country: str
) -> dict[str, Any]:
    """从 API 响应提取 region 字段并对比

    Args:
        code: API 业务码
        port_info: API 返回的 port_info 字典
        original_country: 原始 Excel 中的 country_code

    Returns:
        {
            "publish_region": str,      # 视频发布国家（空字符串表示未获取到）
            "live_region": str,         # 开播国家（空字符串表示从未开播）
            "region_match": bool,       # 是否与 country_code 匹配
            "api_status": str,          # "success" | "failed"
            "error_detail": str         # 失败原因（成功时为空）
        }

    对比逻辑:
        - code=200 或 2001：提取 publish_region 和 live_region
        - region_match = (publish_region == country_code) or (live_region == country_code)
        - code=4xxx/5xxx：region 字段留空，api_status="failed"
    """
    if code in (200, 2001) and port_info:
        publish_region = port_info.get("publish_region", "")
        live_region = port_info.get("live_region", "")
        # 任一 region 匹配即视为匹配
        region_match = (
            publish_region == original_country or
            live_region == original_country
        )
        return {
            "publish_region": publish_region,
            "live_region": live_region,
            "region_match": region_match,
            "api_status": "success",
            "error_detail": ""
        }
    else:
        return {
            "publish_region": "",
            "live_region": "",
            "region_match": False,
            "api_status": "failed",
            "error_detail": f"API 返回 code={code}"
        }


def process_single_row(
    row: pd.Series,
    config: ApiConfig,
    logger
) -> dict[str, Any]:
    """处理单行数据（调用 API + 字段映射）

    Args:
        row: DataFrame 的一行（包含 room_url, country_code 等字段）
        config: API 配置
        logger: 日志对象

    Returns:
        包含新增字段和耗时的字典
    """
    room_url = row["room_url"]
    country_code = row["country_code"]

    # 调用 API
    code, port_info, error_msg, elapsed_time = call_api_with_retry(room_url, config, logger)

    # 提取字段
    result = extract_region_fields(code, port_info, country_code)

    # 如果失败，记录详细错误信息
    if result["api_status"] == "failed" and error_msg:
        result["error_detail"] = error_msg

    # 添加耗时信息
    result["elapsed_time"] = elapsed_time

    return result


def sync_tiktok_regions(
    input_file: Path,
    output_file: Path,
    config: ApiConfig,
    logger,
    dry_run: bool = False,
    max_workers: int = 10
) -> dict[str, Any]:
    """主流程：遍历 TikTok 数据，调用 API，保存结果

    Args:
        input_file: 输入 Excel 路径
        output_file: 输出 Excel 路径
        config: API 配置
        logger: 日志对象
        dry_run: 是否为试运行（只处理前 5 条）
        max_workers: 最大并发线程数

    Returns:
        统计信息字典
    """
    start_time = time.time()

    # 读取 Excel
    df = load_excel_data(input_file, logger)

    # 过滤 TikTok 数据
    tiktok_df = df[df["platform"] == "tiktok"].copy()
    total_count = len(tiktok_df)

    if total_count == 0:
        logger.warning("未找到 platform='tiktok' 的数据")
        return {
            "total": 0, "success": 0, "failed": 0, "match": 0, "mismatch": 0,
            "avg_time": 0, "min_time": 0, "max_time": 0
        }

    logger.info(f"开始处理 TikTok 数据 | 总数={total_count} | 并发数={max_workers}")

    # 试运行模式：只处理前 5 条
    if dry_run:
        tiktok_df = tiktok_df.head(5)
        logger.info(f"试运行模式 | 只处理前 {len(tiktok_df)} 条")

    # 初始化统计
    stats = {"total": 0, "success": 0, "failed": 0, "match": 0, "mismatch": 0}
    failure_reasons = Counter()
    elapsed_times = []  # 记录所有请求耗时

    # 初始化新增字段
    new_fields = {
        "publish_region": [],
        "live_region": [],
        "region_match": [],
        "api_status": [],
        "error_detail": []
    }

    # 使用 ThreadPoolExecutor 并发处理
    results = {}  # {index: result}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_index = {
            executor.submit(process_single_row, row, config, logger): idx
            for idx, row in tiktok_df.iterrows()
        }

        # 使用 tqdm 显示进度
        with tqdm(total=len(future_to_index), desc="处理进度") as pbar:
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    result = future.result()
                    results[idx] = result

                    # 记录耗时
                    elapsed_times.append(result["elapsed_time"])

                    # 更新统计
                    stats["total"] += 1
                    if result["api_status"] == "success":
                        stats["success"] += 1
                        if result["region_match"]:
                            stats["match"] += 1
                        else:
                            stats["mismatch"] += 1
                    else:
                        stats["failed"] += 1
                        failure_reasons[result["error_detail"]] += 1
                        logger.warning(
                            f"API 失败 | room_url={tiktok_df.loc[idx, 'room_url']} | "
                            f"reason={result['error_detail']}"
                        )

                except Exception as e:
                    logger.error(f"处理行 {idx} 时发生异常: {e}")
                    # 记录失败结果
                    results[idx] = {
                        "publish_region": "",
                        "live_region": "",
                        "region_match": False,
                        "api_status": "failed",
                        "error_detail": f"处理异常: {e}",
                        "elapsed_time": 0
                    }
                    stats["total"] += 1
                    stats["failed"] += 1

                pbar.update(1)

    # 按原始顺序整理结果
    for idx in tiktok_df.index:
        result = results[idx]
        for field in new_fields:
            new_fields[field].append(result[field])

    # 将新增字段合并到 tiktok_df
    for field, values in new_fields.items():
        tiktok_df[field] = values

    # 合并回原 DataFrame（保留非 TikTok 行）
    result_df = df.copy()

    # 为所有行初始化新增字段
    result_df["publish_region"] = ""
    result_df["live_region"] = ""
    result_df["region_match"] = False
    result_df["api_status"] = ""
    result_df["error_detail"] = ""

    # 更新 TikTok 行（逐列赋值避免类型冲突）
    for field in new_fields:
        result_df.loc[tiktok_df.index, field] = tiktok_df[field].values

    # 保存结果
    try:
        result_df.to_excel(output_file, index=False, engine="openpyxl")
        logger.info(f"结果已保存到: {output_file}")
    except Exception as e:
        logger.error(f"Excel 保存失败: {e}")
        raise

    # 计算耗时统计
    total_elapsed = time.time() - start_time
    if elapsed_times:
        avg_time = sum(elapsed_times) / len(elapsed_times)
        min_time = min(elapsed_times)
        max_time = max(elapsed_times)
    else:
        avg_time = min_time = max_time = 0

    # 输出统计
    logger.info(
        f"处理完成 | 总数={stats['total']} | 成功={stats['success']} | "
        f"失败={stats['failed']} | 匹配={stats['match']} | "
        f"不匹配={stats['mismatch']} | 总耗时={total_elapsed:.2f}s"
    )

    # 失败原因统计
    if failure_reasons:
        logger.info("失败原因统计:")
        for reason, count in failure_reasons.most_common():
            logger.info(f"  - {reason}: {count} 次")

    # 添加耗时统计到返回值
    stats["avg_time"] = avg_time
    stats["min_time"] = min_time
    stats["max_time"] = max_time
    stats["total_elapsed"] = total_elapsed

    return stats


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="对比 TikTok 主播的国家信息（publish_region vs country_code）"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).parent / "全部直播账号数据.xlsx",
        help="输入 Excel 文件路径（默认：scripts/全部直播账号数据.xlsx）"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "全部直播账号数据_region对比.xlsx",
        help="输出 Excel 文件路径（默认：scripts/全部直播账号数据_region对比.xlsx）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行模式（只处理前 5 条数据）"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="最大并发线程数（默认 10）"
    )
    parser.add_argument(
        "--patch",
        action="store_true",
        help="补丁模式：只重新请求 platform=tiktok 且 live_region 为空的行"
    )
    parser.add_argument(
        "--patch-mismatch",
        action="store_true",
        help="补丁模式：重新请求 platform=tiktok 且 api_status=success 但 region_match 为空或 False 的行"
    )
    return parser.parse_args()


def patch_live_region(
    file_path: Path,
    config: ApiConfig,
    logger,
    dry_run: bool = False,
    max_workers: int = 10
) -> dict[str, Any]:
    """补丁模式：只重新请求 platform=tiktok 且 live_region 为空的行

    Args:
        file_path: 已有结果 Excel 路径（读取并原地更新）
        config: API 配置
        logger: 日志对象
        dry_run: 是否为试运行
        max_workers: 最大并发线程数

    Returns:
        统计信息字典
    """
    start_time = time.time()

    # 读取已有结果文件
    df = load_excel_data(file_path, logger)

    # 筛选需要重新请求的行：platform=tiktok 且 live_region 为空
    mask = (df["platform"] == "tiktok") & (
        df["live_region"].isna() | (df["live_region"] == "")
    )
    patch_df = df[mask].copy()
    total_count = len(patch_df)

    if total_count == 0:
        logger.info("没有需要补丁的数据（所有 TikTok 行的 live_region 已有值）")
        return {
            "total": 0, "success": 0, "failed": 0, "match": 0, "mismatch": 0,
            "avg_time": 0, "min_time": 0, "max_time": 0, "total_elapsed": 0
        }

    logger.info(f"[PATCH] 需要重新请求的行数: {total_count} | 并发数={max_workers}")

    if dry_run:
        patch_df = patch_df.head(5)
        logger.info(f"[PATCH] 试运行模式 | 只处理前 {len(patch_df)} 条")

    # 统计
    stats = {"total": 0, "success": 0, "failed": 0, "match": 0, "mismatch": 0}
    failure_reasons = Counter()
    elapsed_times = []
    results = {}

    # 多线程并发请求
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(process_single_row, row, config, logger): idx
            for idx, row in patch_df.iterrows()
        }

        with tqdm(total=len(future_to_index), desc="[PATCH] 处理进度") as pbar:
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    result = future.result()
                    results[idx] = result
                    elapsed_times.append(result["elapsed_time"])

                    stats["total"] += 1
                    if result["api_status"] == "success":
                        stats["success"] += 1
                        if result["region_match"]:
                            stats["match"] += 1
                        else:
                            stats["mismatch"] += 1
                    else:
                        stats["failed"] += 1
                        failure_reasons[result["error_detail"]] += 1
                        logger.warning(
                            f"API 失败 | room_url={df.loc[idx, 'room_url']} | "
                            f"reason={result['error_detail']}"
                        )
                except Exception as e:
                    logger.error(f"处理行 {idx} 时发生异常: {e}")
                    results[idx] = {
                        "publish_region": "",
                        "live_region": "",
                        "region_match": False,
                        "api_status": "failed",
                        "error_detail": f"处理异常: {e}",
                        "elapsed_time": 0
                    }
                    stats["total"] += 1
                    stats["failed"] += 1

                pbar.update(1)

    # 将结果更新回原 DataFrame
    update_fields = ["publish_region", "live_region", "region_match", "api_status", "error_detail"]
    for idx, result in results.items():
        for field in update_fields:
            df.loc[idx, field] = result[field]

    # 保存
    try:
        df.to_excel(file_path, index=False, engine="openpyxl")
        logger.info(f"[PATCH] 结果已更新到: {file_path}")
    except Exception as e:
        logger.error(f"Excel 保存失败: {e}")
        raise

    # 耗时统计
    total_elapsed = time.time() - start_time
    if elapsed_times:
        avg_time = sum(elapsed_times) / len(elapsed_times)
        min_time = min(elapsed_times)
        max_time = max(elapsed_times)
    else:
        avg_time = min_time = max_time = 0

    # 输出统计
    logger.info(
        f"[PATCH] 处理完成 | 总数={stats['total']} | 成功={stats['success']} | "
        f"失败={stats['failed']} | 匹配={stats['match']} | "
        f"不匹配={stats['mismatch']} | 总耗时={total_elapsed:.2f}s"
    )

    if failure_reasons:
        logger.info("[PATCH] 失败原因统计:")
        for reason, count in failure_reasons.most_common():
            logger.info(f"  - {reason}: {count} 次")

    stats["avg_time"] = avg_time
    stats["min_time"] = min_time
    stats["max_time"] = max_time
    stats["total_elapsed"] = total_elapsed

    return stats


def patch_region_mismatch(
    file_path: Path,
    config: ApiConfig,
    logger,
    dry_run: bool = False,
    max_workers: int = 10
) -> dict[str, Any]:
    """补丁模式：重新请求 api_status=success 但 region_match 为空或 False 的行

    筛选条件：
        - platform = 'tiktok'
        - api_status = 'success'
        - region_match 为空（NaN/空字符串）或 False

    Args:
        file_path: 已有结果 Excel 路径（读取并原地更新）
        config: API 配置
        logger: 日志对象
        dry_run: 是否为试运行
        max_workers: 最大并发线程数

    Returns:
        统计信息字典
    """
    start_time = time.time()

    df = load_excel_data(file_path, logger)

    # 筛选：tiktok + api 成功 + region 未匹配或为空
    is_tiktok = df["platform"] == "tiktok"
    is_success = df["api_status"] == "success"
    region_empty = df["region_match"].isna() | (df["region_match"] == "")
    region_false = df["region_match"] == False  # noqa: E712
    mask = is_tiktok & is_success & (region_empty | region_false)

    patch_df = df[mask].copy()
    total_count = len(patch_df)

    if total_count == 0:
        logger.info("[PATCH-MISMATCH] 没有需要补丁的数据")
        return {
            "total": 0, "success": 0, "failed": 0, "match": 0, "mismatch": 0,
            "avg_time": 0, "min_time": 0, "max_time": 0, "total_elapsed": 0
        }

    logger.info(
        f"[PATCH-MISMATCH] 需要重新请求的行数: {total_count} | 并发数={max_workers}"
    )

    if dry_run:
        patch_df = patch_df.head(5)
        logger.info(f"[PATCH-MISMATCH] 试运行模式 | 只处理前 {len(patch_df)} 条")

    stats = {"total": 0, "success": 0, "failed": 0, "match": 0, "mismatch": 0}
    failure_reasons = Counter()
    elapsed_times = []
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(process_single_row, row, config, logger): idx
            for idx, row in patch_df.iterrows()
        }

        with tqdm(total=len(future_to_index), desc="[PATCH-MISMATCH] 处理进度") as pbar:
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    result = future.result()
                    results[idx] = result
                    elapsed_times.append(result["elapsed_time"])

                    stats["total"] += 1
                    if result["api_status"] == "success":
                        stats["success"] += 1
                        if result["region_match"]:
                            stats["match"] += 1
                        else:
                            stats["mismatch"] += 1
                    else:
                        stats["failed"] += 1
                        failure_reasons[result["error_detail"]] += 1
                        logger.warning(
                            f"API 失败 | room_url={df.loc[idx, 'room_url']} | "
                            f"reason={result['error_detail']}"
                        )
                except Exception as e:
                    logger.error(f"处理行 {idx} 时发生异常: {e}")
                    results[idx] = {
                        "publish_region": "",
                        "live_region": "",
                        "region_match": False,
                        "api_status": "failed",
                        "error_detail": f"处理异常: {e}",
                        "elapsed_time": 0
                    }
                    stats["total"] += 1
                    stats["failed"] += 1

                pbar.update(1)

    # 将结果更新回原 DataFrame
    update_fields = ["publish_region", "live_region", "region_match", "api_status", "error_detail"]
    for idx, result in results.items():
        for field in update_fields:
            df.loc[idx, field] = result[field]

    try:
        df.to_excel(file_path, index=False, engine="openpyxl")
        logger.info(f"[PATCH-MISMATCH] 结果已更新到: {file_path}")
    except Exception as e:
        logger.error(f"Excel 保存失败: {e}")
        raise

    total_elapsed = time.time() - start_time
    if elapsed_times:
        avg_time = sum(elapsed_times) / len(elapsed_times)
        min_time = min(elapsed_times)
        max_time = max(elapsed_times)
    else:
        avg_time = min_time = max_time = 0

    logger.info(
        f"[PATCH-MISMATCH] 处理完成 | 总数={stats['total']} | 成功={stats['success']} | "
        f"失败={stats['failed']} | 匹配={stats['match']} | "
        f"不匹配={stats['mismatch']} | 总耗时={total_elapsed:.2f}s"
    )

    if failure_reasons:
        logger.info("[PATCH-MISMATCH] 失败原因统计:")
        for reason, count in failure_reasons.most_common():
            logger.info(f"  - {reason}: {count} 次")

    stats["avg_time"] = avg_time
    stats["min_time"] = min_time
    stats["max_time"] = max_time
    stats["total_elapsed"] = total_elapsed

    return stats


def main():
    """主函数"""
    args = parse_args()

    # 初始化日志
    logger = Logings("sync_tiktok_region").get_logger()

    try:
        # 加载配置
        config = load_api_config()
        logger.info(f"API 配置加载成功 | endpoint={config.endpoint}")

        if args.patch:
            # 补丁模式：只重新请求 live_region 为空的行
            stats = patch_live_region(
                file_path=args.output,
                config=config,
                logger=logger,
                dry_run=args.dry_run,
                max_workers=args.workers
            )
        elif args.patch_mismatch:
            # 补丁模式：重新请求 api_status=success 但 region_match 为空或 False 的行
            stats = patch_region_mismatch(
                file_path=args.output,
                config=config,
                logger=logger,
                dry_run=args.dry_run,
                max_workers=args.workers
            )
        else:
            # 全量模式
            stats = sync_tiktok_regions(
                input_file=args.input,
                output_file=args.output,
                config=config,
                logger=logger,
                dry_run=args.dry_run,
                max_workers=args.workers
            )

        # 输出最终统计
        mode_label = (
            "[PATCH-MISMATCH 模式]" if args.patch_mismatch
            else "[PATCH 模式]" if args.patch
            else "[全量模式]"
        )
        logger.info("=" * 80)
        logger.info(f"执行完成 {mode_label}")
        logger.info(f"文件: {args.output}")
        logger.info("-" * 80)
        logger.info(f"处理总数: {stats['total']}")
        logger.info(f"成功数: {stats['success']}")
        logger.info(f"失败数: {stats['failed']}")
        logger.info(f"匹配数: {stats['match']}")
        logger.info(f"不匹配数: {stats['mismatch']}")
        logger.info("-" * 80)
        logger.info(f"总耗时: {stats['total_elapsed']:.2f}s")
        logger.info(f"平均耗时: {stats['avg_time']:.2f}s")
        logger.info(f"最短耗时: {stats['min_time']:.2f}s")
        logger.info(f"最长耗时: {stats['max_time']:.2f}s")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"脚本执行失败: {e}")
        raise


if __name__ == "__main__":
    main()

