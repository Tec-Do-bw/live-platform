# TiktokTool 代理稳定性测试

测试 `utils/TiktokTool.py` 的代理使用策略，对比静态代理池和动态代理的稳定性、效率，从而推导出最优请求方法。

## 测试场景

| 场景 | 说明 | 主要代理 | 短响应兜底 |
|------|------|----------|-----------|
| `static_baseline` | 静态代理池基线 | `ip_list.txt` 随机选 | 禁用 |
| `dynamic_baseline` | 动态代理基线 | `gate-hk.kkoip.com -US` 强制 | 禁用 |
| `hybrid_current` | 当前生产策略 | 静态池随机选 | 启用（MX/ID/BR 并发） |
| `adaptive_optimized` | 优化策略 | 静态池随机选 | 启用（按 country_code 智能匹配 + 失败立即切动态） |

## 设计要点

1. **不修改生产代码**：通过 monkey-patch `Downloader.__init__` 和 `TiktokTool._retry_live_with_country_proxy` 切换代理策略
2. **真实流量**：复用 `TiktokTool.getLiveStreamInfo_requests` 的完整请求逻辑（profile + live + 解析）
3. **细粒度埋点**：记录每次请求实际使用的代理、HTTP 状态码、响应大小、错误类型、兜底命中国家

## 使用方式

```bash
cd services/live-monitor

# 全部 4 个场景顺序执行（推荐）
python -m tests.proxy_stability.run_test --scenario all

# 单一场景
python -m tests.proxy_stability.run_test --scenario static_baseline

# 小样本快速验证（前 50 个账号）
python -m tests.proxy_stability.run_test --scenario all --limit 50

# 自定义并发数
python -m tests.proxy_stability.run_test --scenario all --workers 10
```

## 输出

每个场景生成一个 JSON 文件：

```
tests/proxy_stability/results/
├── static_baseline.json
├── dynamic_baseline.json
├── hybrid_current.json
└── adaptive_optimized.json
```

JSON 结构：

```json
{
  "scenario": "static_baseline",
  "total": 420,
  "success": 380,
  "success_rate": 0.905,
  "elapsed_avg_ms": 1850,
  "elapsed_p95_ms": 5200,
  "short_response_count": 12,
  "fallback_hit_count": 0,
  "fallback_hit_by_country": {},
  "error_distribution": {
    "请求直播页失败: timeout": 25,
    "用户信息不存在": 15
  },
  "proxy_quality": [
    {"proxy": "50.2.4.82:7114", "total": 5, "success": 1, "success_rate": 0.2}
  ],
  "country_match_rate": 0.85,
  "records": [...]
}
```

## 字段说明

| 字段 | 说明 |
|------|------|
| `success_rate` | 拿到用户信息且 flv_url 非 error 的比例 |
| `elapsed_p95_ms` | 95% 请求耗时低于此值（ms） |
| `short_response_count` | 直播页响应 <2000 字节的次数（疑似风控） |
| `fallback_hit_count` | 兜底代理成功命中次数 |
| `country_match_rate` | API 返回 region 与账号 country_code 匹配率 |
| `proxy_quality` | 按代理 IP 聚合的成功率（按升序排列，找到低质量代理） |

## 分析重点

1. **静态 vs 动态**：哪种代理成功率更高？延迟差异多大？
2. **代理质量分布**：静态池中有多少 IP 成功率 < 50%？
3. **风控频率**：短响应在哪些代理 / 哪些时段更频繁？
4. **国家匹配**：MX/ID/BR 兜底是否真的有效？是否应该按 country_code 智能选？
5. **优化效果**：场景 4 相比场景 3 的改进幅度
