# TiktokTool 代理稳定性测试报告

> 测试日期：2026-05-27
> 样本：420 个 TikTok 账号（来自 `scripts/全部直播账号数据.xlsx`）
> 并发：10 线程
> 总测试时长：~12 分钟（4 场景 × 420 账号）

## 执行摘要

通过对静态代理池（300 个）和动态代理（gate-hk.kkoip.com）的 4 场景对比测试，得出以下结论：

1. **代理本身不是问题**：4 场景下 420 个账号请求中代理失败 = 0，39 个失败 100% 是账号本身（已注销/改名）
2. **静态池稳定且高速**：成功率 100%，P95 = 5234ms，单代理使用 1-6 次无负担
3. **动态代理慢 2.3 倍**：P95 = 12093ms，不应作为主路径
4. **发现核心 bug**：`utils/downloader/core.py:87-88` 强制使用静态代理，传入的 `proxy` 参数被忽略 → 导致 `_fetch_live_with_country()` 国家代理切换实际**完全失效**

## 测试场景与对比数据

| 场景 | 总数 | 成功 | 成功率 | 代理失败 | 账号失败 | Avg(ms) | P50(ms) | P95(ms) | P99(ms) |
|------|------|------|--------|---------|---------|---------|---------|---------|---------|
| 静态基线 | 420 | 381 | 90.7% | **0** | 39 | 4086 | 4016 | 5234 | 6506 |
| 动态基线 | 420 | 381 | 90.7% | **0** | 39 | 6141 | 5250 | 12093 | 19232 |
| 当前混合 | 420 | 381 | 90.7% | **0** | 39 | 4162 | 3954 | 5156 | 8886 |
| 优化方案 | 420 | 381 | 90.7% | **0** | 39 | 3981 | 3953 | 5095 | 6198 |

> **排除账号自身失败后真实成功率 = 100%（381/381）**

## 关键洞察

### 1. 代理失败为零，问题在哪里？

测试期间所有代理（静态 + 动态）都成功完成请求。39 个失败全部是 `用户信息不存在`，意味着这些账号在 TikTok 已被删除/改名/封禁，与代理无关。

**生产环境观察到的"代理失败"实际可能是**：
- 账号自身已失效，但归因到了代理
- 测试时段恰好风控较弱（国家匹配率 93.4% 也佐证）
- 个别极端时段的偶发超时

### 2. 动态代理延迟劣势显著

| 指标 | 静态 | 动态 | 倍率 |
|------|------|------|------|
| Avg | 4086ms | 6141ms | 1.50× |
| P95 | 5234ms | 12093ms | 2.31× |
| P99 | 6506ms | 19232ms | 2.96× |

动态代理在尾部延迟（P95/P99）上劣势明显，**不应作为主路径**。

### 3. 静态代理池健康度

- 池总大小：300 个
- 实际使用：217-229 个（约 75%）
- 单代理使用：1-6 次（无热点）
- 低成功率（<50%）代理：7-12 个 ← 但全部都是因为命中"已删除账号"，**与代理质量无关**

### 4. 国家兜底逻辑实际是死代码

`TiktokTool._retry_live_with_country_proxy()` 触发条件是直播页响应 < 2000 字节。本次 420 账号测试**未触发一次**，这意味着：
- 该兜底逻辑日常基本不工作
- 即便工作，由于 core.py 的 bug，"切换到 MX/ID/BR 代理"实际**也是随机静态代理**，没有真正实现国家切换

## Bug 修复

### 问题代码

`utils/downloader/core.py:84-92`：

```python
self._client = never_primp.Client(
    impersonate=impersonate,
    impersonate_os="windows",
    proxy='http://'+random.choice(self.ip_list),  # ← 强制随机静态代理
    # proxy=proxy,                                # ← 传入的 proxy 被注释
    timeout=timeout,
    headers=merged_headers,
    max_retries=NP_MAX_RETRIES,
)
```

### 修复方案

让传入的 `proxy` 参数真正生效，仅当未传时回退到静态池随机：

```python
# 代理选择策略：
# - 调用方显式传入 proxy（含动态代理国家切换场景）→ 优先使用
# - 调用方传入 None（明确禁用代理）→ 不走代理
# - 未传 proxy（保留默认 DEFAULT_PROXY）→ 切换为静态代理池随机
if proxy is DEFAULT_PROXY:
    actual_proxy = "http://" + random.choice(self.ip_list)
else:
    actual_proxy = proxy

self._client = never_primp.Client(
    impersonate=impersonate,
    impersonate_os="windows",
    proxy=actual_proxy,
    ...
)
```

### 修复后行为验证

| 调用方式 | 修复前 | 修复后 |
|----------|--------|--------|
| `Downloader()` 默认 | 随机静态 | 随机静态（保持） |
| `Downloader(proxy=动态MX)` | 随机静态 ❌ | 真实动态 MX ✅ |
| `Downloader(proxy=None)` | 随机静态 ❌ | 不走代理 ✅ |

修复后：
- `TiktokTool._fetch_live_with_country("MX")` 真正使用 MX 国家代理
- `TiktokTool(no_proxy=True)` 真正禁用代理（之前是无效的）
- 主路径行为不变（默认仍走静态池），不影响生产

## 最终建议

### 已落地（本次修复）

✅ **修复 core.py 代理参数被忽略的 bug**
- 让 `_fetch_live_with_country` 国家代理切换真正生效
- 让 `TiktokTool(no_proxy=True)` 真正禁用代理
- 主路径默认行为保持不变（静态池随机）

### 暂不实施（基于数据决策）

❌ **不切换主路径到动态代理**
- 理由：动态代理 P95 慢 2.3 倍，无成功率优势

❌ **不引入"失败立即切动态代理"逻辑**
- 理由：测试中代理失败 = 0，不存在需要兜底的场景，过度设计

❌ **不修改国家代理兜底列表（MX/ID/BR）**
- 理由：本次测试未触发一次兜底，没有数据支持改动

❌ **不清理"低质量代理"**
- 理由：低成功率代理实际全是命中"已删除账号"，代理本身没问题

### 未来观测建议

1. **生产环境埋点**：记录真实生产环境的代理失败率，与本次测试对照
2. **监控短响应触发频率**：如果生产环境短响应频繁触发（>1%），再考虑：
   - 按 `country_code` 智能匹配国家（待真实风控数据支持）
   - 扩展 `_LIVE_RETRY_COUNTRIES` 的国家选项
3. **定期复测**：每月运行一次本测试套件，跟踪代理质量变化

## 测试套件交付物

```
services/live-monitor/tests/proxy_stability/
├── __init__.py
├── README.md                    # 使用说明
├── scenario_config.py           # 4 场景配置
├── metrics_collector.py         # 指标采集与聚合
├── scenario_runner.py           # 场景执行器（monkey-patch）
├── run_test.py                  # 主入口
└── results/
    ├── static_baseline.json
    ├── dynamic_baseline.json
    ├── hybrid_current.json
    ├── adaptive_optimized.json
    └── full_run.log
```

### 重跑命令

```bash
cd services/live-monitor

# 全量复测（4 场景 × 420 账号 ~12 分钟）
python -m tests.proxy_stability.run_test --scenario all

# 小样本快速验证
python -m tests.proxy_stability.run_test --scenario all --limit 50
```
