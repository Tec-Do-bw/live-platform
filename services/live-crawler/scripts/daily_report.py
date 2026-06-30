#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日采集报告主入口。

流程:
  1. 解析 T-1 日志 → 当天结构化摘要
  2. 解析 T-2 日志 → 昨天摘要(用于趋势对比)
  3. 用当天结果更新 account_status.json
  4. 调 OpenAI 生成飞书 Markdown 卡片(失败降级为纯文本)
  5. 推送飞书

用法:
  python -m scripts.daily_report                  # 默认分析昨天(T-1)
  python -m scripts.daily_report --date 2026-05-06
  python -m scripts.daily_report --dry-run        # 不推送飞书,仅打印
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

# 项目根目录入 sys.path,允许 `python -m scripts.daily_report`
PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import Logings, logger  # noqa: E402

Logings.configure("daily_report")

from scripts import feishu_webhook, log_parser, openai_client, status_tracker  # noqa: E402

LOGS_DIR = PROJECT_ROOT / "logs"
STATUS_PATH = PROJECT_ROOT / "account_status.json"
PROMPT_PATH = Path(__file__).parent / "prompts" / "daily_report.md"


def run(target_date: date, dry_run: bool = False) -> int:
    logger.info("=" * 60)
    logger.info(f"开始生成采集日报 | 目标日期={target_date.isoformat()} dry_run={dry_run}")
    logger.info("=" * 60)

    # 1. 解析日志
    today_summary = log_parser.parse_by_date(LOGS_DIR, target_date)
    yesterday_summary = log_parser.parse_by_date(LOGS_DIR, target_date - timedelta(days=1))
    logger.info(
        f"日志解析完成 | 今日 stats={today_summary['stats']} "
        f"昨日 stats={yesterday_summary['stats']}"
    )

    # 2. 更新状态文件
    status = status_tracker.load_status(STATUS_PATH)
    status = status_tracker.update_status(status, today_summary, target_date)
    status_tracker.save_status(STATUS_PATH, status)
    problem_accounts = status_tracker.get_problem_accounts(status, min_days=3)
    logger.info(
        f"账号状态更新完成 | 总账号数={len(status)} 问题账号={len(problem_accounts)}"
    )

    # 3. 生成日报文案
    prompt = openai_client.load_prompt(PROMPT_PATH)
    content_md, used_llm = openai_client.generate_report(
        prompt_template=prompt,
        today_summary=today_summary,
        yesterday_summary=yesterday_summary,
        problem_accounts=problem_accounts,
    )
    logger.info(f"日报文案生成完成 | LLM={used_llm} 长度={len(content_md)}")

    # 4. 推送
    title = f"📊 直播采集日报 {target_date.isoformat()}"
    if dry_run:
        logger.info("dry-run 模式,仅打印内容:")
        print(f"\n=== {title} ===\n{content_md}\n")
        return 0

    ok = feishu_webhook.send_card(title=title, content_md=content_md)
    return 0 if ok else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="每日直播采集报告生成器")
    parser.add_argument(
        "--date",
        help="目标日期(YYYY-MM-DD),默认为昨天(T-1)",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不推送飞书,仅打印日报内容",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.date:
        target = date.fromisoformat(args.date)
    else:
        target = date.today() - timedelta(days=1)
    try:
        return run(target, dry_run=args.dry_run)
    except Exception as e:
        logger.exception(f"日报生成异常: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
