# -*- coding: utf-8 -*-
"""场景执行器：通过 monkey-patch + thread-local 切换 TiktokTool 的代理策略。

核心设计：
1. 不修改生产代码 utils/TiktokTool.py 和 utils/downloader/core.py
2. monkey-patch 一次性安装到 Downloader / TiktokTool 上，全局生效
3. 每个线程通过 thread-local 存储自己的场景配置和账号 country_code
4. patch 函数读取 thread-local，决定本次请求的代理选择和兜底行为
5. 复用真实的 TiktokTool.getLiveStreamInfo_requests 流程，仅在外围加 hook 收集指标
"""

from __future__ import annotations

import json
import random
import re
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
from tqdm import tqdm

# 把项目根加入 sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.downloader.core import Downloader as _Downloader
from utils.downloader.config import DEFAULT_HEADERS, NP_MAX_RETRIES
from utils.downloader.models import DownloadResult
from utils.TiktokTool import TiktokTool

import never_primp

from tests.proxy_stability.scenario_config import (
    DEFAULT_DYNAMIC_PROXY,
    Scenario,
    ScenarioConfig,
    TEST_TIMEOUT,
    TEST_WORKERS,
    get_scenario_config,
)
from tests.proxy_stability.metrics_collector import (
    MetricsCollector,
    RequestRecord,
)

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")


# ============================================================================
# 静态代理池
# ============================================================================


def _load_static_pool() -> list[str]:
    ip_list_path = ROOT_DIR / "utils" / "downloader" / "ip_list.txt"
    with open(ip_list_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


_STATIC_POOL = _load_static_pool()


# country_code → 动态代理国家后缀映射（场景 4 智能匹配用）
COUNTRY_PROXY_MAP: dict[str, str] = {
    "MY": "SG", "SG": "SG", "TH": "SG", "VN": "SG", "ID": "ID", "PH": "SG",
    "MM": "SG", "KH": "SG", "LA": "SG", "BN": "SG",
    "JP": "JP", "KR": "KR", "TW": "JP", "HK": "JP", "MO": "JP",
    "US": "US", "CA": "US", "MX": "MX", "BR": "BR",
    "GB": "GB", "DE": "DE", "FR": "FR", "ES": "ES", "IT": "IT",
    "AU": "SG", "NZ": "SG",
    "IN": "ID", "PK": "ID", "BD": "ID",
    "AE": "GB", "SA": "GB", "TR": "GB",
}

DEFAULT_FALLBACK_COUNTRIES = ("MX", "ID", "BR")


# ============================================================================
# 线程局部状态：每个线程独立的场景上下文
# ============================================================================


_state = threading.local()


def _get_state(name: str, default=None):
    return getattr(_state, name, default)


def _set_state(**kwargs):
    for k, v in kwargs.items():
        setattr(_state, k, v)


def _clear_state(*names):
    for n in names:
        if hasattr(_state, n):
            delattr(_state, n)


# ============================================================================
# Patch：构造 Downloader 时根据 thread-local 决定代理
# ============================================================================


_PATCH_INSTALLED = False
_ORIGINAL_INIT = None


def _build_dynamic_proxy(country: str | None = None) -> str:
    """根据国家构造动态代理 URL（已废弃，保留供历史快照场景使用）"""
    target = country or "US"
    return re.sub(r"-[A-Z]{2}@", f"-{target}@", DEFAULT_DYNAMIC_PROXY, count=1)


def _patched_init(self, proxy=None, workers=10, timeout=30.0, max_retries=3,
                  headers=None, on_success=None, on_failure=None,
                  impersonate="chrome_143"):
    """替换 Downloader.__init__：根据 thread-local config 决定代理"""
    config: ScenarioConfig | None = _get_state("config")

    # 优先级 1：调用方显式传入动态代理（如 _fetch_live_with_country 内部）
    if proxy and ("kkoip.com" in proxy or "ipbiubiu.com" in proxy):
        actual_proxy = proxy
    # 优先级 2：场景强制使用动态代理（场景 2，或场景 4 失败兜底标记）
    elif _get_state("force_dynamic", False):
        country = _get_state("force_dynamic_country", "US")
        actual_proxy = _build_dynamic_proxy(country)
    elif config and config.forced_dynamic_proxy:
        actual_proxy = config.forced_dynamic_proxy
    # 优先级 3：使用静态代理池
    elif config and config.use_static_pool:
        actual_proxy = "http://" + random.choice(_STATIC_POOL)
    elif proxy:
        actual_proxy = proxy
    else:
        # 兜底：随机静态（保持与原始 core.py 一致）
        actual_proxy = "http://" + random.choice(_STATIC_POOL)

    # 记录最近一次主请求的代理（仅当不是兜底重试）
    if not _get_state("in_fallback", False):
        _set_state(last_main_proxy=actual_proxy)

    self._workers = workers
    self._timeout = timeout
    self._max_retries = max_retries
    self._on_success = on_success
    self._on_failure = on_failure
    self._impersonate = impersonate
    self.ip_list = _STATIC_POOL

    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    self._merged_headers = merged_headers

    # 兼容重构后的 Downloader 字段：_primary_proxy / _retry_proxy
    self._primary_proxy = actual_proxy
    self._retry_proxy = actual_proxy

    self._client = never_primp.Client(
        impersonate=impersonate,
        impersonate_os="windows",
        proxy=actual_proxy,
        timeout=timeout,
        headers=merged_headers,
        max_retries=NP_MAX_RETRIES,
    )
    self._results: list[DownloadResult] = []
    self._total_elapsed = 0


def _patched_retry_live(self, live_url):
    """已废弃：原 TiktokTool._retry_live_with_country_proxy 已被删除（重构为 Downloader 层重试换代理）。
    保留此函数仅为向后兼容历史测试场景，调用时直接返回 None（视作不触发兜底）。
    """
    return None


def _patched_fetch_country(self, live_url, country):
    """已废弃：原 TiktokTool._fetch_live_with_country 已被删除。"""
    return None


def install_patches():
    """一次性安装所有 monkey-patch（测试开始前调用一次）"""
    global _PATCH_INSTALLED, _ORIGINAL_INIT
    if _PATCH_INSTALLED:
        return
    _ORIGINAL_INIT = _Downloader.__init__

    _Downloader.__init__ = _patched_init  # type: ignore[method-assign]
    # 注意：原代码 patch 的 _retry_live_with_country_proxy / _fetch_live_with_country
    # 已被生产代码删除，本次重构后不再 patch（场景 3/4 的"国家兜底"维度自然失效）
    _PATCH_INSTALLED = True


def uninstall_patches():
    """恢复原始函数（测试结束后调用）"""
    global _PATCH_INSTALLED
    if not _PATCH_INSTALLED:
        return
    _Downloader.__init__ = _ORIGINAL_INIT  # type: ignore[method-assign]
    _PATCH_INSTALLED = False


# ============================================================================
# 单条请求处理
# ============================================================================


def _capture_run_results(tk: TiktokTool, room_url: str):
    """运行 tk.getLiveStreamInfo_requests，同时捕获 profile/live 的中间 DownloadResult"""
    captured: dict = {"profile": None, "live": None, "live_after_fallback": None}
    original_run = _Downloader.run
    fallback_seen = {"flag": False}

    def hook_run(self, tasks):
        results = original_run(self, tasks)
        in_fallback = _get_state("in_fallback", False)
        for t, r in zip(tasks, results):
            if t.task_id == "profile":
                captured["profile"] = r
            elif t.task_id == "live":
                captured["live"] = r
            elif t.task_id and t.task_id.startswith("live-retry-"):
                captured["live_after_fallback"] = r
                fallback_seen["flag"] = True
        return results

    def hook_fetch_one(self, task):
        result = original_fetch_one(self, task)
        if task.task_id and task.task_id.startswith("live-retry-"):
            captured["live_after_fallback"] = result
            fallback_seen["flag"] = True
        return result

    original_fetch_one = _Downloader.fetch_one
    _Downloader.run = hook_run  # type: ignore[method-assign]
    _Downloader.fetch_one = hook_fetch_one  # type: ignore[method-assign]
    try:
        port_info = tk.getLiveStreamInfo_requests(room_url, []) or {}
    finally:
        _Downloader.run = original_run  # type: ignore[method-assign]
        _Downloader.fetch_one = original_fetch_one  # type: ignore[method-assign]

    return port_info, captured


def _is_success(port_info: dict) -> tuple[bool, str, str]:
    """判定单次请求是否成功，并分类失败原因

    Returns:
        (success, error_message, failure_category)
        failure_category: proxy / account / parse / unknown / ""（成功时）

    成功标准：
        - 拿到 uniqueId（用户存在）
        - flv_url 非 "error"
        - 不是 "请求失败" 类异常
    """
    flv_url = port_info.get("flv_url", "")
    unique_id = port_info.get("uniqueId", "")
    message = port_info.get("message", "")

    # 代理/网络层失败：明确的请求失败
    if flv_url == "error":
        if "请求个人页失败" in message or "请求直播页失败" in message:
            return False, message, "proxy"
        if "tk采集异常" in message or "采集内部异常" in message:
            return False, message, "unknown"
        return False, message or "请求失败", "proxy"

    # 账号自身失败：用户不存在（与代理无关）
    if not unique_id and "用户信息不存在" in message:
        return False, message, "account"

    # 解析层失败
    if "页面解析失败" in message:
        return False, message, "parse"

    # 拿到 uniqueId（无论是否在播）→ 算成功
    if unique_id:
        return True, "", ""

    return False, message or "未知失败", "unknown"


def _classify_proxy(proxy_url: str) -> str:
    if not proxy_url:
        return "unknown"
    if "kkoip.com" in proxy_url:
        m = re.search(r"-([A-Z]{2})@", proxy_url)
        return f"dynamic_{m.group(1)}" if m else "dynamic"
    return "static"


def _strip_credentials(proxy_url: str) -> str:
    if not proxy_url:
        return ""
    m = re.match(r"https?://(?:[^@]+@)?([^/]+)", proxy_url)
    return m.group(1) if m else proxy_url


def process_single_account(
    row: pd.Series,
    config: ScenarioConfig,
    collector: MetricsCollector,
) -> None:
    """处理单个 TikTok 账号请求"""
    room_url = str(row.get("room_url", "")).strip()
    country_code = str(row.get("country_code", "")).strip().upper()

    if not room_url or "tiktok.com" not in room_url:
        return

    # 重置 thread-local 状态
    _set_state(
        config=config,
        country_code=country_code,
        last_main_proxy="",
        fallback_hit_country=None,
        in_fallback=False,
        force_dynamic=False,
    )

    start_time = time.monotonic()
    try:
        tk = TiktokTool([], no_proxy=False)
        port_info, captured = _capture_run_results(tk, room_url)
    except Exception as e:
        port_info = {"flv_url": "error", "message": f"{type(e).__name__}: {e}"}
        captured = {"profile": None, "live": None, "live_after_fallback": None}

    success, error_message, failure_category = _is_success(port_info)

    # 场景 4 优化点：主请求失败时强制切动态代理重试一次（仅代理失败重试，账号失败不重试）
    proxy_type_final = _classify_proxy(_get_state("last_main_proxy", ""))
    proxy_used_final = _get_state("last_main_proxy", "")

    if (
        config.fallback_to_dynamic_on_fail
        and not success
        and failure_category in ("proxy", "parse", "unknown")
    ):
        # 切动态代理重新跑一次
        target_country = COUNTRY_PROXY_MAP.get(country_code, "US")
        _set_state(
            force_dynamic=True,
            force_dynamic_country=target_country,
        )
        try:
            tk_retry = TiktokTool([], no_proxy=False)
            port_info_retry, captured_retry = _capture_run_results(tk_retry, room_url)
            success_retry, error_retry, cat_retry = _is_success(port_info_retry)
            if success_retry:
                port_info = port_info_retry
                captured = captured_retry
                success = True
                error_message = ""
                failure_category = ""
                proxy_type_final = f"dynamic_{target_country}"
                proxy_used_final = _build_dynamic_proxy(target_country)
            else:
                error_message = f"{error_message} | retry: {error_retry}"
                failure_category = cat_retry
        except Exception as e:
            error_message = f"{error_message} | retry exception: {e}"
        finally:
            _set_state(force_dynamic=False)

    elapsed_ms = (time.monotonic() - start_time) * 1000

    profile_result = captured.get("profile")
    live_result = captured.get("live")
    live_after = captured.get("live_after_fallback")

    profile_status = profile_result.status_code if profile_result else None
    profile_size = len(profile_result.text or "") if profile_result else 0
    live_status = live_result.status_code if live_result else None
    live_size = len(live_result.text or "") if live_result else 0

    short_response_triggered = bool(
        live_result and live_result.success and live_size and live_size < 2000
    )

    fallback_country = _get_state("fallback_hit_country", None)
    if short_response_triggered and not fallback_country and live_after:
        fallback_country = "FAIL"  # 触发了兜底但全部未命中

    publish_region = str(port_info.get("publish_region", ""))
    live_region = str(port_info.get("live_region", ""))
    region_match = bool(country_code) and (
        publish_region == country_code or live_region == country_code
    )

    collector.record(
        RequestRecord(
            room_url=room_url,
            country_code=country_code,
            success=success,
            elapsed_ms=elapsed_ms,
            proxy_used=_strip_credentials(proxy_used_final),
            proxy_type=proxy_type_final,
            profile_status=profile_status,
            profile_size=profile_size,
            live_status=live_status,
            live_size=live_size,
            short_response_triggered=short_response_triggered,
            fallback_country=fallback_country,
            publish_region=publish_region,
            live_region=live_region,
            region_match=region_match,
            error_message=error_message,
            flv_url=str(port_info.get("flv_url", "")),
            failure_category=failure_category,
        )
    )


# ============================================================================
# 场景执行入口
# ============================================================================


def run_scenario(
    scenario: Scenario | str,
    accounts: pd.DataFrame,
    workers: int = TEST_WORKERS,
) -> MetricsCollector:
    """执行单个场景测试"""
    config = get_scenario_config(scenario)
    collector = MetricsCollector(config.scenario.value, config.description)

    print(f"\n{'='*80}")
    print(f"开始执行场景：{config.scenario.value}")
    print(f"描述：{config.description}")
    print(f"账号数：{len(accounts)} | 并发：{workers}")
    print(f"{'='*80}")

    install_patches()
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(process_single_account, row, config, collector)
                for _, row in accounts.iterrows()
            ]
            for _ in tqdm(as_completed(futures), total=len(futures), desc=config.scenario.value):
                pass
    finally:
        # 测试结束保留 patch（如果跨场景调用，避免反复装卸）
        # 由 main 在最终统一卸载
        pass

    return collector
