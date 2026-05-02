# 采集监控系统 - Brainstorm 总结

**日期**: 2026-03-06
**参与者**: XBW + Claude

---

## 1. 痛点分析

- live-dp 数据采集完整性无法自主监控，依赖后端/前端人工反馈缺失数据后被动补采
- 数据流经多层加工，缺失环节不可见
- 现有系统问题：账号登出后 API 数据=0 仍被统计为"成功"，造成数据丢失不可感知
- 告警系统已写好但未启用

## 2. 核心目标

**按账号维度，监控每次采集后 V1 核心指标对应的 API 数据是否已采集并上报。不校验数据正确性，只校验数据是否存在。**

## 3. V1 核心指标 API 清单

### 账号级 API

| API | 说明 |
|-----|------|
| `/api/v2/insights/creator/live/list` | 直播间列表 |
| `/api/v2/insights/creator/live/stats` (7天) | 关键指标 |
| `/api/v2/insights/creator/live/stats` (单日昨日) | 关键指标-昨日 |
| `/api/v2/insights/creator/live/stats` (数据概览) | 数据概览-关键指标 |
| `/api/v1/streamer_desktop/account_info/get` | 账号信息 |

### 直播间级 API（每个直播场次都需要）

| API | 说明 |
|-----|------|
| `/api/v1/insights/creator/liveroom/recap/core/stats` | 详情-关键指标 |
| `/api/v1/insights/creator/liveroom/recap/trend/chart` (stats_type=52) | 详情-成交趋势 |
| `/api/v1/insights/creator/liveroom/recap/product/list` | 详情-商品列表 |
| `/api/v1/insights/workbench/live/detail/core/stats` | 详情-流量转化 |
| `/api/v1/insights/creator/liveroom/recap/trend/chart` (stats_type=60/61) | 详情-流量趋势 |
| `/api/v1/insights/creator/liveroom/recap/viewer/source/stats` | 详情-用户画像 |
| `/api/v1/insights/creator/liveroom/recap/trend/chart` (内容分析) | 详情-直播趋势 |
| `webcast/room/replay/info` | 直播录像列表 |

## 4. 方案评估

| 方案 | 描述 | 结论 |
|------|------|------|
| A. 爬虫侧嵌入式监控 | 在 send_api_request 处加钩子，记录到 SQLite | **采纳** |
| B. 独立 Kafka 消费服务 | 消费 Kafka topic 建立完整性矩阵 | 淘汰（Kafka 不稳定） |
| C. 后端 API 反查 | 调后端接口反查数据是否入库 | 淘汰（依赖后端配合） |

## 5. 最终方案：方案 A + 前端监控面板

### 架构

```
live_dp 爬虫 --> send_api_request 钩子 --> 写入 SQLite
                                              |
FastAPI REST API <-----------------------------+
      |
Vue3 前端 SPA（由 FastAPI 托管静态文件）
```

### 技术栈

| 层级 | 技术 |
|------|------|
| 监控数据存储 | SQLite |
| 后端 API | FastAPI |
| 前端 | Vue3 |
| 部署 | FastAPI 托管前端静态文件，单服务启动 |

### 数据模型

```
collection_records 表
- id (主键)
- batch_id (采集批次，如 "2026-03-05_20:00")
- platform (tiktok/shopee)
- account_id (浏览器ID)
- group_name (分组)
- room_id (直播间ID，账号级API为空)
- api_type (枚举: live_list / live_stats_7d / core_stats / ...)
- api_url (实际URL)
- status (success/failed)
- collected_at (采集时间)
- response_size (响应大小，用于判断是否空数据)
```

### 前端页面（MVP 3个页面）

1. **总览 Dashboard** - 总账号数、完整/缺失账号、整体完整率、账号列表（支持筛选）
2. **账号详情** - 账号级 API 采集状态 + 该账号下所有直播场次列表及完整性
3. **直播间详情** - V1 核心指标 Checklist，逐项显示采集状态，支持触发补采

## 6. 后续迭代方向

- V2: 监控数据正确性（关键字段非空校验）
- V2: 接入告警通道（钉钉/企业微信），缺失自动通知
- V3: 自动补采闭环（检测到缺失 → 自动触发补采 → 验证补采结果）
