# TikTok 直播大屏 API 采集目录

## 1. API 样本分析表

> **本批样本采集上下文**：collection_id=`k19f2q44`（越南团队 TikTok 账号 `bagsmart_official.vn`），room_id=`7651420995556182804`，region=VN，creator_id=`7158775580024210437`。采集方式：`requests` + socks5 越南代理 + 完整登录 Cookie（`sessionid`/`sid_tt` 等），无额外签名 header。响应金额统一 VND（`amount` 为最小单位字符串 + `amount_formatted`）。样本抓取时间 2026-06-15，实测请求脚本见 scratches/`TK-越南团队实时直播测试-k19f2q44`，配对响应见 `raw/`（**03 source/new 为 2026-06-11 旧批，本次未重采**）。

| API 编号 | 接口名称 | URL 路径 | 请求参数 | 响应核心字段 | 业务含义 | 对应页面区域 |
|---------|---------|---------|---------|------------|---------|------------|
| **03** | source/new | `/api/v3/insights/workbench/live/detail/source/new` | `room_id`<br>`is_content_type`<br>`stats_types=[100]`<br>`version=3` | `stats.all_traffic_distribution[]` (流量来源分布)<br>- `main_source` (一级来源)<br>- `detail_source[]` (二级来源)<br>- 包含：`watch_pv` `ctr` `co` `gmv_usd` `gmv_local` `enter_room_rate` `show_gpm_usd` `show_gpm_local` | 流量来源分析，支持二级细分。包含各来源 GMV、转化率、进房率、千次曝光 GMV | **④ Traffic source**（左中，Channel/Attributed GMV/Impressions/Views 多级来源表） |
| **04all** | user/portrait（三类画像合并） | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_filter.room_id`<br>`room_filter.is_content_type=1`<br>**`stats_types=[80,81,82,83,90, 85,86,87,88, 350,351,352,353]`**（13 个，一次返回三类画像） | `data.stats` 含 13 个分布字段：<br>**Viewer**（全体观众）：`all_gender_distribution` `all_fan_distribution` `all_age_distribution` `all_state_distribution` `country_distribution`<br>**Customer**（付费）：`paid_gender_distribution` `paid_fan_distribution` `paid_age_distribution` `paid_state_distribution`<br>**Impressions**（曝光）：`impressions_gender_distribution` `impressions_country_distribution` `impressions_age_distribution` `impressions_state_distribution`<br>性别 type 20男/21女/22未知；年龄 type 3/4/5；地区/国家 key=名称 value=占比 | 观众画像。**实测一次请求传 13 个 ID 即返回三类画像全部分布字段**，绕过网页分 Tab 限制。完整映射见 [§1.2](#12-userportrait-完整指标-id-映射三类画像一次全返回) | **⑥ Follower analytics**（左下，新粉/老粉/非粉 + GMV/订单/客单价）<br>**⑦ User profile**（右下，Gender/Age/Region）<br>样本：`raw/04all-user-portrait.*` |
| **05** | product/list | `/api/v1/insights/workbench/live/detail/product/list` | `room_filter.room_id`<br>`room_filter.is_content_type=1`<br>`sorting_type=1`（GMV 降序）<br>**`stats_types=[4,5,6,7,10,15,17,18,21,30,35,41,48,51,55,64,120,301,345]`**（19 个） | 响应路径 `data.segments[0].stats[]`，每个商品对象（实测 22 个商品）含：<br>- `id` / `name` / `cover_url` / `is_pinned`（恒定）<br>- `gmv_local`（单品 GMV，金额对象）<br>- `sales`（销量）<br>- `exposure_cnt`（曝光数）<br>- `click_through_rate`（CTR）<br>- `total_click_cnt`（点击数）<br>- `click_order_rate`（CTOR）<br>- `paid_order_cnt` / `paid_main_order_cnt`（订单/SKU 订单）<br>- `paid_user_cnt`（客户数）<br>- `main_aov_local`（客单价）<br>- `watch_gpm_local`（Watch GPM）<br>- `inventory_left_cnt`（剩余库存）<br>- `add_shop_cart_cnt`（加购）<br>- `payment_success_rate`（支付成功率）<br>- `is_live`（是否在售）/ `platform_type` / `sellable_country` / `sellable_countries` / `source`<br>**汇总**：`data.sold_product`（售出商品种类数，实测 `13`） | **商品维度详细数据**，按 GMV 降序，含单品完整转化漏斗。**全量 stats_types→字段映射见 [§1.3](#13-productlist-完整指标-id-映射全量一次返回)，已实测单 ID 逐个锁定** | **⑤ Product List**（中下，Product/Attributed GMV/Product Impressions/CTR/Added to cart 表格）<br>样本：`raw/05-product-list.*` |
| **06** | core/stats | `/api/v1/insights/workbench/live/detail/core/stats` | `room_filter.room_id`<br>`room_filter.is_content_type=1`<br>`room_filter.creator_id`<br>`room_filter.country=VN`<br>**`stats_types`**（本批实测传 55 个：43 正 + 12 负）：<br>正=35 网页可选 + 5 固定 KPI（3/2/5/18/17）+ 3 广告辅助（290/291/292）<br>负=行业基准对比 `[-3,-2,-7,-344,-23,-20,-18,-39,-10,-11,-70,-71]` | `data.stats` 一次返回 41 个字段（实测）：<br>- `gmv_local`（GMV，金额对象，`17761420`）<br>- `sales`（71）/ `current_visitor_cnt`（6）<br>- `paid_order_cnt`（71）/ `main_order_cnt`（47）/ `paid_user_cnt`（36）<br>- `click_through_rate`（LIVE CTR）/ `click_order_rate` / `click_order_rate_main`（CTOR）/ `sku_order_rate`<br>- `main_aov_local` / `sku_aov_local`<br>- `watch_uv`（2826）/ `watch_pv`（4232）/ `watch_pv_one_min_plus`（334）<br>- `client_show_cnt` / `show_pv_per_hour` / `product_view_cnt` / `product_reach_cnt` / `product_click_through_rate`<br>- `avg_view_duration` / `avg_watching_time` / `enter_room_rate` / `enter_room_rate_live_preview`<br>- `live_show_gpm_local` / `watch_gpm_local` / `gmv_local_per_hour`<br>- `payment_success_rate` / `est_gmv_local` / `with_subsidy_gmv_local`<br>- `accumulated_comment_cnt` / `accumulated_sharing_cnt` / `accumulated_new_follower_cnt` / `likes` / `live_comment_rate` / `live_follow_rate` / `live_like_rate` / `live_share_rate`<br>- `ads_cost_local` / `ads_gmv_max_roi` / `is_ads_roi2` / `ads_roi2_effective_time`<br>**benchmark 对比**：`data.stats_benchmark_data.market_cmp_data[]`（本批实回 `{stats_type:315,cmp:"-0.800944"}`） | **最核心 API**，含大屏所有关键指标。**完整 55 个 stats_types ID → 字段名映射见 [§1.1](#11-corestats-完整指标-id-映射api-06-深入)，已逐个抓包实测确认；API 不受网页 16 勾选上限约束** | **② 核心指标卡片**（中央，Attributed GMV/items sold/Current viewers/Ads Cost/Views/Impressions per hour/Avg viewing duration/Follow rate/Tap-through rate/LIVE CTR）<br>样本：`raw/06-core-stats.*` |
| **08** | trend/chart | `/api/v1/insights/workbench/live/detail/trend/chart` | `room_filter.room_id`<br>`room_filter.is_content_type=1`<br>**`stats_types`**（本批实测传 27 个全集）：`[3,52,82,41,344, 20,11,50,14,84,51,92, 23,13,12,16,312,313,314,315, 401,15,91,343,350,81,323]` | `data.trend_data[]`（每条对应一个 `stats_type`，本批返回 27 条）：<br>- 货币类（如 `stats_type=3` GMV、`401` AOV、`91` Watch GPM、`81` Show GPM）：`data[]` 中 `key`=时间戳 / `amount`=金额对象<br>- 计数/比率类（如 `20` Viewers、`11` Views、`50` Product Impressions、`16` Likes）：`data[]` 中 `key`=时间戳 / `value`=数值字符串<br>`granularity=15`（15 分钟粒度，服务端按直播时长自动决定，**不在请求体内**）<br>`timezone_offset=25200` / `timezone="Asia/Ho Chi Minh"`<br>本批每条序列含 50 个时间点 | 性能趋势曲线，按 15 分钟粒度聚合多指标时间序列。**全部 27 个可选指标 ID 见 [§1.4](#14-trendchart-全部可选指标-id-列表独立-id-体系)；网页每次只能选 2 个，但已验证 API 可一次传全部 27 个返回多条序列。⚠️ trend/chart 用独立 ID 体系，勿与 core/stats 的 ID 混用** | **① Performance trends**（左上，Viewers + Attributed GMV 双线趋势图）<br>样本：`raw/08-trend-chart.*` |

---

## 1.1 core/stats 完整指标 ID 映射（API 06 深入）

> 来源：2026-06-15 chrome-devtools 实时抓包 + JS Bundle 枚举定义 + 页面 a11y 快照三方对齐。room_id=7651420995556182804，region=VN。

### 请求结构

```
POST /api/v1/insights/workbench/live/detail/core/stats
```

```json
{
  "request": {
    "room_filter": {
      "room_id": "7651420995556182804",
      "is_content_type": 1,
      "creator_id": "7158775580024210437",
      "country": "VN"
    },
    "stats_types": [/* 指标 ID 数组，见下表 */]
  }
}
```

认证仅依赖 Cookie（`sessionid`/`sid_tt` 等），**无额外签名 header**，页面 fetch 自动携带。

### 指标 ID 映射表

> 共 35 个网页可选指标，按弹窗 UI 4 个分组排列。**枚举常量取自前端 JS bundle（`main.0578107f.js`）的 `LIVE_DETAIL_*` 枚举定义**（共 168 个常量），与 ID 一一对应。**全部字段名均经 2026-06-15 单 ID 单独发请求实测确认（✓）**，唯一例外是 `292 has_ads_roi1`（标 ⚠️，单传时 stats 为空，需联合广告其他 ID 才返回）。

#### 分组一：Transaction（交易，7 项）

| stats_type ID | 枚举常量 | 响应字段名 | 网页显示名 | 类型/示例 |
|---|---|---|---|---|
| 15 | LIVE_DETAIL_MAIN_AOV_LOCAL | `main_aov_local` ✓ | AOV | Currency |
| 27 | LIVE_DETAIL_PAID_USER_CNT | `paid_user_cnt` ✓ | Customers | 整数 |
| 7 | LIVE_DETAIL_PAID_ORDER_CNT | `paid_order_cnt` ✓ | Attributed SKU orders | 整数，`58` |
| 344 | LIVE_DETAIL_MAIN_ORDER_CNT | `main_order_cnt` ✓ | Attributed orders | 整数，`37` |
| 50 | LIVE_DETAIL_PAYMENT_SUCCESS_RATE | `payment_success_rate` ✓ | Payment Rate | 比例字符串，`"1.000000"` |
| 346 | LIVE_DETAIL_EST_GMV_LOCAL | `est_gmv_local` ✓ | Est. GMV | Currency |
| 348 | LIVE_DETAIL_WITH_SUBSIDY_GMV_LOCAL | `with_subsidy_gmv_local` ✓ | GMV with subsidies | Currency |

#### 分组二：Traffic Efficiency（流量效率，18 项）

| stats_type ID | 枚举常量 | 响应字段名 | 网页显示名 | 类型/示例 |
|---|---|---|---|---|
| 71 | LIVE_DETAIL_PRODUCT_REACH_CNT | `product_reach_cnt` ✓ | Product clicks | 整数，`1275` |
| 10 | LIVE_DETAIL_CLICK_THROUGH_RATE | `click_through_rate` ✓ | LIVE CTR | 比例字符串，`"0.428"` |
| 20 | LIVE_DETAIL_WATCH_PV | `watch_pv` ✓ | Views | 整数，`2976` |
| 330 | LIVE_DETAIL_ENTER_ROOM_RATE | `enter_room_rate` ✓ | Tap-through rate | 比例字符串，`"0.028930"` |
| 29 | LIVE_DETAIL_AVG_VIEW_DURATION | `avg_view_duration` ✓ | Avg. viewing duration | 字符串数值（秒），`"48.215388"` |
| 70 | LIVE_DETAIL_PRODUCT_VIEW_CNT | `product_view_cnt` ✓ | Product Impressions | 整数，`25157` |
| 11 | LIVE_DETAIL_CLICK_ORDER_RATE | `click_order_rate` ✓ | CTOR (SKU orders) | 比例字符串，`"0.045"` |
| 39 | LIVE_DETAIL_LIVE_SHOW_GPM_LOCAL | `live_show_gpm_local` ✓ | Show GPM | Currency，`"138772"` VND |
| 43 | LIVE_DETAIL_WATCH_GPM_LOCAL | `watch_gpm_local` ✓ | Watch GPM | Currency，`"4217863"` VND |
| 343 | LIVE_DETAIL_CLICK_ORDER_RATE_MAIN | `click_order_rate_main` ✓ | CTOR | 比例字符串，`"0.026111"` |
| 23 | LIVE_DETAIL_CLIENT_SHOW_CNT | `client_show_cnt` ✓ | Impressions | 整数，`101688` |
| 310 | LIVE_DETAIL_SHOW_PV_PER_HOUR | `show_pv_per_hour` ✓ | Impressions per hour | 整数，`12628` |
| 325 | LIVE_DETAIL_GMV_LOCAL_PER_HOUR | `gmv_local_per_hour` ✓ | GMV per hour | Currency，`"1752425"` VND |
| 130 | LIVE_DETAIL_PRODUCT_CLICK_THROUGH_RATE | `product_click_through_rate` ✓ | CTR | 比例字符串，`"0.049209"` |
| 30 | LIVE_DETAIL_AVG_WATCHING_TIME | `avg_watching_time` ✓ | Avg. viewing duration per view | 整数（秒），`64` |
| 332 | LIVE_DETAIL_ENTER_ROOM_RATE_LIVE_PREVIEW | `enter_room_rate_live_preview` ✓ | Tap-through rate (via LIVE preview) | 比例字符串，`"0.0267"` |
| 323 | LIVE_DETAIL_SKU_ORDER_RATE | `sku_order_rate` ✓ | Order rate (SKU orders) | 比例字符串，`"0.016861"` |
| 349 | LIVE_DETAIL_WATCH_PV_ONE_MIN_PLUS | `watch_pv_one_min_plus` ✓ | > 1 min. views | 整数 |

#### 分组三：Interactions（互动，8 项）

| stats_type ID | 枚举常量 | 响应字段名 | 网页显示名 | 类型/示例 |
|---|---|---|---|---|
| 62 | LIVE_DETAIL_ACCUMULATED_NEW_FOLLOWER_CNT | `accumulated_new_follower_cnt` ✓ | New followers | 整数 |
| 61 | LIVE_DETAIL_ACCUMULATED_SHARING_CNT | `accumulated_sharing_cnt` ✓ | Shares | 整数 |
| 60 | LIVE_DETAIL_ACCUMULATED_COMMENT_CNT | `accumulated_comment_cnt` ✓ | Comments | 整数 |
| 331 | LIVE_DETAIL_LIKES | `likes` ✓ | Likes | 整数 |
| 312 | LIVE_DETAIL_LIVE_COMMENT_RATE | `live_comment_rate` ✓ | Comment rate | 比例字符串 |
| 313 | LIVE_DETAIL_LIVE_FOLLOW_RATE | `live_follow_rate` ✓ | Follow rate | 比例字符串 |
| 314 | LIVE_DETAIL_LIVE_LIKE_RATE | `live_like_rate` ✓ | Like rate | 比例字符串 |
| 315 | LIVE_DETAIL_LIVE_SHARE_RATE | `live_share_rate` ✓ | Share rate | 比例字符串 |

#### 分组四：Ads（广告，2 项）

| stats_type ID | 枚举常量 | 响应字段名 | 网页显示名 | 类型/示例 |
|---|---|---|---|---|
| 241 | LIVE_DETAIL_ADS_COST_LOCAL | `ads_cost_local` ✓ | Ads Cost | Currency，`"2502344"` VND |
| 283 | LIVE_DETAIL_ADS_GMV_MAX_ROI | `ads_gmv_max_roi` ✓ | GMV Max ROI | 浮点数，`6.648` |

---

### 主屏幕固定核心 KPI（不在 35 项可选弹窗内，但实际请求会随附）

主屏幕顶部默认显示的核心 KPI，未出现在指标弹窗中：

| stats_type ID | 枚举常量 | 响应字段名 | 网页显示名 |
|---|---|---|---|
| 3 | LIVE_DETAIL_GMV_LOCAL | `gmv_local` ✓ | Attributed GMV |
| 2 | LIVE_DETAIL_SALES | `sales` ✓ | Attributed items sold |
| 5 | LIVE_DETAIL_CURRENT_VISITOR_CNT | `current_visitor_cnt` ✓ | Current viewers |
| 18 | LIVE_DETAIL_WATCH_UV | `watch_uv` ✓ | Viewers（独立访客 UV，部分页面用到） |
| 17 | LIVE_DETAIL_SKU_AOV_LOCAL | `sku_aov_local` ✓ | AOV (SKU)（同 main_aov_local 互补） |

---

### 内部辅助 ID（非用户可选指标，但抓包请求中常带）

实测请求体里出现但不对外暴露在 UI 中的辅助标志位 / 时间戳，用于广告 ROI 切换状态：

| stats_type ID | 枚举常量 | 响应字段名 | 含义 |
|---|---|---|---|
| 290 | LIVE_DETAIL_ADS_IS_ROI2 | `is_ads_roi2` ✓ | 是否启用 ROI2 模式（布尔） |
| 291 | LIVE_DETAIL_ADS_ROI2_EFFECTIVE_TIME | `ads_roi2_effective_time` ✓ | ROI2 生效时间戳 |
| 292 | LIVE_DETAIL_HAS_ADS_ROI1 | `has_ads_roi1` ⚠️ | 是否有 ROI1 数据（合法但单 ID 单独传时 stats 为空，需与其他广告 ID 联合请求才返回字段） |

### 负数 ID = 行业基准对比

负数 ID 是对应正数 ID 取反，表示请求该指标的**行业基准对比数据**，结果落在 `stats_benchmark_data.market_cmp_data[]`（不在 `stats` 里单独返回字段）。例如 `-11` → 在 `market_cmp_data` 中返回 `{stats_type:11, cmp:"-0.035"}`。当前场景下仅 `click_order_rate`（11）实际有对比数据，其余无。

### ✅ 验证结论：API 不受网页 16 个勾选上限约束

2026-06-15 用 `evaluate_script` 在页面上下文真实重放请求验证：

| 测试 | 传入 ID 数 | 返回字段数 | code | 结论 |
|---|---|---|---|---|
| 原始网页请求 | 35（23 正 + 12 负） | 22 | 0 | 正常 |
| 仅正数 23 个 | 23 | 22 | 0 success | 成功 |
| **全部 26 个 UI 可选指标** | **26（超过 UI 上限 16）** | **26** | **0 success** | **全部返回** |
| 含无效（乱）ID 的大集合 | 61 | 0 | 98001004 | invalid params（含非法 ID） |

**结论**：API 层面唯一校验是「stats_type ID 必须合法」，传多少返多少，无数量上限。**直接传入全集即可一次拿回全部指标，无需任何 UI 勾选逻辑**。

```python
# 推荐：一次请求拿回 35 个网页可选指标 + 5 个固定 KPI + 3 个广告辅助位 = 43 个
FULL_STATS_TYPES = [
    # Transaction（交易）7
    15, 27, 7, 344, 50, 346, 348,
    # Traffic Efficiency（流量效率）18
    71, 10, 20, 330, 29, 70, 11, 39, 43, 343, 23, 310, 325, 130, 30, 332, 323, 349,
    # Interactions（互动）8
    62, 61, 60, 331, 312, 313, 314, 315,
    # Ads（广告）2
    241, 283,
    # 主屏幕固定 KPI（非弹窗可选）5
    3, 2, 5, 18, 17,
    # 广告辅助内部位（可选）3
    290, 291, 292,
    # 负数：行业基准对比（可选，仅部分指标有数据）
    -3, -2, -7, -344, -23, -20, -18, -39, -10, -11, -70, -71,
]
```

> ⚠️ 注意：传入的每个 ID 都必须是合法枚举值，混入无效 ID 会触发 `code=98001004 invalid params` 导致整个请求失败。
>
> ✅ **§1.1 全部 35 项 + 主屏幕 5 项 KPI 的字段名均已抓包实测确认**（2026-06-15 用 `evaluate_script` 单 ID 逐个发请求验证）。唯一例外：`292 has_ads_roi1` 单 ID 单独传时 stats 为空（合法 code=0），与其他广告 ID 联合时才会携带，已在表里标注。

---

## 1.2 user/portrait 完整指标 ID 映射（三类画像一次全返回）

> 来源：2026-06-15 chrome-devtools 实时抓包 + `evaluate_script` 真实重放验证。

### 请求结构

```
POST /api/v1/insights/workbench/live/detail/user/portrait
```

```json
{
  "request": {
    "room_filter": { "room_id": "...", "is_content_type": 1 },
    "stats_types": [/* 指标 ID 数组 */]
  }
}
```

> 注意：`user/portrait` 的 `room_filter` 实测只需 `room_id` + `is_content_type`（不含 creator_id/country），与 core/stats 略有差异。

### 网页分三个 Tab，对应三类画像

| 画像类别（网页 Tab） | stats_type ID 组 |
|---|---|
| **Viewer profile**（全部观众） | 80, 81, 82, 83, 90 |
| **Customer profile**（付费客户） | 85, 86, 87, 88 |
| **Impressions profile**（曝光人群） | 350, 351, 352, 353 |

### ✅ 验证结论：三类画像可一次请求全返回

`evaluate_script` 真实重放：传入合并的 ID 一次请求，`code=0`，三类画像分布字段全部到齐。**绕过网页分 Tab 逐组请求的限制**。

### 指标 ID 映射表（单 ID 实测确认）

> 验证方法：2026-06-15 用 `evaluate_script` **逐个单独传 1 个 stats_type**，记录响应 `data.stats` 里返回的分布字段。**全部为实测确认。**

| stats_type ID | 响应字段名 | 画像类别 | 含义 |
|---|---|---|---|
| 80 | `all_gender_distribution` | Viewer | 全体观众性别分布（type 20=男/21=女/22=未知） |
| 81 | `all_fan_distribution` | Viewer | 全体观众粉丝层级分布（type 10/11/12/13） |
| 82 | `all_age_distribution` | Viewer | 全体观众年龄分布（type 3/4/5） |
| 83 | `all_state_distribution` | Viewer | 全体观众地区分布（key=省份/value=占比） |
| 90 | `country_distribution` | Viewer | 全体观众国家分布 |
| 85 | `paid_gender_distribution` | Customer | 付费客户性别分布 |
| 86 | `paid_fan_distribution` | Customer | 付费客户粉丝层级分布 |
| 87 | `paid_age_distribution` | Customer | 付费客户年龄分布 |
| 88 | `paid_state_distribution` | Customer | 付费客户地区分布 |
| 350 | `impressions_gender_distribution` | Impressions | 曝光人群性别分布 |
| 351 | `impressions_country_distribution` | Impressions | 曝光人群国家分布 |
| 352 | `impressions_age_distribution` | Impressions | 曝光人群年龄分布 |
| 353 | `impressions_state_distribution` | Impressions | 曝光人群地区分布 |

> ⚠️ **ID 89 实测无效**：单独传 `89` 时 `code=0` 但 `data.stats` 为空（不返回任何字段）。之前推断的「customer country」不成立——付费客户没有独立的国家分布字段。Customer profile 实际只有 4 个有效 ID（85/86/87/88）。

### 另一套维度：粉丝 GMV 贡献（单 ID 实测确认）

除上表三类人口画像外，`user/portrait` 还有另一组 ID（早期样本曾用 `[92,93,95,81,86]`），实测确认对应「粉丝分层的 GMV/订单/客单价贡献」维度，与人口画像**不同**：

| stats_type ID | 响应字段名 | 含义 |
|---|---|---|
| 92 | `follower_gmv_local_distribution` | 各粉丝层级 GMV 贡献（type 10/11/12/13，含 amount 金额对象） |
| 93 | `follower_sku_order_distribution` | 各粉丝层级 SKU 订单数 |
| 95 | `follower_main_aov_local_distribution` | 各粉丝层级客单价 |

> 注：旧文档曾把 `92→all_fan_distribution`、`81→follower_sku_order` 等，实测全部纠正为上表。按需求二选一或与人口画像合并提交。

### 推荐全集

```python
# 人口画像（性别/年龄/地区/国家 × 全体/付费/曝光三类）
USER_PORTRAIT_FULL = [80, 81, 82, 83, 90, 85, 86, 87, 88, 350, 351, 352, 353]
# 如需粉丝 GMV 贡献维度，再并入：92, 93, 95
```

---

## 1.3 product/list 完整指标 ID 映射（全量一次返回）

> 来源：2026-06-15 chrome-devtools 实时抓包 + `evaluate_script` 真实重放验证。

### 请求结构

```
POST /api/v1/insights/workbench/live/detail/product/list
```

```json
{
  "request": {
    "room_filter": { "room_id": "...", "is_content_type": 1 },
    "sorting_type": 1,
    "stats_types": [/* 指标 ID 数组 */]
  }
}
```

> 额外参数 `sorting_type`（排序方式，网页默认 1=GMV 降序）。

### ✅ 验证结论：全量 stats_types 一次返回

`evaluate_script` 真实重放：传入去重后的 24 个 ID，`code=0`，返回 22 个商品、每个商品携带全部指标字段。**无数量限制，一次拿回所有商品指标**。

### 指标 ID → 商品字段映射（单 ID 实测确认）

> 验证方法：2026-06-15 用 `evaluate_script` **逐个单独传 1 个 stats_type**，对比响应商品对象比基线（`id`/`name`/`cover_url`/`is_pinned`）多出的字段，从而精确锁定每个 ID 对应的字段。**全部为实测确认，非推断。**

| stats_type ID | 商品响应字段名 | 含义 | 示例值 |
|---|---|---|---|
| 4 | `is_live` | 商品是否在售 | `false` |
| 5 | `platform_type` | 平台类型 | `5` |
| 6 | `sellable_country` | 可售国家 | `"VN"` |
| 7 | `source` | 商品来源 | `"TikTok"` |
| 10 | `exposure_cnt` | 商品曝光数 / Product Impressions | `4903` |
| 15 | `click_through_rate` | 点击率 / CTR | `"0.046..."` |
| 17 | `paid_order_cnt` | 订单数 / Attributed orders | `5` |
| 18 | `paid_main_order_cnt` | SKU 订单数 / Attributed SKU orders | `8` |
| 21 | `gmv_local` | 单品 GMV（Currency 对象） | `2.621.500₫` |
| 30 | `total_click_cnt` | 商品点击数 / Product clicks | `260` |
| 35 | `click_order_rate` | 点击下单率 / CTOR | `"0.030..."` |
| 41 | `paid_user_cnt` | 付费用户数 / Customers | `5` |
| 48 | `watch_gpm_local` | 观看千次 GMV / Watch GPM | Currency |
| 51 | `inventory_left_cnt` | 剩余库存 / Available stock | `4601` |
| 55 | `payment_success_rate` | 支付成功率 / Payment rate | `"1.000000"` |
| 64 | `sellable_countries` | 可售国家列表 | 数组 |
| 120 | `add_shop_cart_cnt` | 加购数 / Added to cart | `25` |
| 301 | `main_aov_local` | 客单价 / AOV | Currency |
| 345 | `sales` | 售出件数 / Items sold | `8` |
| 1 | （单传无字段返回） | 合法但单独请求不产出指标字段 | — |
| 2 | （单传无字段返回） | 合法但单独请求不产出指标字段 | — |
| 3 | （单传无字段返回） | 合法但单独请求不产出指标字段 | — |
| 37 | （单传无字段返回） | 合法但单独请求不产出指标字段 | — |
| 350 | （单传无字段返回） | 合法但单独请求不产出指标字段 | — |

> ⚠️ ID `1/2/3/37/350` 单独传时 `code=0`（合法）但商品对象不新增任何指标字段，可能是占位/与其他 ID 重复触发同一字段。需要某字段时请用上表已锁定的 ID。
>
> 恒定返回字段（与 stats_type 无关，任意请求都带）：`id` / `name` / `cover_url` / `is_pinned`。

### 推荐全集

```python
# 实测可一次返回所有商品指标字段的有效 ID 全集
PRODUCT_LIST_FULL = [4, 5, 6, 7, 10, 15, 17, 18, 21, 30, 35, 41, 48, 51, 55, 64, 120, 301, 345]
```

---

## 1.4 trend/chart 全部可选指标 ID 列表（独立 ID 体系）

> 来源：2026-06-15 chrome-devtools 实时抓包 + `evaluate_script` 真实重放 + 页面 a11y 快照。

### 请求结构

```
POST /api/v1/insights/workbench/live/detail/trend/chart
```

```json
{
  "request": {
    "room_filter": { "room_id": "...", "is_content_type": 1 },
    "stats_types": [3, 20]
  }
}
```

> `granularity` **不在请求体内**，由服务端按直播时长自动决定（样本返回 `granularity=15`，即 15 分钟粒度）。响应含 `granularity` / `timezone_offset` / `timezone`。

### ⚠️ 关键：trend/chart 用独立 ID 体系，勿与 core/stats 混用

trend/chart 的 stats_type 数字与 core/stats / product/list **完全不是同一套编号**。例如：

| 指标 | trend/chart ID | core/stats ID |
|---|---|---|
| Viewers（观看 UV） | **20** | 18 |
| Views（观看 PV） | **11** | 20 |
| Attributed GMV | 3 | 3 |
| Items sold | **52** | 2 |

调用 trend/chart 必须用本节的 ID 表，不能套用 §1.1 的 ID。

### ✅ 验证结论：可一次传多个指标，绕过网页「每次 2 个」限制

`evaluate_script` 真实重放：传入超过 2 个 stats_types（如 `[3,20,52,41]`），`code=0`，trend_data 按传入数量返回对应条数。**网页「每次只能选 2 个」纯属前端 UI 约束，服务端无此限制。** 一次传全部 27 个合法 ID 即可返回全部趋势序列。

### 全部 27 个可选指标（按网页分组，已人工核实）

> 来源：在网页 Performance trends 趋势图指标下拉中逐个核实，**全部 27 个 ID 与名称为人工锁定**，非推断。

#### Transaction（交易）

| trend ID | 指标名称 | 数据格式 |
|---|---|---|
| 3 | Attributed GMV | `amount` 金额对象 |
| 52 | Attributed items sold | `amount` |
| 82 | Customers | `value` 计数 |
| 41 | Attributed SKU orders | `amount` |
| 344 | Attributed orders | `amount` |

#### Traffic Efficiency（流量效率）

| trend ID | 指标名称 | 数据格式 |
|---|---|---|
| 20 | Viewers | `value` 计数 |
| 11 | Views | `value` 计数 |
| 50 | Product Impressions | `value` 计数 |
| 14 | LIVE CTR | `value` 小数率 |
| 84 | Tap-through rate | `value` 小数率 |
| 51 | Product Clicks | `value` 计数 |
| 92 | Impressions | `value` 计数 |

#### Interactions（互动）

| trend ID | 指标名称 | 数据格式 |
|---|---|---|
| 23 | New followers | `value` 计数 |
| 13 | Shares | `value` 计数 |
| 12 | Comments | `value` 计数 |
| 16 | Likes | `value` 计数 |
| 312 | Comment rate | `value` 小数 |
| 313 | Follow rate | `value` 小数 |
| 314 | Like rate | `value` 小数 |
| 315 | Share rate | `value` 小数 |

#### Conversion（转化）

| trend ID | 指标名称 | 数据格式 |
|---|---|---|
| 401 | AOV | `value` |
| 15 | CTOR (SKU orders) | `value` 小数率 |
| 91 | Watch GPM | `value` 小数 |
| 343 | CTOR | `value` 小数率 |
| 350 | Payment Rate | `value` 小数率 |
| 81 | Show GPM | `amount` 金额对象 |
| 323 | Order rate (SKU orders) | `value` 小数率 |

### 已确认合法 ID 全集（共 27 个）

```python
TREND_CHART_FULL = [
    # Transaction
    3, 52, 82, 41, 344,
    # Traffic Efficiency
    20, 11, 50, 14, 84, 51, 92,
    # Interactions
    23, 13, 12, 16, 312, 313, 314, 315,
    # Conversion
    401, 15, 91, 343, 350, 81, 323,
]
# 一次传全集即可拿回全部 27 条趋势序列；或按需挑选子集
```

---

## 2. 数据完整性评估

### 已覆盖核心数据需求

| 大屏模块 | 覆盖情况 | 覆盖 API |
|---------|---------|---------|
| ✅ 核心指标卡片（GMV/观众/订单/转化率） | **完整** | `06-core-stats` |
| ✅ 性能趋势图（多指标时间曲线） | **完整** | `08-trend-chart`（15 分钟粒度，本批一次拉 27 个指标） |
| ✅ 历史趋势对比（市场/自身对比） | **完整** | `06-core-stats` 的 `stats_benchmark_data` |
| ✅ 流量来源分析 | **完整** | `03-source-new`（2026-06-11 旧批，本次未重采） |
| ✅ 观众画像-粉丝分层 | **完整** | `04all-user-portrait`（Viewer 组 `80,81,82,83,90`） |
| ✅ 观众画像-人群（性别/年龄/地区） | **完整** | `04all-user-portrait`（Customer 组 `85,86,87,88` + Impressions 组 `350-353`） |
| ✅ 商品列表与明细 | **完整** | `05-product-list` |

---

## 3. 已补充 API + 待验证清单

### ✅ 本批重采（2026-06-15，collection_id=k19f2q44 越南团队）

| API | 路径 | 状态 |
|-----|------|------|
| 核心指标 | `/api/v1/insights/workbench/live/detail/core/stats` | ✅ **真实请求验证**，一次传 55 个 stats_types（43 正+12 负）返回 41 个字段 + benchmark |
| 商品列表 | `/api/v1/insights/workbench/live/detail/product/list` | ✅ **真实请求验证**，19 个 stats_types 返回 22 个商品 + `sold_product` 汇总 |
| 性能趋势图 | `/api/v1/insights/workbench/live/detail/trend/chart` | ✅ **真实请求验证**，一次传 27 个指标返回 27 条 15 分钟粒度序列 |
| 观众画像（三类合并） | `/api/v1/insights/workbench/live/detail/user/portrait` | ✅ **真实请求验证**，13 个 ID 一次返回 Viewer/Customer/Impressions 三类全部分布 |

> ⚠️ `03-source-new` 为 2026-06-11 旧批样本，本次未重采；其字段以旧样本为准。

---

## 4. 采集实现优先级

| 优先级 | API | 实现建议 |
|-------|-----|---------|
| **P0** | `06-core-stats` | 立即实现，覆盖核心指标卡片 + 历史/市场对比 |
| **P0** | `05-product-list` | ✅ **已抓包**，商品列表是核心诉求，包含单品完整转化漏斗 |
| **P1** | `08-trend-chart` | ✅ **已抓包**，性能趋势曲线（一次传 27 个指标，15 分钟粒度） |
| **P1** | `03-source-new` | 流量归因分析，辅助运营优化（2026-06-11 旧批） |
| **P1** | `04all-user-portrait` | ✅ **已抓包**，三类画像（Viewer/Customer/Impressions）一次 13 个 ID 全返回 |

---

## 5. MVP 可验证范围

现有 **5 对 API 样本**（覆盖 5 个业务接口，user/portrait 三类画像已合并为一次请求）已可构建直播大屏 MVP：

- **顶部卡片**：`06-core-stats` 的 `gmv_local`、`sales`、`watch_uv`、`click_through_rate`
- **性能趋势图**：`08-trend-chart` 一次 27 个指标的 15 分钟粒度时间序列
- **历史趋势对比**：`06-core-stats.stats_benchmark_data.market_cmp_data[]`
- **流量分析**：`03-source-new` 饼图/柱状图（2026-06-11 旧批）
- **观众画像**：`04all-user-portrait` 一次返回 Viewer/Customer/Impressions 三类（性别/年龄/地区/国家 + 粉丝层级）
- **商品列表**：`05-product-list` 商品表格（GMV/销量/库存/点击率/加购数）+ `sold_product` 汇总

**覆盖范围**：核心指标、趋势、流量、观众画像与商品明细。

---

## 6. 原始样本文件清单

| 编号 | 文件名 | 对应区域 |
|------|--------|---------|
| 03 | `raw/03-source-new.*` | ④ Traffic source（2026-06-11 旧批，未重采） |
| 04all | `raw/04all-user-portrait.*` | ⑥ Follower analytics + ⑦ User profile（三类画像合并，`stats_types=[80,81,82,83,90,85,86,87,88,350,351,352,353]`） |
| 05 | `raw/05-product-list.*` | ⑤ Product List |
| 06 | `raw/06-core-stats.*` | ② 核心指标卡片 |
| 08 | `raw/08-trend-chart.*` | ① Performance trends |

> 本批（04all/05/06/08）采集上下文：collection_id=`k19f2q44` 越南团队，room_id=`7651420995556182804`，请求脚本见 scratches/`TK-越南团队实时直播测试-k19f2q44`。
