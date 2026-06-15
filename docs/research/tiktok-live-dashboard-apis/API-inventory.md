# TikTok 直播大屏 API 采集目录

## 1. API 样本分析表

| API 编号 | 接口名称 | URL 路径 | 请求参数 | 响应核心字段 | 业务含义 | 对应页面区域 |
|---------|---------|---------|---------|------------|---------|------------|
| **03** | source/new | `/api/v3/insights/workbench/live/detail/source/new` | `room_id`<br>`is_content_type`<br>`stats_types=[100]`<br>`version=3` | `stats.all_traffic_distribution[]` (流量来源分布)<br>- `main_source` (一级来源)<br>- `detail_source[]` (二级来源)<br>- 包含：`watch_pv` `ctr` `co` `gmv_usd` `gmv_local` `enter_room_rate` `show_gpm_usd` `show_gpm_local` | 流量来源分析，支持二级细分。包含各来源 GMV、转化率、进房率、千次曝光 GMV | **④ Traffic source**（左中，Channel/Attributed GMV/Impressions/Views 多级来源表） |
| **04** | user/portrait（粉丝分层） | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_id`<br>`is_content_type`<br>**`stats_types=[92,93,95,81,86]`** | `stats.all_fan_distribution[]` (粉丝分布，type 10/11/12/13)<br>`stats.paid_fan_distribution[]` (付费粉丝分布)<br>`stats.follower_gmv_local_distribution[]` (粉丝 GMV 分布)<br>`stats.follower_sku_order_distribution[]` (粉丝订单分布)<br>`stats.follower_main_aov_local_distribution[]` (粉丝客单价分布) | 观众画像-**粉丝维度**，按粉丝层级统计人数、订单、GMV、客单价 | **⑥ Follower analytics**（左下，新粉/老粉/非粉占比 + 各层 GMV/订单/客单价）<br>样本：`raw/04-user-portrait.*` |
| **04b** | user/portrait（人群画像） | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_id`<br>`is_content_type`<br>**`stats_types=[85,86,87,88,89]`** | `stats.paid_gender_distribution[]` (性别分布，type 20=男/21=女/22=未知)<br>`stats.paid_age_distribution[]` (年龄分布，type 3/4/5)<br>`stats.paid_state_distribution[]` (地区分布，key=省份/value=占比)<br>`stats.paid_fan_distribution[]` (付费粉丝分布) | 观众画像-**人群维度**，按性别/年龄/地区统计付费用户分布 | **⑦ User profile**（右下，Gender/Age/Region 用户画像）<br>样本：`raw/04b-user-portrait.*` |
| **05** | product/list | `/api/v1/insights/workbench/live/detail/product/list` | `room_id`<br>`is_content_type`<br>`sorting_type` (排序：1=GMV降序)<br>`stats_types` (17个商品指标ID) | **商品列表**（每个商品包含）：<br>- `id` / `name` / `cover_url` (商品ID/名称/封面)<br>- `gmv_local` (单品 GMV)<br>- `sales` (销量)<br>- `exposure_cnt` (曝光数)<br>- `click_through_rate` (点击率)<br>- `click_order_rate` (点击下单率)<br>- `main_aov_local` (客单价)<br>- `inventory_left_cnt` (剩余库存)<br>- `add_shop_cart_cnt` (加购数)<br>- `is_pinned` (是否置顶)<br>- `is_live` (是否在售)<br>**汇总指标**：<br>- `sold_product` (售出商品种类数) | **商品维度详细数据**，支持按 GMV/销量/点击率等排序，包含单品完整转化漏斗 | **⑤ Product List**（中下，Product/Attributed GMV/Product Impressions/CTR/Added to cart 表格） |
| **06** | core/stats | `/api/v1/insights/workbench/live/detail/core/stats` | `room_id`<br>`is_content_type`<br>`creator_id`<br>`country`<br>`stats_types` (33个指标ID) | **核心指标**：<br>- `gmv_local` (总 GMV)<br>- `sales` (销量)<br>- `current_visitor_cnt` (在线人数)<br>- `click_through_rate` (点击率)<br>- `click_order_rate` (点击下单率)<br>- `main_aov_local` (客单价)<br>- `watch_uv` / `watch_pv` (观看 UV/PV)<br>- `avg_view_duration` (平均观看时长)<br>- `accumulated_new_follower_cnt` (新增粉丝)<br>- `product_click_rate` (商品点击率)<br>- `show_pv_per_hour` / `gmv_local_per_hour` (时均曝光/GMV)<br>**benchmark 对比**：<br>- `market_cmp_data[]` (市场对比)<br>- `self_cmp_data[]` (历史对比) | **最核心 API**，包含大屏所有关键指标：GMV、销量、流量、转化、粉丝、广告 ROI。提供市场/历史趋势对比 | **② 核心指标卡片**（中央大红框，Attributed GMV/items sold/Current viewers/Ads Cost/Views/Impressions per hour/Avg viewing duration/Follow rate/Tap-through rate/LIVE CTR） |
| **08** | trend/chart | `/api/v1/insights/workbench/live/detail/trend/chart` | `room_id`<br>`is_content_type`<br>`stats_types=[20,3]` (20=Viewers, 3=GMV) | `trend_data[]`（每条对应一个 `stats_type`）：<br>- `stats_type=20`：`data[]` 中 `key`=时间戳 / `value`=在线人数<br>- `stats_type=3`：`data[]` 中 `key`=时间戳 / `amount`=GMV 金额对象<br>`granularity` (5=5分钟粒度)<br>`timezone_offset` / `timezone` | 性能趋势曲线，按 5 分钟粒度聚合在线人数与 GMV。样本含 22 个时间点 | **① Performance trends**（左上，Viewers + Attributed GMV 双线趋势图）<br>样本：`raw/08-trend-chart.*` |

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
