# Shopee 回放直播间详情数据调研报告

## 1. 调研背景

### 1.1 调研目标
- 补充 Shopee 回放直播间（liveList/v2 来源）的详情数据采集接口
- 对比实时直播间（sessionList 来源）与回放直播间的接口差异
- 为后续实现回放直播间详情采集提供技术方案

### 1.2 调研方法
- 使用 chrome-devtools 工具访问 Shopee 回放直播间详情页
- 分析网络请求，提取关键接口和参数
- 对比实时直播间和回放直播间的接口差异

## 2. 调研结果

### 2.1 回放直播间详情接口

通过分析 `https://seller.shopee.com.my/creator-center/insight/live/15684298` 页面，发现回放直播间使用以下 2 个详情接口：

#### 接口 1: liveDetail

**基本信息**
- **URL**: `GET /api/supply/lm/sellercenter/liveDetail?sessionId={sessionId}`
- **作用**: 获取回放直播间的基础信息和汇总指标
- **采集方式**: JS 注入

**关键请求头**
```
x-region: my
x-region-domain: com.my
x-region-timezone: +0800
language: en
x-env: live
accept: application/json
content-type: application/json
```

**响应数据结构**
```json
{
  "code": 0,
  "data": {
    "liveInfo": {
      "sessionId": 15684298,
      "title": "Baju Bersih & Wangi!! Join now!",
      "status": 2,
      "coverImage": "https://cf.shopee.com.my/file/...",
      "startTime": 1774843257489,
      "duration": 35959625
    },
    "performance": {
      "views": 172810,
      "viewers": 70445,
      "likes": 21269,
      "comments": 172,
      "shares": 51,
      "paidOrders": 71,
      "paidSales": 1954.64,
      "confirmedOrders": 71,
      "confirmedSales": 1954.64,
      "placedOrders": 73,
      "placedSales": 1987.55,
      "itemPlacedOrders": 77,
