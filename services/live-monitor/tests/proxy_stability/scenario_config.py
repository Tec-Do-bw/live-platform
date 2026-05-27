# -*- coding: utf-8 -*-
"""测试场景配置：定义 4 种代理策略的切换参数。

通过 monkey-patch 切换 Downloader 的代理选择行为，避免直接修改生产代码。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Scenario(str, Enum):
    """测试场景枚举"""

    STATIC_BASELINE = "static_baseline"  # 场景 1：仅静态代理池
    DYNAMIC_BASELINE = "dynamic_baseline"  # 场景 2：仅动态代理（默认 -US）
    HYBRID_CURRENT = "hybrid_current"  # 场景 3：生产环境逻辑（静态 + 短响应兜底）
    ADAPTIVE_OPTIMIZED = "adaptive_optimized"  # 场景 4：优化策略


@dataclass
class ScenarioConfig:
    """单个场景的测试配置"""

    scenario: Scenario
    description: str
    use_static_pool: bool  # 主请求是否使用静态代理池随机选择
    forced_dynamic_proxy: str | None  # 是否强制使用动态代理（None 表示按 use_static_pool 决定）
    enable_country_retry: bool  # 是否启用短响应国家代理兜底（L3）
    fallback_to_dynamic_on_fail: bool  # 主请求失败时是否立即切动态代理（场景 4 优化点）
    smart_country_match: bool  # 国家代理是否按账号 country_code 智能选择（场景 4 优化点）


# 默认动态代理（来自 utils/downloader/config.py）
DEFAULT_DYNAMIC_PROXY = "http://7758105-0c83c22f:26394524-US@gate-hk.kkoip.com:19187"

# 测试结果输出目录
RESULTS_DIR = "tests/proxy_stability/results"

# 测试并发数（与生产一致）
TEST_WORKERS = 10

# 单次请求超时（秒）
TEST_TIMEOUT = 15.0


SCENARIO_CONFIGS: dict[Scenario, ScenarioConfig] = {
    Scenario.STATIC_BASELINE: ScenarioConfig(
        scenario=Scenario.STATIC_BASELINE,
        description="静态代理池基线：仅使用 ip_list.txt 随机选择，禁用所有兜底",
        use_static_pool=True,
        forced_dynamic_proxy=None,
        enable_country_retry=False,
        fallback_to_dynamic_on_fail=False,
        smart_country_match=False,
    ),
    Scenario.DYNAMIC_BASELINE: ScenarioConfig(
        scenario=Scenario.DYNAMIC_BASELINE,
        description="动态代理基线：强制使用 gate-hk.kkoip.com（默认 -US 落地），禁用其他兜底",
        use_static_pool=False,
        forced_dynamic_proxy=DEFAULT_DYNAMIC_PROXY,
        enable_country_retry=False,
        fallback_to_dynamic_on_fail=False,
        smart_country_match=False,
    ),
    Scenario.HYBRID_CURRENT: ScenarioConfig(
        scenario=Scenario.HYBRID_CURRENT,
        description="生产混合策略：静态代理池主请求 + 短响应触发国家代理兜底（MX/ID/BR）",
        use_static_pool=True,
        forced_dynamic_proxy=None,
        enable_country_retry=True,
        fallback_to_dynamic_on_fail=False,
        smart_country_match=False,
    ),
    Scenario.ADAPTIVE_OPTIMIZED: ScenarioConfig(
        scenario=Scenario.ADAPTIVE_OPTIMIZED,
        description="自适应优化：失败立即切动态 + 按 country_code 智能匹配国家",
        use_static_pool=True,
        forced_dynamic_proxy=None,
        enable_country_retry=True,
        fallback_to_dynamic_on_fail=True,
        smart_country_match=True,
    ),
}


def get_scenario_config(scenario: Scenario | str) -> ScenarioConfig:
    """获取场景配置"""
    if isinstance(scenario, str):
        scenario = Scenario(scenario)
    return SCENARIO_CONFIGS[scenario]
