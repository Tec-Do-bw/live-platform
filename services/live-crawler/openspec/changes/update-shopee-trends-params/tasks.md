## 1. 实施
- [ ] 1.1 阅读 `spiders/shopee.py` 中 `_handle_shopee_live_list`，明确 `startTime/endTime` 来源。
- [ ] 1.2 在 `webdriver/browserapi.py` 拦截 `api/supply/lm/sellercenter/realtime/dashboard/trends` 时，注入指定 params 并确保录制/回放带上。
- [ ] 1.3 如需，确认 `core/config_base.py` 中监听列表包含该路由（已存在则跳过）。
- [ ] 1.4 本地验证：发起趋势请求，检查请求/响应含 `startTime/endTime/sessionId/metricTrend`，返回 200。
- [ ] 1.5 更新本清单勾选并执行 `openspec validate update-shopee-trends-params --strict`。
