# TikTok 直播大屏数据 API 服务设计

> Status: ready for implementation
> Date: 2026-06-23
> Scope: 下游接口二 `POST /api/v1/tiktok/dashboard/data`

## Goal

在 `services/live-crawler` 中实现 TikTok 直播大屏数据接口，供后端按 `dataType + roomId + collectionId` 拉取 5 类 TikTok 大屏原始响应信封。

该接口只负责采集与透传 TikTok 原始响应，不解析业务字段、不落库、不做 MySQL 迁移、不接入 Kafka。

## Authoritative Sources

- 下游接口契约：`docs/research/tiktok-live-dashboard-apis/tiktok-live-dashboard-downstream-api.md`
- 上游请求真值：`docs/research/tiktok-live-dashboard-apis/API-inventory.md`
- 对外文档：`docs/research/tiktok-live-dashboard-apis/feishu-dashboard-api-doc.md`
- Cookie/session 口径：`services/live-crawler/crawlers/http/tiktok/collector.py`
- TikTok HTTP 生命周期：`.claude/rules/tiktok-http-lifecycle.md`

实现时以 `API-inventory.md` 为上游请求参数的单一真值。`summary.md` 中的 Phase 1 基础设施准备和 SQLite 到 MySQL 迁移不进入本次范围。

## Architecture Decision

采用方案 A：接口二归属 `services/live-crawler` 根服务域，新增 `api/` 模块，不继续扩展 `services/live-crawler/monitor`。

`monitor` 当前只保留 Cookie API、TikTok 凭据刷新 API、登录状态兼容层和 SQLite 最小连接能力。旧采集监控埋点已经是 no-op，不再把大屏数据 API 放进 `monitor`，避免扩大历史监控边界。

为降低部署改动，新的 `api.server` 复用现有 Cookie API 和 TikTok 凭据刷新 router，并新增 dashboard router。`monitor.server` 保留为兼容入口，内部转向或复用新的 app，避免旧命令立即失效。

## Non-Goals

- 不做 SQLite 到 MySQL 迁移。
- 不新增大屏数据缓存。
- 不把大屏原始响应写入 `room` 表、SQLite、MySQL 或 Kafka。
- 不允许后端传入自定义 `stats_types`。
- 不复用 browser 版 JS 注入拼装逻辑。
- 不使用 `services.cookie_manager` 的旧 `cookies` 表路径读取 TikTok 大屏凭据。

## API Contract

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
  "collectionId": "k19f2q44"
}
```

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `dataType` | string | yes | 只允许 `core_stats`、`trend_chart`、`source_new`、`user_portrait`、`product_list` |
| `roomId` | string | yes | 来自接口一开播状态返回 |
| `collectionId` | string | yes | 首版按 `account_id/browser_id` 使用，用来读取 `account_credentials` |

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
| `trend_chart` | `/api/v1/insights/workbench/live/detail/trend/chart` | `room_filter.room_id`、`is_content_type=1`、`TREND_CHART_FULL` 27 个独立趋势 ID |
| `source_new` | `/api/v3/insights/workbench/live/detail/source/new` | `room_id`、`is_content_type=1`、`stats_types=[100]`、`version=3` |
| `user_portrait` | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_filter.room_id`、`is_content_type=1`、`stats_types=[80,81,82,83,90,85,86,87,88,350,351,352,353]` |
| `product_list` | `/api/v1/insights/workbench/live/detail/product/list` | `room_filter.room_id`、`is_content_type=1`、`sorting_type=1`、`stats_types=[4,5,6,7,10,15,17,18,21,30,35,41,48,51,55,64,120,301,345]` |

`trend_chart` 的 ID 体系独立于 `core_stats`。实现和测试都必须防止误用 `CORE_STATS_TYPES`。

## Cookie And Session Rules

接口二必须复用 `collector.py` 的 TikTok HTTP session 口径：

1. 通过 `setup_session(collectionId)` 读取 `account_credentials`。
2. `Credentials.token_data` 转为 session cookies。
3. `Credentials.fingerprint_spec` 传给 `get_session()`，继续使用 `curl_cffi` 指纹。
4. `ext_json.query_string` 作为 URL query 来源，通过白名单过滤后拼接。
5. `fetch_account_info()` 校验 `code == 0 && data.user_id` 后才允许请求大屏接口。

凭据仍从 SQLite `monitor/data/monitor.db` 内的 `account_credentials` 表读取。`collectionId` 首版按账号 `account_id/browser_id` 处理。如果未来后端传入的 `collectionId` 与账号 ID 不同，需要新增显式映射层，再进入 `setup_session()`。

## Business-Code Semantics

`account_info` 是登录态判定接口，继续使用严格业务码校验。`code != 0` 表示登录态失效或凭据不可用，API 返回 `login_required`。

5 个 dashboard 业务接口不使用 `_check_code()` 改写 TikTok 业务响应。只要 HTTP 请求成功并拿到响应体，就包装为成功信封，即使 TikTok 原始响应里 `code != 0`。这样对齐下游契约：上游业务异常原样进入 `request.response`，由后端或数仓解析。

网络异常、HTTP 非 2xx、JSON 解析失败、session 建立失败，才属于 API 层失败。

## File Structure

新增和修改文件按以下边界组织：

| Path | Responsibility |
| --- | --- |
| `services/live-crawler/api/__init__.py` | live-crawler API 包标识 |
| `services/live-crawler/api/server.py` | FastAPI app，挂载 cookie、refresh、dashboard routers |
| `services/live-crawler/api/routes/dashboard_routes.py` | `POST /api/v1/tiktok/dashboard/data` 路由、鉴权、错误映射 |
| `services/live-crawler/api/schemas/dashboard.py` | Pydantic request/response schema、`DashboardDataType` 枚举 |
| `services/live-crawler/services/dashboard_data.py` | 业务编排：session、fetch 分发、信封补字段 |
| `services/live-crawler/crawlers/http/tiktok/collector.py` | 新增 dashboard 专用 fetchers 和指标常量 |
| `services/live-crawler/monitor/server.py` | 兼容旧启动入口，复用新 app |
| `services/live-crawler/start_pro.bat` | 将 API 服务启动命令改为 `python -m api.server` |
| `services/live-crawler/README.md` | 更新 API 服务说明和测试命令 |
| `docs/ROADMAP.md` | 增加接口二实施项或完成状态 |

## Collector Design

`collector.py` 增加 dashboard 专用函数，避免把下游实时查询语义和调度式 `collect_tiktok()` 混在一起。

建议函数：

```python
def fetch_dashboard_core_stats(session: Any, cred: Credentials, room_id: str) -> FetchResult: ...
def fetch_dashboard_trend_chart(session: Any, cred: Credentials, room_id: str) -> FetchResult: ...
def fetch_dashboard_source_new(session: Any, cred: Credentials, room_id: str) -> FetchResult: ...
def fetch_dashboard_user_portrait(session: Any, cred: Credentials, room_id: str) -> FetchResult: ...
def fetch_dashboard_product_list(session: Any, cred: Credentials, room_id: str) -> FetchResult: ...
```

这些函数：

- 使用 `DEFAULT_RETRY_EXCEPTIONS` 做网络级重试。
- 不把 `TikTokBusinessCodeError` 放进 retry exceptions。
- HTTP 成功后返回 `_make_result(ok=True, ...)`。
- request body 严格按 `API-inventory.md` 固定。
- URL query 继续通过 `_build_filtered_url()` 白名单构造。

`core_stats` 的 `creator_id` 来自 `cred.ext["creator_id"]`，`country` 来自 `cred.region.upper()`。当 `creator_id` 缺失时，仍发请求但记录 warning；不在接口层编造 creator id。

## Service Flow

`dashboard_data.py` 的主流程：

1. 验证 `dataType`、`roomId`、`collectionId` 非空。
2. 调用 `setup_session(collectionId)`。
3. 根据 `dataType` 分发到对应 dashboard fetcher。
4. 调用 `_format_message(result.url, result.request_body, result.response_body, cred.token_data, collectionId)`。
5. 覆盖或补充：
   - `message["dataSource"] = "live_crawler_tiktok_http"`
   - `message["dataType"] = dataType`
   - `message["roomId"] = roomId`
   - `message["socketUserId"] = collectionId`
6. 关闭 session。
7. 返回 `{"code": 200, "message": "success", "data": message}`。

`LoginRequired` 映射为 `code=5001, reason=login_required`。`FatalError` 中凭据缺失或 `query_string` 缺失映射为 `code=4041, reason=session_not_found`。

本接口是按需查询，不主动调用 `send_api_request()` 上报数仓。后端需要入库时消费接口返回的信封。

## Test Strategy

### Unit Tests

新增 `services/live-crawler/tests/crawlers/http/test_tiktok_dashboard_fetchers.py`：

- `core_stats` request body 包含 `creator_id`、`country`、55 个 stats types。
- `trend_chart` 使用 27 个独立趋势 ID。
- `source_new` 使用 v3 path、`room_id` 扁平结构、`version=3`。
- `user_portrait` 使用 13 个画像 ID。
- `product_list` 使用 `sorting_type=1` 和 19 个商品 ID。
- dashboard fetchers 收到 TikTok `{"code": 98001021}` 时仍返回 `ok=True` 和原始响应。

新增 `services/live-crawler/tests/services/test_dashboard_data.py`：

- 成功路径返回 `code=200` 和信封字段 `dataType/roomId/dataSource/socketUserId`。
- `setup_session()` 抛 `LoginRequired` 时返回 `login_required`。
- 凭据缺失映射为 `session_not_found`。
- session 在成功和失败路径都关闭。

新增 `services/live-crawler/tests/api/test_tiktok_dashboard_routes.py`：

- 缺少 `X-API-Token` 返回 422 或 403。
- token 错误返回 403。
- 非法 `dataType` 返回 422。
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
python -m api.server
```

用真实有效的 TikTok `collectionId/account_id` 调用：

```powershell
curl.exe -X POST http://127.0.0.1:8777/api/v1/tiktok/dashboard/data `
  -H "Content-Type: application/json" `
  -H "X-API-Token: <token>" `
  -d "{\"dataType\":\"core_stats\",\"roomId\":\"<room_id>\",\"collectionId\":\"<account_id>\"}"
```

预期返回 `code=200`，`data.request.response` 是 TikTok 原始 JSON 字符串。

## Implementation Order

1. 增加 dashboard fetcher 常量和函数，并用 fake session 锁定请求体。
2. 增加 `dashboard_data.py` service，测试 session 生命周期和信封补字段。
3. 增加 FastAPI schema/router/server，测试 token、校验和错误映射。
4. 将 `monitor.server` 改为兼容入口，更新 `start_pro.bat` 和 README。
5. 跑目标 pytest，做本地服务烟测。
6. 根据实现状态更新 `docs/ROADMAP.md`。

## Risks

| Risk | Mitigation |
| --- | --- |
| `collectionId` 与 `account_id` 不一致 | 首版明确按同一 ID 处理；如果后端传参不同，新增映射层后再实现 |
| `creator_id` 缺失导致 `core_stats` 返回不完整 | 复用 `setup_session()` 的 `ext_json`；缺失时 warning 并原样返回 TikTok 响应 |
| 修改 `collector.py` 影响调度采集 | dashboard fetchers 与 `collect_tiktok()` 分离，回归跑现有 TikTok HTTP 测试 |
| 上游业务码被接口层吞掉 | dashboard fetchers 不调用 `_check_code()`，HTTP 成功即包装原始响应 |
| 旧部署命令仍启动 `monitor.server` | `monitor.server` 保留兼容 app，README 和 `start_pro.bat` 切到 `api.server` |

## Acceptance Criteria

- `POST /api/v1/tiktok/dashboard/data` 支持 5 个 `dataType`。
- 5 类上游请求参数与 `API-inventory.md` 对齐。
- Cookie/session 获取只通过 `setup_session()` 和 `account_credentials`。
- 不做 MySQL 迁移。
- TikTok dashboard `code != 0` 原样进入 `request.response`。
- API 层错误按 `error.reason` 返回。
- 新增测试和现有 TikTok HTTP 回归测试通过。
