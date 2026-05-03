# Shopee 数仓对接文档

## 文档说明

本文档面向后端开发、数仓 ETL 工程师，说明 Shopee 直播数据采集的接口规范和参数要求。

### 采集时间维度说明

**示例日期**：假设当前日期为 T = 2026-03-31

#### 通用采集模式（适用于大部分接口）

| 采集模式 | 时间范围 | 说明 |
|---------|---------|------|
| **增量采集** | 近 7 天 | `timeDim=7d`, `endDate=2026-03-30`（T-1） |
| **全量采集** | 近 30 天 | `timeDim=30d`, `endDate=2026-03-30`（T-1） |

#### 数据概览接口特殊说明（仅适用于 2.1 和 2.2）

**2.1 Data Overview** 和 **2.2 Cumulative Trend** 采用 **by day** 模式：

| 采集模式 | 请求次数 | 说明 |
|---------|---------|------|
| **增量采集** | 7 次 | 逐日请求，每次 `timeDim=1d`<br>   - `endDate=2026-03-30`（T-1）<br>   - `endDate=2026-03-29`（T-2）<br>   - ... 到 `endDate=2026-03-24`（T-7） |
| **全量采集** | 30 次 | 逐日请求，每次 `timeDim=1d`<br>从 `endDate=2026-03-30`（T-1）到 `endDate=2026-03-01`（T-30） |

**重要说明**：
- 所有 `endDate` 参数必须使用对应国家时区的日期，不能硬编码
- 除 2.1 和 2.2 外，其他接口使用通用采集模式（`timeDim=7d` 或 `timeDim=30d`）

---

## 总数据结构

**字段结构与 TikTok 保持一致**

```json
{
    "params": "",
    "cookies": "身份信息，需要保存，参考 live_account_info 表",
    "fromUrl": "请求的 URL",
    "extra": {
        "media_user_id": "媒体用户 ID",
        "media_shop_id": "媒体店铺 ID"
    },
    "sign": "身份验证标识（数仓可以忽略）",
    "socketUserId": "插件唯一标识 ID（用于和账号弱绑定使用）",
    "userType": "用户类型（用于判断数据来源是客户账号还是普通账号，数仓应该用不到，可以忽略）",
    "updateTime": "获取数据的时间戳",
    "request": {
        "response": "真正的数据 json",
        "url": "实际请求的 API 链接"
    }
}
```

---

## Base URL 说明

**国家域名映射**：根据 AdsPower 分组名自动匹配

| 国家 | 域名 | 时区 |
|------|------|------|
| 马来西亚 | `shopee.com.my` | UTC+8 |
| 印度尼西亚 | `shopee.co.id` | UTC+7 |
| 泰国 | `shopee.co.th` | UTC+7 |
| 新加坡 | `shopee.com.sg` | UTC+8 |
| 越南 | `shopee.vn` | UTC+7 |
| 巴西 | `shopee.com.br` | UTC-3 |
| 墨西哥 | `shopee.com.mx` | UTC-6 |

**Base URL 格式**：`https://seller.shopee.{domain}`

**说明**：
- `endDate` 参数必须使用对应国家时区的昨天日期（T-1）
- 例如：马来西亚（UTC+8）当前时间 2026-03-31 10:00 → `endDate=2026-03-30`

---

## 接口清单

### 1. 账号信息

| 接口名称 | API | 请求参数 |
|---------|-----|---------|
| login | `api/v2/login` | GET 请求无提交参数 |

**说明**：获取 `media_user_id` 和 `media_shop_id`，添加到所有后续接口的 `extra` 字段

---

### 2. 数据概览

#### 2.1 Data Overview

**接口**: `GET /api/supply/lm/sellercenter/overview/v3`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `endDate` | string | 是 | 查询日期（国家时区的日期，格式 YYYY-MM-DD） |
| `timeDim` | string | 是 | 固定值 `1d`（按天查询） |

**采集模式**:

| 模式 | 请求次数 | 说明 |
|------|---------|------|
| **增量** | 7 次 | 逐日请求 7 次，每次 `timeDim=1d`<br>   - `timeDim=1d&endDate=2026-03-30`（T-1）<br>   - `timeDim=1d&endDate=2026-03-29`（T-2）<br>   - `timeDim=1d&endDate=2026-03-28`（T-3）<br>   - ... 到 `timeDim=1d&endDate=2026-03-24`（T-7） |
| **全量** | 30 次 | 逐日请求 30 次，从 `endDate=2026-03-30` 到 `endDate=2026-03-01` |

#### 2.2 Cumulative Trend

**接口**: `GET /api/supply/lm/sellercenter/metricTrend/v2`

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `endDate` | string | 是 | 查询日期（国家时区的日期，格式 YYYY-MM-DD） |
| `timeDim` | string | 是 | 固定值 `1d`（按天查询） |

**采集模式**:

| 模式 | 请求次数 | 说明 |
|------|---------|------|
| **增量** | 8 次 | 同 2.1 Data Overview |
| **全量** | 30 次 | 同 2.1 Data Overview |

---

### 3. 直播列表

#### 3.1 实时直播列表

| 接口名称 | API | 请求参数 |
|---------|-----|---------|
| live-Livestreams List (实时) | `api/supply/lm/sellercenter/realtime/sessionList` | `page=1&pageSize=100&name=&orderBy=&sort=` |

**说明**：通过网络监听拦截，获取当前正在直播的直播间列表

#### 3.2 历史直播列表

| 接口名称 | API | 增量 | 全量 |
|---------|-----|------|------|
| live-Livestreams List (历史) | `api/supply/lm/sellercenter/liveList/v2` | `page=1&pageSize=100&name=&orderBy=&sort=&timeDim=7d&endDate=2026-03-30` | `page=1&pageSize=100&name=&orderBy=&sort=&timeDim=30d&endDate=2026-03-30` |

**说明**：
- 增量模式：只抓第一页
- 全量模式：分页抓取直到结束（最多 50 页）

---

### 4. 直播间详情

**说明**：
- 对所有直播间采集详情数据
- `startTime` 从 `sessionList` 或 `liveList` 响应中获取
- `endTime` 需要生成当地时区的当前时间（毫秒时间戳）
- 获取的数据范围为从 `startTime` 到 `endTime`

#### 4.1 Overview

| 接口名称 | API | 请求参数 |
|---------|-----|---------|
| overview | `api/supply/lm/sellercenter/realtime/dashboard/overview` | `sessionId=14015168` |

#### 4.2 GMV Trend

| 接口名称 | API | 请求参数 |
|---------|-----|---------|
| gmv-trend | `api/supply/lm/sellercenter/realtime/dashboard/trends` | `sessionId={sessionId}&startTime={startTime}&endTime={endTime}&metricTrend=order,gmv,confirmedGmv,confirmedOrder` |

**参数说明**：
- `sessionId`: 直播间 ID（从 sessionList 获取）
- `startTime`: 开播时间（毫秒时间戳，从 sessionList 获取）
- `endTime`: 当前时间（毫秒时间戳，从 sessionList 获取或使用采集时刻）
- `metricTrend`: 订单相关指标组

#### 4.3 CCU Trend

| 接口名称 | API | 请求参数 |
|---------|-----|---------|
| ccu-trend | `api/supply/lm/sellercenter/realtime/dashboard/trends` | `sessionId={sessionId}&startTime={startTime}&endTime={endTime}&metricTrend=ccu,engagedCcu,entering` |

**参数说明**：
- `sessionId`: 直播间 ID
- `startTime`: 开播时间（毫秒时间戳）
- `endTime`: 当前时间（毫秒时间戳）
- `metricTrend`: 观众相关指标组

#### 4.4 Comment Trend

| 接口名称 | API | 请求参数 |
|---------|-----|---------|
| comment-trend | `api/supply/lm/sellercenter/realtime/dashboard/trends` | `sessionId={sessionId}&startTime={startTime}&endTime={endTime}&metricTrend=comment,addToCart` |

**参数说明**：
- `sessionId`: 直播间 ID
- `startTime`: 开播时间（毫秒时间戳）
- `endTime`: 当前时间（毫秒时间戳）
- `metricTrend`: 互动相关指标组

#### 4.5 Viewer Source

| 接口名称 | API | 请求参数 |
|---------|-----|---------|
| viewer-source | `api/supply/lm/sellercenter/realtime/dashboard/viewer-source` | `sessionId=13841179` |

#### 4.6 Viewer Profile

| 接口名称 | API | 请求参数 |
|---------|-----|---------|
| viewer-profile | `api/supply/lm/sellercenter/realtime/dashboard/viewer-profile` | `sessionId=13841179` |

#### 4.7 Buyer Profile

| 接口名称 | API | 请求参数 |
|---------|-----|---------|
| buyer-profile | `api/supply/lm/sellercenter/realtime/dashboard/buyer-profile` | `sessionId=13841179` |

---

### 5. 回放直播间详情

#### 5.1 Data Insight

| 接口名称 | API | 请求参数 |
|---------|-----|---------|
| data-insight | `api/supply/lm/sellercenter/liveDetail` | `sessionId=13841179` |

#### 5.2 Incremental Trend

**接口**: `GET /api/supply/lm/sellercenter/liveCoordinate/v2`

**用途**: 获取回放直播间的 1 分钟粒度趋势数据（Sales Trend、Traffic Trend、Interaction Trend）

**请求参数**:

| 参数 | 类型 | 必填 | 说明 | 示例值 |
|------|------|------|------|--------|
| sessionId | string | 是 | 直播间 ID | `15684298` |
| startTime | long | 是 | 直播开始时间戳（毫秒），需向下取整到分钟级（秒数为 0）<br>计算方式：`floor(liveInfo.startTime / 60000) * 60000` | `1774843200000` |
| size | int | 是 | 返回数据点数量（每个点 1 分钟）<br>计算方式：`ceil(duration / 60000)` 或固定值<br>**建议上限**: 1440（24 小时） | `600` |

**字段说明**:

| 字段 | 类型 | 说明 | 对应指标类型 |
|------|------|------|-------------|
| time | long | 时间戳（毫秒），每个数据点间隔 60 秒 | - |
| views | int | 浏览量 | Traffic Trend |
| viewers | int | 观众数 | Traffic Trend |
| ccu | int | 并发在线人数 | Traffic Trend |
| engagedCcu | int | 互动观众数 | Traffic Trend |
| likes | int | 点赞数 | Interaction Trend |
| comment | int | 评论数 | Interaction Trend |
| atc | int | 加购数（Add to Cart） | Interaction Trend |
| confirmedOrders | int | 确认订单数 | Sales Trend |
| confirmedSales | decimal | 确认销售额 | Sales Trend |
| placedOrders | int | 下单数 | Sales Trend |
| placedSales | decimal | 下单金额 | Sales Trend |

**采集逻辑**:

1. 先调用 `liveDetail` 接口获取 `liveInfo.startTime` 和 `duration`
2. 计算请求参数：
   ```python
   # startTime 向下取整到分钟级（秒数为 0）
   start_time = (liveInfo['startTime'] // 60000) * 60000
   
   # size 根据直播时长计算（向上取整），不设上限
   import math
   size = math.ceil(liveInfo['duration'] / 60000)
   
   # 示例：duration=35959625ms → size=600（10小时）
   # 示例：duration=172800000ms → size=2880（48小时）
   ```
3. **采用激进策略**：一次性请求获取整场直播的全部数据，不设 size 上限

**注意事项**:

- `startTime` 必须向下取整到分钟级，否则数据点时间戳会不对齐
- 响应数据按时间升序排列，每个数据点间隔 60 秒（1 分钟粒度）
- **激进策略说明**：无论直播时长多长（即使超过 48 小时），都一次性请求全部数据
- 经测试，Shopee 服务器支持较大的 size 值，暂未发现上限
- 如果遇到超长直播导致请求失败或超时，再考虑分批策略
- 如果直播时长超过 `size` 分钟，只返回前 `size` 个数据点（因此 size 必须足够大）

---

## 采集说明

### 采集方式

- **网络监听拦截**：`realtime/sessionList`
- **JS 注入执行**：其他所有接口

### 采集规则

1. **实时直播间**（status=1）：采集 7 个详情接口（overview + 3 个 trends + 3 个 profile）
2. **回放直播间**（status=2）：采集 2 个详情接口（liveDetail + liveCoordinate）
3. **分页采集**：`liveList/v2` 全量模式下分页抓取，最多 50 页

### 时区处理

所有 `endDate` 参数必须使用对应国家时区的昨天日期（T-1），不能硬编码。
