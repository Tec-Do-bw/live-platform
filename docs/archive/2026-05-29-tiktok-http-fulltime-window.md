# TikTok HTTP 全量采集时间窗改造：固定近 28 天 -> 可配置窗口

> 状态：已实现（待真实账号验证）
> 关联代码：`services/live-crawler/crawlers/http/tiktok/collector.py`
> 关联配置：`services/live-crawler/core/config_base.py`
> 关联规则：`.claude/rules/tiktok-collection-time.md`
> 创建：2026-05-29
> 更新：2026-06-04

## 1. 需求

TikTok HTTP 全量采集时间范围从旧的「近 28 天」改为「可控时间窗」：

- 默认全量采集近 `60` 天，即账号当地时区 `today-60 00:00:00` 到 `today 00:00:00`，不含今天。
- 支持配置固定起始日期，例如 `TIKTOK_HTTP_FULL_START_DATE=2026-04-01` 时，从账号当地时区 `2026-04-01 00:00:00` 采到当地今天 `00:00:00`，不含今天。
- 固定起始日期优先级高于默认天数。
- 增量模式保持不变，仍采近 3 天。

## 2. 关键背景

### 2.1 live/list 的旧 `period=33` 锁死「近 28 天」

旧 `_time_window()` 虽然计算了 `days_back`，但 payload 的 `time_selector` 只使用 `period/granularity/base_timestamp/timezone_offset`。

全量「近 28 天」实际由 TikTok 服务端枚举 `period=33` 决定，不受 `days_back` 控制。要改变范围，必须把 `live/list` 改成自定义时间范围。

### 2.2 用户实测 curl 验证了自定义时间范围写法

用户提供的 `live/list` curl 使用：

```json
"time_selector": {
  "period": 2,
  "granularity": 1,
  "start_timestamp": "1772352000",
  "end_timestamp": "1780041600",
  "timezone_offset": -28800
}
```

这与现有 `fetch_live_stats` 的 `period=2` 自定义时间写法同源。

## 3. 配置

配置集中在 `services/live-crawler/core/config_base.py`：

```python
TIKTOK_HTTP_CONFIG = {
    "full_window_days": int(os.getenv("TIKTOK_HTTP_FULL_WINDOW_DAYS", "60")),
    "full_start_date": os.getenv("TIKTOK_HTTP_FULL_START_DATE", "").strip(),
}
```

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `TIKTOK_HTTP_FULL_WINDOW_DAYS` | `60` | 未配置固定起始日期时，全量采集近 N 天 |
| `TIKTOK_HTTP_FULL_START_DATE` | 空 | 固定全量起始日期，格式 `YYYY-MM-DD`，配置后优先于 `full_window_days` |

## 4. 改造范围

| # | 接口 / 函数 | 改动内容 |
|---|------------|---------|
| 1 | `live/list` `_time_window` + `fetch_live_list` | 全量改为 `period=2/granularity=1/start_timestamp/end_timestamp/timezone_offset`；增量保持旧口径 |
| 2 | `live/list` 翻页 | 全量按 `page` 翻页，单页 500，短页停止，上限 10 页并告警 |
| 3 | `live/stats` 日聚合循环 | 全量天数按配置窗口动态计算；增量仍为 3 天 |
| 4 | `trend/chart` / `core/stats` | 无时间参数，不直接改；房间变多会使请求数线性增长 |
| 5 | `filter_rooms_by_window` | 全量仍不二次过滤，由 `live/list` 服务端时间窗限制 |

## 5. 错误处理

- `TIKTOK_HTTP_FULL_WINDOW_DAYS` 非正整数时，采集阶段抛 `ValueError`。
- `TIKTOK_HTTP_FULL_START_DATE` 不是 `YYYY-MM-DD` 时，采集阶段抛 `ValueError`。
- 固定起始日期晚于或等于账号当地今天时，采集阶段抛 `ValueError`。

## 6. 测试

新增测试文件：`services/live-crawler/tests/crawlers/http/test_tiktok_collector_full_window.py`

覆盖：

- 默认全量近 60 天。
- `TIKTOK_HTTP_FULL_START_DATE=2026-04-01` 优先于默认天数。
- 非法固定起始日期 fail-fast。
- `fetch_live_list` 全量 payload 使用自定义时间窗和分页参数。
- `live/stats` 全量日聚合天数跟随固定起始日期。
- `live/list` 全量翻页到短页停止，并合并所有页房间再过滤。

## 7. 任务清单

- [x] 新增 `TIKTOK_HTTP_CONFIG`，集中读取 `TIKTOK_HTTP_FULL_WINDOW_DAYS` 与 `TIKTOK_HTTP_FULL_START_DATE`
- [x] 新增 `_full_window_bounds(region)` 辅助函数
- [x] 改 `_time_window` 全量分支为自定义时间范围
- [x] 改 `fetch_live_list` payload 的 `time_selector`（period=2 + start/end + 本地时区）
- [x] `fetch_live_list` 支持 `page` 参数
- [x] `collect_tiktok` 增加 live/list 翻页循环 + 停止条件 + 上限保护
- [x] `live/stats` 日聚合循环改为动态天数
- [x] 补单测（窗口计算 / payload / live_stats 天数 / 翻页）
- [x] 更新 `.claude/rules/tiktok-collection-time.md`
- [ ] 实测一个真实账号，核对返回房间数与日期范围
