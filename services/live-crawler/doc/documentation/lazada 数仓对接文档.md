# Lazada 数仓对接文档

## 文档说明

本文档面向后端开发、数仓 ETL 工程师，说明 Lazada 直播数据采集的接口规范和参数要求。

### 采集端说明

```text
采集分为两个端接口：
- 卖家中心主站：https://sellercenter.lazada.co.th
- LazLive 直播后台：https://live.lazada.co.th/app/live-list
```

### 采集时间维度说明

**示例日期**：假设当前日期为 T = 2026-04-09

#### 通用采集模式（适用于 1.2、1.3 场次/商品列表接口）


| 采集模式     | 时间范围   | 说明                                 |
| -------- | ------ | ---------------------------------- |
| **增量采集** | 近 7 天  | `period=l7d`, `dateRange=20260402  |
| **全量采集** | 近 30 天 | `period=l30d`, `dateRange=20260310 |


#### by day 逐日采集模式（适用于 1.1、2.1 ~ 2.9 数据洞察接口）


| 采集模式     | 请求次数 | 说明                 |
| -------- | ---- | ------------------ |
| **增量采集** | 7 次  | 逐日请求，`dateRange=当日 |
| **全量采集** | 30 次 | 逐日请求，`dateRange=当日 |


**重要说明**：

- 所有日期参数必须使用对应国家时区的日期，不能硬编码
- 实时接口（1.4、1.5）无需日期参数，每次采集获取当天数据

---

## 总数据结构

```json
{
    "params": "",
    "method": "GET",
    "body": "",
    "cookies": "",
    "fromUrl": "",
    "extra": {
        "seller_id": "",
        "venture": ""
    },
    "sign": "",
    "socketUserId": "",
    "userType": "",
    "updateTime": "",
    "request": {
        "response": "",
        "url": ""
    }
}
```

### 字段说明


| 字段                 | 类型     | 说明                                             |
| ------------------ | ------ | ---------------------------------------------- |
| `params`           | string | URL 查询参数（GET/POST 均有，也包含在 `request.url` 中，可为空） |
| `method`           | string | 请求方法：`GET` 或 `POST`                            |
| `body`             | string | POST 请求体（仅 POST 请求有值，GET 请求为空字符串）              |
| `cookies`          | string | 身份信息，需要保存，参考 `live_account_info` 表             |
| `fromUrl`          | string | 请求的页面 URL                                      |
| `extra`            | object | 扩展信息                                           |
| `extra.seller_id`  | string | Lazada 卖家 ID（如 `101007760547`）                 |
| `extra.venture`    | string | 国家/区域代码（如 `TH`、`MY`、`ID`）                      |
| `sign`             | string | 身份验证标识（数仓可忽略）                                  |
| `socketUserId`     | string | 插件唯一标识 ID（用于和账号弱绑定使用）                          |
| `userType`         | string | 用户类型（数仓可忽略）                                    |
| `updateTime`       | string | 获取数据的时间戳                                       |
| `request.response` | string | 真正的数据 JSON                                     |
| `request.url`      | string | 实际请求的 API 链接（含 query string）                   |


---

## 接口清单

**Base URL**: `https://acs-m.lazada.co.th`

---

### 1. 卖家中心 - 营销中心

#### 1.1 直播概览

**接口**: `GET /h5/mtop.lazada.live.data.seller.metrics/1.0/`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "jsv": "2.6.1",
    "appKey": "4272",
    "t": "1775735809750",
    "sign": "938f2dd2512e4201900e947277ab919f",
    "v": "1.0",
    "timeout": "30000",
    "H5Request": "true",
    "url": "mtop.lazada.live.data.seller.metrics",
    "x-i18n-language": "en",
    "api": "mtop.lazada.live.data.seller.metrics",
    "type": "originaljson",
    "dataType": "json",
    "valueType": "original",
    "x-i18n-regionID": "LAZADA_TH",
    "data": "{\"period\":\"day\",\"dateRange\":\"20260407|20260407\"}"
}
```

**响应**:

```json
{"api":"mtop.lazada.live.data.seller.metrics","data":{"model":{"metrics":[{"desc":"Value of guided livestream orders including shipping fees.","format":"money","key":"guidedGmvLocal","name":"Revenue","sortable":true,"value":6103.22},{"desc":"Total units sold of guided livestream orders.","format":"number","key":"guidedUnitPurchase","name":"Units sold","sortable":true,"value":12},{"desc":"Number of orders made within 7 days guided by livestreams featuring your products. Orders include all paid non-COD orders and all confirmed COD orders, including cancelled, returned and refunded orders","format":"number","key":"guidedOrderCnt","name":"Orders","sortable":true,"value":11},{"desc":"Number of users that made orders","format":"number","key":"guidedBuyer","name":"Buyers","sortable":true,"value":9},{"desc":"Number of livestreams that you have started, excluding test livestreams. Deleted sessions are included","format":"number","key":"sessionCnt","name":"Sessions","sortable":true,"value":329},{"desc":"Selling products in  live room","format":"number","key":"itemTotal","name":"Featured Items","sortable":true,"value":26},{"desc":"Total number of units of products added to cart guided by the livestream","format":"number","key":"guidedA2cQty","name":"Added to cart","sortable":true,"value":36},{"desc":"Number of times users click on a highlighted product or a product in the pink basket","format":"number","key":"guidedIpv","name":"Product clicks","sortable":true,"value":316},{"desc":"Average Revenue per Order","format":"number","key":"aov","name":"Aov","sortable":false,"value":554.84}],"updatedOn":"2026/04/08"},"msg":"Success"},"ret":["SUCCESS::调用成功"],"v":"1.0"}
```

---

#### 1.2 直播场次详情

**接口**: `GET /h5/mtop.lazada.live.data.seller.productrooms/1.0/`

**采集模式**: 通用采集模式

**请求参数（全量）**:

```json
{
    "jsv": "2.6.1",
    "appKey": "4272",
    "t": "1775726080849",
    "sign": "fcf86f2b88065a8c1b29d24a30025aa4",
    "v": "1.0",
    "timeout": "30000",
    "H5Request": "true",
    "url": "mtop.lazada.live.data.seller.productRooms",
    "x-i18n-language": "en",
    "api": "mtop.lazada.live.data.seller.productRooms",
    "type": "originaljson",
    "dataType": "json",
    "valueType": "original",
    "x-i18n-regionID": "LAZADA_TH",
    "data": "{\"period\":\"l30d\",\"dateRange\":\"20260310|20260408\",\"pageNum\":1,\"pageSize\":100}"
}
```

**请求参数（增量）**:

```json
{
    "jsv": "2.6.1",
    "appKey": "4272",
    "t": "1775726234826",
    "sign": "7147b16e3479385c9e943f2ec024b708",
    "v": "1.0",
    "timeout": "30000",
    "H5Request": "true",
    "url": "mtop.lazada.live.data.seller.productRooms",
    "x-i18n-language": "en",
    "api": "mtop.lazada.live.data.seller.productRooms",
    "type": "originaljson",
    "dataType": "json",
    "valueType": "original",
    "x-i18n-regionID": "LAZADA_TH",
    "data": "{\"period\":\"l7d\",\"dateRange\":\"20260402|20260408\",\"pageNum\":1,\"pageSize\":100}"
}
```

**响应**: 数据量较大，见 `productrooms_response.json`

---

#### 1.3 直播商品详情

**接口**: `GET /h5/mtop.lazada.live.data.seller.products/1.0/`

**采集模式**: 通用采集模式

**请求参数（全量）**:

```json
{
    "jsv": "2.6.1",
    "appKey": "4272",
    "t": "1775726608368",
    "sign": "f323f3fa147d025807c2ac7069616c81",
    "v": "1.0",
    "timeout": "30000",
    "H5Request": "true",
    "url": "mtop.lazada.live.data.seller.products",
    "x-i18n-language": "en",
    "api": "mtop.lazada.live.data.seller.products",
    "type": "originaljson",
    "dataType": "json",
    "valueType": "original",
    "x-i18n-regionID": "LAZADA_TH",
    "data": "{\"period\":\"l30d\",\"dateRange\":\"20260310|20260408\",\"pageNum\":1,\"pageSize\":100}"
}
```

**请求参数（增量）**:

```json
{
    "jsv": "2.6.1",
    "appKey": "4272",
    "t": "1775726773857",
    "sign": "624061aec67b82ebf86d98574cb02e8e",
    "v": "1.0",
    "timeout": "30000",
    "H5Request": "true",
    "url": "mtop.lazada.live.data.seller.products",
    "x-i18n-language": "en",
    "api": "mtop.lazada.live.data.seller.products",
    "type": "originaljson",
    "dataType": "json",
    "valueType": "original",
    "x-i18n-regionID": "LAZADA_TH",
    "data": "{\"period\":\"l7d\",\"dateRange\":\"20260402|20260408\",\"pageNum\":1,\"pageSize\":100}"
}
```

**响应**: 数据量较大，见 `products_response.json`

---

#### 1.4 实时表现（累计趋势）

**接口**: `GET /ba/sycm/lazada/faas/dashboard/realtime/key/detail/trend/accumulationV2.json`

**采集模式**: 实时接口，无需日期参数

**请求参数**: 无额外参数

**响应**: 数据量较大，见 `realtime_trend_response.json`

---

#### 1.5 实时大屏

**接口**: `GET /ba/sycm/faas/dashboard/realtime/key/detailV2.json`

**采集模式**: 实时接口，无需日期参数

**请求参数**: 无额外参数

**响应**:

```json
{"code":0,"data":{"yesterday":{"revenue":{"value":5071.67},"buyers":{"value":9},"productGuidedRate":{"value":1.0},"productConversionRate":{"value":0.0413},"uvNew":{"value":228},"revenuePerBuyer":{"value":563.5189},"orders":{"value":9},"pvNew":{"value":653},"ipvUv":{"value":228},"conversionRate":{"value":0.0413},"uvWorth":{"value":23.2645}},"yesterdayTotal":{"cartItmQty":{"value":38},"statDate":{"value":1775577600000},"addToCartConversionRate":{"value":0.0978},"buyers":{"value":14},"cartByrCnt":{"value":31},"productGuidedRate":{"value":0.9842},"payAmountMP3":{"value":7076.9},"unitsSold":{"value":23},"revenuePerBuyer":{"value":505.4929},"wishlistUv":{"value":0},"ipvUv":{"value":312},"conversionRate":{"value":0.0442},"venture":{"value":"TH"},"ipv":{"value":803},"revenue":{"value":7076.9},"sellerId":{"value":"101007760547"},"productConversionRate":{"value":0.0449},"uvNew":{"value":317},"orders":{"value":14},"payBuyerMP3":{"value":14},"wishlistCnt":{"value":0},"pvNew":{"value":864},"revenueMP3":{"value":7076.9},"uvWorth":{"value":22.3246}},"today":{"cartItmQty":{"value":14},"addToCartConversionRate":{"value":0.0485},"buyers":{"cycleCrc":-0.3333333333,"value":6},"cartByrCnt":{"value":11},"productGuidedRate":{"cycleCrc":0E-10,"value":1.0},"payAmountMP3":{"value":1615.71},"unitsSold":{"value":8},"revenuePerBuyer":{"cycleCrc":-0.5221367021,"value":269.285},"wishlistUv":{"value":0},"redeemedCollectableVoucherCount":{"value":14},"ipvUv":{"cycleCrc":-0.0043859649,"value":227},"conversionRate":{"cycleCrc":-0.3607748184,"value":0.0264},"ipv":{"value":510},"revenue":{"cycleCrc":-0.6814244618,"value":1615.71},"productConversionRate":{"cycleCrc":-0.3607748184,"value":0.0264},"uvNew":{"cycleCrc":-0.0043859649,"value":227},"orders":{"cycleCrc":-0.3333333333,"value":6},"payBuyerMP3":{"value":6},"wishlistCnt":{"value":0},"pvNew":{"cycleCrc":-0.1669218989,"value":544},"revenueMP3":{"value":1615.71},"statHour":{"value":"00"},"uvWorth":{"cycleCrc":-0.6940531711,"value":7.1177}},"updateTime":"2026-04-09 17:13:09","totalWeekGMV":{"revenue":{"value":27346.079999999998}}},"message":"","success":true,"traceId":"21010c9417757295897992117e5513"}
```

---

### 2. 卖家中心 - 数据洞察（生意参谋）

#### 数据洞察-生意参谋-关键指标

##### 2.1.1 关键指标概览

**接口**: `GET /ba/sycm/`[mtop.lazada.live.data](http://mtop.lazada.live.data).seller.metrics`.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day"
}
```

**响应**:

```json
{"code":0,"data":{"statDate":{"value":1775491200000},"wishlistVisitor":{"cycleCrc":-0.6363636364,"syncCrc":-0.5555555556,"value":8},"returnPayAmount":{"cycleCrc":null,"syncCrc":null,"value":0.0},"addToCartQuantity":{"cycleCrc":-0.7101449275,"syncCrc":-0.3750000000,"value":20},"wishlistSKU":{"cycleCrc":-0.6388888889,"syncCrc":-0.4583333333,"value":13},"refundBillAmount":{"cycleCrc":null,"syncCrc":null,"value":0},"pricePerBuyer":{"cycleCrc":-0.2037947216,"syncCrc":-0.1818744007,"value":502.20714285714286},"ipvUv":{"cycleCrc":-0.7014778325,"syncCrc":-0.5965379494,"value":303},"bounceRate":{"cycleCrc":null,"syncCrc":null},"addToCartVisitor":{"cycleCrc":-0.7234042553,"syncCrc":-0.4583333333,"value":13},"paidOrderAmount":{"cycleCrc":-0.7200000000,"syncCrc":-0.6956521739,"value":7},"payAmount":{"cycleCrc":-0.7677734605,"syncCrc":-0.7396873093,"value":3515.45},"payBuyer":{"cycleCrc":-0.7083333333,"syncCrc":-0.6818181818,"value":7},"paidRate":{"cycleCrc":-0.0274590164,"syncCrc":-0.2154992548,"value":0.022950819672131147},"uvNew":{"cycleCrc":-0.7000983284,"syncCrc":-0.5944148936,"value":305},"cancelPayAmount":{"cycleCrc":-0.7346620292,"syncCrc":-0.4948321639,"value":319.65},"paidItemAmountPrd":{"cycleCrc":-0.7692307692,"syncCrc":-0.7073170732,"value":12},"unitsSoldPerOrder":{"cycleCrc":-0.1758173077,"syncCrc":-0.0383148210,"value":1.7143},"pvNew":{"cycleCrc":-0.6216867470,"syncCrc":-0.5078369906,"value":785},"avgStaytime":{"cycleCrc":null,"syncCrc":null},"revenuePerOrder":{"cycleCrc":-0.1706195724,"syncCrc":-0.1446868895,"value":502.2071},"uvWorth":{"cycleCrc":-0.2256577354,"syncCrc":-0.3581798577,"value":11.526065573770492},"seller_id":{"value":101007760547},"refundAmount":{"cycleCrc":null,"syncCrc":-1.0000000000,"value":0}},"message":"","success":true,"traceId":"21010c9417757305045475282e5513"}
```

---

##### 2.1.2 关键指标趋势

**接口**: `GET /ba/sycm/lazada/faas/dashboard/key/trendV2.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day",
    "indexCode": "payAmount,uvNew,statDate"
}
```

**响应**:

```json
{"code":0,"data":{"statDate":[1772985600000,1773072000000,1773158400000,1773244800000,1773331200000,1773417600000,1773504000000,1773590400000,1773676800000,1773763200000,1773849600000,1773936000000,1774022400000,1774108800000,1774195200000,1774281600000,1774368000000,1774454400000,1774540800000,1774627200000,1774713600000,1774800000000,1774886400000,1774972800000,1775059200000,1775145600000,1775232000000,1775318400000,1775404800000,1775491200000],"payAmount":[15287.53,11720.69,11764.65,10668.19,19197.88,19168.17,17352.8,16648.74,15781.34,5113.93,16997.4,12534.68,10537.32,13001.13,11425.64,16487.42,25461.61,13081.41,10266.02,9246.24,10499.7,9916.09,13504.72,4230.26,4330.16,9974.25,17270.65,14207.1,15138.02,3515.45],"uvNew":[671,742,668,886,1054,929,2036,1174,1250,919,948,1388,1168,500,368,443,841,542,674,611,845,863,752,760,569,356,804,583,1017,305],"timePeriod":["03-10","03-11","03-12","03-13","03-14","03-15","03-16","03-17","03-18","03-19","03-20","03-21","03-22","03-23","03-24","03-25","03-26","03-27","03-28","03-29","03-30","03-31","04-01","04-02","04-03","04-04","04-05","04-06","04-07"]},"message":"","success":true,"traceId":"2102fcd617757334778472352eb2c7"}
```

---

#### 数据洞察-生意参谋-流量看板

##### 2.2.1 流量概览

**接口**: `GET /ba/sycm/lazada/faas/dashboard/traffic/overall.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day"
}
```

**响应**:

```json
{"code":0,"data":{"statDate":{"value":1775491200000},"productGuidedRate":{"cycleCrc":-0.0046092184,"syncCrc":-0.0053068990,"value":0.9934},"productConversionRate":{"cycleCrc":-0.0229647965,"syncCrc":-0.2113711371,"value":0.0231023102310231},"uvNew":{"cycleCrc":-0.7000983284,"syncCrc":-0.5944148936,"value":305},"payBuyer":{"cycleCrc":-0.7083333333,"syncCrc":-0.6818181818,"value":7},"ipvUv":{"cycleCrc":-0.7014778325,"syncCrc":-0.5965379494,"value":303}},"message":"","success":true,"traceId":"2102fcd617757334778702354eb2c7"}
```

---

##### 2.2.2 流量来源排名

**接口**: `GET /ba/sycm/lazada/faas/dashboard/traffic/source/ranking.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day",
    "pageSize": "5",
    "page": "1"
}
```

**响应**:

```json
{"code":0,"data":[{"channelLvl1Id":{"value":10002},"parentChannelId":{"value":"10002"},"buyers":{},"totalUV":{"value":213},"trafficRevenue":{},"conversionRate":{},"visitorValue":{},"trafficOrders":{},"channelLevel":{"value":2},"hideInBa":{"value":"N"},"channelName":{"value":"On Platform Seller Guided"},"trafficRevenuePerBuyer":{},"channelId":{"value":"21000"}},{"channelLvl1Id":{"value":10001},"parentChannelId":{"value":"10001"},"channelLevel":{"value":2},"totalUV":{"value":31},"hideInBa":{"value":"N"},"channelName":{"value":"Others (including lazada OM)"},"conversionRate":{"value":0.0},"channelId":{"value":"23000"}},{"channelLvl1Id":{"value":10001},"parentChannelId":{"value":"10001"},"channelLevel":{"value":2},"totalUV":{"value":26},"hideInBa":{"value":"N"},"channelName":{"value":"Organic Search"},"conversionRate":{"value":0.038462},"channelId":{"value":"20004"}},{"channelLvl1Id":{"value":10001},"parentChannelId":{"value":"10001"},"channelLevel":{"value":2},"totalUV":{"value":18},"hideInBa":{"value":"N"},"channelName":{"value":"Coins Channel"},"conversionRate":{"value":0.222222},"channelId":{"value":"20008"}},{"channelLvl1Id":{"value":10001},"parentChannelId":{"value":"10001"},"channelLevel":{"value":2},"totalUV":{"value":17},"hideInBa":{"value":"N"},"channelName":{"value":"Orders"},"conversionRate":{"value":0.058824},"channelId":{"value":"20022"}}],"message":"","success":true,"traceId":"2102fcd617757334778782355eb2c7"}
```

---

##### 2.2.3 搜索关键词排名

**接口**: `GET /ba/sycm/lazada/faas/dashboard/traffic/search/ranking.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day",
    "pageSize": "5",
    "page": "1"
}
```

**响应**:

```json
{"code":0,"data":[{"displayKeyword":{"value":"nature key"},"totalUV":{"value":5},"searchKeyword":{"value":"nature key"},"conversionRate":{"value":0.0}},{"displayKeyword":{"value":"natures key"},"totalUV":{"value":4},"searchKeyword":{"value":"natures key"},"conversionRate":{"value":0.0}},{"displayKeyword":{"value":"แอปเปิ้ลไซเดอร์กัมมี่"},"totalUV":{"value":3},"searchKeyword":{"value":"แอปเปิ้ล ไซเดอร์ กัมมี่"},"conversionRate":{"value":0.0}},{"displayKeyword":{"value":"แอปเปิ้ลไซเดอร์เวนิก้า"},"totalUV":{"value":3},"searchKeyword":{"value":"แอปเปิ้ล ไซเดอร์ เวนิก้า"},"conversionRate":{"value":0.0}},{"displayKeyword":{"value":"แอปเปิ้ลกัมมี่"},"totalUV":{"value":1},"searchKeyword":{"value":"แอปเปิ้ล กัมมี่"},"conversionRate":{"value":0.0}}],"message":"","success":true,"traceId":"2102fcd617757334778952357eb2c7"}
```

---

#### 数据洞察-生意参谋-商品控制面板

##### 2.3.1 商品概览

**接口**: `GET /ba/sycm/lazada/faas/dashboard/product/overview.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day"
}
```

**响应**:

```json
{"code":0,"data":{"statDate":{"value":1775491200000},"uv":{"value":305},"purchasableSKU":{"value":74},"pv":{"value":749},"paidItemAmount":{"value":12},"activeSKU":{"value":75},"sKUVisitor":{"value":18},"orderedSKURate":{"cycleCrc":-0.3571428571,"value":0.12},"orderedSKU":{"value":9},"viewedSKU":{"value":12},"viewedSKURate":{"cycleCrc":-0.4285714286,"value":0.16},"prdViewRate":{"cycleCrc":-0.0606060606,"value":0.9117647058823529},"prdViewCnt":{"value":31},"prdUv":{"value":303},"prdCount":{"value":34},"purchasableSKURate":{"cycleCrc":0,"value":0.9866666666666667}},"message":"","success":true,"traceId":"2102fcd617757334775322334eb2c7"}
```

---

##### 2.3.2 商品诊断

**接口**: `GET /ba/sycm/lazada/faas/product/diagnosis/overview.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day"
}
```

**响应**:

```json
{"code":0,"data":{"statDate":{},"skuWeightSuggest":{"value":0},"conversionDropping":{"value":0},"revenueDropping":{"value":3},"poorReviews":{"value":0},"shortOrOutOfStock":{"value":1},"notSelling":{"value":6},"notSellingPrd":{"value":12},"conversionDroppingPrd":{"value":12},"priceUncompetitive":{"value":0}},"message":"","success":true,"traceId":"2102fcd617757334775392335eb2c7"}
```

---

##### 2.3.3 商品排名-按营收

**接口**: `GET /ba/sycm/lazada/faas/product/performance/batch/itemV2.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "orderBy": "productRevenue",
    "dateType": "day",
    "dateRange": "2026-04-07|2026-04-07",
    "pageSize": "5",
    "cateId": "",
    "brandId": "",
    "searchStr": "",
    "device": "1",
    "order": "desc",
    "dashboard": "true"
}
```

**响应**: 见 `product_performance_revenue.json`（包含商品详细信息：营收、订单、访客等）

---

##### 2.3.4 商品排名-按访客数

**接口**: `GET /ba/sycm/lazada/faas/product/performance/batch/itemV2.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "orderBy": "productIpvUv",
    "dateType": "day",
    "dateRange": "2026-04-07|2026-04-07",
    "pageSize": "5",
    "cateId": "",
    "brandId": "",
    "searchStr": "",
    "device": "1",
    "order": "desc",
    "dashboard": "true"
}
```

**响应**: 见 `product_performance_ipvuv.json`（包含商品详细信息：访客数、营收、转化率等）

---

#### 数据洞察-生意参谋-营销工具看板

##### 2.4.1 营销概览

**接口**: `GET /ba/sycm/lazada/faas/dashboard/promotion/board/overview.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day"
}
```

**响应**:

```json
{"code":0,"data":{"voucher":{"statDate":{"value":1775491200000},"guidedType":{"value":"3"},"guidedRevenue":{"cycleCrc":-0.7648201221,"syncCrc":-0.6802799352,"value":3515.45},"unitsSoldPerOrder":{"cycleCrc":-0.0203661798,"syncCrc":0.0118997025,"value":1.4286},"orders":{"cycleCrc":-0.7083333333,"syncCrc":-0.5882352941,"value":7},"storeOverAllComp":{},"revenuePerOrder":{"cycleCrc":-0.1936690590,"syncCrc":-0.2235370095,"value":502.2071},"guidedName":{"value":"Voucher"}},"freeShippingMax":{"statDate":{"value":1775491200000},"guidedType":{"value":"5"},"guidedRevenue":{"cycleCrc":-0.7234241917,"syncCrc":-0.7036651465,"value":3515.4500000000003},"unitsSoldPerOrder":{"cycleCrc":-0.0322449533,"syncCrc":-0.0306032435,"value":1.4286},"orders":{"cycleCrc":-0.6666666667,"syncCrc":-0.6315789474,"value":7},"revenuePerOrder":{"cycleCrc":-0.1702726199,"syncCrc":-0.1956626296,"value":502.2071},"guidedName":{"value":"Free Shipping Max"}},"nonPromotion":{"statDate":{"value":1775491200000},"guidedType":{"value":"-1"},"guidedRevenue":{"cycleCrc":null,"syncCrc":-1.0000000000,"value":0.0},"unitsSoldPerOrder":{"cycleCrc":null,"syncCrc":null},"orders":{"cycleCrc":null,"syncCrc":-1.0000000000,"value":0},"revenuePerOrder":{"cycleCrc":null,"syncCrc":null},"guidedName":{"value":"Non-Promotion"}},"flexiCombo":{"statDate":{"value":1775491200000},"guidedType":{"value":"2"},"guidedRevenue":{"cycleCrc":-0.8589442210,"syncCrc":-0.7580006999,"value":1804.93},"unitsSoldPerOrder":{"cycleCrc":0.4358974359,"syncCrc":0.3124835940,"value":3.5},"orders":{"cycleCrc":-0.8750000000,"syncCrc":-0.7777777778,"value":2},"storeOverAllComp":{"value":"+1"},"revenuePerOrder":{"cycleCrc":0.1284461613,"syncCrc":0.0889968797,"value":902.465},"guidedName":{"value":"Flexi Combo"}},"storeFlashSale":{"statDate":{"value":1775491200000},"guidedType":{"value":"7"},"guidedRevenue":{"cycleCrc":0.4262627310,"syncCrc":1.7278324124,"value":3026.23},"unitsSoldPerOrder":{"cycleCrc":-0.5555666667,"syncCrc":0.3333000000,"value":1.3333},"orders":{"cycleCrc":2.0000000000,"syncCrc":2.0000000000,"value":6},"revenuePerOrder":{"cycleCrc":-0.5245790582,"syncCrc":-0.0907224691,"value":504.3717},"guidedName":{"value":"Store Flash Sale"}},"storeOverall":{"statDate":{"value":1775491200000},"guidedType":{"value":"0"},"guidedRevenue":{"cycleCrc":-0.7677734605,"syncCrc":-0.7396873093,"value":3515.4500000000003},"unitsSoldPerOrder":{"cycleCrc":-0.1758173077,"syncCrc":-0.0383148210,"value":1.7143},"orders":{"cycleCrc":-0.7200000000,"syncCrc":-0.6956521739,"value":7},"revenuePerOrder":{"cycleCrc":-0.1706195724,"syncCrc":-0.1446868895,"value":502.2071},"guidedName":{"value":"Store Overall"}},"promotion":{"statDate":{"value":1775491200000},"guidedType":{"value":"1"},"guidedRevenue":{"cycleCrc":-0.7677734605,"syncCrc":-0.7267520221,"value":3515.45},"unitsSoldPerOrder":{"cycleCrc":-0.1758173077,"syncCrc":-0.0768940822,"value":1.7143},"orders":{"cycleCrc":-0.7200000000,"syncCrc":-0.6666666667,"value":7},"revenuePerOrder":{"cycleCrc":-0.1706195724,"syncCrc":-0.1802560725,"value":502.2071},"guidedName":{"value":"Promotion"}}},"message":"","success":true,"traceId":"2102fcd617757334775572336eb2c7"}
```

---

##### 2.4.2 营销趋势

**接口**: `GET /ba/sycm/lazada/faas/dashboard/promotion/board/trend.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day"
}
```

**响应**:

```json
{"code":0,"data":{"statDate":[1772985600000,1773072000000,1773158400000,1773244800000,1773331200000,1773417600000,1773504000000,1773590400000,1773676800000,1773763200000,1773849600000,1773936000000,1774022400000,1774108800000,1774195200000,1774281600000,1774368000000,1774454400000,1774540800000,1774627200000,1774713600000,1774800000000,1774886400000,1774972800000,1775059200000,1775145600000,1775232000000,1775318400000,1775404800000,1775491200000],"guidedRevenue":[15287.53,11720.690000000002,11764.650000000001,10668.19,19197.88,19168.17,17352.800000000003,16648.739999999998,15781.34,5113.93,16997.4,12534.680000000002,9770.039999999999,13001.130000000003,10641.64,16487.420000000002,25260.009999999995,13081.409999999998,10266.02,9246.24,10499.7,9709.09,12865.419999999996,4230.26,4330.160000000001,9974.249999999998,17270.649999999998,14207.099999999997,15138.02,3515.45]},"message":"","success":true,"traceId":"2102fcd617757334775632337eb2c7"}
```

---

##### 2.4.3 营销分类占比

**接口**: `GET /ba/sycm/lazada/faas/dashboard/promotion/board/category/ratio.json`

**采集模式**: by day 逐日采集

**请求参数**:

```json
{
    "dateRange": "2026-04-07|2026-04-07",
    "dateType": "day"
}
```

**响应**:

```json
{"code":0,"data":{"voucherRatio":{"value":0.4482758620689655},"freeShippingRatio":{"value":0.16091954022988506},"flexiComboRatio":{"value":0.26436781609195403}},"message":"","success":true,"traceId":"2102fcd617757334775682338eb2c7"}
```

---

### 3. LazLive 直播后台

#### 3.1 直播场次列表

**接口**: `POST /h5/mtop.lazada.live.querylivesbystatus/1.0/`

**采集模式**: 通用采集模式

- 全量：获取全部数据，如果下一页有数据，继续翻页
- 增量：根据近7天的时间判断是否要翻页

**请求参数（URL query string）**:

```json
{
    "jsv": "2.6.1",
    "appKey": "4272",
    "t": "1775727621615",
    "sign": "e01fc79d8f3410520ede65cf4244a202",
    "v": "1.0",
    "timeout": "30000",
    "H5Request": "true",
    "url": "mtop.lazada.live.querylivesbystatus",
    "type": "originaljson",
    "method": "POST",
    "api": "mtop.lazada.live.querylivesbystatus",
    "dataType": "json",
    "valueType": "original",
    "x-i18n-regionID": "LAZADA_TH"
}
```

**请求体（POST body）**:

```json
{
    "data": "{\"_timezone\":-7,\"pageNum\":1,\"pageSize\":100,\"roomStatus\":\"Notice,Online,End,History\",\"orderByRoomStatus\":\"Notice,Online,End,History\"}"
}
```

**响应**: 见 `querylivesbystatus.json`

---

#### 3.2 直播详情

**接口**: `GET /h5/mtop.lazada.live.data.presenter.room.metrics/1.0/`

**采集模式**: 逐场次请求（基于 3.1 返回的 `liveUuid`）

**请求参数**:

```json
{
    "jsv": "2.6.1",
    "appKey": "4272",
    "t": "1775728555795",
    "sign": "04adedcdff86aa36f7ab4eda958ab4fc",
    "v": "1.0",
    "timeout": "30000",
    "H5Request": "true",
    "url": "mtop.lazada.live.data.presenter.room.metrics",
    "x-i18n-language": "en",
    "api": "mtop.lazada.live.data.presenter.room.metrics",
    "type": "originaljson",
    "dataType": "json",
    "valueType": "original",
    "x-i18n-regionID": "LAZADA_TH",
    "data": "{\"liveUuid\":\"caea24b1-57a9-4e35-a603-91af3a9568a7\",\"needCycleRate\":true,\"scene\":\"center_room_overview\",\"type\":\"total\"}"
}
```

**响应**:

```json
{"api":"mtop.lazada.live.data.presenter.room.metrics","data":{"model":{"bizCode":"LAZADA_TH","liveUuid":"caea24b1-57a9-4e35-a603-91af3a9568a7","metrics":[{"desc":"Value of guided livestream orders including shipping fees.","format":"money","key":"guidedGmvLocal","name":"Revenue","sortable":true,"value":788.8}{"desc":"Total units sold of guided livestream orders.","format":"number","key":"guidedUnitPurchase","name":"Units sold","sortable":true,"value":1}{"desc":"Number of orders made within 7 days guided by livestreams featuring your products. Orders include all paid non-COD orders and all confirmed COD orders,including cancelled,returned and refunded orders","format":"number","key":"guidedOrderCnt","name":"Orders","sortable":true,"value":1}{"desc":"Total number of units of products added to cart guided by the livestream","format":"number","key":"guidedA2cQty","name":"Added to cart","sortable":true,"value":1}{"desc":"Number of users that made orders","format":"number","key":"guidedBuyer","name":"Buyers","sortable":true,"value":1}{"desc":"Number of times users click on a highlighted product or a product in the pink basket","format":"number","key":"guidedIpv","name":"Product clicks","sortable":true,"value":4}{"desc":"Number of users that click on products divided by number of viewers in liveroom","format":"percent","key":"productClickRate","name":"Product click rate","sortable":false,"value":13}{"desc":"Number of buyers divided by number of users that click on products","format":"percent","key":"clickToBuyer","name":"Click to buyer","sortable":false,"value":5E+1}{"desc":"Average Revenue per Order","format":"number","key":"aov","name":"Aov","sortable":false,"value":788.8}{"desc":"Number of times your livestreams have been viewed","format":"number","key":"enterPv","name":"Views","sortable":true,"value":25}{"desc":"Average watch duration per Viewer in your livestreams","format":"duration","key":"avgWatchTime","name":"Average watch time","sortable":false,"value":38}{"desc":"Number of new followers acquired through livestreams","format":"number","key":"followersIncrease","name":"New followers","sortable":true,"value":0}{"desc":"Number of likes in your livestreams","format":"number","key":"likePv","name":"Likes","sortable":true,"value":0}],"updatedOn":"2026/04/08"},"msg":"Success"},"ret":["SUCCESS::调用成功"],"v":"1.0"}
```

