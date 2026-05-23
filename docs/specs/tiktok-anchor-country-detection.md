# TikTok 主播开播国家识别规范

> 状态：主路径与降级路径已实测验证（2026-05-22）
> 适用：直播间监控、ADS Power VPN 出口分配
> 鉴权：全程无需登录被监控主播账号；爬虫账号 cookie 可选

## 目标

给定**任一 TikTok 主播相关 URL**（直播间 / 主页 / 视频页），输出该主播账号当前实际运营所在的 ISO-3166 alpha-2 国家码（如 `VN` / `ID` / `TH`），用于：
- 给主播匹配同区域的 ADS Power 浏览器 VPN 出口
- 校验主播 IP 与业务运营区域一致

## 入口归一化

无论输入是哪种 TK URL，先解析出 `<handle>`：

| 输入 URL 形态 | handle 抠取正则 |
|---|---|
| `https://www.tiktok.com/@<handle>/live` | `r'/@([^/?#]+)'` |
| `https://www.tiktok.com/@<handle>` | 同上 |
| `https://www.tiktok.com/@<handle>/video/<vid>` | 同上 |
| `https://vm.tiktok.com/<shortcode>` | 先 HEAD 取 Location 头跟随重定向，再走上方正则 |

## 三级链路总览

按准确度排序，自上而下尝试，前一条命中即返回：

| 级别 | 数据源 | 字段语义 | 命中前提 |
|------|--------|----------|----------|
| 主路径 | `webcast/gift/list/`（webcast）| 主播**当前实际运营国** | 主播在播或刚下播，能拿到 `room_id` |
| 离线兜底 | 持久化历史 `room_id` 重放主路径 | 同上（主播上一场运营国）| 项目库中存有该 handle 的历史 `room_id` |
| 最终 fallback | 视频 SSR 的 `locationCreated` | 视频**上传时**的网络出口国 | 主播至少有 1 条公开视频 |

---

## 主路径：`webcast/gift/list/` → `pages[0].region`

### 接口

```
GET https://webcast.us.tiktok.com/webcast/gift/list/
```

### 必传参数

| 参数 | 取值 | 说明 |
|------|------|------|
| `room_id` | 主播当前直播间 ID（18~20 位数字串） | 由直播间 SSR HTML 中的 `room_id` 字段获取 |
| `aid` | `1988` | TikTok Web 固定 app id |
| `app_language` | `en` | 仅影响错误文案，不影响 region 字段 |
| `channel` | `tiktok_web` | 固定 |
| `device_platform` | `web_pc` | 固定 |
| `region` | `US`（任意值即可）| 这是访客 region，不影响响应中的 `pages[0].region` |
| `webcast_language` | `en` | 同 `app_language` |
| `device_id` | 任意 19 位数字串 | webmssdk 设备指纹，匿名亦可生成 |

### 响应字段

```
data.pages[0].region   ← ISO-3166 alpha-2 主播运营国
```

**字段语义**：`pages[0].region` 是 TikTok 内部按主播账号运营国分发的礼物面板配置标识，**直接绑定主播账号注册/运营所在的 TikTok Shop 区域**，与访客 IP、直播 CDN、上传 IP 均无关。

### `room_id` 获取

```
GET https://www.tiktok.com/@<handle>/live
→ 响应 HTML 中正则匹配 `(?:room_id|roomId|liveRoomId)\s*[:=]\s*["']?(\d{15,22})`
```

主播在播时返回有效 `room_id`；下播后 `room_id` 字段消失或对应房间状态置为关闭。

### 鉴权与签名

- 不需要登录被监控主播账号
- 不需要登录任何 TikTok 真实用户账号
- 需要 `X-Bogus` / `X-Gnarly` 签名（项目已有），签名输入即上述 query string
- `msToken` 可选；不带也能通

### 实测验证

| handle | room_id | 返回 region | cm 标注 | 一致 |
|---|---|---|---|---|
| `skechersvnfashion` | 7642545542178294535 | **VN** | VN | ✅ |
| `odolparfumholic` | 上一场房间 | **ID** | ID | ✅ |

---

## 离线兜底：主播不在播

主路径要求 `room_id` 存活。当 `/@<handle>/live` 返回 "主播未在直播" 时，按以下顺序兜底：

### 兜底 1：使用持久化的历史 `room_id`

- 项目库（`services/live-monitor`）已持久化每个被监控主播的最近一次 `room_id`
- 直接拿历史 `room_id` 重放主路径请求
- TikTok 服务端对已结束的 `room_id` **仍会返回** `pages[0].region`（实测 odolparfumholic 即为下播状态命中）

### 兜底 2：触发一次直播态轮询，等待最近一场

- 监控服务本身就是周期性轮询主播在播状态
- 主播下次开播时，主路径自动命中并刷新数据库中的 `room_id`
- 适用于主播虽长期未播但仍有活跃账号的场景

### 兜底 1 的失效条件

- 该主播从未被监控过 → 库内无历史 `room_id`
- TikTok 端 `room_id` 失效（账号封禁、长期不播等极少数情况）

进入兜底 1 仍失败时，**回落到最终 fallback**。

---

## 最终 fallback：视频 SSR 的 `locationCreated`

### 接口

```
GET https://www.tiktok.com/@<handle>/video/<video_id>
```

### 响应字段

```
HTML 内嵌 <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">
  → __DEFAULT_SCOPE__
    → webapp.video-detail
      → itemInfo.itemStruct.locationCreated   ← ISO-3166 alpha-2
```

### 字段语义（与主路径关键区别）

`locationCreated` 反映的是**视频上传时网络出口的国家**，**不等于**主播实际运营国：

- 主播在国 A 用国 B VPN 上传 → `locationCreated = B`
- 主播频繁切 VPN → 同账号多条视频 `locationCreated` 可能不一致（实测 `poseshoes` 8 条视频中 7 条 US + 1 条 ID）
- 字段在 TikTok 公开生态中**仅** SSR HTML 暴露，所有 XHR API（`/api/item/detail/`、`/api/post/item_list/` 等）的 `itemStruct` 已精简掉此字段

### 取值策略

- 取最近 N 条视频（建议 N=3~5）的 `locationCreated`，做多数票
- 一致率高 → 高置信，与主路径结果可交叉校验
- 不一致 → 标记为低置信，建议告警人工复核

### `video_id` 获取

```
Step A: handle → secUid
  GET https://www.tiktok.com/@<handle>
  → __DEFAULT_SCOPE__["webapp.user-detail"].userInfo.user.secUid

Step B: secUid → video_id 列表（需 X-Bogus / X-Gnarly 签名）
  GET https://www.tiktok.com/api/post/item_list/
        ?secUid=<secUid>&count=3&cursor=0
        &aid=1988&app_language=en&device_platform=web_pc&region=US
  → response.itemList[*].id
```

### 失效条件

- 账号 0 条公开视频
- 全部视频均设为非公开
- 主播长期切 VPN 上传，导致字段语义偏离运营国

进入此分支仍失败时，识别失败，**返回 null 并告警**，不要做任何概率性推断（语言、用户名后缀、商品币种等均不可靠）。

---

## 已撞过的墙（已逐一证伪，不要再走）

| 路径 | 结论 |
|------|------|
| `/@<handle>/live` 的 SIGI_STATE | 无任何 region/country 字段 |
| `/@<handle>` profile 的 `webapp.user-detail.user` | 无 region；`user.language` 是 UI 语言不可靠 |
| `/@<handle>` profile 的 `__UNIVERSAL_DATA__` 其他 scope | 仅访客 region |
| `/api/post/item_list/` 的 `author` | Web 接口已精简，无 region |
| `/api/related/item_list/` 的 `author` 和 `itemStruct` | 同样精简 |
| `/api/item/detail/?itemId=<id>`（带签名） | itemStruct 已精简掉 `locationCreated` |
| `/api/user/detail/` 未签名 | 200 + 空 body |
| `/webcast/room/enter/` 的 `region` | 是**访客** region（如 `US`），非主播 |
| `/webcast/room/enter/` 的 `owner` 对象 | 仅 `idc_region` CDN 机房，无主播国家 |
| `/webcast/feed/` 的 `region` | 客户端入参，不是主播属性 |
| `/webcast/user/`、`/webcast/user/attr/` | 无 region 字段 |
| `/tiktok/event/list/v1` 的 `events[].host.region` | 字段可用但**仅当主播挂了 Sale 活动**才返回，覆盖率太低 |
| `/api-live/user/room`（批量主播） | 无 region/country 字段 |
| pull_url CDN 节点名（sg01 / useast5） | CDN 边缘节点分配，不等于主播所在国 |

---

## 关键不变式

| 不变式 | 实测证据 |
|--------|----------|
| 主路径 `pages[0].region` 直接绑定主播账号运营区域 | VN / ID 双账号交叉验证一致 |
| 主路径不依赖访客 cookie 与主播登录 | 浏览器重启清空 sessionid 后仍返回正确 region |
| 历史 `room_id` 在主播下播后仍可复用 | odolparfumholic 下播状态下重放成功 |
| `locationCreated` 仅 SSR HTML 暴露 | 全 XHR API 已逐一证伪 |

---

## 集成建议

`services/live-monitor/utils/TiktokTool.py` 已具备 SIGI_STATE 解析能力，本规范新增能力建议作为独立工具方法，复用项目现有 xb-xg 签名实现。

调用时机：
- 主播首次入库时识别一次，持久化国家码到数据库
- 与历史 `room_id` 一同维护，互为兜底数据
- 周/月级回归校验，发现切区时告警人工确认

降级链路应有日志埋点，分别统计主路径命中率、离线兜底命中率、最终 fallback 命中率，便于评估主播池的"在播率"与字段稳定性。

---

## 参考资料

- [ScrapeCreators – How to find TikTok creator regions](https://scrapecreators.com/blog/how-to-find-tiktok-creator-regions-the-hidden-method-tiktok-doesn-t-want-you-to-know)
- [davidteather/TikTok-Api user.py](https://github.com/davidteather/TikTok-Api/blob/main/TikTokApi/api/user.py)
- [yt-dlp TikTok aweme API issue #10213](https://github.com/yt-dlp/yt-dlp/issues/10213)
