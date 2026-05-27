# -*- coding: utf-8 -*-
"""TiktokTool 代理稳定性主测试脚本

用法：
    cd services/live-monitor

    # 单一场景
    python -m tests.proxy_stability.run_test --scenario static_baseline
    python -m tests.proxy_stability.run_test --scenario dynamic_baseline
    python -m tests.proxy_stability.run_test --scenario hybrid_current
    python -m tests.proxy_stability.run_test --scenario adaptive_optimized

    # 全部场景顺序执行
    python -m tests.proxy_stability.run_test --scenario all

    # 指定账号数（小样本验证）
    python -m tests.proxy_stability.run_test --scenario all --limit 50

    # 指定并发数
    python -m tests.proxy_stability.run_test --scenario all --workers 10
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd

# 项目根加入 sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.proxy_stability.scenario_config import (
    RESULTS_DIR,
    Scenario,
    TEST_WORKERS,
)
from tests.proxy_stability.scenario_runner import (
    run_scenario,
    install_patches,
    uninstall_patches,
)
from tests.proxy_stability.metrics_collector import (
    compare_scenarios,
    quick_summary,
)

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")


def load_tiktok_accounts(excel_path: Path, limit: int | None = None) -> pd.DataFrame:
    """从 Excel 读取 TikTok 账号数据，过滤 platform=tiktok 的行"""
    df = pd.read_excel(excel_path, engine="openpyxl")
    tiktok_df = df[df["platform"] == "tiktok"].copy()
    tiktok_df = tiktok_df[tiktok_df["room_url"].astype(str).str.contains("tiktok.com", na=False)]
    if limit:
        tiktok_df = tiktok_df.head(limit)
    print(f"已加载 TikTok 账号：{len(tiktok_df)} 条")
    return tiktok_df


def run_single_scenario(
    scenario: Scenario,
    accounts: pd.DataFrame,
    workers: int,
    output_dir: Path,
):
    """运行单个场景并保存结果"""
    collector = run_scenario(scenario, accounts, workers=workers)
    output_path = output_dir / f"{scenario.value}.json"
    collector.dump_json(output_path)
    metrics = collector.aggregate()
    print(f"\n{quick_summary(metrics)}")
    print(f"详细数据已保存到：{output_path}")
    return metrics


def main():
    parser = argparse.ArgumentParser(description="TiktokTool 代理稳定性测试")
    parser.add_argument(
        "--scenario",
        choices=["static_baseline", "dynamic_baseline", "hybrid_current",
                 "adaptive_optimized", "all"],
        default="all",
        help="测试场景（默认 all 顺序执行全部）",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT_DIR / "scripts" / "全部直播账号数据.xlsx",
        help="账号数据 Excel 路径",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制账号数量（小样本验证）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=TEST_WORKERS,
        help=f"并发数（默认 {TEST_WORKERS}）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT_DIR / "tests" / "proxy_stability" / "results",
        help="结果输出目录",
    )
    args = parser.parse_args()

    accounts = load_tiktok_accounts(args.input, args.limit)
    if accounts.empty:
        print("没有可测试的 TikTok 账号，退出")
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.scenario == "all":
        scenarios = [
            Scenario.STATIC_BASELINE,
            Scenario.DYNAMIC_BASELINE,
            Scenario.HYBRID_CURRENT,
            Scenario.ADAPTIVE_OPTIMIZED,
        ]
    else:
        scenarios = [Scenario(args.scenario)]

    metrics_list = []
    install_patches()
    try:
        for scenario in scenarios:
            m = run_single_scenario(scenario, accounts, args.workers, args.output_dir)
            metrics_list.append(m)
    finally:
        uninstall_patches()

    if len(metrics_list) > 1:
        print("\n" + "=" * 80)
        print("场景对比汇总")
        print("=" * 80)
        print(compare_scenarios(metrics_list))


if __name__ == "__main__":
    main()
