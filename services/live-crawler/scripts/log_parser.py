#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志解析器 — 把 loguru 纯文本日志压缩为结构化 JSON 摘要。

输入: services/live-crawler/logs/YYYY-MM-DD.logs(每天约 5 万行)
输出: 结构化 dict,包含每轮汇总、单账号结果、错误聚合
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from pathlib import Path

# 日志通用前缀: "2026-05-06 00:01:18 | INFO     | task_scheduler.py:155 - "
LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| "
    r"(?P<level>\w+)\s+\| "
    r"(?P<module>[^:]+):(?P<line>\d+) - "
    r"(?P<msg>.*)$"
)

# 任务开始: "开始执行定时采集任务 - ... (crawl_type=realtime, platform_filter=lazada)"
TASK_START_RE = re.compile(
    r"开始执行定时采集任务.*?\(crawl_type=(?P<crawl_type>\w+), platform_filter=(?P<platform>\w+)\)"
)

# 平台行: "📱 平台: LAZADA | 账号数: 2 | 时区分组: ALL"
PLATFORM_RE = re.compile(r"📱 平台: (?P<platform>\w+) \| 账号数: (?P<count>\d+)")

# 单账号开始: "[1/2] 账号: k1c0io17 | 分组: 泰国团队-lazada | 用户名: z9Nn0omL"
ACCOUNT_START_RE = re.compile(
    r"\[\d+/\d+\] 账号: (?P<browser_id>\S+) \| 分组: (?P<group>\S+)"
)

# 单账号结果: "✓ [增量] 采集成功" / "✗ [全量] 采集失败"
ACCOUNT_RESULT_RE = re.compile(r"[✓✗] \[(?P<mode>\S+)\] 采集(?P<result>成功|失败)")

# 每轮汇总: "总计: 2/2 账号采集成功, 0 账号失败"
ROUND_SUMMARY_RE = re.compile(
    r"总计: (?P<success>\d+)/(?P<total>\d+) 账号采集成功, (?P<fail>\d+) 账号失败"
)

# 登出/需登录信号
LOGOUT_PATTERNS = (
    "需要登录",
    "login_status=False",
    "login_status: False",
    "账号已登出",
    "登录失效",
    "cookie 失效",
    "Cookie 过期",
)


def parse_log_file(log_path: Path) -> dict:
    """解析单日日志文件,返回结构化摘要。

    Args:
        log_path: 日志文件绝对路径

    Returns:
        dict 含: date / rounds / account_results / errors / error_summary
    """
    result: dict = {
        "date": log_path.stem,  # 文件名 2026-05-06 即日期
        "log_path": str(log_path),
        "rounds": [],
        "account_results": [],
        "errors": [],
        "error_summary": {},
        "stats": {
            "total_rounds": 0,
            "total_accounts": 0,
            "total_success": 0,
            "total_fail": 0,
            "total_errors": 0,
        },
    }

    if not log_path.exists():
        result["error_summary"]["__file_missing__"] = 1
        return result

    current_round: dict | None = None
    current_account: dict | None = None
    error_msg_counter: Counter[str] = Counter()

    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            m = LINE_RE.match(line)
            if not m:
                continue
            ts = m.group("ts")
            level = m.group("level").strip()
            module = m.group("module")
            msg = m.group("msg")

            # 任务轮次开始
            if mt := TASK_START_RE.search(msg):
                current_round = {
                    "time": ts,
                    "crawl_type": mt.group("crawl_type"),
                    "platform_filter": mt.group("platform"),
                    "account_count": 0,
                    "success": 0,
                    "fail": 0,
                }
                result["rounds"].append(current_round)
                result["stats"]["total_rounds"] += 1
                continue

            # 平台行(补足账号数)
            if mp := PLATFORM_RE.search(msg):
                if current_round is not None:
                    current_round["account_count"] = int(mp.group("count"))
                continue

            # 单账号开始
            if ma := ACCOUNT_START_RE.search(msg):
                current_account = {
                    "time": ts,
                    "browser_id": ma.group("browser_id"),
                    "group": ma.group("group"),
                    "platform": _platform_from_group(ma.group("group")),
                    "country": _country_from_group(ma.group("group")),
                    "result": "unknown",
                    "mode": None,
                    "logout_signal": False,
                }
                result["account_results"].append(current_account)
                continue

            # 单账号结果
            if mr := ACCOUNT_RESULT_RE.search(msg):
                if current_account is not None:
                    current_account["mode"] = mr.group("mode")
                    current_account["result"] = (
                        "success" if mr.group("result") == "成功" else "fail"
                    )
                continue

            # 每轮汇总
            if ms := ROUND_SUMMARY_RE.search(msg):
                success = int(ms.group("success"))
                fail = int(ms.group("fail"))
                total = int(ms.group("total"))
                if current_round is not None:
                    current_round["success"] = success
                    current_round["fail"] = fail
                    if not current_round["account_count"]:
                        current_round["account_count"] = total
                result["stats"]["total_success"] += success
                result["stats"]["total_fail"] += fail
                result["stats"]["total_accounts"] += total
                continue

            # 登出信号(覆盖到 current_account)
            if any(p in msg for p in LOGOUT_PATTERNS):
                if current_account is not None:
                    current_account["logout_signal"] = True

            # ERROR 收集(限流类高频信息只取前缀做聚合)
            if level == "ERROR":
                short_msg = _shorten_error(msg)
                error_msg_counter[short_msg] += 1
                # 只保留前 200 条原始 ERROR,避免内存爆炸
                if len(result["errors"]) < 200:
                    result["errors"].append(
                        {"time": ts, "module": module, "message": msg[:300]}
                    )
                result["stats"]["total_errors"] += 1

    # 错误聚合(Top 20)
    result["error_summary"] = dict(error_msg_counter.most_common(20))
    return result


def _platform_from_group(group_name: str) -> str | None:
    """从分组名(例 '泰国团队-lazada')提取平台。"""
    for p in ("lazada", "tiktok", "shopee"):
        if p in group_name.lower():
            return p
    return None


def _country_from_group(group_name: str) -> str | None:
    """从分组名提取国家关键词(简单映射,够日报用即可)。"""
    table = {
        "泰国": "TH", "马来": "MY", "印尼": "ID", "越南": "VN",
        "菲律宾": "PH", "新加坡": "SG", "巴西": "BR", "中国台湾": "TW",
        "台湾": "TW", "美国": "US",
    }
    for cn, code in table.items():
        if cn in group_name:
            return code
    return None


def _shorten_error(msg: str) -> str:
    """把 ERROR 消息归一化以便计数(去掉变量部分)。"""
    # 去掉 (第N次尝试) 后缀
    msg = re.sub(r"\(第\d+次尝试\)", "", msg)
    # 去掉具体的 browser_id / IP / 数字
    msg = re.sub(r"browser_id=\S+", "browser_id=*", msg)
    msg = re.sub(r"\d+\.\d+\.\d+\.\d+", "*.*.*.*", msg)
    msg = re.sub(r"\b\d{6,}\b", "<NUM>", msg)
    return msg.strip()[:200]


def parse_by_date(logs_dir: Path, target_date: date) -> dict:
    """按日期解析(便于主入口直接传 date 对象)。"""
    log_path = logs_dir / f"{target_date.isoformat()}.logs"
    return parse_log_file(log_path)
