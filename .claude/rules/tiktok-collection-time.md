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

> HTTP 版实现在 `collector.py`，三链路衔接见 [[tiktok-http-lifecycle]]。
> 增量模式浏览器版与 HTTP 版保持同一口径；HTTP 版全量已支持配置化时间窗，
> 浏览器版全量仍保持近 28 天，后续如需统一需单独改 `browserapi._generate_daily_payloads`。

## live/stats 接口日聚合

| 链路 / 模式 | 日期范围 | 说明 |
|------------|---------|------|
| HTTP 增量 | T-1、T-2、T-3（昨天往前 3 天） | latest_available_date 固定为 today - 1，无结算延迟 |
| HTTP 全量 | 默认 T-60 ~ T-1；配置 `TIKTOK_HTTP_FULL_START_DATE=YYYY-MM-DD` 后为该日起至 T-1 | 起点和终点均按账号当地时区 00:00:00 计算 |
| 浏览器全量 | T-28 ~ T-1（近 28 天） | 本次未改浏览器链路 |

- **HTTP 版**（`collector.py`）：锚点 `_local_yesterday(region)`（账号当地 today-1），增量范围 `range(0,3)`，全量范围由 `_full_window_bounds(region)` 动态计算；时区从 `TIKTOK_REGION_PROFILES[region]` 取
- **浏览器版**（`browserapi._generate_daily_payloads`）：时区 `_infer_timezone(group_name)` 从 TIMEZONE_MAP 推断，默认 Asia/Singapore
- 每天的时间窗口：UTC 00:00:00 ~ 次日 UTC 00:00:00（24 小时）
- time_selector: `granularity=1`（自定义时间）、`period=2`、`timezone_offset="0"`

## live/list 直播间过滤

| 模式 | 过滤规则 | 说明 |
|------|---------|------|
| 增量 | `live_end_timestamp >= 三天前 00:00:00` | 只采近 3 天的直播间 |
| 全量 | 不过滤 | 由 live/list 自定义时间窗限制范围 |

- **HTTP 版**：`collector.filter_rooms_by_window(rooms, region, full)`，时区从 `TIKTOK_REGION_PROFILES` 取；全量 `live/list` 使用 `period=2` + `start_timestamp/end_timestamp` 自定义时间窗
- **浏览器版**（`tiktok.py` / `mx_tiktok.py`）：时区从请求体 `time_selector.timezone_offset`（秒）提取，mx_tiktok 与 tiktok 规则一致

## HTTP 全量窗口配置

配置集中在 `services/live-crawler/core/config_base.py` 的 `TIKTOK_HTTP_CONFIG`：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `TIKTOK_HTTP_FULL_WINDOW_DAYS` | `60` | 未配置固定起始日期时，全量采集近 N 天（T-N ~ T-1） |
| `TIKTOK_HTTP_FULL_START_DATE` | 空 | 固定起始日期，格式 `YYYY-MM-DD`；配置后优先于 `TIKTOK_HTTP_FULL_WINDOW_DAYS` |

示例：`TIKTOK_HTTP_FULL_START_DATE=2026-04-01` 表示从账号当地时区 `2026-04-01 00:00:00` 采集到当地今天 `00:00:00`（不含今天）。

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
- HTTP 增量与浏览器增量的日期锚点必须保持一致（都是账号当地 today-1）
