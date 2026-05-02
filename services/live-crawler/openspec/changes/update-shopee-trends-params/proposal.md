# Change: Shopee 实时趋势拦截参数补全

## Why
- 拦截 `api/supply/lm/sellercenter/realtime/dashboard/trends` 未携带指定时间区间，导致录制/回放数据不准确。

## What Changes
- 拦截上述路由的请求时，注入 `_handle_shopee_live_list` 标注的 `startTime/endTime`，并固定携带 `sessionId=13841179` 与 `metricTrend=[ccu, engagedCcu, entering]`。
- 确保录制与回放的请求/响应包含上述参数。
- 调整实现参考 `webdriver/browserapi.py` 现有拦截改写逻辑（约 196 行）与 `spiders/shopee.py` 时间来源。

## Impact
- 受影响规格：`shopee-live` 能力（实时趋势拦截/回放）。
- 受影响代码：`spiders/shopee.py`、`webdriver/browserapi.py`、`core/config_base.py` 中监听路由配置。
