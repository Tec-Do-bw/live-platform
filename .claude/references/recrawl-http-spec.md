# 补采 HTTP 请求规格

补采模块通过独立 HTTP 请求重新采集缺失数据时，请求参数和 headers 必须与 JS 注入请求**完全一致**。

## trend/chart 请求

参考 `tiktok.py:_fetch_trend_chart_via_js`

### URL 格式
```
{api_base_url}/api/v1/insights/creator/liveroom/recap/trend/chart?{query_string}
```

- `api_base_url`: 从 live/list 响应 URL 动态提取（默认 `https://shop.tiktok.com`）
- `query_string`: 继承 live/list 原始 URL 的查询参数（user_language, locale, aid, fp 等）

### Headers
继承自 live/list 请求头：
- 过滤 `:` 开头的伪头部
- 补充 `Content-Type: application/json`

### Body

**GMV 请求**：
```json
{
  "request": {
    "room_filter": {"room_id": "<room_id>", "query_online": true},
    "stats_types": [3],
    "granularity": 1
  }
}
```

**Stats 请求**：
```json
{
  "request": {
    "room_filter": {"room_id": "<room_id>", "query_online": true},
    "stats_types": [3, 20, 341, 21, 22, 12, 16, 23, 50, 51, 40],
    "granularity": 1
  }
}
```

## live/stats 请求

参考 `browserapi.py:_handle_live_stats_injection`

### URL
继承自原始拦截到的 live/stats URL

### Headers
继承自原始拦截到的 `packet.request.headers`

### Body
深拷贝原始 payload，仅替换 `time_selector`：
```json
{
  "period": 2,
  "granularity": 11,
  "end_timestamp": "<(D+1) UTC 00:00>",
  "start_timestamp": "<(D-1) UTC 00:00>",
  "timezone_offset": "0"
}
```

## 实现要求

1. **持久化请求上下文**
   - 正常采集时将 headers / api_base_url / query_string / cookies / payload_template 持久化到 `request_context` 表

2. **补采时读取上下文**
   - 从 `request_context` 读取完整请求参数
   - 通过 AdsPower 代理 IP 发出 HTTP 请求

3. **代理 IP 获取**
   - 通过 AdsPower V2 API (`POST /api/v2/browser-profile/list`) 获取 `user_proxy_config`
