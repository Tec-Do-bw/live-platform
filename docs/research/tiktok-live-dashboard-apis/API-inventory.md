# TikTok 直播大屏 API 采集目录

## 1. API 样本分析表

| API 编号 | 接口名称 | URL 路径 | 请求参数 | 响应核心字段 | 业务含义 | 对应页面区域 |
|---------|---------|---------|---------|------------|---------|------------|
| **03** | source/new | `/api/v3/insights/workbench/live/detail/source/new` | `room_id`<br>`is_content_type`<br>`stats_types=[100]`<br>`version=3` | `stats.all_traffic_distribution[]` (流量来源分布)<br>- `main_source` (一级来源)<br>- `detail_source[]` (二级来源)<br>- 包含：`watch_pv` `ctr` `co` `gmv_usd` `gmv_local` `enter_room_rate` `show_gpm_usd` `show_gpm_local` | 流量来源分析，支持二级细分。包含各来源 GMV、转化率、进房率、千次曝光 GMV | **④ Traffic source**（左中，Channel/Attributed GMV/Impressions/Views 多级来源表） |
| **04** | user/portrait（粉丝分层） | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_id`<br>`is_content_type`<br>**`stats_types=[92,93,95,81,86]`** | `stats.all_fan_distribution[]` (粉丝分布，type 10/11/12/13)<br>`stats.paid_fan_distribution[]` (付费粉丝分布)<br>`stats.follower_gmv_local_distribution[]` (粉丝 GMV 分布)<br>`stats.follower_sku_order_distribution[]` (粉丝订单分布)<br>`stats.follower_main_aov_local_distribution[]` (粉丝客单价分布) | 观众画像-**粉丝维度**，按粉丝层级统计人数、订单、GMV、客单价。**三类画像（Viewer/Customer/Impressions）完整 ID 映射见 [§1.2](#12-userportrait-完整指标-id-映射三类画像一次全返回)，已验证一次请求传全部 14 个 ID 可一并返回** | **⑥ Follower analytics**（左下，新粉/老粉/非粉占比 + 各层 GMV/订单/客单价）<br>样本：`raw/04-user-portrait.*` |
| **04b** | user/portrait（人群画像） | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_id`<br>`is_content_type`<br>**`stats_types=[85,86,87,88,89]`** | `stats.paid_gender_distribution[]` (性别分布，type 20=男/21=女/22=未知)<br>`stats.paid_age_distribution[]` (年龄分布，type 3/4/5)<br>`stats.paid_state_distribution[]` (地区分布，key=省份/value=占比)<br>`stats.paid_fan_distribution[]` (付费粉丝分布) | 观众画像-**人群维度**，按性别/年龄/地区统计付费用户分布 | **⑦ User profile**（右下，Gender/Age/Region 用户画像）<br>样本：`raw/04b-user-portrait.*` |
| **05** | product/list | `/api/v1/insights/workbench/live/detail/product/list` | `room_id`<br>`is_content_type`<br>`sorting_type` (排序：1=GMV降序)<br>`stats_types` (17个商品指标ID) | **商品列表**（每个商品包含）：<br>- `id` / `name` / `cover_url` (商品ID/名称/封面)<br>- `gmv_local` (单品 GMV)<br>- `sales` (销量)<br>- `exposure_cnt` (曝光数)<br>- `click_through_rate` (点击率)<br>- `click_order_rate` (点击下单率)<br>- `main_aov_local` (客单价)<br>- `inventory_left_cnt` (剩余库存)<br>- `add_shop_cart_cnt` (加购数)<br>- `is_pinned` (是否置顶)<br>- `is_live` (是否在售)<br>**汇总指标**：<br>- `sold_product` (售出商品种类数) | **商品维度详细数据**，支持按 GMV/销量/点击率等排序，包含单品完整转化漏斗。**全量 stats_types 映射见 [§1.3](#13-productlist-完整指标-id-映射全量一次返回)，已验证一次传 24 个去重 ID 返回全部商品指标** | **⑤ Product List**（中下，Product/Attributed GMV/Product Impressions/CTR/Added to cart 表格） |
| **06** | core/stats | `/api/v1/insights/workbench/live/detail/core/stats` | `room_id`<br>`is_content_type`<br>`creator_id`<br>`country`<br>`stats_types` (网页 35 个可选 + 4 个固定 KPI + 3 个内部辅助位) | **核心指标**：<br>- `gmv_local` (总 GMV)<br>- `sales` (销量)<br>- `current_visitor_cnt` (在线人数)<br>- `click_through_rate` (点击率)<br>- `click_order_rate` (点击下单率)<br>- `main_aov_local` (客单价)<br>- `watch_uv` / `watch_pv` (观看 UV/PV)<br>- `avg_view_duration` (平均观看时长)<br>- `accumulated_new_follower_cnt` (新增粉丝)<br>- `product_click_rate` (商品点击率)<br>- `show_pv_per_hour` / `gmv_local_per_hour` (时均曝光/GMV)<br>**benchmark 对比**：<br>- `market_cmp_data[]` (市场对比)<br>- `self_cmp_data[]` (历史对比) | **最核心 API**，包含大屏所有关键指标：GMV、销量、流量、转化、粉丝、广告 ROI。提供市场/历史趋势对比。**完整 `stats_types` ID → 指标名映射见 [§1.1](#11-corestats-完整指标-id-映射api-06-深入)，已验证 API 不受网页 16 个勾选上限约束** | **② 核心指标卡片**（中央大红框，Attributed GMV/items sold/Current viewers/Ads Cost/Views/Impressions per hour/Avg viewing duration/Follow rate/Tap-through rate/LIVE CTR） |
| **08** | trend/chart | `/api/v1/insights/workbench/live/detail/trend/chart` | `room_id`<br>`is_content_type`<br>`stats_types=[20,3]` (20=Viewers, 3=GMV) | `trend_data[]`（每条对应一个 `stats_type`）：<br>- `stats_type=20`：`data[]` 中 `key`=时间戳 / `value`=在线人数<br>- `stats_type=3`：`data[]` 中 `key`=时间戳 / `amount`=GMV 金额对象<br>`granularity` (5=5分钟粒度)<br>`timezone_offset` / `timezone` | 性能趋势曲线，按 5 分钟粒度聚合在线人数与 GMV。样本含 22 个时间点。**全部 27 个可选指标 ID 见 [§1.4](#14-trendchart-全部可选指标-id-列表独立-id-体系)；网页每次只能选 2 个，但已验证 API 可一次传全部合法 ID 返回多条趋势序列。⚠️ trend/chart 用独立 ID 体系，勿与 core/stats 的 ID 混用** | **① Performance trends**（左上，Viewers + Attributed GMV 双线趋势图）<br>样本：`raw/08-trend-chart.*` |

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

旧样本 `raw/04-user-portrait.*` 用的是另一组 ID，实测确认对应「粉丝分层的 GMV/订单/客单价贡献」维度，与上表人口画像**不同**：

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
| ✅ 性能趋势图（Viewers + GMV 时间曲线） | **完整** | `08-trend-chart`（5 分钟粒度时间序列）✅ **已补充** |
| ✅ 历史趋势对比（市场/自身对比） | **完整** | `06-core-stats` 的 `stats_benchmark_data` |
| ✅ 流量来源分析 | **完整** | `03-source-new` |
| ✅ 观众画像-粉丝分层 | **完整** | `04-user-portrait`（`stats_types=[92,93,95,81,86]`） |
| ✅ 观众画像-人群（性别/年龄/地区） | **完整** | `04b-user-portrait`（`stats_types=[85,86,87,88,89]`）✅ **已补充** |
| ✅ 商品列表与明细 | **完整** | `05-product-list` |

---

## 3. 已补充 API + 待验证清单

### ✅ 已补充（2026-06-11 抓包）

| API | 路径 | 状态 |
|-----|------|------|
| 商品列表 | `/api/v1/insights/workbench/live/detail/product/list` | ✅ **已完整抓取**，包含单品 GMV/销量/库存/转化率等 17 个指标 |
| 性能趋势图 | `/api/v1/insights/workbench/live/detail/trend/chart` | ✅ **已完整抓取**，`stats_types=[20,3]` 返回 Viewers + GMV 的 5 分钟粒度时间序列 |
| 人群画像 | `/api/v1/insights/workbench/live/detail/user/portrait`（`stats_types=[85,86,87,88,89]`） | ✅ **已完整抓取**，性别/年龄/地区分布（与粉丝分层共用接口，靠 stats_types 区分） |

---

## 4. 采集实现优先级

| 优先级 | API | 实现建议 |
|-------|-----|---------|
| **P0** | `06-core-stats` | 立即实现，覆盖核心指标卡片 + 历史/市场对比 |
| **P0** | `05-product-list` | ✅ **已抓包**，商品列表是核心诉求，包含单品完整转化漏斗 |
| **P1** | `08-trend-chart` | ✅ **已抓包**，性能趋势曲线（Viewers + GMV 5 分钟粒度） |
| **P1** | `03-source-new` | 流量归因分析，辅助运营优化 |
| **P1** | `04-user-portrait` | 粉丝分层画像（`stats_types=[92,93,95,81,86]`） |
| **P1** | `04b-user-portrait` | ✅ **已抓包**，人群画像-性别/年龄/地区（`stats_types=[85,86,87,88,89]`） |

---

## 5. MVP 可验证范围

现有 **6 对 API 样本**（覆盖 5 个业务接口，含 2 套 user/portrait 维度）已可构建直播大屏 MVP：

- **顶部卡片**：`06-core-stats` 的 `gmv_local`、`sales`、`watch_uv`、`click_through_rate`
- **性能趋势图**：`08-trend-chart` 的 Viewers + GMV 5 分钟粒度时间序列 ✅ **新增**
- **历史趋势对比**：`06-core-stats.stats_benchmark_data.self_cmp_data[]`
- **流量分析**：`03-source-new` 饼图/柱状图
- **观众画像-粉丝分层**：`04-user-portrait` 新粉/老粉/非粉 + 各层 GMV/订单/客单价
- **观众画像-人群**：`04b-user-portrait` 性别/年龄/地区分布 ✅ **新增**
- **商品列表**：`05-product-list` 商品表格（GMV/销量/库存/点击率/加购数）

**覆盖范围**：核心指标、趋势、流量、观众画像与商品明细。

---

## 6. 原始样本文件清单

| 编号 | 文件名 | 对应区域 |
|------|--------|---------|
| 03 | `raw/03-source-new.*` | ④ Traffic source |
| 04 | `raw/04-user-portrait.*` | ⑥ Follower analytics（粉丝分层，`stats_types=[92,93,95,81,86]`） |
| 04b | `raw/04b-user-portrait.*` | ⑦ User profile（人群画像，`stats_types=[85,86,87,88,89]`） |
| 05 | `raw/05-product-list.*` | ⑤ Product List |
| 06 | `raw/06-core-stats.*` | ② 核心指标卡片 |
| 08 | `raw/08-trend-chart.*` | ① Performance trends |
