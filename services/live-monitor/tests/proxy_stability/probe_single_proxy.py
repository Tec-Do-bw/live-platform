# -*- coding: utf-8 -*-
"""单一代理（特别是动态代理）的多轮探测：验证 IP 轮换、延迟、成功率。

用法：
    cd services/live-monitor

    # 测试 ipbiubiu 新动态代理
    python -m tests.proxy_stability.probe_single_proxy \\
        --proxy "w8a3gsvcnv3y_c_US:EYaCbD1o3qMrneUm@dp1.ipbiubiu.com:10769" \\
        --rounds 30

    # 测试 kkoip 动态代理对比
    python -m tests.proxy_stability.probe_single_proxy \\
        --proxy "7758105-0c83c22f:26394524-US@gate-hk.kkoip.com:19187" \\
        --rounds 30
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import never_primp
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.downloader.config import DEFAULT_HEADERS

# 探测目标：用 ip 查询服务获取出口 IP，验证轮换
IP_PROBE_URL = "https://ipinfo.io/json"
# TikTok 探测目标
TIKTOK_PROBE_URL = "https://www.tiktok.com/@tiktok"
PROBE_TIMEOUT = 10.0
MIN_TIKTOK_SIZE = 5000


def probe_ip_rotation(proxy_url: str, rounds: int, workers: int) -> dict:
    """探测出口 IP 轮换情况"""
    print(f"\n[阶段 1] 探测出口 IP 轮换（{rounds} 轮）")
    ips: list[str] = []
    countries: list[str] = []
    cities: list[str] = []
    latencies: list[float] = []
    errors: list[str] = []

    def _one_request(_):
        try:
            client = never_primp.Client(
                impersonate="chrome_143",
                proxy=proxy_url,
                timeout=PROBE_TIMEOUT,
                max_retries=1,
            )
            t0 = time.monotonic()
            resp = client.get(IP_PROBE_URL)
            elapsed = (time.monotonic() - t0) * 1000
            if resp.status_code == 200:
                data = json.loads(resp.text)
                return {
                    "ip": data.get("ip", ""),
                    "country": data.get("country", ""),
                    "city": data.get("city", ""),
                    "region": data.get("region", ""),
                    "elapsed": elapsed,
                }
            return {"error": f"HTTP {resp.status_code}", "elapsed": elapsed}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one_request, i) for i in range(rounds)]
        for f in tqdm(as_completed(futures), total=rounds, desc="IP 轮换探测"):
            r = f.result()
            if "ip" in r:
                ips.append(r["ip"])
                countries.append(r["country"])
                cities.append(r["city"])
                latencies.append(r["elapsed"])
            else:
                errors.append(r.get("error", "unknown"))

    unique_ips = list(set(ips))
    return {
        "rounds": rounds,
        "success": len(ips),
        "fail": len(errors),
        "unique_ips": len(unique_ips),
        "ip_rotation_rate": len(unique_ips) / len(ips) if ips else 0,
        "ips_sample": ips[:10],
        "countries": dict(Counter(countries)),
        "cities": dict(Counter(cities).most_common(10)),
        "latencies": latencies,
        "errors": dict(Counter(errors)),
    }


def probe_tiktok_access(proxy_url: str, rounds: int, workers: int) -> dict:
    """探测对 TikTok 的访问能力"""
    print(f"\n[阶段 2] 探测 TikTok 访问能力（{rounds} 轮）")
    success_count = 0
    short_count = 0
    fail_count = 0
    latencies: list[float] = []
    sizes: list[int] = []
    errors: list[str] = []

    def _one_request(_):
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
            resp = client.get(TIKTOK_PROBE_URL)
            elapsed = (time.monotonic() - t0) * 1000
            size = len(resp.text or "")
            if resp.status_code == 200 and size >= MIN_TIKTOK_SIZE:
                return {"status": "success", "elapsed": elapsed, "size": size}
            elif resp.status_code == 200:
                return {"status": "short", "elapsed": elapsed, "size": size}
            return {"status": "fail", "error": f"HTTP {resp.status_code}", "elapsed": elapsed}
        except Exception as e:
            return {"status": "fail", "error": f"{type(e).__name__}"}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one_request, i) for i in range(rounds)]
        for f in tqdm(as_completed(futures), total=rounds, desc="TikTok 探测"):
            r = f.result()
            if r["status"] == "success":
                success_count += 1
                latencies.append(r["elapsed"])
                sizes.append(r["size"])
            elif r["status"] == "short":
                short_count += 1
                sizes.append(r["size"])
                errors.append(f"short_response({r['size']})")
            else:
                fail_count += 1
                errors.append(r.get("error", "unknown"))

    return {
        "rounds": rounds,
        "success": success_count,
        "short_response": short_count,
        "fail": fail_count,
        "success_rate": success_count / rounds,
        "latencies": latencies,
        "avg_size": sum(sizes) / len(sizes) if sizes else 0,
        "errors": dict(Counter(errors)),
    }


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


def _stats(latencies: list[float]) -> dict:
    if not latencies:
        return {"avg": 0, "p50": 0, "p95": 0, "p99": 0, "min": 0, "max": 0}
    return {
        "avg": sum(latencies) / len(latencies),
        "p50": _percentile(latencies, 50),
        "p95": _percentile(latencies, 95),
        "p99": _percentile(latencies, 99),
        "min": min(latencies),
        "max": max(latencies),
    }


def main():
    parser = argparse.ArgumentParser(description="单一代理多轮探测")
    parser.add_argument("--proxy", required=True,
                        help="代理 URL，格式 user:pass@host:port（自动加 http://）")
    parser.add_argument("--rounds", type=int, default=30, help="每阶段探测次数")
    parser.add_argument("--workers", type=int, default=10, help="并发数")
    parser.add_argument("--name", default=None, help="代理名称（用于结果文件命名）")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT_DIR / "tests" / "proxy_stability" / "results")
    args = parser.parse_args()

    proxy_url = args.proxy if args.proxy.startswith("http") else f"http://{args.proxy}"
    proxy_host = re.search(r"@([^:]+)", args.proxy)
    name = args.name or (proxy_host.group(1) if proxy_host else "unknown")

    print(f"代理：{proxy_url}")
    print(f"代理标识：{name}")
    print(f"轮数：{args.rounds} | 并发：{args.workers}")

    rotation = probe_ip_rotation(proxy_url, args.rounds, args.workers)
    tiktok = probe_tiktok_access(proxy_url, args.rounds, args.workers)

    rotation_stats = _stats(rotation["latencies"])
    tiktok_stats = _stats(tiktok["latencies"])

    print(f"\n{'='*80}")
    print(f"代理探测报告 - {name}")
    print(f"{'='*80}")
    print(f"\n[出口 IP 轮换]")
    print(f"  总轮数：{rotation['rounds']} | 成功：{rotation['success']} | 失败：{rotation['fail']}")
    print(f"  独立 IP 数：{rotation['unique_ips']} / {rotation['success']}")
    print(f"  轮换率：{rotation['ip_rotation_rate']:.1%}（"
          f"{'每次都换 IP' if rotation['ip_rotation_rate'] >= 0.95 else '部分轮换' if rotation['ip_rotation_rate'] > 0.5 else '基本不换'}）")
    print(f"  国家分布：{rotation['countries']}")
    print(f"  城市分布（Top10）：{rotation['cities']}")
    print(f"  延迟：avg={rotation_stats['avg']:.0f}ms | p50={rotation_stats['p50']:.0f}ms | "
          f"p95={rotation_stats['p95']:.0f}ms | min={rotation_stats['min']:.0f}ms | "
          f"max={rotation_stats['max']:.0f}ms")
    print(f"  IP 样本（前 10）：{rotation['ips_sample']}")
    if rotation["errors"]:
        print(f"  错误：{rotation['errors']}")

    print(f"\n[TikTok 访问能力]")
    print(f"  总轮数：{tiktok['rounds']} | 成功：{tiktok['success']}（{tiktok['success_rate']:.1%}）")
    print(f"  短响应（疑似风控）：{tiktok['short_response']}")
    print(f"  失败：{tiktok['fail']}")
    print(f"  延迟：avg={tiktok_stats['avg']:.0f}ms | p50={tiktok_stats['p50']:.0f}ms | "
          f"p95={tiktok_stats['p95']:.0f}ms | p99={tiktok_stats['p99']:.0f}ms")
    print(f"  平均响应大小：{tiktok['avg_size']:.0f} bytes")
    if tiktok["errors"]:
        print(f"  错误分布：{tiktok['errors']}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"single_proxy_{name}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "proxy_host": name,
            "rounds": args.rounds,
            "ip_rotation": {**rotation, "stats": rotation_stats},
            "tiktok_access": {**tiktok, "stats": tiktok_stats},
        }, f, ensure_ascii=False, indent=2)
    print(f"\n详细数据已保存：{out_path}")


if __name__ == "__main__":
    main()
