#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAI 客户端封装 — 调用失败时降级为纯文本摘要,日报永不丢失。"""

from __future__ import annotations

import json
import os
import time
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
    return os.getenv("OPENAI_MODEL") or _openai_config().get("model") or "gpt-4o-mini"


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
    }

    client = OpenAI(api_key=api_key, timeout=_resolve_timeout())
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
    stats = today.get("stats", {})
    lines: list[str] = []
    lines.append(f"📊 **直播采集日报 {today.get('date', '?')}** (降级文本)")
    lines.append("")
    lines.append("🟢 **基础统计**")
    lines.append(f"- 任务轮次: {stats.get('total_rounds', 0)}")
    lines.append(f"- 账号成功: {stats.get('total_success', 0)}")
    lines.append(f"- 账号失败: {stats.get('total_fail', 0)}")
    lines.append(f"- 错误总数: {stats.get('total_errors', 0)}")
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

    error_summary = today.get("error_summary") or {}
    if error_summary:
        lines.append("⚠️ **异常 Top 5**")
        for msg, cnt in list(error_summary.items())[:5]:
            lines.append(f"- {msg}: {cnt} 次")
        lines.append("")

    if yesterday:
        y_stats = yesterday.get("stats", {})
        lines.append("📈 **与昨天对比**")
        lines.append(
            f"- 成功数: {y_stats.get('total_success', 0)} → "
            f"{stats.get('total_success', 0)}"
        )
        lines.append(
            f"- 错误数: {y_stats.get('total_errors', 0)} → "
            f"{stats.get('total_errors', 0)}"
        )

    return "\n".join(lines)


def load_prompt(prompt_path: Path) -> str:
    """读取 prompt 模板,文件缺失时返回默认空模板。"""
    if not prompt_path.exists():
        logger.warning(f"Prompt 模板不存在: {prompt_path},使用空模板")
        return "请根据用户提供的 JSON 数据生成中文飞书 Markdown 日报。"
    return prompt_path.read_text(encoding="utf-8")
