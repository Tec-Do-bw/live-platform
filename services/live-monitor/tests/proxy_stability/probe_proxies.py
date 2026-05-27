# -*- coding: utf-8 -*-
"""静态代理池质量探测：逐一测试 ip_list.txt 中每个代理的连通性和延迟。

用法：
    cd services/live-monitor

    # 默认每个代理测 3 次
    python -m tests.proxy_stability.probe_proxies

    # 每个代理测 5 次（更准确但更慢）
    python -m tests.proxy_stability.probe_proxies --rounds 5

    # 并发 20（加速探测）
    python -m tests.proxy_stability.probe_proxies --workers 20

    # 只输出摸鱼代理（成功率 < 100% 或 P50 > 阈值）
    python -m tests.proxy_stability.probe_proxies --bad-only

输出：
    - 控制台：按成功率升序排列的代理质量表
    - JSON：tests/proxy_stability/results/proxy_probe.json
    - TXT：tests/proxy_stability/results/good_proxies.txt（清洗后的代理列表，可直接替换 ip_list.txt）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import never_primp
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.downloader.config import DEFAULT_HEADERS, NP_MAX_RETRIES

# 探测目标：TikTok 个人页（轻量、稳定、不触发风控）
PROBE_URL = "https://www.tiktok.com/@tiktok"
PROBE_TIMEOUT = 10.0  # 单次超时
MIN_RESPONSE_SIZE = 5000  # 有效响应最小字节数（排除空页/风控页）


@dataclass
class ProbeResult:
    """单个代理的探测结果"""
    proxy: str  # user:pass@host:port
    host_port: str  # host:port（脱敏）
    rounds: int  # 总探测次数
    success_count: int
    fail_count: int
    success_rate: float
    latencies_ms: list[float]  # 成功请求的延迟列表
    avg_ms: float
    p50_ms: float
    p95_ms: float
    errors: list[str]  # 失败原因
    short_response_count: int  # 响应过短（疑似风控）
    verdict: str  # good / slow / unstable / dead


def probe_single_proxy(proxy_line: str, rounds: int) -> ProbeResult:
    """对单个代理执行多轮探测"""
    proxy_url = f"http://{proxy_line}"
    # 脱敏：只保留 host:port
    parts = proxy_line.split("@")
    host_port = parts[-1] if "@" in proxy_line else proxy_line

    latencies: list[float] = []
    errors: list[str] = []
    short_count = 0

    for _ in range(rounds):
        try:
            client = never_primp.Client(
                impersonate="chrome_143",
                impersonate_os="windows",
                proxy=proxy_url,
                timeout=PROBE_TIMEOUT,
                headers=DEFAULT_HEADERS,
                max_retries=1,
            )
            t0 = time.monotonic()
            resp = client.get(PROBE_URL)
            elapsed = (time.monotonic() - t0) * 1000

            if resp.status_code == 200 and len(resp.text or "") >= MIN_RESPONSE_SIZE:
                latencies.append(elapsed)
            elif resp.status_code == 200:
                short_count += 1
                errors.append(f"short_response({len(resp.text or '')})")
            else:
                errors.append(f"HTTP_{resp.status_code}")
        except Exception as e:
            err_name = type(e).__name__
            errors.append(err_name)

    success_count = len(latencies)
    fail_count = rounds - success_count
    success_rate = success_count / rounds if rounds else 0

    avg_ms = sum(latencies) / len(latencies) if latencies else 0
    p50_ms = _percentile(latencies, 50)
    p95_ms = _percentile(latencies, 95)

    # 判定
    if success_rate == 0:
        verdict = "dead"
    elif success_rate < 0.7:
        verdict = "unstable"
    elif p50_ms > 8000:
        verdict = "slow"
    else:
        verdict = "good"

    return ProbeResult(
        proxy=proxy_line,
        host_port=host_port,
        rounds=rounds,
        success_count=success_count,
        fail_count=fail_count,
        success_rate=success_rate,
        latencies_ms=latencies,
        avg_ms=avg_ms,
        p50_ms=p50_ms,
        p95_ms=p95_ms,
        errors=errors,
        short_response_count=short_count,
        verdict=verdict,
    )


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100.0)
    f_idx = int(k)
    c_idx = min(f_idx + 1, len(sorted_v) - 1)
    if f_idx == c_idx:
        return sorted_v[f_idx]
    d = k - f_idx
    return sorted_v[f_idx] + (sorted_v[c_idx] - sorted_v[f_idx]) * d


def main():
    parser = argparse.ArgumentParser(description="静态代理池质量探测")
    parser.add_argument("--rounds", type=int, default=3, help="每个代理探测次数（默认 3）")
    parser.add_argument("--workers", type=int, default=20, help="并发数（默认 20）")
    parser.add_argument("--bad-only", action="store_true", help="只显示摸鱼代理")
    parser.add_argument("--latency-threshold", type=float, default=8000,
                        help="P50 延迟阈值（ms），超过判定为 slow（默认 8000）")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT_DIR / "tests" / "proxy_stability" / "results")
    args = parser.parse_args()

    # 读取代理池
    ip_list_path = ROOT_DIR / "utils" / "downloader" / "ip_list.txt"
    with open(ip_list_path, "r", encoding="utf-8") as f:
        proxies = [line.strip() for line in f if line.strip()]

    print(f"代理池大小：{len(proxies)}")
    print(f"每个代理探测 {args.rounds} 次 | 并发 {args.workers}")
    print(f"探测目标：{PROBE_URL}")
    print(f"超时：{PROBE_TIMEOUT}s | 最小响应：{MIN_RESPONSE_SIZE} bytes")
    print(f"延迟阈值：{args.latency_threshold}ms")
    print()

    results: list[ProbeResult] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(probe_single_proxy, p, args.rounds): p
            for p in proxies
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="探测中"):
            results.append(future.result())

    # 按成功率升序排列
    results.sort(key=lambda r: (r.success_rate, -r.avg_ms))

    # 统计
    dead = [r for r in results if r.verdict == "dead"]
    unstable = [r for r in results if r.verdict == "unstable"]
    slow = [r for r in results if r.verdict == "slow"]
    good = [r for r in results if r.verdict == "good"]

    print(f"\n{'='*80}")
    print(f"探测完成 | 总数：{len(results)}")
    print(f"  good（正常）：{len(good)}")
    print(f"  slow（P50 > {args.latency_threshold}ms）：{len(slow)}")
    print(f"  unstable（成功率 < 70%）：{len(unstable)}")
    print(f"  dead（成功率 = 0%）：{len(dead)}")
    print(f"{'='*80}\n")

    # 输出摸鱼代理
    bad_proxies = dead + unstable + slow
    if bad_proxies:
        print(f"摸鱼代理（{len(bad_proxies)} 个）：")
        print(f"{'Host:Port':<25} {'成功率':>6} {'Avg(ms)':>8} {'P50(ms)':>8} {'判定':>10} {'错误':>30}")
        print("-" * 95)
        for r in bad_proxies:
            err_summary = ", ".join(set(r.errors))[:30] if r.errors else ""
            print(f"{r.host_port:<25} {r.success_rate:>5.0%} {r.avg_ms:>8.0f} "
                  f"{r.p50_ms:>8.0f} {r.verdict:>10} {err_summary:>30}")
    else:
        print("没有摸鱼代理，全部正常！")

    if not args.bad_only and good:
        print(f"\n正常代理（{len(good)} 个）延迟分布：")
        all_latencies = [ms for r in good for ms in r.latencies_ms]
        if all_latencies:
            print(f"  Avg: {sum(all_latencies)/len(all_latencies):.0f}ms")
            print(f"  P50: {_percentile(all_latencies, 50):.0f}ms")
            print(f"  P95: {_percentile(all_latencies, 95):.0f}ms")
            print(f"  P99: {_percentile(all_latencies, 99):.0f}ms")

    # 保存结果
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # JSON 完整数据
    json_path = args.output_dir / "proxy_probe.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(results),
            "good": len(good),
            "slow": len(slow),
            "unstable": len(unstable),
            "dead": len(dead),
            "results": [asdict(r) for r in results],
        }, f, ensure_ascii=False, indent=2)
    print(f"\n详细数据已保存：{json_path}")

    # 清洗后的代理列表（只保留 good）
    good_path = args.output_dir / "good_proxies.txt"
    with open(good_path, "w", encoding="utf-8") as f:
        for r in sorted(good, key=lambda x: x.avg_ms):
            f.write(r.proxy + "\n")
    print(f"清洗后代理列表：{good_path}（{len(good)} 个，可替换 ip_list.txt）")

    # 摸鱼代理列表
    if bad_proxies:
        bad_path = args.output_dir / "bad_proxies.txt"
        with open(bad_path, "w", encoding="utf-8") as f:
            for r in bad_proxies:
                f.write(f"{r.proxy}  # {r.verdict} rate={r.success_rate:.0%} avg={r.avg_ms:.0f}ms\n")
        print(f"摸鱼代理列表：{bad_path}（{len(bad_proxies)} 个）")


if __name__ == "__main__":
    main()
