# TikTok 直播大屏 下游数据接口规范

> 本文档定义 live-platform 对**后端(大屏调用方)**暴露的 HTTP 接口契约。
> 上游 API 调研见 [`docs/research/tiktok-live-dashboard-apis/API-inventory.md`](API-inventory.md)。
> 信封格式对齐 `services/live-crawler/crawlers/http/tiktok/collector.py` 的 `_format_message`。
> 平台范围:**当前仅 TikTok**。

## 1. 背景与定位

后端直播大屏需要两类数据:

1. **账号是否开播 + room_id** —— 房间号每场直播都变,大屏必须先拿到当前 room_id。
2. **5 个大屏业务接口** —— 核心指标、趋势、流量、画像、商品等(对应上游 5 对 API 样本)。

本层是**下游数据接口 API 层**:对后端屏蔽 Redis / Holo / TikTok 上游的内部实现细节,后端只依赖本文档的接口契约。

**设计原则:爬虫只返回原始数据,不在本层做业务解析。** 5 个大屏业务接口的原始 TikTok 响应以 JSON 字符串原样透传,字段解析由后端 / 数仓完成。

### 1.1 后端调用链

```
①  后端 ──POST live-status/batch (collectionIds[]) ──▶ live-monitor ──读 Redis──▶ 返回 [{collectionId, isLive, roomId, flvUrl, timezone, startTime, title}]
                                                                                          │
②  后端拿到 roomId + collectionId ──POST dashboard/data (dataType, roomId, collectionId)──▶ live-crawler ──▶ 信封(含原始响应)
```

先问 live-monitor 拿 `roomId`,再拿着 `roomId` + `collectionId` 去问 live-crawler 取大屏数据。

### 1.2 接口归属

| 接口 | 归属服务 | 数据源 | 领域 |
|------|----------|--------|------|
| 开播状态批量查询 | **live-monitor** | Redis(种子 ← Holo) | 直播状态 |
| 大屏数据(5 个业务接口) | **live-crawler** | TikTok 大屏 API | 数据采集 |

---

## 2. 接口一:开播状态批量查询 @ live-monitor

### 2.1 端点

```
POST /api/v1/tiktok/live-status/batch
```

用 POST 传数组,避免 collection_id 数量大时 GET 拼接超 URL 长度限制。

### 2.2 入参

```json
{ "collectionIds": ["coll_1001", "coll_1002", "coll_1003"] }
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `collectionIds` | string[] | 是 | 一个或多个 collection_id;本层据此读 Redis |

### 2.3 出参

成功(列表式,逐项对应请求中的 collection_id):

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "collectionId": "coll_1001",
      "isLive": true,
      "roomId": "7544720840995162887",
      "flvUrl": "https://pull-flv-.../stream.flv",
      "timezone": "Asia/Ho_Chi_Minh",
      "startTime": "1781485260",
      "title": "TikTok Shop Live"
    },
    {
      "collectionId": "coll_1002",
      "isLive": false,
      "roomId": "",
      "flvUrl": "",
      "timezone": "",
      "startTime": "",
      "title": ""
    },
    {
      "collectionId": "coll_1003",
      "isLive": false,
      "roomId": "",
      "flvUrl": "",
      "timezone": "",
      "startTime": "",
      "title": ""
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `collectionId` | string | 回显请求中的 collection_id |
| `isLive` | bool | 是否开播,由 `flvUrl` 非空且非 `"error"` 推导 |
| `roomId` | string | 当前直播间号;未开播为空字符串 |
| `flvUrl` | string | 直播流地址;未开播为空字符串 |
| `timezone` | string | 直播间时区;未开播为空字符串 |
| `startTime` | string | 开播时间,平台原样返回;未开播为空字符串 |
| `title` | string | 直播间标题;未开播为空字符串 |

### 2.4 约定

- `isLive` 推导规则对齐 `services/live-monitor/utils/TiktokTool.py` 的 `flv_url` 三态约定:非空且非 `"error"` → 开播中;`""` → 未开播。
- **后端传入的 collection_id 都是有效的,Redis 中必然存在对应记录**,因此出参不区分"查不到"与"未开播",也不省略任何项。
- 返回列表顺序与请求 `collectionIds` 一一对应。
- 后端拿到 `roomId` 后,接力调用接口二(见第 3 节)。

### 2.5 业务码

沿用 live-monitor 现有业务码字典(见 [`services/live-monitor/docs/specs/live-room-api.md`](../../services/live-monitor/docs/specs/live-room-api.md)):

| code | 含义 |
|------|------|
| 200 | success |
| 5099 | 内部异常(如 Redis 不可用),`data` 为 null |

> 单条记录的"未开播"不是错误,通过 `isLive=false` 表达,整体 `code` 仍为 200。

---

## 3. 接口二:大屏数据 @ live-crawler

### 3.1 端点

```
POST /api/v1/tiktok/dashboard/data
```

单一统一端点,用 `dataType` 区分 5 个大屏业务接口。

### 3.2 入参

```json
{ "dataType": "core_stats", "roomId": "7544720840995162887", "collectionId": "coll_1001" }
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `dataType` | string | 是 | 5 种之一(见 3.3) |
| `roomId` | string | 是 | 来自接口一 |
| `collectionId` | string | 是 | 采集任务标识,本层据此定位账号会话(内部映射到 collector 的 `socketUserId`) |

上游细节(`stats_types`、`creator_id`、`country`、排序、分页)由本层按 `dataType` **内部固定填充**,不暴露给后端。

### 3.3 dataType 枚举

| dataType | 上游 API | URL 路径 | 页面区域 | 内部固定参数 |
|----------|----------|----------|----------|--------------|
| `core_stats` | 06 core/stats | `/api/v1/insights/workbench/live/detail/core/stats` | ② 核心指标卡片 | `room_filter.room_id`、`is_content_type=1`、`creator_id`、`country`、`stats_types`(55 个:43 个正向指标 + 12 个负数行业基准对比) |
| `trend_chart` | 08 trend/chart | `/api/v1/insights/workbench/live/detail/trend/chart` | ① 性能趋势 | `room_filter.room_id`、`is_content_type=1`、`TREND_CHART_FULL`(27 个合法 ID,独立 ID 体系) |
| `source_new` | 03 source/new | `/api/v3/insights/workbench/live/detail/source/new` | ④ 流量来源 | `room_id`、`is_content_type`、`stats_types=[100]`、`version=3`(2026-06-11 旧批样本,本次未重采) |
| `user_portrait` | 04all user/portrait | `/api/v1/insights/workbench/live/detail/user/portrait` | ⑥ Follower analytics + ⑦ User profile | `room_filter.room_id`、`is_content_type=1`、`stats_types=[80,81,82,83,90,85,86,87,88,350,351,352,353]` |
| `product_list` | 05 product/list | `/api/v1/insights/workbench/live/detail/product/list` | ⑤ 商品列表 | `room_filter.room_id`、`is_content_type=1`、`sorting_type=1`、`stats_types`(19 个有效 ID:`[4,5,6,7,10,15,17,18,21,30,35,41,48,51,55,64,120,301,345]`) |

> `user_portrait` 对齐上游 `04all-user-portrait` 样本,一次请求返回 Viewer / Customer / Impressions 三类画像,覆盖 Follower analytics 与 User profile 两个页面区域。
> `trend_chart` 使用独立 `stats_type` ID 体系,实现时必须使用 `API-inventory.md` §1.4 的 `TREND_CHART_FULL`,不能套用 `core_stats` 的指标 ID。

### 3.4 出参信封

沿用 `_format_message` 既有信封(数仓已在消费的格式),新增 `dataType` 与 `roomId` 两个判别字段:

```json
{
  "params": "",
  "cookies": "[{...}]",
  "fromUrl": "https://.../core/stats",
  "extra": "{...}",
  "sign": "xxx",
  "userType": 6.0,
  "dataSource": "live_crawler_tiktok_http",
  "dataType": "core_stats",
  "roomId": "7544720840995162887",
  "updateTime": 1781149500000,
  "socketUserId": "browser_abc",
  "request": {
    "response": "{\"code\":0,\"message\":\"success\",\"data\":{...}}",
    "url": "https://.../core/stats"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `params` | string | 保留字段(URL query),当前空字符串 |
| `cookies` | string(JSON) | Cookie 列表 JSON 字符串化 |
| `fromUrl` | string | 上游完整请求 URL |
| `extra` | string\|null | 请求体;无则为 null |
| `sign` | string | 数据签名(`Settings.DATA_SERVER_CONFIG.api_sign`) |
| `userType` | float | 固定 6.0 |
| `dataSource` | string | `live_crawler_tiktok_http`(`live_crawler_{platform}_{method}` 约定) |
| `dataType` | string | **新增**,判别字段,标识 5 种数据之一 |
| `roomId` | string | **新增**,回显 |
| `updateTime` | int | 消息时间戳(毫秒) |
| `socketUserId` | string | 账号会话标识;本层用入参 `collectionId` 内部映射填充 |
| `request.response` | string | **TikTok 原始响应的 JSON 字符串,不解析** |
| `request.url` | string | 上游请求 URL |

#### 关键约定

- `request.response` 是上游响应的 JSON 字符串,字段解析由后端 / 数仓完成,本层不碰。
- 信封与现有 Shopee / Lazada 数仓入库链路同款,**零改造**。
- 对后端入参叫 `collectionId`,对下游信封仍是既有字段 `socketUserId`(由本层内部映射),后端口径统一且数仓格式不变。

### 3.5 错误处理

区分"上游业务异常"与"API 层自身失败":

**上游业务异常**(code≠0 / 未开播 / room 不存在):原样塞进 `request.response`,本层不判断,信封照常返回。后端 / 数仓自己从原始响应读取。

**API 层自身失败**(登录态失效 / 上游超时 / 拿不到会话):返回独立错误对象:

```json
{
  "code": 5001,
  "message": "上游请求失败",
  "dataType": "core_stats",
  "roomId": "7544720840995162887",
  "error": { "reason": "login_required", "detail": "..." }
}
```

错误码沿用 live-monitor 现有字典:

| code | 含义 |
|------|------|
| 5001 | 上游请求失败(超时 / 网络错误) |
| 5099 | 采集内部异常(兜底) |
| 4041 | 会话 / 账号不存在 |

`error.reason` 枚举(可扩展):`login_required`、`upstream_timeout`、`session_not_found`、`internal_error`。

---

## 4. 实现待定项

以下属实现细节,不影响本接口契约,实现阶段再定:

- **Redis key 结构**:`collection_id` → 直播状态(`isLive`/`roomId`/`flvUrl`/`timezone`/`startTime`/`title`)的存储结构,以及写入链路,详见 [`docs/specs/live-monitor-stream-redis-bridge.md`](../../specs/live-monitor-stream-redis-bridge.md)。
- **Holo 种子映射**:种子表到 `collection_id` 的映射关系。
- **collector 补齐**:目前 `collector.py` 仅实现 `fetch_core_stats`(06)与 `fetch_trend_chart`(08),另外 3 种(`source_new`/`user_portrait`/`product_list`)的 `fetch_*` 函数待补齐。
- **creator_id / country 解析来源**:`core_stats` 所需的 `creator_id`、`country` 由本层内部解析的具体数据来源。
- **trend/chart 指标 ID**:`trend_chart` 必须使用独立 ID 表 `TREND_CHART_FULL`,不能复用 `core_stats` 的 `stats_types`。
- **dataSource 常量**:现 `constants.py` 为 `DataSource.TIKTOK = "live_crawler_tiktok"`,实现时按约定改为 / 新增 `_http` 后缀变体。

---

## 5. 参考

- 上游 API 调研:[`docs/research/tiktok-live-dashboard-apis/API-inventory.md`](API-inventory.md)(见 §1.1-§1.4 的完整 `stats_types` 与字段映射)
- 信封原型:`services/live-crawler/crawlers/http/tiktok/collector.py` `_format_message`
- live-monitor 业务码与响应规范:[`services/live-monitor/docs/specs/live-room-api.md`](../../services/live-monitor/docs/specs/live-room-api.md)
- dataSource 字段约定:`services/live-crawler/crawlers/constants.py`