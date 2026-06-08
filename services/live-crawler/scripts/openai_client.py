#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAI 客户端封装 — 调用失败时降级为纯文本摘要,日报永不丢失。"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:  # 未安装 openai 时降级也能工作
    OpenAI = None  # type: ignore[assignment]

from utils.logger import logger

DEFAULT_MAX_RETRIES = 2


def _openai_config() -> dict:
    """读取 OPENAI_CONFIG 作为 model/timeout/api_key 的回退源。

    懒加载导入,避免模块级硬依赖 core.config;导入失败时返回空字典安全降级。
    """
    try:
        from core.config import Settings

        return Settings.OPENAI_CONFIG or {}
    except Exception as e:  # 配置不可用时不应阻断日报生成
        logger.warning(f"读取 OPENAI_CONFIG 失败,回退源不可用: {e}")
        return {}


def _resolve_model() -> str:
    return os.getenv("OPENAI_MODEL") or _openai_config().get("model") or "deepseek-v4-flash"


def _resolve_base_url() -> str | None:
    return os.getenv("OPENAI_BASE_URL") or _openai_config().get("base_url") or None


def _resolve_timeout() -> int:
    raw = os.getenv("OPENAI_TIMEOUT_SECONDS")
    if raw:
        return int(raw)
    return int(_openai_config().get("timeout_seconds", 30))


def _resolve_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY") or _openai_config().get("api_key") or None


def generate_report(
    prompt_template: str,
    today_summary: dict,
    yesterday_summary: dict | None,
    problem_accounts: list[dict],
) -> tuple[str, bool]:
    """生成日报文案。

    Returns:
        (markdown 文案, is_llm_generated)
        is_llm_generated=False 表示走了降级路径
    """
    api_key = _resolve_api_key()
    if not api_key or OpenAI is None:
        logger.warning("OPENAI_API_KEY 未配置或 openai 包未安装,降级为纯文本摘要")
        return _fallback_report(today_summary, yesterday_summary, problem_accounts), False

    user_payload = {
        "today_summary": today_summary,
        "yesterday_summary": yesterday_summary or {},
        "problem_accounts": problem_accounts,
        "report_metrics": build_report_metrics(
            today_summary,
            yesterday_summary,
            problem_accounts,
        ),
    }

    client = OpenAI(api_key=api_key, base_url=_resolve_base_url(), timeout=_resolve_timeout())
    model = _resolve_model()
    last_err: Exception | None = None
    for attempt in range(1, DEFAULT_MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt_template},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False),
                    },
                ],
                temperature=0.3,
            )
            content = resp.choices[0].message.content or ""
            if content.strip():
                return content.strip(), True
            raise RuntimeError("OpenAI 返回内容为空")
        except Exception as e:
            last_err = e
            logger.warning(f"OpenAI 调用失败(第 {attempt} 次): {e}")
            if attempt < DEFAULT_MAX_RETRIES:
                time.sleep(2 * attempt)

    logger.error(f"OpenAI 调用最终失败,降级为纯文本: {last_err}")
    return _fallback_report(today_summary, yesterday_summary, problem_accounts), False


def _fallback_report(
    today: dict,
    yesterday: dict | None,
    problem_accounts: list[dict],
) -> str:
    """无 LLM 时的纯文本摘要,保证日报不丢。"""
    metrics = build_report_metrics(today, yesterday, problem_accounts)
    stats = today.get("stats", {})
    lines: list[str] = []
    lines.append(f"📊 **直播采集日报 {today.get('date', '?')}** (降级文本)")
    lines.append("")
    lines.append("🟢 **采集完整度**")
    lines.append(f"- 任务轮次: {stats.get('total_rounds', 0)}")
    lines.append(f"- 账号成功: {stats.get('total_success', 0)}")
    lines.append(f"- 账号失败: {stats.get('total_fail', 0)}")
    lines.append(f"- 登出账号: {metrics['logout_count']}")
    lines.append(f"- 未知结果账号: {metrics['unknown_result_count']}")
    lines.append(f"- 错误总数: {stats.get('total_errors', 0)}")
    for group in metrics["collection_groups"][:12]:
        lines.append(
            f"- {group['platform']} | {group['country']}: "
            f"{group['success_rate_percent']}% "
            f"({group['success']}/{group['success'] + group['fail']}, "
            f"账号数 {group['total']}, 登出 {group['logout']})"
        )
    lines.append("")

    if problem_accounts:
        lines.append(f"🔴 **问题账号(连续登出 ≥ 3 天) {len(problem_accounts)} 个**")
        for rec in problem_accounts[:10]:
            country = rec.get("country") or "?"
            platform = rec.get("platform") or "?"
            days = rec.get("consecutive_logout_days", 0)
            lines.append(
                f"- `{rec.get('browser_id')}` ({country}-{platform}): 已登出 {days} 天"
            )
        lines.append("")
    else:
        lines.append("🔴 **问题账号**: 无")
        lines.append("")

    if metrics["failure_reasons"]:
        lines.append("⚠️ **采集失败原因 Top 5**")
        for item in metrics["failure_reasons"]:
            if item["yesterday_count"]:
                lines.append(
                    f"- {item['reason']}: {item['count']} 个账号"
                    f"(昨天 {item['yesterday_count']} 个账号)"
                )
            else:
                lines.append(f"- {item['reason']}: {item['count']} 个账号")
        lines.append("")

    if metrics["top_errors"]:
        lines.append("🧯 **异常日志 Top 5**")
        for item in metrics["top_errors"]:
            lines.append(f"- {item['message']}: {item['count']} 次")
        lines.append("")

    comparison = metrics.get("comparison") or {}
    if comparison:
        lines.append("📈 **与昨天对比**")
        lines.append(
            f"- 整体成功率: {comparison['yesterday_success_rate_percent']}% → "
            f"{comparison['today_success_rate_percent']}%"
        )
        lines.append(
            f"- 异常总数: {comparison['yesterday_errors']} → "
            f"{comparison['today_errors']}"
        )

    return "\n".join(lines)


def build_report_metrics(
    today: dict,
    yesterday: dict | None,
    problem_accounts: list[dict],
) -> dict:
    """生成确定性日报指标,供 LLM 和降级文本共用。"""
    today_groups = _group_account_results(today.get("account_results") or [])
    yesterday_groups = _group_account_results(
        (yesterday or {}).get("account_results") or []
    )
    today_stats = today.get("stats") or {}
    yesterday_stats = (yesterday or {}).get("stats") or {}
    today_known = int(today_stats.get("total_success") or 0) + int(
        today_stats.get("total_fail") or 0
    )
    yesterday_known = int(yesterday_stats.get("total_success") or 0) + int(
        yesterday_stats.get("total_fail") or 0
    )

    metrics: dict = {
        "date": today.get("date"),
        "collection_groups": [],
        "unknown_result_count": sum(
            1
            for ar in today.get("account_results", [])
            if ar.get("result") == "unknown"
        ),
        "logout_count": sum(
            1
            for ar in today.get("account_results", [])
            if ar.get("result") == "logout"
        ),
        "failure_reasons": _failure_reasons(
            today.get("account_results") or [],
            (yesterday or {}).get("account_results") or [],
        ),
        "top_errors": _top_errors(
            today.get("error_summary") or {},
            (yesterday or {}).get("error_summary") or {},
        ),
        "problem_account_count": len(problem_accounts),
    }

    for key in sorted(today_groups):
        group = today_groups[key]
        yesterday_group = yesterday_groups.get(key, {})
        success = group["success"]
        fail = group["fail"]
        known_total = success + fail
        success_rate = round(success / known_total, 4) if known_total else 0
        yesterday_success = int(yesterday_group.get("success") or 0)
        yesterday_fail = int(yesterday_group.get("fail") or 0)
        yesterday_known_total = yesterday_success + yesterday_fail
        yesterday_rate = (
            round(yesterday_success / yesterday_known_total, 4)
            if yesterday_known_total
            else None
        )
        metrics["collection_groups"].append(
            {
                "platform": key[0].upper(),
                "country": key[1],
                "total": group["total"],
                "success": success,
                "fail": fail,
                "logout": group["logout"],
                "unknown": group["unknown"],
                "success_rate": success_rate,
                "success_rate_percent": round(success_rate * 100, 1),
                "yesterday_success_rate": yesterday_rate,
                "yesterday_success_rate_percent": (
                    round(yesterday_rate * 100, 1)
                    if yesterday_rate is not None
                    else None
                ),
            }
        )

    if yesterday is not None:
        today_rate = (
            round(today_stats.get("total_success", 0) / today_known, 4)
            if today_known
            else 0
        )
        yesterday_rate = (
            round(yesterday_stats.get("total_success", 0) / yesterday_known, 4)
            if yesterday_known
            else 0
        )
        metrics["comparison"] = {
            "today_success_rate": today_rate,
            "today_success_rate_percent": round(today_rate * 100, 1),
            "yesterday_success_rate": yesterday_rate,
            "yesterday_success_rate_percent": round(yesterday_rate * 100, 1),
            "today_errors": int(today_stats.get("total_errors") or 0),
            "yesterday_errors": int(yesterday_stats.get("total_errors") or 0),
        }

    return metrics


def _group_account_results(account_results: list[dict]) -> dict[tuple[str, str], dict]:
    """按平台和国家聚合账号结果。"""
    groups: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"total": 0, "success": 0, "fail": 0, "logout": 0, "unknown": 0}
    )
    for ar in account_results:
        platform = ar.get("platform") or "unknown"
        country = ar.get("country") or "?"
        bucket = groups[(platform, country)]
        bucket["total"] += 1
        result = ar.get("result")
        if result == "success":
            bucket["success"] += 1
        elif result == "fail":
            bucket["fail"] += 1
        elif result == "logout":
            bucket["logout"] += 1
        else:
            bucket["unknown"] += 1
    return groups


def _failure_reasons(today_results: list[dict], yesterday_results: list[dict]) -> list[dict]:
    """聚合非登出采集失败原因。"""
    today_counter: dict[str, int] = defaultdict(int)
    yesterday_counter: dict[str, int] = defaultdict(int)
    for ar in today_results:
        if ar.get("result") == "fail":
            today_counter[ar.get("failure_reason") or "采集失败"] += 1
    for ar in yesterday_results:
        if ar.get("result") == "fail":
            yesterday_counter[ar.get("failure_reason") or "采集失败"] += 1

    return [
        {
            "reason": reason,
            "count": count,
            "yesterday_count": int(yesterday_counter.get(reason) or 0),
        }
        for reason, count in sorted(
            today_counter.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
    ]


def _top_errors(today_errors: dict, yesterday_errors: dict) -> list[dict]:
    """生成带昨日次数的异常 Top 5。"""
    return [
        {
            "message": msg,
            "count": cnt,
            "yesterday_count": int(yesterday_errors.get(msg) or 0),
        }
        for msg, cnt in list(today_errors.items())[:5]
    ]


def load_prompt(prompt_path: Path) -> str:
    """读取 prompt 模板,文件缺失时返回默认空模板。"""
    if not prompt_path.exists():
        logger.warning(f"Prompt 模板不存在: {prompt_path},使用空模板")
        return "请根据用户提供的 JSON 数据生成中文飞书 Markdown 日报。"
    return prompt_path.read_text(encoding="utf-8")
