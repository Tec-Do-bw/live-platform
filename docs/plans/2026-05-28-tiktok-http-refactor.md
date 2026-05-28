# TikTok 爬虫 HTTP 化重构（包括墨西哥变体）

> 优先级: P2
> 工期: 2-3 天
> 前置: Phase 4 监控简化完成
> 状态: 待执行
> 修订: 2026-05-28（基于真实 CURL 验证 + spider-scaffold 规范对齐）

---

## 0. 第一性原理诊断

**最贵的浪费在哪里？**

| 现状 | 第一性原理 | 白痴指数 |
|---|---|---|
| 浏览器 + JS 注入 + DOM 操作拿 6 个 API | sessionid Cookie + HTTP 直调 | ~5× |
| 浏览器版 Cookie 从 DrissionPage 内存读，绕过 SQLite Vault | 复用现成 Vault | 0× 新增成本 |
| 滑块 OCR + Tab 切换 + replay 滚动选 28 天 | HTTP 不需要 | ∞ |
| 多文件拆分（signer/endpoints/time_window） | 一个 collector.py 集中 | 2× 维护成本 |
| 异步实现 | 同步 curl_cffi Session 即可 | 1.5× 复杂度 |

**核心洞察（基于真实 CURL 验证）**：

用户提供的实际抓包确认：
- 请求头**没有** `X-Bogus` / `_signature` / `X-Gnarly` 等加密参数
- 仅依赖 `sessionid` + `msToken` + `tt_csrf_token` 三个 cookie
- 设备指纹在 query string（`fp` / `device_id` / `browser_*`）
- `x-tt-store-region` 标识国家

**结论**：浏览器自动化 100% 价值消失，**不需要任何加密签名层**，纯 HTTP 直调即可。

**架构原则（养号 / 采集解耦）**：

```
养号（adspower-server）         采集（live-crawler）
─────────────────────────       ─────────────────────────
浏览器常驻保活                   纯 HTTP（curl_cffi 同步）
侦测 sessionid 变化              从 Vault 读 token + ext_json
触发登录 + 发登录回调            按 fetch_* 单接口调用
       │                                ▲
       └─── PUT /api/credentials/{id} ──┘
            (统一 SQLite Vault)
```

---

## 1. 数据库设计（统一公共表）

### 1.1 account_credentials 表（跨平台共用）

替代原 `cookies` 表，所有平台共享：

```sql
CREATE TABLE account_credentials (
    account_id    TEXT PRIMARY KEY,           -- ADSPower browser_id
    platform      TEXT NOT NULL,              -- tiktok / shopee / lazada
    group_name    TEXT NOT NULL,              -- ADSPower 分组名(团队归属,调度按此分组)
    token         TEXT NOT NULL,              -- cookies JSON（核心凭据）
    region        TEXT NOT NULL,              -- 账号真实国家代码(从 API 抓取,与 group_name 解耦)
    proxy         TEXT,                       -- http://user:pass@host:port
    ext_json      TEXT,                       -- 平台特有的请求参数
    extra         TEXT,                       -- 其他扩展字段（JSON）
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_group_platform ON account_credentials(group_name, platform);
CREATE INDEX idx_platform_region ON account_credentials(platform, region);
```

> ⚠️ **核心约束**:`group_name` 和 `region` 是两个正交维度,严禁互相反推。
> - `group_name` ← ADSPower 分组名原样同步,是**调度决策依据**和日报聚合维度
> - `region` ← **必须从 API 真实抓取**(TikTok 用响应里的 `carrier_region` / `x-tt-store-region`),用于域名/时区/请求头/采集逻辑
> - 旧链路用 `"印尼" in group_name → "co.id"` 反推国家是技术债,本次 TikTok 重构必须清除;Lazada 端的同类债务**不在本次范围**。

### 1.2 字段说明

| 字段 | 用途 | TikTok 示例 |
|------|------|------------|
| `account_id` | 账号唯一标识 | ADSPower `browser_id` |
| `platform` | 平台类型 | `tiktok` |
| `group_name` | ADSPower 分组名(团队归属) | `印尼团队` / `美区直播组` |
| `token` | 登录凭据（cookies） | `{"sessionid": "...", "msToken": "...", "tt_csrf_token": "..."}` |
| `region` | 账号真实国家代码(API 抓取) | `US` / `ID` / `MY` / `MX` |
| `proxy` | 代理地址 | `http://user:pass@host:8080` |
| `ext_json` | 平台请求参数 | `{"query_string": "fp=xxx&device_id=...", "creator_id": "...", "user_agent": "..."}` |
| `extra` | 扩展字段 | `{"last_login": "2026-05-28", "shop_id": "..."}` |
| `updated_at` | 最后更新时间 | 用于刷新调度 |

### 1.3 数据流

**写入方**（adspower-server / 刷新模块）：
```
PUT /api/credentials/{account_id}
{
    "platform": "tiktok",
    "group_name": "印尼团队",
    "token": {...cookies...},
    "region": "US",
    "proxy": "http://...",
    "ext_json": {"query_string": "...", "creator_id": "...", "user_agent": "..."}
}
```

**读取方**（live-crawler）：
```python
cred = load_credentials(account_id, platform="tiktok")
```

---

## 2. 整体架构

```
养号侧                         统一 SQLite Vault              采集侧
─────────                      ──────────────────             ───────
ADSPower 浏览器  ─────PUT────► account_credentials  ◄─读取─── collector.py
定期刷新任务（每天 1 次）         token + region                   纯 HTTP
                                + proxy + ext_json
                                + extra
```

**核心原则**：
- 养号与采集解耦：浏览器只用于"上下文刷新"和"登录恢复"，不参与日常采集
- 共享 Vault：所有平台凭据集中在 `account_credentials` 表
- 完全 HTTP：日常 100% HTTP，无浏览器依赖

---

## 3. 文件结构（极简）

```
services/live-crawler/crawlers/http/tiktok/
├── __init__.py
└── collector.py                  # 所有方法集中（fetch_* + parse_* + collect_*）

services/live-crawler/utils/
├── http_session.py               # curl_cffi Session 工厂（已有，复用）
├── credentials.py                # account_credentials 表读写（新增）
├── headers.py                    # build_headers（已有，复用）
└── types.py                      # FetchResult / FatalError（已有，复用）

services/live-crawler/jobs/
└── refresh_credentials.py        # 定期刷新任务（每天 1 次 cron）
```

**核心实现就 1 个文件**：`collector.py`

---

## 4. collector.py 设计（同步 + 单文件）

### 4.1 单接口方法清单（每个端点一个独立 fetch_*）

| 函数 | 端点 | 用途 |
|------|------|------|
| `fetch_account_info` | GET `/api/v1/streamer_desktop/account_info/get` | 验证登录态 |
| `fetch_live_list` | POST `/api/v2/insights/creator/live/list` | 直播间列表（基础 stats_types） |
| `fetch_live_list_extended` | POST `/api/v2/insights/creator/live/list` | 直播间列表（扩展 stats_types） |
| `fetch_live_stats` | POST `/api/v2/insights/creator/live/stats` | 单日汇总（T-1~T-28） |
| `fetch_trend_chart` | POST `/api/v1/insights/creator/liveroom/recap/trend/chart` | 单房间趋势 |
| `fetch_core_stats` | POST `/api/v1/insights/workbench/live/detail/core/stats` | 单房间核心统计 |

每个 `fetch_*` 都是同步函数，签名统一为 `(session, cred, ...) -> FetchResult`。

### 4.2 编排函数

`collect_tiktok(account_id, full)` 生成器，串行处理所有直播间，yield (ok, item)。

### 4.3 完整代码（参考实现）

```python
"""TikTok HTTP 采集器（同步实现，所有方法集中）"""
import json
import time
import random
from datetime import datetime, timedelta, timezone, date
from typing import TypedDict
from urllib.parse import parse_qs

from utils.http_session import get_session, sync_retry
from utils.headers import build_headers
from utils.credentials import load_credentials, Credentials
from utils.types import FatalError, LoginRequired
from utils.logger import logger


# ==================== 类型契约 ====================

class FetchResult(TypedDict):
    ok: bool
    data: dict
    raw: str


class RoomMeta(TypedDict):
    room_id: str
    room_name: str
    live_start_ts: int
    live_end_ts: int
    revenue: str
    currency_code: str


# ==================== 常量 ====================

BASE_URL = "https://shop.tiktok.com"

LIVE_LIST_BASIC_STATS = [10, 15, 11, 12, 13, 14, 80, 95, 20, 100, 101]

LIVE_LIST_EXTENDED_STATS = [
    10, 15, 11, 12, 13, 14, 80, 88, 95, 90, 72, 96, 70, 86,
    20, 29, 25, 50, 41, 42, 21, 40, 100, 101, 62, 61
]

TREND_CHART_STATS_BASIC = [3]
TREND_CHART_STATS_FULL = [3, 20, 341, 21, 22, 12, 16, 23, 50, 51, 40]

CORE_STATS_TYPES = [
    23, 20, 325, 310, 39, 29, 312, 313, 332, 330, 10, 323,
    315, 314, 349, 241, 3, 2, 5, 18, 290, 291, 292,
    -23, -20, -39, -330, -10, -3, -2, -18
]

TIMEZONE_OFFSET_MAP = {
    'US': -28800, 'ID': 25200, 'MY': 28800,
    'SG': 28800, 'MX': -21600, 'TH': 25200, 'VN': 25200,
}


# ==================== 辅助函数 ====================

def _parse_ext(cred: Credentials) -> dict:
    """从 credentials 的 ext_json 字段解析 TikTok 特有参数"""
    ext = json.loads(cred.ext_json) if cred.ext_json else {}
    return {
        'query_string': ext.get('query_string', ''),
        'creator_id': ext.get('creator_id', ''),
        'user_agent': ext.get('user_agent', ''),
    }


def _build_url(path: str, query_string: str = '', extra_params: dict = None) -> str:
    """构造完整 URL，继承 query_string"""
    qs = query_string or ''
    if extra_params:
        extra_qs = '&'.join(f'{k}={v}' for k, v in extra_params.items())
        qs = f"{qs}&{extra_qs}" if qs else extra_qs
    return f"{BASE_URL}{path}?{qs}" if qs else f"{BASE_URL}{path}"


def _build_tiktok_headers(session, cred: Credentials, ext: dict) -> dict:
    """构造 TikTok 请求头（基于 build_headers 扩展）"""
    return build_headers(
        session,
        origin=BASE_URL,
        referer=f"{BASE_URL}/streamer/compass/livestream-analytics/view",
        extra={
            'x-tt-store-region': cred.region.lower(),
            'user-agent': ext['user_agent'] or session.headers.get('user-agent'),
        }
    )


def _time_window(region: str, full: bool) -> dict:
    """计算时间窗（基于账号时区）"""
    offset = TIMEZONE_OFFSET_MAP.get(region.upper(), 0)
    tz_obj = timezone(timedelta(seconds=offset))
    now = datetime.now(tz_obj)
    return {
        'period': 33,
        'granularity': 32,
        'base_timestamp': str(int(now.timestamp())),
        'timezone_offset': offset,
        'days_back': 28 if full else 3,
    }


# ==================== fetch_* 单接口方法 ====================

@sync_retry(retries=2, delay=1.0)
def fetch_account_info(session, cred: Credentials) -> FetchResult:
    """GET /api/v1/streamer_desktop/account_info/get  验证登录态"""
    ext = _parse_ext(cred)
    url = _build_url(
        '/api/v1/streamer_desktop/account_info/get',
        ext['query_string'],
        {'version': '1'}
    )
    resp = session.get(url, headers=_build_tiktok_headers(session, cred, ext), timeout=10)
    resp.raise_for_status()
    data = resp.json()
    is_logged_in = data.get('code') == 0 and data.get('data', {}).get('user_id')
    logger.info(f'[{cred.account_id}/account_info] HTTP {resp.status_code} logged_in={is_logged_in}')
    return {'ok': bool(is_logged_in), 'data': data.get('data', {}), 'raw': resp.text}


@sync_retry(retries=2, delay=1.0)
def fetch_live_list(session, cred: Credentials, full: bool = False) -> FetchResult:
    """POST /api/v2/insights/creator/live/list  直播间列表（基础）"""
    ext = _parse_ext(cred)
    url = _build_url('/api/v2/insights/creator/live/list', ext['query_string'])
    tw = _time_window(cred.region, full)
    payload = {
        "request": {
            "params": [{
                "time_selector": {
                    "period": tw['period'],
                    "granularity": tw['granularity'],
                    "base_timestamp": tw['base_timestamp'],
                    "timezone_offset": tw['timezone_offset'],
                },
                "list_control": {
                    "rules": [{"direction": 2, "field": "LIVE_LIST_LIVE_START_TIMESTAMP"}],
                    "pagination": {"size": 500, "page": 0}
                },
                "stats_types": LIVE_LIST_BASIC_STATS
            }]
        },
        "version": "2"
    }
    resp = session.post(url, headers=_build_tiktok_headers(session, cred, ext), json=payload, timeout=15)
    resp.raise_for_status()
    logger.info(f'[{cred.account_id}/live_list] HTTP {resp.status_code} len={len(resp.text)}')
    return {'ok': True, 'data': resp.json(), 'raw': resp.text}


@sync_retry(retries=2, delay=1.0)
def fetch_live_list_extended(session, cred: Credentials, full: bool = False) -> FetchResult:
    """POST /api/v2/insights/creator/live/list  扩展 stats_types"""
    ext = _parse_ext(cred)
    url = _build_url('/api/v2/insights/creator/live/list', ext['query_string'])
    tw = _time_window(cred.region, full)
    payload = {
        "request": {
            "params": [{
                "time_selector": {
                    "period": tw['period'],
                    "granularity": tw['granularity'],
                    "base_timestamp": tw['base_timestamp'],
                    "timezone_offset": tw['timezone_offset'],
                },
                "list_control": {
                    "rules": [{"direction": 2, "field": "LIVE_LIST_LIVE_START_TIMESTAMP"}],
                    "pagination": {"size": 500, "page": 0}
                },
                "stats_types": LIVE_LIST_EXTENDED_STATS
            }]
        },
        "version": "2"
    }
    resp = session.post(url, headers=_build_tiktok_headers(session, cred, ext), json=payload, timeout=15)
    resp.raise_for_status()
    logger.info(f'[{cred.account_id}/live_list_ext] HTTP {resp.status_code} len={len(resp.text)}')
    return {'ok': True, 'data': resp.json(), 'raw': resp.text}


@sync_retry(retries=2, delay=1.0)
def fetch_trend_chart(session, cred: Credentials, room_id: str, stats_types: list[int]) -> FetchResult:
    """POST /api/v1/insights/creator/liveroom/recap/trend/chart  单房间趋势"""
    ext = _parse_ext(cred)
    url = _build_url('/api/v1/insights/creator/liveroom/recap/trend/chart', ext['query_string'])
    payload = {
        "request": {
            "room_filter": {"room_id": room_id, "query_online": True},
            "stats_types": stats_types,
            "granularity": 1
        }
    }
    resp = session.post(url, headers=_build_tiktok_headers(session, cred, ext), json=payload, timeout=10)
    resp.raise_for_status()
    logger.info(f'[{cred.account_id}/trend_chart] room={room_id} HTTP {resp.status_code}')
    return {'ok': True, 'data': resp.json(), 'raw': resp.text}


@sync_retry(retries=2, delay=1.0)
def fetch_core_stats(session, cred: Credentials, room_id: str) -> FetchResult:
    """POST /api/v1/insights/workbench/live/detail/core/stats  单房间核心统计"""
    ext = _parse_ext(cred)
    KEEP_KEYS = {
        'device_id', 'fp', 'device_platform', 'cookie_enabled',
        'screen_width', 'screen_height', 'browser_language', 'browser_platform',
        'browser_name', 'browser_version', 'browser_online', 'timezone_name',
    }
    raw_params = parse_qs(ext['query_string'], keep_blank_values=True)
    base_params = {k: v[0] for k, v in raw_params.items() if k in KEEP_KEYS}
    base_params['app_name'] = 'i18n_ecom_shop'
    base_params['vertical'] = '3'
    qs = '&'.join(f'{k}={v}' for k, v in base_params.items())
    url = f"{BASE_URL}/api/v1/insights/workbench/live/detail/core/stats?{qs}"
    payload = {
        "request": {
            "room_filter": {
                "room_id": room_id,
                "is_content_type": 1,
                "creator_id": ext['creator_id'],
                "country": cred.region.upper(),
            },
            "stats_types": CORE_STATS_TYPES
        }
    }
    resp = session.post(url, headers=_build_tiktok_headers(session, cred, ext), json=payload, timeout=10)
    resp.raise_for_status()
    logger.info(f'[{cred.account_id}/core_stats] room={room_id} HTTP {resp.status_code}')
    return {'ok': True, 'data': resp.json(), 'raw': resp.text}


@sync_retry(retries=2, delay=1.0)
def fetch_live_stats(session, cred: Credentials, target_date: date) -> FetchResult:
    """POST /api/v2/insights/creator/live/stats  单日汇总"""
    ext = _parse_ext(cred)
    url = _build_url('/api/v2/insights/creator/live/stats', ext['query_string'])
    start_ts = int(datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    end_ts = start_ts + 86400
    payload = {
        "request": {
            "time_selector": {
                "period": 2,
                "granularity": 1,
                "start_timestamp": str(start_ts),
                "end_timestamp": str(end_ts),
                "timezone_offset": "0"
            },
            "stats_types": LIVE_LIST_BASIC_STATS
        }
    }
    resp = session.post(url, headers=_build_tiktok_headers(session, cred, ext), json=payload, timeout=10)
    resp.raise_for_status()
    logger.info(f'[{cred.account_id}/live_stats] date={target_date} HTTP {resp.status_code}')
    return {'ok': True, 'data': resp.json(), 'raw': resp.text}


# ==================== 解析与过滤 ====================

def parse_rooms(live_list_data: dict) -> tuple[list[RoomMeta], str]:
    """从 live/list 响应解析房间列表 + creator_id"""
    segments = live_list_data.get('data', {}).get('segments', [{}])
    first = segments[0] if segments else {}
    creator_id_list = first.get('filter', {}).get('creator_id', [])
    creator_id = creator_id_list[0] if creator_id_list else ''
    stats = first.get('timed_lists', [{}])[0].get('stats', [])
    rooms = []
    for stat in stats:
        room_id = stat.get('live_id')
        live_end = stat.get('live_end_timestamp', 0)
        if not room_id or live_end == 0:
            continue
        revenue = stat.get('revenue', {})
        rooms.append({
            'room_id': str(room_id),
            'room_name': stat.get('live_name', ''),
            'live_start_ts': stat.get('live_start_timestamp', 0),
            'live_end_ts': live_end,
            'revenue': revenue.get('amount', '0'),
            'currency_code': revenue.get('currency_code', ''),
        })
    return rooms, creator_id


def filter_rooms_by_window(rooms: list[RoomMeta], region: str, full: bool) -> list[RoomMeta]:
    """按时间窗过滤房间（增量 3 天 / 全量不过滤）"""
    if full:
        return rooms
    offset = TIMEZONE_OFFSET_MAP.get(region.upper(), 0)
    tz_obj = timezone(timedelta(seconds=offset))
    now = datetime.now(tz_obj)
    cutoff = now - timedelta(days=3)
    cutoff_dt = datetime(cutoff.year, cutoff.month, cutoff.day, 0, 0, 0, tzinfo=tz_obj)
    cutoff_ts = int(cutoff_dt.timestamp())
    return [r for r in rooms if r['live_end_ts'] >= cutoff_ts]


# ==================== collect_* 编排 ====================

def collect_tiktok(account_id: str, full: bool = False, batch_id: str = None):
    """采集编排（生成器，yield (ok, item)）"""
    cred = load_credentials(account_id, platform='tiktok')
    if not cred or not cred.token:
        raise FatalError(f'[{account_id}] 凭据缺失，需要刷新')

    session = get_session(
        spec=cred.fingerprint_spec,
        proxy=cred.proxy,
        cookies=json.loads(cred.token),
    )

    try:
        login_result = fetch_account_info(session, cred)
        if not login_result['ok']:
            raise LoginRequired(f'[{account_id}] 登录态失效')

        list_result = fetch_live_list(session, cred, full)
        ext_result = fetch_live_list_extended(session, cred, full)

        yield True, {'label': 'live_list', 'data': list_result['data']}
        yield True, {'label': 'live_list_extended', 'data': ext_result['data']}

        rooms, creator_id = parse_rooms(list_result['data'])
        if creator_id:
            _update_creator_id(cred, creator_id)

        rooms = filter_rooms_by_window(rooms, cred.region, full)
        logger.info(f'[{account_id}] 找到 {len(rooms)} 个直播间，full={full}')

        for i, room in enumerate(rooms):
            room_id = room['room_id']
            try:
                trend1 = fetch_trend_chart(session, cred, room_id, TREND_CHART_STATS_BASIC)
                trend2 = fetch_trend_chart(session, cred, room_id, TREND_CHART_STATS_FULL)
                core = fetch_core_stats(session, cred, room_id)
                yield True, {'label': 'trend_chart_basic', 'room_id': room_id, 'data': trend1['data']}
                yield True, {'label': 'trend_chart_full', 'room_id': room_id, 'data': trend2['data']}
                yield True, {'label': 'core_stats', 'room_id': room_id, 'data': core['data']}
            except Exception as e:
                logger.exception(f'[{account_id}] room {room_id} 采集失败')
                yield False, {'label': 'room_failed', 'room_id': room_id, 'error': str(e)}

            if i < len(rooms) - 1:
                time.sleep(random.uniform(0.5, 1.5))

        if full:
            today = date.today()
            for days_back in range(1, 29):
                target = today - timedelta(days=days_back)
                try:
                    stats_result = fetch_live_stats(session, cred, target)
                    yield True, {'label': 'live_stats', 'date': target.isoformat(), 'data': stats_result['data']}
                except Exception as e:
                    logger.exception(f'[{account_id}] live_stats {target} 失败')
                    yield False, {'label': 'live_stats_failed', 'date': target.isoformat(), 'error': str(e)}
    finally:
        session.close()


def _update_creator_id(cred: Credentials, creator_id: str):
    """如果 creator_id 变化，更新到 ext_json"""
    ext = json.loads(cred.ext_json) if cred.ext_json else {}
    if ext.get('creator_id') != creator_id:
        ext['creator_id'] = creator_id
        cred.ext_json = json.dumps(ext)
        cred.save()
```

---

## 5. 上下文刷新模块

`jobs/refresh_credentials.py`：

```python
class CredentialsRefresher:
    """每天 1 次刷新 TikTok 上下文（启动浏览器提取）"""

    def refresh_account(self, account_id: str) -> bool:
        # 1. 启动 ADSPower 浏览器(同时拿到 group_name)
        browser = adspower_client.start_browser(account_id)
        group_name = adspower_client.get_group_name(account_id)
        try:
            # 2. 访问 TikTok shop 页面
            tab = browser.new_tab(f'{BASE_URL}/streamer/compass/livestream-analytics/view')
            # 3. 等待 live/list API 触发
            api_data = browser_api.get_listened_data(
                tab, ['api/v2/insights/creator/live/list'], wait_time=10
            )
            if not api_data:
                return False
            # 4. 提取上下文(region 从 API 真实抓取,禁止从 group_name 反推)
            first = api_data[0]
            parsed = urlparse(first['url'])
            cookies = browser_api.get_cookies(tab)
            proxy = adspower_client.get_proxy(account_id)
            query_string = parsed.query
            carrier_region = parse_qs(parsed.query).get('carrier_region', [''])[0].upper()
            user_agent = first['headers'].get('user-agent', '')
            response_data = json.loads(first['response'])
            creator_id_list = response_data.get('data', {}).get('segments', [{}])[0]\
                                          .get('filter', {}).get('creator_id', [])
            creator_id = creator_id_list[0] if creator_id_list else ''
            # 5. 写入统一表(group_name 与 region 各自独立来源)
            save_credentials(
                account_id=account_id,
                platform='tiktok',
                group_name=group_name,
                token=json.dumps(cookies),
                region=carrier_region,
                proxy=proxy,
                ext_json=json.dumps({
                    'query_string': query_string,
                    'creator_id': creator_id,
                    'user_agent': user_agent,
                }),
            )
            return True
        finally:
            adspower_client.stop_browser(account_id)
```

**触发方式**：
- Cron：每天凌晨 3 点（业务低峰期）批量刷新所有账号
- 即时触发：HTTP 采集器检测到 401 时入队（异步，不阻塞当次采集）

---

## 6. 时间窗规则（保持不变）

| 模式 | 范围 | 说明 |
|------|------|------|
| 增量 | T-1 ~ T-3（近 3 天） | latest_available_date = today - 1，无结算延迟 |
| 全量 | T-1 ~ T-28 | 与 data-overview 页面 "Last 28 days" 对齐 |

- 时区从 `account_credentials.region` 的 `TIMEZONE_OFFSET_MAP` 推断
- live/list 直播间过滤：增量按 `live_end_timestamp >= 三天前 00:00:00`
- 禁用 `SETTLEMENT_HOUR`

详见 `.claude/rules/tiktok-collection-time.md`。

---

## 7. 与 spider-spec 对齐清单

| spec 维度 | 本设计落地 |
|----------|-----------|
| §4.1 单一会话工厂 | `get_session()` 来自 `utils.http_session`，业务文件不直接 import curl_cffi |
| §4.2 双层重试 | 网络层（curl_cffi `retry=N`）+ 业务层 `@sync_retry` |
| §4.3 显式 timeout/headers | 每个 fetch_* 显式传 timeout，headers 走 `build_headers()` |
| §4.4 异常分级 | `FatalError` 中止整轮（凭据缺失），普通异常 yield (False, ...) 继续 |
| §4.5 禁止裸 import | 不直接 `from curl_cffi import requests` |
| §4.6 指纹策略 | `cred.fingerprint_spec` 从 `extra` 派生（账号池模式） |
| §5.1 一函数一接口 | 6 个独立 `fetch_*` 函数 |
| §5.2 TypedDict 契约 | `FetchResult` / `RoomMeta` |
| §5.3 collect 编排 | `collect_tiktok(account_id, full)` 生成器 |
| §5.4 错误统计真实化 | yield (False, ...) 不吞异常 |

---

## 8. 工厂路由集成

`crawlers/factory.py`：

```python
class LiveCrawlerFactory:
    @staticmethod
    def create(account, full_collection=False, batch_id=None):
        platform = account.platform
        mode = os.getenv('TIKTOK_CRAWLER_MODE', 'http')

        if platform == 'tiktok':
            if mode == 'http':
                # 包括墨西哥，统一处理
                return TikTokHttpCollector(account.account_id, full_collection, batch_id)
            else:
                return TikTokLiveCrawler(account.browser_id, full_collection, batch_id)
        # 其他平台维持现有路由
        ...
```

**墨西哥变体合并**：HTTP 版统一处理所有国家，`MxTikTokLiveCrawler` 删除。

**登录回调**：
- adspower-server 侦测 sessionid 变化是单一回调源（不变）
- 删除浏览器版 `tiktok.py` 内嵌的 `send_login_callback` 调用（避免双写）
- 保留 HTTP 采集器 `account_info` 401 时的登出回调（兜底）

---

## 9. 数据契约（关键）

- 跑现有浏览器版抓 1 个真实账号，`format_api_message` 输出存 fixture（`tests/fixtures/tiktok_browser_message.json`）
- HTTP 版输出与 fixture 字段级 diff，差异手动审，允许语义等价的格式差异（如时间戳精度），禁止字段缺失/新增

---

## 10. 灰度与切换

1. **灰度账号选择**：1 个 ID/SG/MY/MX 各 1 个，跑 24h
2. **对照指标**：
   - 数据条数 ±5%
   - Kafka 字段一致
   - 采集耗时（预期 HTTP 比 Browser 快 3-5×）
3. **切换控制**：SQLite 加列 `crawler_mode TEXT DEFAULT NULL`，值为 `http` 时走 HTTP
4. **全量切换**：灰度通过后，`TIKTOK_CRAWLER_MODE=http` 默认值，全量切换
5. **代码删除**：浏览器版 `crawlers/browser/tiktok.py` + `mx_tiktok.py` 删除

---

## 11. 当前 vs 重构后对比

| 维度 | 当前（浏览器+JS） | 重构后（HTTP 同步） |
|------|------------------|-------------------|
| 单账号耗时 | 30-60s | **5-15s** |
| 内存 | 300-500MB/账号 | **~10MB/账号** |
| 并发上限 | 8-12 | **30-50**（多进程） |
| 稳定性 | ~85% | **~98%** |
| 滑块处理 | OCR | **不需要** |
| 代码量 | 1100+ 行 | **~400 行（collector.py）** |
| 文件数 | 4+（browser/tiktok.py, mx_tiktok.py 等） | **1** |
| 维护成本 | 高（DOM/JS/URL 偏移） | **低** |

---

## 12. 依赖与风险

### 依赖
- `curl_cffi >= 0.15.0`（已在 `BaseHttpCrawler` 引入，Lazada 在用）
- 不需要 `PyExecJS` / `node`（无加密签名）

### 风险

| 风险 | 缓解 |
|------|------|
| sessionid 过期未刷新 | account_info 兜底 + 401 触发刷新入队 |
| TikTok 增加签名要求 | 监控 401/403 比例，快速降级回浏览器版 |
| query_string 失效（fp/device_id 过期） | 24h 定期刷新 + 即时刷新 |
| 高并发触发风控 | 多进程账号隔离 + 单账号串行 + 随机延迟 0.5-1.5s |
| Cookie 在 Vault 过期但 adspower 未侦测 | 采集器 account_info 兜底判活 |

### 回滚
- 任何环节出问题：`crawler_mode` 字段清空，瞬间回浏览器版
- 浏览器版代码灰度通过前不删除

---

## 13. 验收清单

- [ ] `account_credentials` 表创建,含 `group_name` 字段 + `(group_name, platform)` 索引,从现有 `cookies` 表迁移完成
- [ ] `utils/credentials.py` 读写完成（含 fingerprint_spec 派生 + `group_name` 字段)
- [ ] `collector.py` 6 个 fetch_* + parse_rooms + filter + collect_tiktok 完成
- [ ] `jobs/refresh_credentials.py` 完成 + cron 配置(同步 `group_name` + `region` 各自来源)
- [ ] 调度入口按 `group_name` 分组采集(替代原 `group_name in account` 的内存逻辑)
- [ ] 全仓搜索 `LAZADA_COUNTRY_MAP` 同款"分组名反推 region"模式,TikTok 链路必须消除(Lazada 留作后续 ticket)
- [ ] FakeSession 单元测试通过
- [ ] 灰度账号(包括墨西哥)24h 数据条数 ±5%、字段 100% 对齐
- [ ] 浏览器版代码已删除(`crawlers/browser/tiktok.py` + `mx_tiktok.py`)
- [ ] `services/live-crawler/CLAUDE.md` 已更新
- [ ] adspower-server 写入端点改为 `PUT /api/credentials/{id}`(带 `group_name` 字段)

---

## 14. 实施步骤

| 步骤 | 工期 | 内容 |
|------|------|------|
| 1. 数据库迁移 | 0.5 天 | 创建 `account_credentials` 表 + 迁移脚本（从 cookies 表） |
| 2. 凭据管理 + 刷新任务 | 0.5 天 | `utils/credentials.py` + `jobs/refresh_credentials.py` + cron |
| 3. collector.py 单文件 | 1 天 | 6 个 fetch_* + parse + filter + collect + 单元测试 |
| 4. 工厂路由 + 灰度 | 0.5-1 天 | `LiveCrawlerFactory` 路由 + `crawler_mode` 字段 + 灰度 24h |
| **总计** | **2-3 天** | |

PR 标题：`feat(live-crawler): TikTok 全量 HTTP 化（统一公共凭据表 + 同步实现）`

---

## 15. 不在本次范围

- 养号侧重构（adspower-server 不动，仅写入端点改名）
- 登出恢复链路（2 轮即时 + 3 轮 fallback）保持现状
- Shopee / Lazada 不动
- 浏览器版作为 fallback 保留（灰度阶段），灰度通过后才删除
- **Lazada `LAZADA_COUNTRY_MAP` 关键词反推国家债务**:同类技术债存在于 `cookie_keeper/browser_refresher.py:18-25`,本次仅清除 TikTok 链路,Lazada 留作后续 ticket
- `cookies` 表 + `services/cookie_manager.py`:Lazada 当前生产链路,与本次 `account_credentials` 表并存,等所有平台 HTTP 化后统一迁移
