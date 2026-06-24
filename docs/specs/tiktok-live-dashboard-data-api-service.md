# TikTok 直播大屏数据 API 服务设计

> Status: ready for implementation
> Date: 2026-06-24
> Scope: 下游接口一 `POST /api/v1/tiktok/live-status/batch` 与下游接口二 `POST /api/v1/tiktok/dashboard/data`

## Goal

在 `services/live-crawler` 中实现 TikTok 直播大屏对外查询面，统一提供 `POST /api/v1/tiktok/live-status/batch` 与 `POST /api/v1/tiktok/dashboard/data`。

其中 `dashboard/data` 负责按 `dataType + roomId + collectionId` 拉取 6 类 TikTok 大屏原始响应信封，`live-status/batch` 负责按 `collectionIds` 读取 Redis 状态。

这些接口只负责采集/透传与状态查询，不解析业务字段、不落库、不做 MySQL 迁移、不接入 Kafka。

## Authoritative Sources

- 下游接口契约：`docs/research/tiktok-live-dashboard-apis/tiktok-live-dashboard-downstream-api.md`
- 上游请求真值：`docs/research/tiktok-live-dashboard-apis/API-inventory.md`
- 对外文档：`docs/research/tiktok-live-dashboard-apis/feishu-dashboard-api-doc.md`
- 现有 live-status 语义：`services/live-monitor/routes/live_status.py`、`services/live-monitor/utils/redis_bridge.py`
- Dashboard 实时采集实现：`services/live-crawler/crawlers/http/tiktok/real_collector.py`
- Cookie/session 与 HTTP helper 口径：`services/live-crawler/crawlers/http/tiktok/collector.py`
- TikTok HTTP 生命周期：`.claude/rules/tiktok-http-lifecycle.md`

实现时以 `API-inventory.md` 为上游请求参数的单一真值；`live-status` 的返回结构以当前 live-monitor 语义为迁移基线。`summary.md` 中的 Phase 1 基础设施准备和 SQLite 到 MySQL 迁移不进入本次范围。

## Architecture Decision

采用方案 A：复用 `services/live-crawler/monitor/server.py` 作为唯一 FastAPI 入口，在 `monitor/api/` 下同时挂载 Cookie API、TikTok 凭据刷新 API、live-status 查询与 dashboard 数据路由。

`live-status` 的 Redis 读路径迁移到 `services/live-crawler/utils/redis_bridge.py`，保留现有返回字段与失败语义，但不再依赖 `services/live-monitor/routes/live_status.py`。`services/live-monitor` 只保留状态生产者职责，不再暴露对外查询路由。

## Non-Goals

- 不做 SQLite 到 MySQL 迁移。
- 不新增大屏数据缓存。
- 不把大屏原始响应写入 `room` 表、SQLite、MySQL 或 Kafka。
- 不改变 live-monitor 作为 Redis 状态生产者的职责。
- 不改变 live-status 返回字段结构。
- 不允许后端传入自定义 `stats_types`。
- 不复用 browser 版 JS 注入拼装逻辑。
- 不使用 `services.cookie_manager` 的旧 `cookies` 表路径读取 TikTok 大屏凭据。

## Live Status Contract

### Endpoint

```http
POST /api/v1/tiktok/live-status/batch
X-API-Token: <Settings.COOKIE_API_CONFIG.token>
Content-Type: application/json
```

该接口复用现有 Cookie API token，与 `dashboard/data` 使用同一套 `X-API-Token`。调用方缺失或传错 `X-API-Token` 时返回 HTTP 403。接口只读 Redis，不触发 TikTok 上游请求。

### Request

```json
{
  "collectionIds": ["k19f2q44", "k19f2q45"]
}
```

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `collectionIds` | string[] | yes | 按请求顺序逐项查询；缺失或空数组时返回空 `data` 列表 |

### Success Response

成功响应返回 batch 状态列表。`isLive`、`roomId`、`flvUrl` 保持与现有 live-monitor 语义一致。

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "collectionId": "k19f2q44",
      "isLive": true,
      "roomId": "7544720840995162887",
      "flvUrl": "https://pull-flv.example/live.flv"
    },
    {
      "collectionId": "k19f2q45",
      "isLive": false,
      "roomId": "",
      "flvUrl": ""
    }
  ]
}
```

### API-Layer Error Response

Redis 读取失败返回独立错误对象。鉴权失败由 FastAPI 层返回 HTTP 403。

```json
{
  "code": 5099,
  "message": "Redis unavailable: connection refused",
  "data": null
}
```

| Code | Meaning |
| --- | --- |
| `5099` | Redis 不可用或读取异常 |

## Dashboard Contract

### Endpoint

```http
POST /api/v1/tiktok/dashboard/data
X-API-Token: <Settings.COOKIE_API_CONFIG.token>
Content-Type: application/json
```

首版复用现有 Cookie API token，避免在内网接口裸奔。调用方缺失或传错 `X-API-Token` 时返回 HTTP 403。

### Request

```json
{
  "dataType": "core_stats",
  "roomId": "7544720840995162887",
  "collectionId": "k19f2q44",
  "timeRange": "full"
}
```

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `dataType` | string | yes | 只允许 `core_stats`、`trend_chart`、`source_new`、`user_portrait`、`product_list`、`room_info` |
| `roomId` | string | yes | 来自 live-status/batch 或调用方已知的 TikTok room_id |
| `collectionId` | string | yes | 首版按 `account_id/browser_id` 使用，用来读取 `account_credentials` |
| `timeRange` | string | no | 仅 `trend_chart` 生效；`full` 为默认，`last_5m`、`last_30m` 会映射为上游 `start_time` |

### Success Response

成功响应返回采集信封。`request.response` 是 TikTok 原始 JSON 字符串，后端和数仓自行解析。

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "params": "",
    "cookies": "[{...}]",
    "fromUrl": "https://shop.tiktok.com/api/v1/insights/workbench/live/detail/core/stats?...",
    "extra": "{\"request\":{\"room_filter\":{\"room_id\":\"7544720840995162887\",\"is_content_type\":1},\"stats_types\":[...]}}",
    "sign": "xxx",
    "userType": 6.0,
    "dataSource": "live_crawler_tiktok_http",
    "dataType": "core_stats",
    "roomId": "7544720840995162887",
    "updateTime": 1781149500000,
    "socketUserId": "k19f2q44",
    "request": {
      "response": "{\"code\":0,\"message\":\"success\",\"data\":{...}}",
      "url": "https://shop.tiktok.com/api/v1/insights/workbench/live/detail/core/stats?..."
    }
  }
}
```

### API-Layer Error Response

API 层自身失败返回独立错误对象。

```json
{
  "code": 5001,
  "message": "上游请求失败",
  "dataType": "core_stats",
  "roomId": "7544720840995162887",
  "error": {
    "reason": "login_required",
    "detail": "[k19f2q44] 登录态失效"
  }
}
```

| Code | Meaning |
| --- | --- |
| `4000` | 入参非法 |
| `4041` | `collectionId` 无对应账号凭据 |
| `5001` | 上游请求失败或超时 |
| `5099` | 采集内部异常 |

`error.reason` 使用 `invalid_request`、`session_not_found`、`login_required`、`upstream_timeout`、`upstream_error`、`internal_error`。

## Upstream Dashboard Data Types

每个 `dataType` 对应一个固定上游 endpoint 和固定请求参数集合。实现不得根据前端展示字段裁剪请求。

| dataType | Upstream Path | Fixed Request |
| --- | --- | --- |
| `core_stats` | `/api/v1/insights/workbench/live/detail/core/stats` | `room_filter.room_id`、`is_content_type=1`、`creator_id`、`country`、55 个 `stats_types` |
| `trend_chart` | `/api/v1/insights/workbench/live/detail/trend/chart` | `room_filter.room_id`、`is_content_type=1`、`TREND_CHART_FULL` 27 个独立趋势 ID；`timeRange` 映射为可选 `start_time` |
| `source_new` | `/api/v3/insights/workbench/live/detail/source/new` | `room_id`、`is_content_type=1`、`stats_types=[100]`、`version=3` |
| `user_portrait` | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_filter.room_id`、`is_content_type=1`、`stats_types=[80,81,82,83,90,85,86,87,88,350,351,352,353]` |
| `product_list` | `/api/v1/insights/workbench/live/detail/product/list` | `room_filter.room_id`、`is_content_type=1`、`sorting_type=1`、`stats_types=[4,5,6,7,10,15,17,18,21,30,35,41,48,51,55,64,120,301,345]` |
| `room_info` | `/api/v1/insights/workbench/live/detail/room/info` | `room_filter.room_id`、`is_content_type=1`、无 `stats_types` |

`trend_chart` 的 ID 体系独立于 `core_stats`。实现和测试都必须防止误用 `CORE_STATS_TYPES`。
`room_info` 与 `live-status/batch` 职责互补：前者返回富房间信息，后者返回轻量开播状态。

## Cookie And Session Rules

接口二由 `real_collector.py` 承载 dashboard 专用请求函数，但必须复用 `collector.py` 的 TikTok HTTP session 口径：

1. 通过 `setup_session(collectionId)` 读取 `account_credentials`。
2. `Credentials.token_data` 转为 session cookies。
3. `Credentials.fingerprint_spec` 传给 `get_session()`，继续使用 `curl_cffi` 指纹。
4. `ext_json.query_string` 作为 URL query 来源，通过白名单过滤后拼接。
5. `fetch_account_info()` 校验 `code == 0 && data.user_id` 后才允许请求大屏接口。

凭据仍从 SQLite `monitor/data/monitor.db` 内的 `account_credentials` 表读取。`collectionId` 首版按账号 `account_id/browser_id` 处理。如果未来后端传入的 `collectionId` 与账号 ID 不同，需要新增显式映射层，再进入 `setup_session()`。

## Business-Code Semantics

`account_info` 是登录态判定接口，继续使用严格业务码校验。`code != 0` 表示登录态失效或凭据不可用，API 返回 `login_required`。

6 个 dashboard 业务接口不使用 `_check_code()` 改写 TikTok 业务响应。只要 HTTP 请求成功并拿到响应体，就包装为成功信封，即使 TikTok 原始响应里 `code != 0`。这样对齐下游契约：上游业务异常原样进入 `request.response`，由后端或数仓解析。

网络异常、HTTP 非 2xx、JSON 解析失败、session 建立失败，才属于 API 层失败。

## File Structure

新增和修改文件按以下边界组织：

| Path | Responsibility |
| --- | --- |
| `services/live-crawler/monitor/server.py` | 统一 FastAPI app，挂载 cookie、refresh、live-status、dashboard routers |
| `services/live-crawler/monitor/api/live_status_routes.py` | `POST /api/v1/tiktok/live-status/batch` 路由、鉴权、Redis 读取、错误映射 |
| `services/live-crawler/monitor/api/dashboard_routes.py` | `POST /api/v1/tiktok/dashboard/data` 路由、鉴权、错误映射 |
| `services/live-crawler/monitor/schemas/dashboard.py` | Pydantic request/response schema、`DashboardDataType` 与 `DashboardTimeRange` 枚举 |
| `services/live-crawler/utils/redis_bridge.py` | 迁入 live-status Redis 仓储、状态查询和 batch 映射 |
| `services/live-crawler/services/dashboard_data.py` | 业务编排：session、fetch 分发、信封补字段 |
| `services/live-crawler/crawlers/http/tiktok/real_collector.py` | dashboard 专用 fetchers、指标常量、timeRange/start_time 请求拼装 |
| `services/live-crawler/crawlers/http/tiktok/collector.py` | 保留调度采集主链路，并向 `real_collector.py` 提供可复用 session、URL、result、credentials helpers |
| `services/live-monitor/routes/live_status.py` | 删除，不再暴露 live-monitor 查询路由 |
| `services/live-monitor/tests/test_live_status_batch.py` | 删除或迁移到 live-crawler 测试目录 |

## Collector Design

新建 `real_collector.py` 承载 dashboard 专用函数，避免把下游实时查询语义和调度式 `collector.py::collect_tiktok()` 混在一起。

`real_collector.py` 可以从 `collector.py` 导入并复用已有的 `Credentials`、`FetchResult`、`DEFAULT_RETRY_EXCEPTIONS`、`_build_filtered_url()`、`_make_result()`、`_format_message()` 等通用能力。若当前 helper 是私有函数，实施时应优先做最小导出或局部复用，不把调度采集逻辑复制到 `real_collector.py`。

建议函数：

```python
def fetch_dashboard_core_stats(session: Any, cred: Credentials, room_id: str) -> FetchResult: ...
def fetch_dashboard_trend_chart(session: Any, cred: Credentials, room_id: str, start_time: int | None = None) -> FetchResult: ...
def fetch_dashboard_source_new(session: Any, cred: Credentials, room_id: str) -> FetchResult: ...
def fetch_dashboard_user_portrait(session: Any, cred: Credentials, room_id: str) -> FetchResult: ...
def fetch_dashboard_product_list(session: Any, cred: Credentials, room_id: str) -> FetchResult: ...
def fetch_dashboard_room_info(session: Any, cred: Credentials, room_id: str) -> FetchResult: ...
```

这些函数：

- 使用 `DEFAULT_RETRY_EXCEPTIONS` 做网络级重试。
- 不把 `TikTokBusinessCodeError` 放进 retry exceptions。
- HTTP 成功后返回 `_make_result(ok=True, ...)`。
- request body 严格按 `API-inventory.md` 固定。
- URL query 继续通过 `_build_filtered_url()` 白名单构造。
- `trend_chart` 仅在 `timeRange != "full"` 时传入 `start_time`。
- `room_info` 请求体不包含 `stats_types`。

`core_stats` 的 `creator_id` 来自 `cred.ext["creator_id"]`，`country` 来自 `cred.region.upper()`。当 `creator_id` 缺失时，仍发请求但记录 warning；不在接口层编造 creator id。

## Service Flow

`live_status_routes.py` 的主流程：

1. 校验 `X-API-Token` 必须等于 `Settings.COOKIE_API_CONFIG["token"]`。
2. 从 JSON body 读取 `collectionIds`，缺失时按空数组处理。
3. 将每个 `collectionId` 转为字符串并保持请求顺序。
4. 调用 `LiveRedisRepository.list_live_status(collection_ids)`。
5. Redis 读取失败返回 `{"code": 5099, "message": "Redis unavailable: ...", "data": null}`。
6. 成功时返回 `{"code": 200, "message": "success", "data": rows}`。

`dashboard_data.py` 的主流程：

1. 验证 `dataType`、`roomId`、`collectionId` 非空，校验 `timeRange` 只允许 `full`、`last_5m`、`last_30m`。
2. 调用 `setup_session(collectionId)`。
3. 如果 `dataType == "trend_chart"`，将 `timeRange` 映射为 `start_time`：`full` 不传，`last_5m` 为 `now - 300`，`last_30m` 为 `now - 1800`。
4. 根据 `dataType` 分发到对应 dashboard fetcher。
5. 调用 `_format_message(result.url, result.request_body, result.response_body, cred.token_data, collectionId)`。
6. 覆盖或补充：
   - `message["dataSource"] = "live_crawler_tiktok_http"`
   - `message["dataType"] = dataType`
   - `message["roomId"] = roomId`
   - `message["socketUserId"] = collectionId`
7. 关闭 session。
8. 返回 `{"code": 200, "message": "success", "data": message}`。

`LoginRequired` 映射为 `code=5001, reason=login_required`。`FatalError` 中凭据缺失或 `query_string` 缺失映射为 `code=4041, reason=session_not_found`。

本接口是按需查询，不主动调用 `send_api_request()` 上报数仓。后端需要入库时消费接口返回的信封。

## Test Strategy

### Unit Tests

新增 `services/live-crawler/tests/crawlers/http/test_tiktok_dashboard_fetchers.py`：

- `core_stats` request body 包含 `creator_id`、`country`、55 个 stats types。
- `trend_chart` 使用 27 个独立趋势 ID。
- `trend_chart` 在传入 `start_time` 时把它写入请求体。
- `source_new` 使用 v3 path、`room_id` 扁平结构、`version=3`。
- `user_portrait` 使用 13 个画像 ID。
- `product_list` 使用 `sorting_type=1` 和 19 个商品 ID。
- `room_info` 使用 room/info path，request body 无 `stats_types`。
- dashboard fetchers 收到 TikTok `{"code": 98001021}` 时仍返回 `ok=True` 和原始响应。

新增 `services/live-crawler/tests/services/test_dashboard_data.py`：

- 成功路径返回 `code=200` 和信封字段 `dataType/roomId/dataSource/socketUserId`。
- `trend_chart` 的 `timeRange` 正确映射为 `start_time`。
- `room_info` 返回同一信封格式，且 request body 不包含 `stats_types`。
- `setup_session()` 抛 `LoginRequired` 时返回 `login_required`。
- 凭据缺失映射为 `session_not_found`。
- session 在成功和失败路径都关闭。

新增 `services/live-crawler/tests/monitor/test_live_status_batch.py`：

- 缺少 `X-API-Token` 返回 422 或 403。
- token 错误返回 403。
- 返回顺序与请求 `collectionIds` 一致。
- Redis 无状态时返回未开播对象。
- Redis 异常返回 `code=5099` 和 `data=null`。

新增 `services/live-crawler/tests/monitor/test_tiktok_dashboard_routes.py`：

- 缺少 `X-API-Token` 返回 422 或 403。
- token 错误返回 403。
- 非法 `dataType` 返回 422。
- 非法 `timeRange` 返回 422 或 `code=4000`。
- 合法请求调用 service 并返回 JSON。

### Regression Tests

继续运行现有 TikTok HTTP 测试，防止影响调度采集链路：

```bat
cd services/live-crawler
python -m pytest tests/crawlers/http/test_tiktok_collector_query_params.py tests/crawlers/http/test_tiktok_collector_credential_validation.py tests/crawlers/http/test_tiktok_collector_business_retry.py tests/crawlers/http/test_tiktok_adapter_recovery.py -v
```

### Manual Smoke Test

```bat
cd services/live-crawler
set APP_ENV=pro
python -m monitor.server
```

用真实有效的 TikTok `collectionId/account_id` 调用 live-status：

```powershell
curl.exe -X POST http://127.0.0.1:8777/api/v1/tiktok/live-status/batch `
  -H "Content-Type: application/json" `
  -H "X-API-Token: <token>" `
  -d "{\"collectionIds\":[\"<account_id>\"]}"
```

预期返回 `code=200`，`data[0]` 包含 `collectionId/isLive/roomId/flvUrl`。

再调用 dashboard：

```powershell
curl.exe -X POST http://127.0.0.1:8777/api/v1/tiktok/dashboard/data `
  -H "Content-Type: application/json" `
  -H "X-API-Token: <token>" `
  -d "{\"dataType\":\"trend_chart\",\"roomId\":\"<room_id>\",\"collectionId\":\"<account_id>\",\"timeRange\":\"last_5m\"}"
```

预期返回 `code=200`，`data.request.response` 是 TikTok 原始 JSON 字符串。

## Implementation Order

1. 将 live-status Redis 读路径和 batch 路由迁移到 `services/live-crawler`，用 fake Redis 锁定返回结构。
2. 新建 `real_collector.py`，放入 dashboard fetcher 常量和函数，补齐 `room_info` 与 `trend_chart.timeRange`。
3. 增加 `dashboard_data.py` service，测试 session 生命周期、`timeRange` 映射和信封补字段。
4. 在 `monitor.server` 中注册 live-status 与 dashboard routers，保留 `python -m monitor.server` 启动方式。
5. 删除 `services/live-monitor/routes/live_status.py` 及旧测试，避免双入口。
6. 跑目标 pytest，做本地服务烟测，并按实现结果更新 README / ROADMAP。

## Risks

| Risk | Mitigation |
| --- | --- |
| `live-status/batch` 服务归属改变导致调用方仍打 live-monitor | 保持请求/响应结构不变，发布时同步切换调用地址；不保留 live-monitor 双入口 |
| Redis key 或状态过期语义在迁移中变化 | 迁入当前 `LiveRedisRepository.list_live_status()` 语义，并用 fake Redis 测试顺序、缺失、过期、异常 |
| `collectionId` 与 `account_id` 不一致 | 首版明确按同一 ID 处理；如果后端传参不同，新增映射层后再实现 |
| `creator_id` 缺失导致 `core_stats` 返回不完整 | 复用 `setup_session()` 的 `ext_json`；缺失时 warning 并原样返回 TikTok 响应 |
| 改动 `collector.py` helper 影响调度采集 | `real_collector.py` 只复用通用 helper，不改 `collect_tiktok()` 主流程；回归跑现有 TikTok HTTP 测试 |
| `trend_chart.timeRange` 映射错误 | 对 `full/last_5m/last_30m` 写 service 层单测，锁定 `start_time` 是否存在及秒数偏移 |
| `room_info` 与 live-status 职责混淆 | `room_info` 仅作为 dashboard dataType 返回富信息；live-status 只返回轻量开播状态 |
| 上游业务码被接口层吞掉 | dashboard fetchers 不调用 `_check_code()`，HTTP 成功即包装原始响应 |

## Acceptance Criteria

- `POST /api/v1/tiktok/live-status/batch` 在 `services/live-crawler` 中可用，返回结构与旧 live-monitor 路由一致。
- `POST /api/v1/tiktok/live-status/batch` 与 `dashboard/data` 都校验同一套 `X-API-Token`。
- `services/live-monitor/routes/live_status.py` 不再作为下游接口入口存在。
- `POST /api/v1/tiktok/dashboard/data` 支持 6 个 `dataType`：`core_stats`、`trend_chart`、`source_new`、`user_portrait`、`product_list`、`room_info`。
- `trend_chart` 支持 `timeRange=full|last_5m|last_30m`，并正确映射上游 `start_time`。
- 6 类上游请求参数与 `API-inventory.md` 对齐。
- Cookie/session 获取只通过 `setup_session()` 和 `account_credentials`。
- 不做 MySQL 迁移。
- TikTok dashboard `code != 0` 原样进入 `request.response`。
- API 层错误按 `error.reason` 返回。
- 新增测试和现有 TikTok HTTP 回归测试通过。
