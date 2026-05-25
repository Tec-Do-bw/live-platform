# 直播间拉流接口文档（v2）

> **版本**：v2.0（响应标准化）
> **状态**：规范已定稿，代码实施中
> **设计文档**：[`docs/designs/2026-05-25-live-room-api-standardization.md`](../designs/2026-05-25-live-room-api-standardization.md)
> **更新日期**：2026-05-25

---

## 通用约定

| 项 | 说明 |
|----|------|
| Host | 服务端同 main.py 部署地址 |
| 认证 | 请求头 `access-token: AFDD0B4AD2EC172C586E2150770FBF9E` |
| 请求体 | `application/json` |
| 响应体 | `application/json`，HTTP 状态码始终 200（鉴权失败除外，HTTP 401） |

---

## 统一响应结构

### 成功（`code` = 200 / 2001 / 2002）

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "mateUrl": "<原始请求链接>",
    "port_info": { /* 平台数据 */ }
  }
}
```

### 失败（`code` = 4xxx / 5xxx）

```json
{
  "code": 5002,
  "message": "上游响应解析失败",
  "data": {
    "mateUrl": "<原始请求链接>",
    "port_info": null
  },
  "error": {
    "platform": "tiktok",
    "reason": "PARSE_FAILED",
    "detail": "SIGI_STATE 提取失败"
  }
}
```

### 鉴权失败（HTTP 401）

```json
{ "code": 401, "message": "Unauthorized" }
```

---

## 业务码字典

| code | 含义 | 调用方行为建议 |
|------|------|----------------|
| `200` | 正常直播中 | 启动录制 / 消费 `flv_url` |
| `2001` | 当前未开播 | 更新主播档案，不启动录制 |
| `2002` | 历史直播已结束 | 同上 |
| `401` | 未授权 | 检查 access-token |
| `4001` | 入参缺失（mateUrl 为空） | 修正请求 |
| `4002` | 入参格式错误（URL 不属于支持平台） | 修正请求 |
| `4041` | 直播间不存在 | 标记链接失效，不再重试 |
| `4042` | 短链已失效 | 同上 |
| `5001` | 上游请求失败（超时/网络错误） | 可重试 |
| `5002` | 上游响应解析失败 | 可重试（可能是临时页面变更） |
| `5003` | 上游限流或风控 | 延迟重试 |
| `5099` | 采集内部异常（兜底） | 可重试 |

> **重试策略建议**：`4xxx` 不可重试（资源/入参问题）；`5xxx` 可重试（建议指数退避，最多 3 次）。

---

## `error.reason` 枚举

| reason | 对应 code | 说明 |
|--------|-----------|------|
| `INVALID_PARAM` | 4001 / 4002 | 入参问题 |
| `ROOM_NOT_FOUND` | 4041 | 直播间不存在 |
| `SHORT_URL_EXPIRED` | 4042 | 短链失效 |
| `UPSTREAM_REQUEST_FAILED` | 5001 | 上游 HTTP 请求失败 |
| `PARSE_FAILED` | 5002 | 上游响应解析失败 |
| `RATE_LIMITED` | 5003 | 上游限流/风控 |
| `INTERNAL_ERROR` | 5099 | 未分类内部异常 |

---

## 字段说明

### 顶层字段

| 字段 | 类型 | 始终存在 | 说明 |
|------|------|----------|------|
| `code` | int | 是 | 业务码 |
| `message` | str | 是 | 人类可读说明，**不参与逻辑判断** |
| `data` | object | 是（鉴权失败除外） | 载荷 |
| `error` | object | 仅失败时 | 错误详情 |

### `data` 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `mateUrl` | str | 原始请求链接 |
| `port_info` | object \| null | 成功时为平台数据；失败时为 `null` |

### `error` 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `platform` | str | `tiktok` \| `shopee` \| `lazada` |
| `reason` | str | 机器可读枚举（见上表） |
| `detail` | str | 简要原因摘要（不含堆栈） |

### `port_info` 公共字段（`code=200` 时）

| 字段 | 类型 | 说明 |
|------|------|------|
| `flv_url` | str | 首选 FLV 播放地址（**仅 code=200 时存在且非空**） |
| `play_urls` | list[str] | 可用播放地址列表（多清晰度） |
| `roomId` | str | 平台房间 ID |
| `startTime` | str \| int | 开播时间（平台原样） |
| `filePath` | str | 本地保存路径标识（店铺/主播） |

### `port_info` 平台特有字段

**TikTok**（`code=200` 或 `code=2001`）：

| 字段 | 说明 |
|------|------|
| `secUid` | 加密用户 ID |
| `uniqueId` | 用户名 |
| `signature` | 签名 |
| `id` | 用户数字 ID |
| `nickname` | 昵称 |
| `url` | 直播间完整 URL |

**Lazada**（`code=200` 或 `code=2002`）：

| 字段 | 说明 |
|------|------|
| `liveUuid` | 直播场次 UUID |
| `roomStatus` | 房间状态（`Online` / `History`） |
| `title` | 直播标题 |
| `mediaUserId` | 媒体用户 ID |
| `mediaUserName` | 媒体用户名称 |

**Shopee**（`code=200` 或 `code=2001`）：

| 字段 | 说明 |
|------|------|
| `session` | 直播元数据对象 |

---

## 接口列表

### 1) 获取 TikTok 直播间信息

- **方法**：`POST /liveRoom/portInfo`
- **Headers**：`access-token` 必填
- **Body**：
```json
{ "mateUrl": "https://www.tiktok.com/@xxx/live" }
```

#### 响应示例

**正常直播中（code=200）**：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "mateUrl": "https://www.tiktok.com/@petersonslabbeauty/live",
    "port_info": {
      "flv_url": "https://pull-flv-l1-mus.pstatp.com/...",
      "play_urls": ["https://pull-flv-l1-mus.pstatp.com/..."],
      "startTime": "1756642228",
      "secUid": "MS4wLjABAAAA...",
      "uniqueId": "petersonslabbeauty",
      "roomId": "7544720840995162887",
      "signature": "...",
      "id": "7475615528578941968",
      "nickname": "petersonslab.my.skincare",
      "url": "https://www.tiktok.com/@petersonslabbeauty/live",
      "filePath": "petersonslabbeauty"
    }
  }
}
```

**当前未开播（code=2001）**：
```json
{
  "code": 2001,
  "message": "当前未开播",
  "data": {
    "mateUrl": "https://www.tiktok.com/@petersonslabbeauty/live",
    "port_info": {
      "secUid": "MS4wLjABAAAA...",
      "uniqueId": "petersonslabbeauty",
      "roomId": "7544720840995162887",
      "signature": "...",
      "id": "7475615528578941968",
      "nickname": "petersonslab.my.skincare",
      "url": "https://www.tiktok.com/@petersonslabbeauty/live",
      "filePath": "petersonslabbeauty"
    }
  }
}
```

**直播间不存在（code=4041）**：
```json
{
  "code": 4041,
  "message": "直播间不存在",
  "data": {
    "mateUrl": "https://www.tiktok.com/@sndjksdahjkdncdhjdfb/live",
    "port_info": null
  },
  "error": {
    "platform": "tiktok",
    "reason": "ROOM_NOT_FOUND",
    "detail": "用户信息不存在"
  }
}
```

**上游请求失败（code=5001）**：
```json
{
  "code": 5001,
  "message": "上游请求失败",
  "data": {
    "mateUrl": "https://www.tiktok.com/@xxx/live",
    "port_info": null
  },
  "error": {
    "platform": "tiktok",
    "reason": "UPSTREAM_REQUEST_FAILED",
    "detail": "请求直播页超时"
  }
}
```

**采集内部异常（code=5099）**：
```json
{
  "code": 5099,
  "message": "采集内部异常",
  "data": {
    "mateUrl": "https://www.tiktok.com/@xxx/live",
    "port_info": null
  },
  "error": {
    "platform": "tiktok",
    "reason": "INTERNAL_ERROR",
    "detail": "JSON 解码失败"
  }
}
```

---

### 2) 获取 Shopee 直播间信息

- **方法**：`POST /liveRoom/shopeeInfo`
- **Headers**：`access-token` 必填
- **Body**：
```json
{ "mateUrl": "https://my.shp.ee/xxxx" }
```

#### 响应示例

**正常直播中（code=200）**：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "mateUrl": "https://my.shp.ee/mLYd9Av",
    "port_info": {
      "session": { "uid": 14217105, "username": "maybellinemy", "play_url": "..." },
      "play_urls": ["https://play-tx-las.livetech.shopee.com.my/live/my-live-2436-14217105.flv?..."],
      "flv_url": "https://play-tx-las.livetech.shopee.com.my/live/my-live-2436-14217105.flv?...",
      "filePath": "maybellinemy",
      "startTime": 1765530323368
    }
  }
}
```

**当前未开播（code=2001）**：
```json
{
  "code": 2001,
  "message": "当前未开播",
  "data": {
    "mateUrl": "https://my.shp.ee/mLYd9Av",
    "port_info": {
      "session": { "uid": 14217105, "username": "maybellinemy" },
      "filePath": "maybellinemy"
    }
  }
}
```

**直播间不存在（code=4041）**：
```json
{
  "code": 4041,
  "message": "直播间不存在",
  "data": {
    "mateUrl": "https://my.shp.ee/xxxx",
    "port_info": null
  },
  "error": {
    "platform": "shopee",
    "reason": "ROOM_NOT_FOUND",
    "detail": "短链解析无有效 session URL"
  }
}
```

**采集内部异常（code=5099）**：
```json
{
  "code": 5099,
  "message": "采集内部异常",
  "data": {
    "mateUrl": "https://my.shp.ee/xxxx",
    "port_info": null
  },
  "error": {
    "platform": "shopee",
    "reason": "INTERNAL_ERROR",
    "detail": "session 数据获取超时"
  }
}
```

---

### 3) 获取 Lazada 直播间信息

- **方法**：`POST /liveRoom/lazadaInfo`
- **Headers**：`access-token` 必填
- **Body**：
```json
{ "mateUrl": "https://s.lazada.com.xx/xxxx" }
```

#### 响应示例

**正常直播中（code=200）**：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "mateUrl": "https://s.lazada.com.my/s.4Uxxx",
    "port_info": {
      "roomId": "10026286",
      "liveUuid": "7aca9015-f670-4fcd-aead-f02c3f7c8ad1",
      "roomStatus": "Online",
      "title": "12.12 CHRISTMAS SALES IS HERE",
      "startTime": 1765516431000,
      "play_urls": [
        "http://pull-live.lazcdn.com/peacock/7aca9015..._new-720p.flv?...",
        "http://pull-live.lazcdn.com/peacock/7aca9015..._new-480p.flv?..."
      ],
      "flv_url": "http://pull-live.lazcdn.com/peacock/7aca9015..._new-720p.flv?...",
      "filePath": "teamfulove",
      "mediaUserId": "300680704072",
      "mediaUserName": "teamfulove"
    }
  }
}
```

**历史直播已结束（code=2002）**：
```json
{
  "code": 2002,
  "message": "历史直播已结束",
  "data": {
    "mateUrl": "https://s.lazada.com.my/s.4Uxxx",
    "port_info": {
      "roomId": "10026286",
      "mediaUserId": "300680704072",
      "mediaUserName": "teamfulove"
    }
  }
}
```

**直播间不存在（code=4041）**：
```json
{
  "code": 4041,
  "message": "直播间不存在",
  "data": {
    "mateUrl": "https://s.lazada.com.my/s.xxxx",
    "port_info": null
  },
  "error": {
    "platform": "lazada",
    "reason": "ROOM_NOT_FOUND",
    "detail": "短链 302 重定向，无有效直播间"
  }
}
```

**上游请求失败（code=5001）**：
```json
{
  "code": 5001,
  "message": "上游请求失败",
  "data": {
    "mateUrl": "https://s.lazada.com.my/s.xxxx",
    "port_info": null
  },
  "error": {
    "platform": "lazada",
    "reason": "UPSTREAM_REQUEST_FAILED",
    "detail": "mtop.lazada.live.query 请求超时"
  }
}
```

**上游响应解析失败（code=5002）**：
```json
{
  "code": 5002,
  "message": "上游响应解析失败",
  "data": {
    "mateUrl": "https://s.lazada.com.my/s.xxxx",
    "port_info": null
  },
  "error": {
    "platform": "lazada",
    "reason": "PARSE_FAILED",
    "detail": "直播数据为空"
  }
}
```

---

## 调用方判断逻辑（推荐）

```python
response = requests.post(url, json={"mateUrl": mate_url}, headers=headers).json()

code = response["code"]

if code == 200:
    # 正在直播，消费 flv_url
    flv_url = response["data"]["port_info"]["flv_url"]
    start_recording(flv_url)

elif code in (2001, 2002):
    # 用户存在但未开播，可更新主播档案
    port_info = response["data"]["port_info"]
    update_streamer_profile(port_info)

elif code == 401:
    raise AuthError("access-token 无效")

elif 4000 <= code < 5000:
    # 资源/入参问题，不重试
    reason = response["error"]["reason"]
    mark_url_invalid(mate_url, reason)

elif 5000 <= code < 6000:
    # 服务端/上游问题，可重试
    reason = response["error"]["reason"]
    schedule_retry(mate_url, reason)
```

---

## 历史请求耗时（内部压测 100 次参考）

| 平台 | 平均耗时 | 最长耗时 |
|------|----------|----------|
| Shopee | 5.83s | 15.93s |
| TikTok | 1.35s | 2.74s |
| Lazada | 0.30s | 2.82s |

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v2.0 | 2026-05-25 | 响应标准化：业务 code 区分错误类型，新增 error 对象，移除 flv_url 魔法值 |
| v1.0 | 2025-12-12 | 初版文档 |
