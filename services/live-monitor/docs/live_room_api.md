## 直播间拉流接口文档

### 通用约定
- Host：服务端同 main.py 部署地址
- 认证：请求头 `access-token: AFDD0B4AD2EC172C586E2150770FBF9E`
- 请求体：`application/json`
- 响应体：`application/json`

### 公共字段说明
- `code`：业务状态码，成功为 `200`，鉴权失败返回 `401`
- `message`：业务描述
- `data`：载荷
  - `mateUrl`：请求的直播间原始地址
  - `port_info`：直播解析结果
    - `flv_url`：首选 FLV 播放地址，未开播时为空或 `error`
    - `play_urls`：可用播放地址列表（多清晰度 FLV/HLS）
    - `roomId`：平台房间/直播间 ID
    - `startTime`：开播时间（时间戳或字符串，平台原样）
    - `filePath`：用于本地保存的文件路径名（店铺/主播标识）
    - 其他平台特有字段：
      - TikTok：`secUid`、`uniqueId`、`signature`、`id`、`nickname`、`url`
      - Lazada：`liveUuid`（前台直播场次id）、`roomStatus`、`title`、`mediaUserId`（媒体用户ID）、`mediaUserName`（媒体用户名称）
      - Shopee：`session`（包含直播元数据）
    - 错误场景：`message` 字段体现错误原因，例如 `直播间不存在`、`采集异常`

### 接口列表

#### 1) 获取 TikTok 直播间信息
- 方法：`POST /liveRoom/portInfo`
- Headers：`access-token` 必填
- Body：
```json
{ "mateUrl": "https://www.tiktok.com/@xxx/live" }
```
- 响应示例
  - 成功（示例来自 `docs/example_data/TiktokLive.json`）：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "port_info": {
      "startTime": "1756642228",
      "flv_url": "",
      "secUid": "…",
      "uniqueId": "petersonslabbeauty",
      "roomId": "7544720840995162887",
      "signature": "…",
      "id": "7475615528578941968",
      "nickname": "petersonslab.my.skincare",
      "url": "https://www.tiktok.com/@petersonslabbeauty/live",
      "filePath": "petersonslabbeauty"
    },
    "mateUrl": "https://www.tiktok.com/@petersonslabbeauty/live"
  }
}
```
  - 采集异常（异常捕获，例如解析失败）：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "port_info": { "flv_url": "error", "roomId": "", "message": "tk采集异常", "filePath": "" },
    "mateUrl": "<原始链接>"
  }
}
```
  - 直播间不存在（命中 `errorUrl.txt` 或解析失败）：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "port_info": { "flv_url": "error", "roomId": "", "message": "直播间不存在", "filePath": "" },
    "mateUrl": "<原始链接>"
  }
}
```
  - 鉴权失败：
```json
{ "code": 401, "message": "Unauthorized" }
```

#### 2) 获取 Shopee 直播间信息
- 方法：`POST /liveRoom/shopeeInfo`
- Headers：`access-token` 必填
- Body：
```json
{ "mateUrl": "https://my.shp.ee/xxxx" }
```
- 响应示例
  - 成功（示例来自 `docs/example_data/ShopeeLive.json`）：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "port_info": {
      "session": { "...": "直播元数据" },
      "play_urls": ["https://play-tx-las.livetech.shopee.com.my/live/my-live-2436-14217105.flv?..."],
      "flv_url": "https://play-tx-las.livetech.shopee.com.my/live/my-live-2436-14217105.flv?...",
      "filePath": "maybellinemy",
      "startTime": 1765530323368
    },
    "mateUrl": "https://my.shp.ee/mLYd9Av"
  }
}
```
  - 直播间不存在（命中 `errorUrl.txt`）：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "port_info": { "flv_url": "error", "roomId": "", "message": "直播间不存在", "filePath": "" },
    "mateUrl": "<原始链接>"
  }
}
```
  - 采集异常（异常捕获）：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "port_info": { "flv_url": "error", "roomId": "", "message": "shopee采集异常", "filePath": "" },
    "mateUrl": "<原始链接>"
  }
}
```
  - 鉴权失败同上

#### 3) 获取 Lazada 直播间信息
- 方法：`POST /liveRoom/lazadaInfo`
- Headers：`access-token` 必填
- Body：
```json
{ "mateUrl": "https://s.lazada.com.xx/xxxx" }
```
- 响应示例
  - 成功（示例来自 `docs/example_data/LazadaLive.json`）：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "port_info": {
      "roomId": "10026286",
      "liveUuid": "7aca9015-f670-4fcd-aead-f02c3f7c8ad1",
      "roomStatus": "Online",
      "title": "12.12 CHRISTMAS SALES IS HERE 🎄",
      "startTime": 1765516431000,
      "play_urls": ["http://pull-live.lazcdn.com/..._new-720p.flv?...", "..."],
      "flv_url": "http://pull-live.lazcdn.com/peacock/7aca9015-f670-4fcd-aead-f02c3f7c8ad1_new-720p.flv?...",
      "filePath": "teamfulove",
      "mediaUserId": "300680704072",
      "mediaUserName": "teamfulove"
    },
    "mateUrl": "<请求地址>"
  }
}
```
  - 直播间不存在/短链失效（302）：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "port_info": { "flv_url": "error", "roomId": "", "message": "直播间不存在", "filePath": "" },
    "mateUrl": "<原始链接>"
  }
}
```
  - 当前暂无直播：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "port_info": {
      "flv_url": "error",
      "roomId": "10026286",
      "message": "当前暂无直播",
      "filePath": "",
      "mediaUserId": "300680704072",
      "mediaUserName": "teamfulove"
    },
    "mateUrl": "<原始链接>"
  }
}
```
  - 采集异常（异常捕获）：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "port_info": { "flv_url": "error", "roomId": "", "message": "lazada采集异常", "filePath": "" },
    "mateUrl": "<原始链接>"
  }
}
```
  - 鉴权失败同上

### 状态与判定逻辑摘要
- 鉴权失败：`access-token` 不匹配返回 `401`
- 已知错误链接：TikTok/Shopee 会优先检查 `errorUrl.txt`，命中即返回不存在结构
- Lazada：
  - HTTP 302 或未取到 `lazada_share_info` 视为不存在
  - `roomStatus` 为 `History` 且无 `onlineLiveJumpUrl` 时返回"当前暂无直播"，但仍包含用户信息（`mediaUserId`、`mediaUserName`）
- 解析异常：捕获异常时返回 `flv_url: "error"`，并在 `message` 中标注采集异常

### 历史请求耗时（内部压测100次参考）
- Shopee：平均 5.83 秒，最长 15.93 秒
- TikTok：平均 1.35 秒，最长 2.74 秒
- Lazada：平均 0.30 秒，最长 2.82 秒

### 版本
- 文档生成时间：2025-12-12

