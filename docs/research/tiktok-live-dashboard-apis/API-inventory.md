# TikTok 直播大屏 API 采集目录

## 1. API 样本分析表

| API 编号 | 接口名称 | URL 路径 | 请求参数 | 响应核心字段 | 业务含义 | 对应页面区域 |
|---------|---------|---------|---------|------------|---------|------------|
| **01** | room/status | `/api/v1/insights/workbench/live/detail/room/status` | `room_id`<br>`is_content_type` | `status` (房间状态)<br>`duration` (直播时长秒)<br>`ended_at` (结束时间戳)<br>`replay_url` (回放链接) | 直播间状态与回放信息。`status=3` 表示已结束，包含总时长和 m3u8 回放地址 | 顶部 **Duration**（`4 hr, 56 min, 40 sec`）+ 直播起止时间 |
| **02** | event/timeline | `/api/v1/insights/workbench/live/detail/event/timeline` | `room_id`<br>`is_content_type`<br>`language` | `events[]` (事件列表)<br>- `event_type` (类型，2=置顶商品)<br>- `start_timestamp` / `end_timestamp`<br>- `pin_product_event` (商品信息：ID、名称、图片) | 直播事件时间线，记录主播操作（如商品置顶）。可还原主播推品节奏 | 商品列表中的 **Pinned 置顶标记**（推品时间节点） |
| **03** | source/new | `/api/v3/insights/workbench/live/detail/source/new` | `room_id`<br>`is_content_type`<br>`stats_types=[100]`<br>`version=3` | `all_traffic_distribution[]` (流量来源分布)<br>- `main_source` (一级来源)<br>- `detail_source[]` (二级来源)<br>- 包含：`watch_pv` `ctr` `co` `gmv_usd` `gmv_local` `enter_room_rate` `show_gpm_usd` `show_gpm_local` | 流量来源分析，支持二级细分。包含各来源 GMV、转化率、进房率、千次曝光 GMV | **④ Traffic source**（左中，Channel/Attributed GMV/Impressions/Views 多级来源表） |
| **04** | user/portrait（粉丝分层） | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_id`<br>`is_content_type`<br>**`stats_types=[92,93,95,81,86]`** | `all_fan_distribution[]` (粉丝分布，type 10/11/12/13)<br>`paid_fan_distribution[]` (付费粉丝分布)<br>`follower_gmv_local_distribution[]` (粉丝 GMV 分布)<br>`follower_sku_order_distribution[]` (粉丝订单分布)<br>`follower_main_aov_local_distribution[]` (粉丝客单价分布) | 观众画像-**粉丝维度**，按粉丝层级统计人数、订单、GMV、客单价 | **⑥ Follower analytics**（左下，新粉/老粉/非粉占比 + 各层 GMV/订单/客单价）<br>样本：`raw/04-user-portrait.*` |
| **04b** | user/portrait（人群画像） | `/api/v1/insights/workbench/live/detail/user/portrait` | `room_id`<br>`is_content_type`<br>**`stats_types=[85,86,87,88,89]`** | `paid_gender_distribution[]` (性别分布，type 20=男/21=女/22=未知)<br>`paid_age_distribution[]` (年龄分布，type 3/4/5)<br>`paid_state_distribution[]` (地区分布，key=省份/value=占比)<br>`paid_fan_distribution[]` (付费粉丝分布) | 观众画像-**人群维度**，按性别/年龄/地区统计付费用户分布 | **⑦ User profile**（右下，Gender/Age/Region 用户画像）<br>样本：`raw/04b-user-portrait.*` |
| **05** | product/list | `/api/v1/insights/workbench/live/detail/product/list` | `room_id`<br>`is_content_type`<br>`sorting_type` (排序：1=GMV降序)<br>`stats_types` (17个商品指标ID) | **商品列表**（每个商品包含）：<br>- `id` / `name` / `cover_url` (商品ID/名称/封面)<br>- `gmv_local` (单品 GMV)<br>- `sales` (销量)<br>- `exposure_cnt` (曝光数)<br>- `click_through_rate` (点击率)<br>- `click_order_rate` (点击下单率)<br>- `main_aov_local` (客单价)<br>- `inventory_left_cnt` (剩余库存)<br>- `add_shop_cart_cnt` (加购数)<br>- `is_pinned` (是否置顶)<br>- `is_live` (是否在售)<br>**汇总指标**：<br>- `sold_product` (售出商品种类数) | **商品维度详细数据**，支持按 GMV/销量/点击率等排序，包含单品完整转化漏斗 | **⑤ Product List**（中下，Product/Attributed GMV/Product Impressions/CTR/Added to cart 表格） |
| **06** | core/stats | `/api/v1/insights/workbench/live/detail/core/stats` | `room_id`<br>`is_content_type`<br>`creator_id`<br>`country`<br>`stats_types` (33个指标ID) | **核心指标**：<br>- `gmv_local` (总 GMV)<br>- `sales` (销量)<br>- `current_visitor_cnt` (在线人数)<br>- `click_through_rate` (点击率)<br>- `click_order_rate` (点击下单率)<br>- `main_aov_local` (客单价)<br>- `watch_uv` / `watch_pv` (观看 UV/PV)<br>- `avg_view_duration` (平均观看时长)<br>- `accumulated_new_follower_cnt` (新增粉丝)<br>- `product_click_rate` (商品点击率)<br>- `show_pv_per_hour` / `gmv_local_per_hour` (时均曝光/GMV)<br>**benchmark 对比**：<br>- `market_cmp_data[]` (市场对比)<br>- `self_cmp_data[]` (历史对比) | **最核心 API**，包含大屏所有关键指标：GMV、销量、流量、转化、粉丝、广告 ROI。提供市场/历史趋势对比 | **② 核心指标卡片**（中央大红框，Attributed GMV/items sold/Current viewers/Ads Cost/Views/Impressions per hour/Avg viewing duration/Follow rate/Tap-through rate/LIVE CTR） |
| **07** | comment | `/api/v1/insights/workbench/live/recap/comment` | `room_id`<br>`is_content_type` | `next_pagination` (分页信息)<br>`disabled` (是否禁用评论功能) | 评论/弹幕列表（样本为空，可能该直播间未启用或已结束）| **③ Comments**（右上，直播画面旁的实时评论流） |
| **08** | trend/chart | `/api/v1/insights/workbench/live/detail/trend/chart` | `room_id`<br>`is_content_type`<br>`stats_types=[20,3]` (20=Viewers, 3=GMV) | `trend_data[]`（每条对应一个 `stats_type`）：<br>- `stats_type=20`：`data[]` 中 `key`=时间戳 / `value`=在线人数<br>- `stats_type=3`：`data[]` 中 `key`=时间戳 / `amount`=GMV 金额对象<br>`granularity` (5=5分钟粒度)<br>`timezone_offset` / `timezone` | 性能趋势曲线，按 5 分钟粒度聚合在线人数与 GMV。样本含 22 个时间点 | **① Performance trends**（左上，Viewers + Attributed GMV 双线趋势图）<br>样本：`raw/08-trend-chart.*` |

---

## 2. 数据完整性评估

### 已覆盖 95% 核心需求

| 大屏模块 | 覆盖情况 | 覆盖 API |
|---------|---------|---------|
| ✅ 核心指标卡片（GMV/观众/订单/转化率） | **完整** | `06-core-stats` |
| ✅ 性能趋势图（Viewers + GMV 时间曲线） | **完整** | `08-trend-chart`（5 分钟粒度时间序列）✅ **已补充** |
| ✅ 历史趋势对比（市场/自身对比） | **完整** | `06-core-stats` 的 `stats_benchmark_data` |
| ✅ 流量来源分析 | **完整** | `03-source-new` |
| ✅ 观众画像-粉丝分层 | **完整** | `04-user-portrait`（`stats_types=[92,93,95,81,86]`） |
| ✅ 观众画像-人群（性别/年龄/地区） | **完整** | `04b-user-portrait`（`stats_types=[85,86,87,88,89]`）✅ **已补充** |
| ✅ 事件时间线（推品节奏） | **部分** | `02-event-timeline` (只有置顶商品事件) |
| ✅ 直播状态与回放 | **完整** | `01-room-status` |
| ✅ 商品列表与明细 | **完整** | `05-product-list` |
| ⚠️ 弹幕/评论详情 | **API 存在但数据空** | `07-comment` (需进一步验证) |

---

## 3. 已补充 API + 待验证清单

### ✅ 已补充（2026-06-11 抓包）

| API | 路径 | 状态 |
|-----|------|------|
| 商品列表 | `/api/v1/insights/workbench/live/detail/product/list` | ✅ **已完整抓取**，包含单品 GMV/销量/库存/转化率等 17 个指标 |
| 性能趋势图 | `/api/v1/insights/workbench/live/detail/trend/chart` | ✅ **已完整抓取**，`stats_types=[20,3]` 返回 Viewers + GMV 的 5 分钟粒度时间序列 |
| 人群画像 | `/api/v1/insights/workbench/live/detail/user/portrait`（`stats_types=[85,86,87,88,89]`） | ✅ **已完整抓取**，性别/年龄/地区分布（与粉丝分层共用接口，靠 stats_types 区分） |
| 评论 API | `/api/v1/insights/workbench/live/recap/comment` | ⚠️ 接口存在但样本数据为空（可能需进一步验证有评论的直播间） |

### ⚠️ 待进一步验证

| 推测接口 | 可能路径 | 业务含义 | 验证方法 |
|---------|---------|---------|---------|
| 弹幕/评论详情 | `/comment` 或 `/message/stream` | 弹幕内容、用户昵称、发送时间 | 在**有活跃评论的直播间**重新抓包验证 `07-comment` API |
| 观众互动明细 | `/interaction/detail` | 点赞数、分享数、关注数、礼物记录 | devtools 筛选响应含 `like`/`share`/`gift` |
| 主播信息 | `/creator/info` | 主播昵称、头像、粉丝总数 | devtools 筛选响应含 `creator`/`anchor` |

---

## 4. 采集实现优先级

| 优先级 | API | 实现建议 |
|-------|-----|---------|
| **P0** | `06-core-stats` | 立即实现，核心指标 + 趋势对比，覆盖 80% 需求 |
| **P0** | `01-room-status` | 获取直播时长、状态、回放链接 |
| **P0** | `05-product-list` | ✅ **已抓包**，商品列表是核心诉求，包含单品完整转化漏斗 |
| **P1** | `08-trend-chart` | ✅ **已抓包**，性能趋势曲线（Viewers + GMV 5 分钟粒度） |
| **P1** | `03-source-new` | 流量归因分析，辅助运营优化 |
| **P1** | `04-user-portrait` | 粉丝分层画像（`stats_types=[92,93,95,81,86]`） |
| **P1** | `04b-user-portrait` | ✅ **已抓包**，人群画像-性别/年龄/地区（`stats_types=[85,86,87,88,89]`） |
| **P2** | `02-event-timeline` | 推品节奏分析 |
| **P2** | `07-comment` | 评论/弹幕分析（需进一步验证有数据的直播间） |

---

## 5. MVP 可验证范围

现有 **9 个 API 样本**（含 2 套 user/portrait 维度）已可构建直播大屏 MVP：

- **顶部卡片**：`06-core-stats` 的 `gmv_local`、`sales`、`watch_uv`、`click_through_rate`
- **性能趋势图**：`08-trend-chart` 的 Viewers + GMV 5 分钟粒度时间序列 ✅ **新增**
- **历史趋势对比**：`06-core-stats.stats_benchmark_data.self_cmp_data[]`
- **流量分析**：`03-source-new` 饼图/柱状图
- **观众画像-粉丝分层**：`04-user-portrait` 新粉/老粉/非粉 + 各层 GMV/订单/客单价
- **观众画像-人群**：`04b-user-portrait` 性别/年龄/地区分布 ✅ **新增**
- **商品列表**：`05-product-list` 商品表格（GMV/销量/库存/点击率/加购数）
- **回放入口**：`01-room-status` 的 `replay_url`

**覆盖率**：95% 核心需求，只缺"弹幕内容详情"（评论 API 已找到但需验证有数据的直播间）

---

## 6. 原始样本文件清单

| 编号 | 文件名 | 对应区域 |
|------|--------|---------|
| 01 | `raw/01-room-status.*` | 顶部 Duration |
| 02 | `raw/02-event-timeline.*` | 推品事件 |
| 03 | `raw/03-source-new.*` | ④ Traffic source |
| 04 | `raw/04-user-portrait.*` | ⑥ Follower analytics（粉丝分层，`stats_types=[92,93,95,81,86]`） |
| 04b | `raw/04b-user-portrait.*` | ⑦ User profile（人群画像，`stats_types=[85,86,87,88,89]`） |
| 05 | `raw/05-product-list.*` | ⑤ Product List |
| 06 | `raw/06-core-stats.*` | ② 核心指标卡片 |
| 07 | `raw/07-comment.*` | ③ Comments（样本为空） |
| 08 | `raw/08-trend-chart.*` | ① Performance trends |
