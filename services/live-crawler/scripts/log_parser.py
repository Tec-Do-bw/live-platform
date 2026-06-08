#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志解析器 — 把 loguru 纯文本日志压缩为结构化 JSON 摘要。

输入: services/live-crawler/logs/services/{scheduler,manual_once,manual_full}/YYYY-MM-DD.logs
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

# loguru exception 栈里可能带 ANSI 颜色码,日报聚合前需要剥离。
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

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
ACCOUNT_RESULT_RE = re.compile(r"(?P<mark>[✓✗]) \[(?P<mode>[^\]]+)\] 采集(?P<result>成功|失败)")

# 手动全量结果: "✓ [手动全量] 采集结果: 页面数=0, API数=76, 数据数=76"
MANUAL_RESULT_RE = re.compile(r"(?P<mark>[✓✗]) \[(?P<mode>[^\]]+)\] 采集结果:")

# 新版失败结果: "✗ 采集失败: [k1] 凭据缺失，需要刷新" / "✗ 采集失败: None"
PLAIN_FAIL_RE = re.compile(r"✗ 采集失败:")

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
    "检测到账号登出",
    "登录失效",
    "cookie 失效",
    "Cookie 过期",
)

COLLECTION_SERVICE_LOGS = ("scheduler", "manual_once", "manual_full")


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
            "total_logout": 0,
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
            line = _strip_ansi(raw_line.rstrip("\n"))
            m = LINE_RE.match(line)
            if m:
                ts = m.group("ts")
                level = m.group("level").strip()
                module = m.group("module")
                msg = m.group("msg")
            else:
                ts = None
                level = "INFO"
                module = ""
                msg = line

            # ERROR 收集先于业务分支,避免结果行被 continue 后漏聚合。
            if level == "ERROR":
                short_msg = _shorten_error(msg)
                error_msg_counter[short_msg] += 1
                # 只保留前 200 条原始 ERROR,避免内存爆炸
                if len(result["errors"]) < 200:
                    result["errors"].append(
                        {"time": ts, "module": module, "message": msg[:300]}
                    )
                result["stats"]["total_errors"] += 1

            # 任务轮次开始
            if mt := TASK_START_RE.search(msg):
                current_round = _new_round(
                    time=ts,
                    crawl_type=mt.group("crawl_type"),
                    platform_filter=mt.group("platform"),
                )
                result["rounds"].append(current_round)
                continue

            # 平台行(补足账号数)
            if mp := PLATFORM_RE.search(msg):
                if current_round is None:
                    current_round = _new_round(
                        time=ts,
                        crawl_type=_crawl_type_from_log_path(log_path),
                        platform_filter=mp.group("platform").lower(),
                    )
                    result["rounds"].append(current_round)
                if current_round is not None:
                    current_round["account_count"] = int(mp.group("count"))
                continue

            # 单账号开始
            if ma := ACCOUNT_START_RE.search(msg):
                if current_round is None:
                    current_round = _new_round(
                        time=ts,
                        crawl_type=_crawl_type_from_log_path(log_path),
                        platform_filter=_platform_from_group(ma.group("group")),
                    )
                    result["rounds"].append(current_round)
                current_account = {
                    "time": ts,
                    "browser_id": ma.group("browser_id"),
                    "group": ma.group("group"),
                    "platform": _platform_from_group(ma.group("group")),
                    "country": _country_from_group(ma.group("group")),
                    "result": "unknown",
                    "mode": None,
                    "logout_signal": False,
                    "failure_reason": None,
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
                    if current_account["result"] == "fail":
                        current_account["failure_reason"] = "采集失败"
                    _update_current_round_result(current_round, current_account["result"])
                continue

            # 手动全量结果行,用勾叉直接判定当前账号成败。
            if mm := MANUAL_RESULT_RE.search(msg):
                if current_account is not None:
                    current_account["mode"] = mm.group("mode")
                    current_account["result"] = (
                        "success" if mm.group("mark") == "✓" else "fail"
                    )
                    if current_account["result"] == "fail":
                        current_account["failure_reason"] = "采集结果为失败"
                    _update_current_round_result(current_round, current_account["result"])
                continue

            # 新版失败日志没有 mode,但仍应回填到当前账号。
            if PLAIN_FAIL_RE.search(msg):
                if current_account is not None:
                    current_account["result"] = "fail"
                    current_account["failure_reason"] = _extract_plain_fail_reason(msg)
                    _update_current_round_result(current_round, "fail")
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
                continue

            # 登出信号(覆盖到 current_account)
            if any(p in msg for p in LOGOUT_PATTERNS):
                if current_account is not None:
                    current_account["logout_signal"] = True

    _finalize_stats(result)

    # 错误聚合(Top 20)
    result["error_summary"] = dict(error_msg_counter.most_common(20))
    return result


def _strip_ansi(text: str) -> str:
    """清理日志中的 ANSI 颜色码。"""
    return ANSI_RE.sub("", text)


def _new_round(
    time: str | None,
    crawl_type: str,
    platform_filter: str | None,
) -> dict:
    """构造缺少任务开始行时的合成轮次。"""
    return {
        "time": time,
        "crawl_type": crawl_type,
        "platform_filter": platform_filter,
        "account_count": 0,
        "success": 0,
        "fail": 0,
    }


def _crawl_type_from_log_path(log_path: Path) -> str:
    """从入口目录推断缺省 crawl_type。"""
    service_name = log_path.parent.name
    if service_name == "manual_full":
        return "manual_full"
    if service_name == "manual_once":
        return "manual_once"
    return "unknown"


def _update_current_round_result(current_round: dict | None, account_result: str) -> None:
    """在无汇总行的日志里,用账号结果累加轮次统计。"""
    if current_round is None:
        return
    if account_result == "success":
        current_round["success"] = int(current_round.get("success") or 0) + 1
    elif account_result == "fail":
        current_round["fail"] = int(current_round.get("fail") or 0) + 1


def _finalize_stats(result: dict) -> None:
    """用账号结果回算 stats,避免 summary 与结果行重复计数。"""
    account_results = result.get("account_results") or []
    for ar in account_results:
        if ar.get("result") == "fail" and ar.get("logout_signal"):
            ar["result"] = "logout"
            ar["failure_reason"] = "账号登出/需要登录"

    stats = result["stats"]
    stats["total_rounds"] = len(result.get("rounds") or [])
    if account_results:
        stats["total_accounts"] = len(account_results)
        stats["total_success"] = sum(
            1 for ar in account_results if ar.get("result") == "success"
        )
        stats["total_fail"] = sum(
            1 for ar in account_results if ar.get("result") == "fail"
        )
        stats["total_logout"] = sum(
            1 for ar in account_results if ar.get("result") == "logout"
        )


def _extract_plain_fail_reason(msg: str) -> str:
    """从新版失败日志中提取可读失败原因。"""
    reason = PLAIN_FAIL_RE.sub("", msg, count=1).strip()
    reason = re.sub(r"^\[[^\]]+\]\s*", "", reason)
    return reason or "采集失败"


def merge_log_results(results: list[dict], target_date: date) -> dict:
    """合并多个入口日志解析结果。"""
    merged: dict = {
        "date": target_date.isoformat(),
        "log_path": ",".join(r["log_path"] for r in results),
        "log_paths": [r["log_path"] for r in results],
        "rounds": [],
        "account_results": [],
        "errors": [],
        "error_summary": {},
        "stats": {
            "total_rounds": 0,
            "total_accounts": 0,
            "total_success": 0,
            "total_fail": 0,
            "total_logout": 0,
            "total_errors": 0,
        },
    }

    error_counter: Counter[str] = Counter()
    for result in results:
        merged["rounds"].extend(result["rounds"])
        merged["account_results"].extend(result["account_results"])
        merged["errors"].extend(result["errors"])
        error_counter.update(result["error_summary"])
        for key in merged["stats"]:
            merged["stats"][key] += result["stats"].get(key, 0)

    merged["errors"] = merged["errors"][:200]
    merged["error_summary"] = dict(error_counter.most_common(20))
    return merged


def _service_log_paths(logs_dir: Path, target_date: date) -> list[Path]:
    """返回日报需要解析的普通采集入口日志路径。"""
    log_name = f"{target_date.isoformat()}.logs"
    return [
        logs_dir / "services" / service_name / log_name
        for service_name in COLLECTION_SERVICE_LOGS
    ]


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
        "菲律宾": "PH", "新加坡": "SG", "巴西": "BR", "日本": "JP",
        "墨西哥": "MX", "中国台湾": "TW", "台湾": "TW", "美国": "US",
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
    existing_service_logs = [
        log_path for log_path in _service_log_paths(logs_dir, target_date)
        if log_path.exists()
    ]
    if existing_service_logs:
        return merge_log_results(
            [parse_log_file(log_path) for log_path in existing_service_logs],
            target_date,
        )

    # 兼容旧版根目录日期日志，便于历史日期补跑日报。
    legacy_log_path = logs_dir / f"{target_date.isoformat()}.logs"
    return parse_log_file(legacy_log_path)
