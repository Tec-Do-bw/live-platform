---
paths:
  - "services/live-crawler/crawlers/http/tiktok/collector.py"
  - "services/live-crawler/crawlers/http/tiktok/adapter.py"
  - "services/live-crawler/crawlers/browser/tiktok.py"
  - "services/live-crawler/crawlers/browser/mx_tiktok.py"
  - "services/live-crawler/webdriver/browserapi.py"
  - "services/live-crawler/tests/test_daily_payloads.py"
---

# TikTok 采集时间规则

> 浏览器版与 HTTP 版共用同一套时间窗口口径。HTTP 版实现在 `collector.py`，
> 三链路衔接见 [[tiktok-http-lifecycle]]。

## live/stats 接口日聚合

| 模式 | 日期范围 | 说明 |
|------|---------|------|
| 增量 | T-1、T-2、T-3（昨天往前 3 天） | latest_available_date 固定为 today - 1，无结算延迟 |
| 全量 | T-28 ~ T-1（近 28 天） | 与 data-overview 页面的 "Last 28 days" 口径对齐 |

- **HTTP 版**（`collector.py`）：锚点 `_local_yesterday(region)`（账号当地 today-1），范围 `range(0,3)`（增量）/ `range(0,28)`（全量）；时区从 `TIKTOK_REGION_PROFILES[region]` 取
- **浏览器版**（`browserapi._generate_daily_payloads`）：时区 `_infer_timezone(group_name)` 从 TIMEZONE_MAP 推断，默认 Asia/Singapore
- 每天的时间窗口：UTC 00:00:00 ~ 次日 UTC 00:00:00（24 小时）
- time_selector: `granularity=1`（自定义时间）、`period=2`、`timezone_offset="0"`

## live/list 直播间过滤

| 模式 | 过滤规则 | 说明 |
|------|---------|------|
| 增量 | `live_end_timestamp >= 三天前 00:00:00` | 只采近 3 天的直播间 |
| 全量 | 不过滤 | 采集所有已结束的直播间 |

- **HTTP 版**：`collector.filter_rooms_by_window(rooms, region, full)`，时区从 `TIKTOK_REGION_PROFILES` 取；`_time_window` 的 `days_back` 增量 3 / 全量 28
- **浏览器版**（`tiktok.py` / `mx_tiktok.py`）：时区从请求体 `time_selector.timezone_offset`（秒）提取，mx_tiktok 与 tiktok 规则一致

## replay 列表翻页（仅 HTTP 版）

| 模式 | count | 翻页 |
|------|-------|------|
| 增量 | `REPLAY_COUNT_INCREMENTAL=6` | 不翻页，仅最新一页 |
| 全量 | `REPLAY_COUNT_FULL=30` | 按 `data.has_more` 累加 offset |

## region 时区表（HTTP 版）

`collector.TIKTOK_REGION_PROFILES` 含 11 国：JP/SG/MY/CN/ID/TH/VN/PH/BR/MX/US。

> ⚠️ PH=25200(UTC+7) 依历史 `request_context` 推断，未经活账号验证（PH 本土可能是 Manila UTC+8），待有活账号核实。新增国家必须在此表登记，否则 `_region_profile` 走 fallback。

## 禁止事项

- 不得重新引入 SETTLEMENT_HOUR 或任何基于"当地小时数"的结算延迟判断
- 增量模式的天数（3 天）不得随意缩减
- HTTP 版与浏览器版的日期口径必须保持一致（锚点都是账号当地 today-1）
