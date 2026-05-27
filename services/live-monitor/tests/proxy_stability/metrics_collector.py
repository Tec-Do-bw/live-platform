# -*- coding: utf-8 -*-
"""指标采集器：聚合每次请求的耗时、状态、代理使用、错误类型。

按场景输出 JSON 汇总报告，支持按代理 IP / 错误类型 / 国家分布进行交叉分析。
"""

from __future__ import annotations

import json
import statistics
import threading
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class RequestRecord:
    """单次请求的详细记录"""

    room_url: str
    country_code: str  # 账号期望的国家
    success: bool  # 是否拿到有效数据（用户存在 + 直播页有效）
    elapsed_ms: float
    proxy_used: str  # 主请求实际使用的代理（IP:port 或 dynamic_xx）
    proxy_type: str  # static / dynamic / dynamic_xx
    profile_status: int | None  # 个人页 HTTP 状态码
    profile_size: int  # 个人页响应大小
    live_status: int | None  # 直播页 HTTP 状态码
    live_size: int  # 直播页响应大小
    short_response_triggered: bool  # 是否触发了短响应兜底
    fallback_country: str | None  # 兜底命中的国家（None 表示未触发或全部失败）
    publish_region: str  # API 返回的发布国家
    live_region: str  # API 返回的开播国家
    region_match: bool  # 国家匹配
    error_message: str  # 失败原因
    flv_url: str  # 直播流地址（"" 未开播 / "error" 失败 / 实际 URL）
    failure_category: str = ""  # 失败分类：proxy / account / parse / unknown


@dataclass
class ScenarioMetrics:
    """单个场景的汇总指标"""

    scenario: str
    description: str
    started_at: str
    finished_at: str = ""
    total: int = 0
    success: int = 0
    failed: int = 0
    success_rate: float = 0.0
    elapsed_p50_ms: float = 0.0
    elapsed_p95_ms: float = 0.0
    elapsed_p99_ms: float = 0.0
    elapsed_avg_ms: float = 0.0
    short_response_count: int = 0  # 短响应触发次数
    fallback_hit_count: int = 0  # 兜底命中次数
    fallback_hit_by_country: dict[str, int] = field(default_factory=dict)
    error_distribution: dict[str, int] = field(default_factory=dict)
    failure_category_distribution: dict[str, int] = field(default_factory=dict)
    proxy_failure_count: int = 0  # 仅代理相关失败
    account_failure_count: int = 0  # 账号自身导致的失败（用户不存在等）
    proxy_quality: list[dict[str, Any]] = field(default_factory=list)  # 按代理 IP 聚合
    country_match_rate: float = 0.0  # API 国家与期望国家匹配率
    status_code_distribution: dict[str, int] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)


class MetricsCollector:
    """线程安全的指标采集器"""

    def __init__(self, scenario: str, description: str) -> None:
        self._lock = threading.Lock()
        self._records: list[RequestRecord] = []
        self._scenario = scenario
        self._description = description
        self._started_at = datetime.now().isoformat(timespec="seconds")

    def record(self, rec: RequestRecord) -> None:
        with self._lock:
            self._records.append(rec)

    @property
    def total(self) -> int:
        with self._lock:
            return len(self._records)

    def aggregate(self) -> ScenarioMetrics:
        """聚合所有记录为统计结果"""
        with self._lock:
            records = list(self._records)

        m = ScenarioMetrics(
            scenario=self._scenario,
            description=self._description,
            started_at=self._started_at,
            finished_at=datetime.now().isoformat(timespec="seconds"),
            total=len(records),
        )
        if not records:
            return m

        m.success = sum(1 for r in records if r.success)
        m.failed = m.total - m.success
        m.success_rate = m.success / m.total if m.total else 0.0

        elapsed_list = [r.elapsed_ms for r in records]
        m.elapsed_avg_ms = sum(elapsed_list) / len(elapsed_list)
        m.elapsed_p50_ms = _percentile(elapsed_list, 50)
        m.elapsed_p95_ms = _percentile(elapsed_list, 95)
        m.elapsed_p99_ms = _percentile(elapsed_list, 99)

        m.short_response_count = sum(1 for r in records if r.short_response_triggered)
        m.fallback_hit_count = sum(
            1 for r in records if r.fallback_country and r.fallback_country != "FAIL"
        )
        m.fallback_hit_by_country = dict(
            Counter(
                r.fallback_country
                for r in records
                if r.fallback_country and r.fallback_country != "FAIL"
            )
        )

        m.error_distribution = dict(
            Counter(r.error_message for r in records if not r.success)
        )
        m.failure_category_distribution = dict(
            Counter(r.failure_category for r in records if not r.success and r.failure_category)
        )
        m.proxy_failure_count = sum(
            1 for r in records if not r.success and r.failure_category == "proxy"
        )
        m.account_failure_count = sum(
            1 for r in records if not r.success and r.failure_category == "account"
        )

        # 状态码分布（合并 profile + live）
        status_counter: Counter[str] = Counter()
        for r in records:
            if r.profile_status is not None:
                status_counter[f"profile_{r.profile_status}"] += 1
            if r.live_status is not None:
                status_counter[f"live_{r.live_status}"] += 1
        m.status_code_distribution = dict(status_counter)

        # 国家匹配率（仅统计成功且 API 返回了 region 的记录）
        match_candidates = [r for r in records if r.success and (r.publish_region or r.live_region)]
        if match_candidates:
            matched = sum(1 for r in match_candidates if r.region_match)
            m.country_match_rate = matched / len(match_candidates)

        # 按代理 IP 聚合质量（仅静态代理）
        proxy_buckets: dict[str, list[RequestRecord]] = defaultdict(list)
        for r in records:
            if r.proxy_type == "static" and r.proxy_used:
                proxy_buckets[r.proxy_used].append(r)
        proxy_quality = []
        for proxy_ip, recs in proxy_buckets.items():
            successes = sum(1 for r in recs if r.success)
            proxy_quality.append(
                {
                    "proxy": proxy_ip,
                    "total": len(recs),
                    "success": successes,
                    "success_rate": successes / len(recs) if recs else 0.0,
                    "avg_elapsed_ms": sum(r.elapsed_ms for r in recs) / len(recs),
                    "short_response_count": sum(1 for r in recs if r.short_response_triggered),
                }
            )
        proxy_quality.sort(key=lambda x: x["success_rate"])
        m.proxy_quality = proxy_quality

        m.records = [asdict(r) for r in records]
        return m

    def dump_json(self, output_path: Path) -> None:
        """将聚合结果导出为 JSON 文件"""
        m = self.aggregate()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(m), f, ensure_ascii=False, indent=2)


def _percentile(values: list[float], p: float) -> float:
    """计算百分位数"""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * (p / 100.0)
    f_idx = int(k)
    c_idx = min(f_idx + 1, len(sorted_values) - 1)
    if f_idx == c_idx:
        return sorted_values[f_idx]
    d = k - f_idx
    return sorted_values[f_idx] + (sorted_values[c_idx] - sorted_values[f_idx]) * d


def quick_summary(metrics: ScenarioMetrics) -> str:
    """生成简短的人类可读摘要"""
    proxy_only_total = metrics.total - metrics.account_failure_count
    proxy_success_rate = (
        metrics.success / proxy_only_total if proxy_only_total else 0.0
    )
    lines = [
        f"=== {metrics.scenario} ===",
        f"描述：{metrics.description}",
        f"总数：{metrics.total} | 成功：{metrics.success} ({metrics.success_rate:.1%}) | "
        f"失败：{metrics.failed}",
        f"  ↳ 代理失败：{metrics.proxy_failure_count} | 账号失败：{metrics.account_failure_count}",
        f"  ↳ 排除账号失败后真实成功率：{proxy_success_rate:.1%}（{metrics.success}/{proxy_only_total}）",
        f"延迟：avg={metrics.elapsed_avg_ms:.0f}ms | "
        f"p50={metrics.elapsed_p50_ms:.0f}ms | "
        f"p95={metrics.elapsed_p95_ms:.0f}ms | "
        f"p99={metrics.elapsed_p99_ms:.0f}ms",
        f"短响应触发：{metrics.short_response_count} | 兜底命中：{metrics.fallback_hit_count}",
        f"国家匹配率：{metrics.country_match_rate:.1%}",
    ]
    if metrics.failure_category_distribution:
        lines.append(f"失败分类：{metrics.failure_category_distribution}")
    if metrics.fallback_hit_by_country:
        lines.append(f"兜底国家分布：{metrics.fallback_hit_by_country}")
    if metrics.error_distribution:
        top_errors = sorted(
            metrics.error_distribution.items(), key=lambda x: -x[1]
        )[:5]
        lines.append("Top5 错误：")
        for err, cnt in top_errors:
            lines.append(f"  - {err}: {cnt}")
    if metrics.proxy_quality:
        low_quality = [p for p in metrics.proxy_quality if p["success_rate"] < 0.5]
        lines.append(f"低质量代理（成功率 < 50%）：{len(low_quality)} / {len(metrics.proxy_quality)}")
    return "\n".join(lines)


def compare_scenarios(metrics_list: list[ScenarioMetrics]) -> str:
    """生成多场景对比表格（人类可读）"""
    if not metrics_list:
        return "(no data)"
    headers = ["Scenario", "Total", "Success", "Rate", "Avg(ms)", "P95(ms)", "短响应", "国家匹配"]
    rows = [headers]
    for m in metrics_list:
        rows.append([
            m.scenario,
            str(m.total),
            str(m.success),
            f"{m.success_rate:.1%}",
            f"{m.elapsed_avg_ms:.0f}",
            f"{m.elapsed_p95_ms:.0f}",
            str(m.short_response_count),
            f"{m.country_match_rate:.1%}",
        ])
    col_widths = [max(len(r[i]) for r in rows) for i in range(len(headers))]
    sep = "+".join("-" * (w + 2) for w in col_widths)
    out_lines = [sep]
    for i, row in enumerate(rows):
        out_lines.append("|".join(f" {cell:<{col_widths[j]}} " for j, cell in enumerate(row)))
        if i == 0:
            out_lines.append(sep)
    out_lines.append(sep)
    return "\n".join(out_lines)
