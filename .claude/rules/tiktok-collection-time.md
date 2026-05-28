---
paths:
  - "services/live-crawler/crawlers/browser/tiktok.py"
  - "services/live-crawler/crawlers/browser/mx_tiktok.py"
  - "services/live-crawler/webdriver/browserapi.py"
  - "services/live-crawler/tests/test_daily_payloads.py"
---

# TikTok 采集时间规则

## live/stats 接口（browserapi._generate_daily_payloads）

| 模式 | 日期范围 | 说明 |
|------|---------|------|
| 增量 | T-1、T-2、T-3（昨天往前 3 天） | latest_available_date 固定为 today - 1，无结算延迟 |
| 全量 | T-28 ~ T-1（近 28 天） | 与 data-overview 页面的 "Last 28 days" 口径对齐 |

- 时区通过 `_infer_timezone(group_name)` 从 TIMEZONE_MAP 推断，默认 Asia/Singapore
- 每天的时间窗口：UTC 00:00:00 ~ 次日 UTC 00:00:00（24 小时）
- time_selector: `granularity=1`（自定义时间）、`period=2`、`timezone_offset="0"`

## live/list 直播间过滤（tiktok.py / mx_tiktok.py）

| 模式 | 过滤规则 | 说明 |
|------|---------|------|
| 增量 | `live_end_timestamp >= 三天前 00:00:00` | 只采近 3 天的直播间 |
| 全量 | 不过滤 | 采集所有已结束的直播间 |

- 时区从请求体 `time_selector.timezone_offset`（秒）提取
- mx_tiktok 与 tiktok 规则一致（3 天 + 账号时区）

## 禁止事项

- 不得重新引入 SETTLEMENT_HOUR 或任何基于"当地小时数"的结算延迟判断
- 增量模式的天数（3 天）不得随意缩减
