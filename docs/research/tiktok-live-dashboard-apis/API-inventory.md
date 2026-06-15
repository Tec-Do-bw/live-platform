# TikTok 直播大屏 API 采集目录

## 1. API 样本分析表

| API 编号 | 接口名称 | URL 路径 | 请求参数 | 响应核心字段 | 业务含义 | 对应页面区域 |
|---------|---------|---------|---------|------------|---------|------------|
| **03** | source/new | `/api/v3/insights/workbench/live/detail/source/new` | `room_id`<br>`is_content_type`<br>`stats_types=[100]`<br>`version=3` | `stats.all_traffic_distribution[]` (流量来源分布)<br>- `main_source` (一级来源)<br>- `detail_source[]` (二级来源)<br>- 包含：`watch_pv` `ctr` `co` `gmv_usd` `gmv_local` `enter_room_rate` `show_gpm_usd` `show_gpm_local` | 流量来源分析，支持二级细分。包含各来源 GMV、转化率、进房率、千次曝光 GMV | **④ Traffic source**（左中，Channel/Attributed GMV/Impressions/Views 多级来源表） |
| **04** | user/portrait（粉丝分层） | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_id`<br>`is_content_type`<br>**`stats_types=[92,93,95,81,86]`** | `stats.all_fan_distribution[]` (粉丝分布，type 10/11/12/13)<br>`stats.paid_fan_distribution[]` (付费粉丝分布)<br>`stats.follower_gmv_local_distribution[]` (粉丝 GMV 分布)<br>`stats.follower_sku_order_distribution[]` (粉丝订单分布)<br>`stats.follower_main_aov_local_distribution[]` (粉丝客单价分布) | 观众画像-**粉丝维度**，按粉丝层级统计人数、订单、GMV、客单价 | **⑥ Follower analytics**（左下，新粉/老粉/非粉占比 + 各层 GMV/订单/客单价）<br>样本：`raw/04-user-portrait.*` |
| **04b** | user/portrait（人群画像） | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_id`<br>`is_content_type`<br>**`stats_types=[85,86,87,88,89]`** | `stats.paid_gender_distribution[]` (性别分布，type 20=男/21=女/22=未知)<br>`stats.paid_age_distribution[]` (年龄分布，type 3/4/5)<br>`stats.paid_state_distribution[]` (地区分布，key=省份/value=占比)<br>`stats.paid_fan_distribution[]` (付费粉丝分布) | 观众画像-**人群维度**，按性别/年龄/地区统计付费用户分布 | **⑦ User profile**（右下，Gender/Age/Region 用户画像）<br>样本：`raw/04b-user-portrait.*` |
| **05** | product/list | `/api/v1/insights/workbench/live/detail/product/list` | `room_id`<br>`is_content_type`<br>`sorting_type` (排序：1=GMV降序)<br>`stats_types` (17个商品指标ID) | **商品列表**（每个商品包含）：<br>- `id` / `name` / `cover_url` (商品ID/名称/封面)<br>- `gmv_local` (单品 GMV)<br>- `sales` (销量)<br>- `exposure_cnt` (曝光数)<br>- `click_through_rate` (点击率)<br>- `click_order_rate` (点击下单率)<br>- `main_aov_local` (客单价)<br>- `inventory_left_cnt` (剩余库存)<br>- `add_shop_cart_cnt` (加购数)<br>- `is_pinned` (是否置顶)<br>- `is_live` (是否在售)<br>**汇总指标**：<br>- `sold_product` (售出商品种类数) | **商品维度详细数据**，支持按 GMV/销量/点击率等排序，包含单品完整转化漏斗 | **⑤ Product List**（中下，Product/Attributed GMV/Product Impressions/CTR/Added to cart 表格） |
| **06** | core/stats | `/api/v1/insights/workbench/live/detail/core/stats` | `room_id`<br>`is_content_type`<br>`creator_id`<br>`country`<br>`stats_types` (33个指标ID) | **核心指标**：<br>- `gmv_local` (总 GMV)<br>- `sales` (销量)<br>- `current_visitor_cnt` (在线人数)<br>- `click_through_rate` (点击率)<br>- `click_order_rate` (点击下单率)<br>- `main_aov_local` (客单价)<br>- `watch_uv` / `watch_pv` (观看 UV/PV)<br>- `avg_view_duration` (平均观看时长)<br>- `accumulated_new_follower_cnt` (新增粉丝)<br>- `product_click_rate` (商品点击率)<br>- `show_pv_per_hour` / `gmv_local_per_hour` (时均曝光/GMV)<br>**benchmark 对比**：<br>- `market_cmp_data[]` (市场对比)<br>- `self_cmp_data[]` (历史对比) | **最核心 API**，包含大屏所有关键指标：GMV、销量、流量、转化、粉丝、广告 ROI。提供市场/历史趋势对比。**完整 `stats_types` ID → 指标名映射见 [§1.1](#11-corestats-完整指标-id-映射api-06-深入)，已验证 API 不受网页 16 个勾选上限约束** | **② 核心指标卡片**（中央大红框，Attributed GMV/items sold/Current viewers/Ads Cost/Views/Impressions per hour/Avg viewing duration/Follow rate/Tap-through rate/LIVE CTR） |
| **08** | trend/chart | `/api/v1/insights/workbench/live/detail/trend/chart` | `room_id`<br>`is_content_type`<br>`stats_types=[20,3]` (20=Viewers, 3=GMV) | `trend_data[]`（每条对应一个 `stats_type`）：<br>- `stats_type=20`：`data[]` 中 `key`=时间戳 / `value`=在线人数<br>- `stats_type=3`：`data[]` 中 `key`=时间戳 / `amount`=GMV 金额对象<br>`granularity` (5=5分钟粒度)<br>`timezone_offset` / `timezone` | 性能趋势曲线，按 5 分钟粒度聚合在线人数与 GMV。样本含 22 个时间点 | **① Performance trends**（左上，Viewers + Attributed GMV 双线趋势图）<br>样本：`raw/08-trend-chart.*` |

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

按网页 UI 的 4 个分组整理。

#### 分组一：交易（Giao dịch）

| stats_type ID | 枚举常量 | 响应字段名 | 网页显示名 | 类型/示例 |
|---|---|---|---|---|
| 3 | LIVE_DETAIL_GMV_LOCAL | `gmv_local` | Attributed GMV | Currency，`amount="14111400"` VND |
| 2 | LIVE_DETAIL_SALES | `sales` | Items sold | 整数，`58` |
| 7 | LIVE_DETAIL_PAID_ORDER_CNT | `paid_order_cnt` | Attributed SKU Orders | 整数，`58` |
| 344 | LIVE_DETAIL_MAIN_ORDER_CNT | `main_order_cnt` | Attributed Orders | 整数，`37` |
| 15 | LIVE_DETAIL_MAIN_AOV_LOCAL | `main_aov_local` | AOV | Currency |
| 17 | LIVE_DETAIL_SKU_AOV_LOCAL | `sku_aov_local` | AOV (SKU) | Currency |
| 27 | LIVE_DETAIL_PAID_USER_CNT | `paid_user_cnt` | Customers | 整数 |
| 346 | LIVE_DETAIL_EST_GMV_LOCAL | `est_gmv_local` | Est. GMV | Currency（已抓包实测确认） |
| 348 | LIVE_DETAIL_WITH_SUBSIDY_GMV_LOCAL | `with_subsidy_gmv_local` | GMV with subsidy | Currency |

#### 分组二：流量效率（Hiệu quả lưu lượng）

| stats_type ID | 枚举常量 | 响应字段名 | 网页显示名 | 类型/示例 |
|---|---|---|---|---|
| 23 | LIVE_DETAIL_CLIENT_SHOW_CNT | `client_show_cnt` | Impressions | 整数，`101688` |
| 310 | LIVE_DETAIL_SHOW_PV_PER_HOUR | `show_pv_per_hour` | Impressions per hour | 整数，`12628` |
| 18 | LIVE_DETAIL_WATCH_UV | `watch_uv` | Viewers | 整数，`2038` |
| 20 | LIVE_DETAIL_WATCH_PV | `watch_pv` | Views | 整数，`2976` |
| 30 | LIVE_DETAIL_AVG_WATCHING_TIME | `avg_watching_time` | Avg. watch time | 整数（秒），`64` |
| 5 | LIVE_DETAIL_CURRENT_VISITOR_CNT | `current_visitor_cnt` | Current viewers | 整数，`11` |
| 10 | LIVE_DETAIL_CLICK_THROUGH_RATE | `click_through_rate` | LIVE CTR | 比例字符串，`"0.428"` |
| 11 | LIVE_DETAIL_CLICK_ORDER_RATE | `click_order_rate` | CTOR | 比例字符串，`"0.045"` |
| 72 | LIVE_DETAIL_PRODUCT_CLICK_RATE | `product_click_rate` | Product CTR | 比例字符串，`"0.0506"` |
| 70 | LIVE_DETAIL_PRODUCT_VIEW_CNT | `product_view_cnt` | Product impressions | 整数，`25157` |
| 71 | LIVE_DETAIL_PRODUCT_REACH_CNT | `product_reach_cnt` | Product clicks | 整数，`1275` |
| 39 | LIVE_DETAIL_LIVE_SHOW_GPM_LOCAL | `live_show_gpm_local` | Show GPM | Currency，`"138772"` VND |
| 325 | LIVE_DETAIL_GMV_LOCAL_PER_HOUR | `gmv_local_per_hour` | GMV per hour | Currency，`"1752425"` VND |
| 332 | LIVE_DETAIL_ENTER_ROOM_RATE_LIVE_PREVIEW | `enter_room_rate_live_preview` | Enter rate (via LIVE preview) | 比例字符串，`"0.0267"` |
| 349 | LIVE_DETAIL_WATCH_PV_ONE_MIN_PLUS | `watch_pv_one_min_plus` | Views >1 min | 整数 |

#### 分组三：互动（Tương tác）

| stats_type ID | 枚举常量 | 响应字段名 | 网页显示名 | 类型/示例 |
|---|---|---|---|---|
| 62 | LIVE_DETAIL_ACCUMULATED_NEW_FOLLOWER_CNT | `accumulated_new_follower_cnt` | New followers | 整数 |
| 61 | LIVE_DETAIL_ACCUMULATED_SHARING_CNT | `accumulated_sharing_cnt` | Shares | 整数 |
| 60 | LIVE_DETAIL_ACCUMULATED_COMMENT_CNT | `accumulated_comment_cnt` | Comments | 整数 |
| 331 | LIVE_DETAIL_LIKES | `likes` | Likes | 整数 |
| 312 | LIVE_DETAIL_LIVE_COMMENT_RATE | `live_comment_rate` | Comment rate | 比例字符串 |
| 313 | LIVE_DETAIL_LIVE_FOLLOW_RATE | `live_follow_rate` | Follow rate | 比例字符串 |
| 314 | LIVE_DETAIL_LIVE_LIKE_RATE | `live_like_rate` | Like rate | 比例字符串 |
| 315 | LIVE_DETAIL_LIVE_SHARE_RATE | `live_share_rate` | Share rate | 比例字符串 |

#### 分组四：广告（Quảng cáo）

| stats_type ID | 枚举常量 | 响应字段名 | 网页显示名 | 类型/示例 |
|---|---|---|---|---|
| 241 | LIVE_DETAIL_ADS_COST_LOCAL | `ads_cost_local` | Ad spend | Currency，`"2502344"` VND |
| 283 | LIVE_DETAIL_ADS_GMV_MAX_ROI | `ads_gmv_max_roi` | ROI GMV Max | 浮点数，`6.648` |
| 290 | LIVE_DETAIL_ADS_IS_ROI2 | `is_ads_roi2` | （内部标志位） | 布尔，`true` |
| 291 | LIVE_DETAIL_ADS_ROI2_EFFECTIVE_TIME | `ads_roi2_effective_time` | （内部时间戳） | 时间戳，`1781514000` |
| 292 | LIVE_DETAIL_HAS_ADS_ROI1 | `has_ads_roi1` | （内部标志位） | 布尔 |

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
# 推荐：一次请求拿回全部核心指标（省掉 UI 勾选）
FULL_STATS_TYPES = [
    # 交易
    3, 2, 7, 344, 15, 17, 27, 346, 348,
    # 流量效率
    23, 310, 18, 20, 30, 5, 10, 11, 72, 70, 71, 39, 325, 332, 349,
    # 互动
    62, 61, 60, 331, 312, 313, 314, 315,
    # 广告
    241, 283, 290, 291, 292,
    # 负数：行业基准对比（可选）
    -3, -2, -7, -344, -23, -20, -18, -39, -10, -11, -70, -71,
]
```

> ⚠️ 注意：传入的每个 ID 都必须是合法枚举值，混入无效 ID 会触发 `code=98001004 invalid params` 导致整个请求失败。

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
