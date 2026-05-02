## ADDED Requirements
### Requirement: Shopee 实时趋势请求参数补全
系统必须在拦截 `api/supply/lm/sellercenter/realtime/dashboard/trends` 时，使用 Shopee 爬虫提供的时间区间并补全固定参数，以确保录制与回放的数据准确。

#### Scenario: 拦截趋势请求参数补全
- **WHEN** 拦截到 `.../realtime/dashboard/trends` 请求
- **THEN** 请求被改写为携带 `startTime` 与 `endTime`（来自 `_handle_shopee_live_list` 提供的标注值）
- **AND** 携带 `sessionId=13841179` 与 `metricTrend=[ccu, engagedCcu, entering]`
- **AND** 录制/回放中保留上述参数并成功返回 200
