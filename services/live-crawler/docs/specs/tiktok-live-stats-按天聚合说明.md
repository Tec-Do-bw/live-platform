# TikTok live/stats 按天聚合与自定义时间说明

## 1. 背景
> 直播分析-关键指标 按天的数据接口官方失效，需要切成自定义天数的接口【自定义天数全部都是按天计算】

当前 `live/stats` 接口存在两种请求方式：

1. 按天聚合
2. 自定义时间

在 `2026-04-30` 这个例子里，两种方式虽然请求参数不同，但最终拿到的是同一天的数据结果，业务含义一致。

## 2. 两种方式的区别

### 2.1 按天聚合

请求参数示例：

```json
{
  "time_selector": {
    "period": 2,
    "granularity": 11,
    "end_timestamp": 1777593600,
    "start_timestamp": 1777420800,
    "timezone_offset": "0"
  }
}
```

含义：

- `granularity = 11` 表示按天聚合
- 请求窗口是 48 小时
- 对目标日 `2026-04-30`，实际传参为：
  - `start_timestamp = 2026-04-29 00:00:00 UTC`
  - `end_timestamp = 2026-05-01 00:00:00 UTC`

也就是用前一天 00:00 UTC 到后一天 00:00 UTC 的窗口，让服务端返回目标日对应的天级数据。

### 2.2 自定义时间

请求参数示例：

```json
{
  "time_selector": {
    "period": 2,
    "granularity": 1,
    "end_timestamp": 1777593600,
    "start_timestamp": 1777507200,
    "timezone_offset": "0"
  }
}
```

含义：

- `granularity = 1` 表示自定义时间窗口
- 请求窗口是 24 小时
- 对目标日 `2026-04-30`，实际传参为：
  - `start_timestamp = 2026-04-30 00:00:00 UTC`
  - `end_timestamp = 2026-05-01 00:00:00 UTC`

也就是直接请求该时间段内的数据。

## 3. 时间计算对比

以 `2026-04-30` 为例：

| 方式 | granularity | start_timestamp | end_timestamp | UTC 时间范围 |
|------|-------------|-----------------|---------------|--------------|
| 按天聚合 | 11 | 1777420800 | 1777593600 | 2026-04-29 00:00:00 ~ 2026-05-01 00:00:00 |
| 自定义时间 | 1 | 1777507200 | 1777593600 | 2026-04-30 00:00:00 ~ 2026-05-01 00:00:00 |

可以看到：

- 两者传参范围不同
- 但目标业务日期都是 `2026-04-30`

## 4. 多国验证：服务端按创作者本地时区对齐

三个国家使用完全相同的请求参数（同一组 UTC 时间戳），服务端根据创作者所在时区自动对齐到本地自然日。

### 4.1 请求参数（三国完全一致）

| 方式 | start_timestamp | end_timestamp | granularity |
|------|-----------------|---------------|-------------|
| 按天聚合 | 1777420800 (04-29 00:00 UTC) | 1777593600 (05-01 00:00 UTC) | 11 |
| 自定义时间 | 1777507200 (04-30 00:00 UTC) | 1777593600 (05-01 00:00 UTC) | 1 |

### 4.2 服务端响应对比

| 国家 | 时区 | timezone_offset | 按天聚合响应范围（本地时间） | 自定义时间响应范围（本地时间） |
|------|------|-----------------|------------------------------|-------------------------------|
| 新加坡 | UTC+8 | 28800 | 2026-04-29 00:00 ~ 05-01 00:00 SGT | 2026-04-30 00:00 ~ 05-01 00:00 SGT |
| 美国 | UTC-8 | -28800 | 2026-04-29 00:00 ~ 05-01 00:00 PST | 2026-04-30 00:00 ~ 05-01 00:00 PST |
| 印尼 | UTC+7 | 25200 | 2026-04-29 00:00 ~ 05-01 00:00 WIB | 2026-04-30 00:00 ~ 05-01 00:00 WIB |

### 4.3 按天聚合的 timed_stats 分桶

按天聚合模式下，服务端返回 2 个分桶（D-1 和 D 的本地自然日）：

| 国家 | 分桶 1（本地 D-1） | 分桶 2（本地 D） |
|------|---------------------|-------------------|
| 新加坡 | 04-29 00:00 ~ 04-30 00:00 SGT | 04-30 00:00 ~ 05-01 00:00 SGT |
| 美国 | 04-29 00:00 ~ 04-30 00:00 PST | 04-30 00:00 ~ 05-01 00:00 PST |
| 印尼 | 04-29 00:00 ~ 04-30 00:00 WIB | 04-30 00:00 ~ 05-01 00:00 WIB |

自定义时间模式下，只返回 1 个分桶，时间范围与按天聚合的分桶 2 完全一致。

### 4.4 数据一致性验证

| 国家 | 按天聚合分桶 2 的 live_revenue | 自定义时间的 live_revenue | 是否一致 |
|------|-------------------------------|--------------------------|----------|
| 新加坡 | S$386.54 | S$386.54 | 完全一致 |
| 美国 | $3,792.84 | $3,792.84 | 金额一致 |
| 印尼 | Rp38,892,790 | Rp38,892,790 | 金额一致 |

注意：美国和印尼的部分订单指标（如 `sku_order_paid_cnt`、`live_pay_order_ucnt`）在两种模式间存在微小差异，这是因为两次请求时间不同，期间有新订单确认。核心指标（revenue、show_cnt、watch_cnt 等）完全一致。

### 4.5 结论

规律在三个国家完全一致：

- 请求参数不区分国家，统一用 UTC 时间戳
- 服务端自动按创作者本地时区对齐日界线
- 按天聚合返回 2 天分桶，自定义时间返回 1 天分桶
- 两种模式对目标日（2026-04-30）的数据业务含义相同

## 5. 结论

### 5.1 相同点

两种方式在 `2026-04-30` 这个例子中，最终拿到的是同一天的数据，业务含义一致。

### 5.2 不同点

主要区别在请求协议层：

1. `granularity` 不同
   - 按天聚合：`11`
   - 自定义时间：`1`

2. 请求时间窗口不同
   - 按天聚合：48 小时窗口
   - 自定义时间：24 小时窗口

3. 返回结构可能不同
   - 按天聚合可能返回多个 `timed_stats` 分段
   - 自定义时间通常只返回目标日对应的单段数据

## 6. 对接建议

上下游对接时可按下面规则区分：

- 如果看到 `granularity = 11`，这是按天聚合请求
- 如果看到 `granularity = 1`，这是自定义时间请求

但在业务解释上，应统一按目标自然日数据理解，不要仅根据 UTC 请求窗口长度判断是不是同一天。

## 7. 一句话说明

对于 `2026-04-30`，按天聚合和自定义时间两种请求方式虽然时间参数不同，但服务端最终都落到同一个业务日期，因此结果可以按同一天数据理解，只是请求协议和时间窗口定义不同。

## 8. 数据说明（新加坡地区示例）

以下为新加坡地区 `2026-04-30` 的实际请求参数与响应，供数仓解析参考。

### 8.1 按天聚合（granularity = 11）

**请求参数：**

```json
{
  "request": {
    "params": [
      {
        "time_selector": {
          "period": 2,
          "granularity": 11,
          "end_timestamp": 1777593600,
          "start_timestamp": 1777420800,
          "timezone_offset": "0"
        },
        "stats_types": [11, 115, 13, 200, 106, 81, 82, 201, 202, 70, 210, 211, 212, 213],
        "is_live_type": true
      }
    ]
  },
  "version": "2"
}
```

**响应（取 timed_stats 最后一个分桶即为目标日数据）：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "segments": [
      {
        "time_selector": {
          "period": 2,
          "granularity": 11,
          "timezone_offset": 28800,
          "start_timestamp": 1777392000,
          "end_timestamp": 1777564800,
          "locale": "en-SG"
        },
        "filter": {
          "creator_id": "7316918121109324818"
        },
        "timed_stats": [
          {
            "start_timestamp": 1777392000,
            "end_timestamp": 1777478400,
            "stats": {
              "live_revenue": {"amount_formatted": "S$0.00", "amount_delimited": "0.00", "amount": "0", "currency_code": "SGD", "currency_symbol": "S$"},
              "live_show_gpm": {"amount_formatted": "S$0.00", "amount_delimited": "0.00", "amount": "0", "currency_code": "SGD", "currency_symbol": "S$"},
              "new_follower_cnt": 1,
              "sku_order_paid_cnt": 0,
              "item_sold_cnt": 0,
              "product_view": 797,
              "product_click": 44,
              "live_pay_order_ucnt": 0,
              "live_ctr": "0.1888",
              "live_co": "0.0000",
              "live_like_cnt": 10,
              "live_comment_cnt": 6,
              "live_show_cnt": 5968,
              "live_watch_cnt": 233
            }
          },
          {
            "start_timestamp": 1777478400,
            "end_timestamp": 1777564800,
            "stats": {
              "live_revenue": {"amount_formatted": "S$386.54", "amount_delimited": "386.54", "amount": "386.54", "currency_code": "SGD", "currency_symbol": "S$"},
              "live_show_gpm": {"amount_formatted": "S$25.29", "amount_delimited": "25.29", "amount": "25.29", "currency_code": "SGD", "currency_symbol": "S$"},
              "new_follower_cnt": 1,
              "sku_order_paid_cnt": 1,
              "item_sold_cnt": 1,
              "product_view": 2479,
              "product_click": 67,
              "live_pay_order_ucnt": 1,
              "live_ctr": "0.1530",
              "live_co": "0.0149",
              "live_like_cnt": 6,
              "live_comment_cnt": 4,
              "live_show_cnt": 15286,
              "live_watch_cnt": 438
            }
          }
        ]
      }
    ]
  }
}
```

### 8.2 自定义时间（granularity = 1）

**请求参数：**

```json
{
  "request": {
    "params": [
      {
        "time_selector": {
          "period": 2,
          "granularity": 1,
          "end_timestamp": 1777593600,
          "start_timestamp": 1777507200,
          "timezone_offset": "0"
        },
        "stats_types": [11, 115, 13, 200, 106, 81, 82, 201, 202, 70, 210, 211, 212, 213],
        "is_live_type": true
      }
    ]
  },
  "version": "2"
}
```

**响应（只返回 1 个分桶，即目标日数据）：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "segments": [
      {
        "time_selector": {
          "period": 2,
          "granularity": 1,
          "timezone_offset": 28800,
          "start_timestamp": 1777478400,
          "end_timestamp": 1777564800,
          "locale": "en-SG"
        },
        "filter": {
          "creator_id": "7316918121109324818"
        },
        "timed_stats": [
          {
            "start_timestamp": 1777478400,
            "end_timestamp": 1777564800,
            "stats": {
              "live_revenue": {"amount_formatted": "S$386.54", "amount_delimited": "386.54", "amount": "386.54", "currency_code": "SGD", "currency_symbol": "S$"},
              "live_show_gpm": {"amount_formatted": "S$25.29", "amount_delimited": "25.29", "amount": "25.29", "currency_code": "SGD", "currency_symbol": "S$"},
              "new_follower_cnt": 1,
              "sku_order_paid_cnt": 1,
              "item_sold_cnt": 1,
              "product_view": 2479,
              "product_click": 67,
              "live_pay_order_ucnt": 1,
              "live_ctr": "0.1530",
              "live_co": "0.0149",
              "live_like_cnt": 6,
              "live_comment_cnt": 4,
              "live_show_cnt": 15286,
              "live_watch_cnt": 438
            }
          }
        ]
      }
    ]
  }
}
```

### 8.3 解析要点

1. **按天聚合**返回 2 个 `timed_stats` 分桶，数仓应取**最后一个分桶**作为目标日数据
2. **自定义时间**只返回 1 个分桶，直接使用即可
3. 金额字段使用 `amount` 做数值计算，`currency_code` 标识币种
4. 比率字段（`live_ctr`、`live_co`）为字符串格式的小数，需转为浮点数