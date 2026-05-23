# TikTok 直播流 URL 抓取规范

> 状态:已在开播账号 `poseshoes` 实测验证(2026-05-22)
> 适用:直播流录制(FFmpeg 拉流)、流地址巡检
> 数据源:TikTok Web SSR (`/@<handle>/live` 的 `<script id="SIGI_STATE">`)

## 目标

给定**开播中**的 TikTok 直播间 URL,抽出可直接灌给 FFmpeg / 播放器的 FLV / RTMP 拉流地址(所有清晰度档位 + H264/H265 双编码)。

主播国家码识别另见 [`tiktok-anchor-country-detection.md`](./tiktok-anchor-country-detection.md),两者数据源不同,**不可混用**。

## 数据源结论

经穷举测试,**直播页 SSR 已直接吐出全部清晰度的 FLV URL**,不需要任何 XHR、不需要签名、不需要浏览器:

```
GET https://www.tiktok.com/@<handle>/live          ← desktop UA + 单次匿名 GET
└── <script id="SIGI_STATE">
    └── LiveRoom.liveRoomUserInfo
        ├── user                  ← anchor 基础信息(id / secUid / uniqueId / nickname / roomId)
        └── liveRoom
            ├── status            ← 2 = 开播中;其他值无 streamData
            ├── streamId          ← 拉流地址中的 stream-<streamId>
            ├── title / startTime / coverUrl
            ├── streamData        ← H264 多档(嵌套 JSON 字符串)
            │   └── pull_data.stream_data        (字符串,需再 JSON.parse)
            │       ├── common.room_id
            │       └── data.{hd|ld|ao}.main
            │           ├── flv         ← FLV 拉流 URL ★
            │           ├── hls         ← 经实测为空
            │           ├── rtc / cmaf / dash / lls / tsl / tile  ← 均为空
            │           └── sdk_params  (码率/分辨率/CDN 元数据)
            └── hevcStreamData    ← H265 多档(同结构,更多档位)
                └── pull_data.stream_data
                    └── data.{origin|uhd_60|hd_60|hd|sd|ld|ao}.main.flv
```

**关键事实**:
- `pull_data.stream_data` 这一层是**字符串**,需要再 `json.loads` 一次
- `CurrentRoom.roomId` 在 SSR 时是空字符串(client-side hydration 后才填充),要拿 roomId 走 `user.roomId` 或 `streamData...stream_data.common.room_id`
- 必须 desktop Chrome UA:**iPhone/iPad UA 拿到的简化 HTML 无 SIGI_STATE 标签**

## 入口归一化

抠 `<handle>`:

| 输入 URL | handle 抠取 |
|---|---|
| `https://www.tiktok.com/@poseshoes/live` | `r'/@([^/?#]+)'` |
| `https://vm.tiktok.com/<shortcode>` | 先 HEAD 跟随 Location,再走上方正则 |

非 `/live` 路径需补 `/live` 后缀;主页 SSR **不含** `LiveRoom`,直接 GET `/@<handle>` 取不到流地址。

## 抽取流程(单次 HTTP)

```
Step 1 (唯一一步):
  GET https://www.tiktok.com/@<handle>/live
       Headers: desktop Chrome UA(必须)
  → regex 截 <script id="SIGI_STATE">…</script> JSON
  → JSON.parse → LiveRoom.liveRoomUserInfo.liveRoom
  → 校验 status === 2(开播中)
  → JSON.parse(streamData.pull_data.stream_data)     # H264
  → JSON.parse(hevcStreamData.pull_data.stream_data) # H265
  → 各档位 .main.flv 即拉流 URL
```

**特点**:
- 全链路 **1 次 HTTP GET**,无签名,无浏览器,匿名可用
- 实测 < 1s
- 同一份响应也能顺带拿主播 `id / secUid / uniqueId / nickname`(`liveRoomUserInfo.user`)

## 抽取代码

```python
import re
import json
from typing import Optional

UA_DESKTOP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
URL_HANDLE_RE = re.compile(r'/@([^/?#]+)')
SIGI_RE = re.compile(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', re.S)


def fetch_live_stream_urls(any_live_url: str, session=None) -> dict | None:
    """从 TK 直播间 URL 抽出全部清晰度 FLV 拉流地址。

    返回:
        {
            "status": 2,                           # 直播状态
            "room_id": "7642343335780879124",
            "stream_id": "1560563496049705052",
            "anchor": {"id":..., "sec_uid":..., "unique_id":..., "nickname":...},
            "h264": {"hd": "...flv", "ld": "...flv", "ao": "...flv"},
            "h265": {"origin":..., "uhd_60":..., "hd_60":..., "hd":..., "sd":..., "ld":..., "ao":...},
        }
        未开播或解析失败返回 None
    """
    import requests
    sess = session or requests

    m = URL_HANDLE_RE.search(any_live_url)
    if not m:
        return None
    handle = m.group(1)

    resp = sess.get(
        f'https://www.tiktok.com/@{handle}/live',
        headers={'User-Agent': UA_DESKTOP, 'Accept-Language': 'en-US,en;q=0.9'},
        timeout=10,
    )
    sigi_m = SIGI_RE.search(resp.text)
    if not sigi_m:
        return None
    sigi = json.loads(sigi_m.group(1))
    lri = sigi.get('LiveRoom', {}).get('liveRoomUserInfo', {})
    live_room = lri.get('liveRoom') or {}
    if live_room.get('status') != 2:
        return None  # 未开播

    def extract(stream_data_obj):
        inner_raw = (stream_data_obj or {}).get('pull_data', {}).get('stream_data')
        if not inner_raw:
            return {}
        inner = json.loads(inner_raw)
        return {q: qv['main']['flv'] for q, qv in inner.get('data', {}).items() if qv.get('main', {}).get('flv')}

    user = lri.get('user') or {}
    return {
        'status': live_room.get('status'),
        'room_id': str(user.get('roomId') or ''),
        'stream_id': str(live_room.get('streamId') or ''),
        'anchor': {
            'id': user.get('id'),
            'sec_uid': user.get('secUid'),
            'unique_id': user.get('uniqueId'),
            'nickname': user.get('nickname'),
        },
        'h264': extract(live_room.get('streamData')),
        'h265': extract(live_room.get('hevcStreamData')),
    }
```

## URL 形态与生命周期

```
https://pull-w5-sg01.tiktokcdn-us.com/game/stream-<streamId>_<quality_suffix>.flv
  ?expire=1780629272      # Unix 秒,约 14 天有效
  &sign=<32位 md5>         # CDN 防盗链签名
  [&lsb_session_id=...]   # 偶发,可去掉
  [&only_audio=1]         # 纯音频版本
```

- `expire` 实测 ~14 天;过期后需重抓 SSR
- 同一场直播内 `sign` **可复用**;单场直播跨地区切 CDN 时 URL 会变(host 中 `sg01` 等节点名跟随 CDN 调度)
- 主播下播再开播,`streamId` 一定变,旧 URL 立刻失效

## 清晰度档位(poseshoes 实测)

| 档位 | 编码 | 分辨率 | 码率 | 出现位置 |
|---|---|---|---|---|
| `origin` | H265 | 1080x1920 | 4.8 Mbps | hevcStreamData |
| `uhd_60` | H265 | 1080x1920 60fps | 4.0 Mbps | hevcStreamData |
| `hd_60` | H265 | 720x1280 60fps | 2.6 Mbps | hevcStreamData |
| `hd` | H265 | 720x1280 | 1.6 Mbps | hevcStreamData |
| `hd` | H264 | 720x1280 | 1.8 Mbps | streamData |
| `sd` | H265 | 540x960 | 1.0 Mbps | hevcStreamData |
| `ld` | H265 | 360x640 | 0.6 Mbps | hevcStreamData |
| `ld` | H264 | 360x640 | 0.6 Mbps | streamData |
| `ao` | (audio) | — | 0 | 两者均有 |

> 不同主播开播档位不同。代码消费时遍历 `data` 字典而非硬编码 key。

## 已撞过的墙(不要再走)

| 路径 | 结论 |
|------|------|
| iPhone / iPad UA 抓 `/live` HTML | 返回精简 HTML,**无 SIGI_STATE 标签**,拿不到任何流字段 |
| 直播页 `__UNIVERSAL_DATA_FOR_REHYDRATION__` | `__DEFAULT_SCOPE__` 仅 5 个 i18n / app-context scope,**无 live-room scope** |
| `CurrentRoom.roomId` | SSR 时为空字符串,client-side hydration 后才填 |
| 主页 `/@<handle>` SSR | 不含 `LiveRoom`,即使开播也取不到 |
| Playwright `document.outerHTML` 抓 hydration 后 DOM | `webapp.user-detail` / SIGI_STATE 部分内容会被 React 改写覆盖,要用 raw HTTP 抓 |
| `webcast.us.tiktok.com/webcast/room/enter/`(备用 XHR) | 返回 `data.stream_url.flv_pull_url`(HD1/SD1/SD2),但需 X-Bogus + X-Gnarly 签名;SSR 已含等价信息,无收益 |
| `/webcast/feed/` | 仅返回推荐房间列表,无目标主播流 |

## 关键不变式

| 不变式 | 实测证据 |
|--------|----------|
| 开播 (`status === 2`) 时 `streamData` / `hevcStreamData` 一定存在 | poseshoes 实测 9 条 FLV URL |
| 同一 handle 在同一场直播内,所有档位 `streamId` 一致 | 9 条 URL 中 `stream-1560563496049705052` 一致 |
| `pull_data.stream_data` 是**字符串**,必须二次 `json.loads` | 容易踩坑 |
| 桌面 UA 才有 SIGI_STATE,移动 UA 走另一路简化 HTML | curl 双 UA 对照确认 |
| 无须任何签名 / 登录 Cookie | 匿名 GET 直接 200 |

## 实测样本(2026-05-22)

| handle | status | h264 档位 | h265 档位 | URL 数 |
|---|---|---|---|---|
| `poseshoes` | 2 (开播) | hd / ld / ao | origin / uhd_60 / hd_60 / hd / sd / ld / ao | 9 |

> 多账号回归验证未覆盖。新增账号时建议先 `curl -H 'UA: <desktop>' /@<h>/live | grep -o 'pull-.*\.flv[^\"]*'` 验证。

## 盲区与妥协

| 盲区 | 影响 |
|------|------|
| 未开播账号 | `status != 2`,本法返回 None;需先用其他渠道判断开播 |
| 单场直播跨 CDN 切换 | URL 中 `sg01` 等节点会变,需重抓 SSR;`expire` 内同节点仍可拉 |
| 私密直播 / 付费直播 (`paidEvent != 0` / `liveSubOnly`) | SSR 可能不返回 streamData,需登录态 Cookie 重试 |
| 区域限制 | 出口 IP 与主播运营区差异大时,SSR 可能返回 challenge;桌面 UA + 正常出口实测无问题 |
| URL host 中 `sg01` 等 CDN 节点名 | 是边缘调度结果,**不等于主播所在国**(国家识别走另文档) |

## 集成建议(最小侵入)

`services/live-stream/` 现有 FFmpeg 拉流模块需先得到 `flv_url` 才能启动。新增工具方法供调度器使用:

```python
# 建议位置:services/live-stream/utils/tiktok_stream_resolver.py
def fetch_live_stream_urls(any_live_url: str) -> dict | None:
    """实现见 docs/specs/tiktok-live-stream-url-fetch.md。"""
```

调用时机:
- 房主开播事件触发时,解析 1 次拿到全部档位 URL
- 拉流断流重连前,**重新解析一次**(若 expire 临近)
- 持久化 `room_id` + `stream_id` + 选定档位 URL 到任务表

## 成本与限流

| 项目 | 评估 |
|------|------|
| 单房间串行 | < 1s(单次 GET) |
| 批量并发(8 房间) | < 2s(无签名,可全并发) |
| 鉴权 | 匿名即可 |
| 签名 | **不需要** |
| 浏览器 | **不需要** |
| 限流 | 8 房间顺序请求未触发 challenge;批量并发建议每 IP < 10 QPS |
| 付费 | 全免费,无第三方依赖 |

## 参考资料

- 项目同目录 [`tiktok-anchor-country-detection.md`](./tiktok-anchor-country-detection.md) — 国家码识别(数据源不同)
- `services/live-stream/` 现有 FFmpeg 拉流实现
