# TikTok 直播大屏数据 API 服务实施计划

> **给 agentic 执行者：** 按任务逐项执行，并用 checkbox (`- [ ]`) 跟踪进度。只有当任务相互独立，且风险/规模值得引入评审开销时，才使用 `subagent-driven-development`；否则使用 `executing-plans`，或带检查点的内联执行。

**目标：** 在 `services/live-crawler` 中实现 TikTok 直播大屏查询 API，包括带鉴权的 `live-status/batch` 和 `dashboard/data`，然后移除旧的 `live-monitor` 查询路由。

**架构：** `services/live-crawler/monitor/server.py` 成为 Cookie API、TikTok 凭据刷新、live-status 读取和大屏数据拉取的单一 FastAPI 入口。`live-status/batch` 通过迁移后的 `LiveRedisRepository` 读取 Redis；`dashboard/data` 使用新的 `real_collector.py` 承载仅供大屏使用的 TikTok HTTP fetcher，同时复用 `collector.py` 中的 session、credential、URL、header 和 envelope 辅助逻辑。

**技术栈：** Python 3.12、FastAPI、Pydantic、redis-py、通过现有 `utils.http_session` 使用 curl_cffi、pytest。

---

## 源规格

按 `docs/specs/tiktok-live-dashboard-data-api-service.md` 实现。

仅在规格文档指向这些资料时，把它们作为参考：

- `docs/research/tiktok-live-dashboard-apis/API-inventory.md`
- `docs/research/tiktok-live-dashboard-apis/feishu-dashboard-api-doc.md`
- `docs/research/tiktok-live-dashboard-apis/tiktok-live-dashboard-downstream-api.md`
- `.claude/rules/tiktok-http-lifecycle.md`
- `services/live-crawler/CLAUDE.md`
- `services/live-monitor/CLAUDE.md`

## 不可违背项

- `POST /api/v1/tiktok/live-status/batch` 位于 `services/live-crawler`，不放在 `services/live-monitor`。
- `POST /api/v1/tiktok/live-status/batch` 和 `POST /api/v1/tiktok/dashboard/data` 都必须要求 `X-API-Token`，并与 `Settings.COOKIE_API_CONFIG["token"]` 对比。
- 新的 live-crawler 路由测试通过后，移除 `services/live-monitor/routes/live_status.py`。
- 大屏 fetcher 放在 `services/live-crawler/crawlers/http/tiktok/real_collector.py`。
- 不添加任意下游 `stats_types` 输入。
- 不把 TikTok business payload 解析成业务 DTO；返回现有 `_format_message()` envelope，并保留原始 `request.response`。
- 六个大屏 business endpoint 不调用 `_check_code()`。只要 HTTP 成功，即使 TikTok `code != 0` 也返回成功的 API envelope。
- 继续使用 `setup_session(collectionId)` 和 `account_credentials`；不要为 TikTok 大屏凭据读取旧的 `cookies` 表。
- `trend_chart` 使用自己的 27-ID 集合，绝不复用 `CORE_STATS_TYPES`。
- 不做 MySQL migration，不加 Kafka producer，不加 dashboard cache。

## 文件结构

新建：

- `services/live-crawler/monitor/api/auth.py` — 新路由共用的 `X-API-Token` 依赖。
- `services/live-crawler/monitor/api/live_status_routes.py` — `POST /api/v1/tiktok/live-status/batch` 路由。
- `services/live-crawler/monitor/api/dashboard_routes.py` — `POST /api/v1/tiktok/dashboard/data` 路由。
- `services/live-crawler/monitor/schemas/dashboard.py` — Pydantic 请求 schema 和枚举。
- `services/live-crawler/utils/redis_bridge.py` — 迁移后的 Redis 状态读取器，使用 live-crawler Apollo 配置访问方式。
- `services/live-crawler/services/dashboard_data.py` — 大屏编排和 API 层错误映射。
- `services/live-crawler/crawlers/http/tiktok/real_collector.py` — 仅供大屏使用的 TikTok HTTP fetcher 与常量。
- `services/live-crawler/tests/utils/test_redis_bridge.py` — 迁移后的 Redis 状态行为测试。
- `services/live-crawler/tests/monitor/test_live_status_batch.py` — 新的带鉴权 live-status 路由测试。
- `services/live-crawler/tests/monitor/test_tiktok_dashboard_routes.py` — 大屏路由测试。
- `services/live-crawler/tests/services/test_dashboard_data.py` — 大屏服务测试。
- `services/live-crawler/tests/crawlers/http/test_tiktok_dashboard_fetchers.py` — 大屏 fetcher 测试。

修改：

- `services/live-crawler/monitor/server.py` — 引入两个新 router，并更新 app title。
- `services/live-crawler/README.md` — 记录扩展后的 `python -m monitor.server` API 职责。
- `services/live-monitor/main.py` — 移除 `routes.live_status` import 和 `app.include_router(live_status_router)`。
- `services/live-monitor/README.md` — 从 live-monitor API 文档和模块树中移除 live-status 路由。
- `docs/ROADMAP.md` — 如果开始执行，将大屏 API 实现移入 active plan index；实现完成后标记完成。

删除：

- `services/live-monitor/routes/live_status.py`
- `services/live-monitor/tests/test_live_status_batch.py`

保留：

- 保留 `services/live-monitor/utils/redis_bridge.py`，因为 live-monitor 仍然负责写入 Redis 状态。
- 保留 `services/live-monitor/tests/test_redis_bridge.py`，因为它保护写入侧 Redis 语义。

## 任务 0：预检与基线

**文件：**
- 读取：`docs/specs/tiktok-live-dashboard-data-api-service.md`
- 读取：`.claude/rules/tiktok-http-lifecycle.md`
- 读取：`services/live-crawler/CLAUDE.md`
- 读取：`services/live-monitor/CLAUDE.md`

- [x] **步骤 1：确认当前工作树，不要回退用户改动**

运行：

```bash
git status --short
```

预期：可能存在无关的本地改动。保留这些改动，只编辑本计划列出的文件。

- [x] **步骤 2：编辑前确认源符号**

运行：

```bash
codegraph explore "tiktok collector setup_session _format_message _build_filtered_url LiveRedisRepository live_status_routes monitor server"
```

预期：当前位置包括：

- `services/live-crawler/crawlers/http/tiktok/collector.py`
- `services/live-crawler/monitor/server.py`
- `services/live-monitor/routes/live_status.py`
- `services/live-monitor/utils/redis_bridge.py`

- [x] **步骤 3：运行聚焦的基线测试**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/crawlers/http/test_tiktok_collector_query_params.py tests/crawlers/http/test_tiktok_collector_credential_validation.py tests/crawlers/http/test_tiktok_collector_business_retry.py -v
```

预期：通过。如果编辑前已有基线失败，记录准确的失败测试名，并且只有在失败与本计划无关时才继续。

运行：

```bash
cd services/live-monitor
uv run --python 3.12 pytest tests/test_redis_bridge.py tests/test_live_status_batch.py -v
```

预期：在删除旧 live-status 路由前通过。

## 任务 1：将 Redis 状态读取器迁移到 live-crawler

**文件：**
- 新建：`services/live-crawler/utils/redis_bridge.py`
- 新建：`services/live-crawler/tests/utils/test_redis_bridge.py`
- 保留：`services/live-monitor/utils/redis_bridge.py`
- 保留：`services/live-monitor/tests/test_redis_bridge.py`

- [x] **步骤 1：编写 live-crawler Redis bridge 测试**

创建 `services/live-crawler/tests/utils/test_redis_bridge.py`，包含下面这组聚焦测试。它锁定 `live-status/batch` 所需的读取契约；写入侧测试保留在 `services/live-monitor/tests/test_redis_bridge.py`。

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.redis_bridge import LiveRedisRepository, config_key, status_key


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.expirations = {}

    def hset(self, key, mapping=None, **kwargs):
        values = mapping or kwargs
        self.hashes.setdefault(key, {}).update({str(k): str(v) for k, v in values.items()})
        return len(values)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def expire(self, key, seconds):
        self.expirations[key] = int(seconds)
        return True


def test_list_live_status_keeps_requested_order_and_missing_is_offline():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    redis.hset(
        status_key("coll_live"),
        mapping={
            "collectionId": "coll_live",
            "isLive": "1",
            "roomId": "room-1",
            "flvUrl": "https://pull/live.flv",
            "expiresAt": "2000",
        },
    )

    rows = repo.list_live_status(["coll_missing", "coll_live"], now=1001)

    assert rows == [
        {"collectionId": "coll_missing", "isLive": False, "roomId": "", "flvUrl": ""},
        {"collectionId": "coll_live", "isLive": True, "roomId": "room-1", "flvUrl": "https://pull/live.flv"},
    ]


def test_list_live_status_treats_expired_status_as_offline():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    redis.hset(
        status_key("coll_live"),
        mapping={
            "collectionId": "coll_live",
            "isLive": "1",
            "roomId": "room-1",
            "flvUrl": "https://pull/live.flv",
            "expiresAt": "1010",
        },
    )

    rows = repo.list_live_status(["coll_live"], now=1011)

    assert rows == [{"collectionId": "coll_live", "isLive": False, "roomId": "", "flvUrl": ""}]


def test_list_live_status_treats_disabled_config_as_offline():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    redis.hset(config_key("coll_live"), mapping={"enabled": "0"})
    redis.hset(
        status_key("coll_live"),
        mapping={
            "collectionId": "coll_live",
            "isLive": "1",
            "roomId": "room-1",
            "flvUrl": "https://pull/live.flv",
            "expiresAt": "2000",
        },
    )

    rows = repo.list_live_status(["coll_live"], now=1000)

    assert rows == [{"collectionId": "coll_live", "isLive": False, "roomId": "", "flvUrl": ""}]


def test_list_live_status_treats_dirty_expires_at_as_offline():
    redis = FakeRedis()
    repo = LiveRedisRepository(redis)
    redis.hset(
        status_key("coll_live"),
        mapping={
            "collectionId": "coll_live",
            "isLive": "1",
            "roomId": "room-1",
            "flvUrl": "https://pull/live.flv",
            "expiresAt": "dirty",
        },
    )

    rows = repo.list_live_status(["coll_live"], now=1000)

    assert rows == [{"collectionId": "coll_live", "isLive": False, "roomId": "", "flvUrl": ""}]
```

- [x] **步骤 2：运行新测试，确认模块缺失**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/utils/test_redis_bridge.py -v
```

预期：失败，报 `utils.redis_bridge` 的 `ModuleNotFoundError` 或 import error。

- [x] **步骤 3：创建 `services/live-crawler/utils/redis_bridge.py`**

基于当前 `services/live-monitor/utils/redis_bridge.py` 的读取语义实现。使用相同的 Redis key 名称和 `_status_to_batch_item()` 行为，保证 live-monitor 已写入的 key 仍然可读。

在新文件中使用这个 live-crawler 专属的 Apollo 配置适配器：

```python
from core.apollo import APOLLO


def _redis_config() -> dict[str, str]:
    return {
        "redisHost": APOLLO.get_value("redisHost", ""),
        "redisPort": APOLLO.get_value("redisPort", "6379"),
        "redisPassword": APOLLO.get_value("redisPassword", ""),
        "redisDb": APOLLO.get_value("redisDb", "0"),
    }
```

在 `LiveRedisRepository._create_default_client()` 中使用它：

```python
@staticmethod
def _create_default_client() -> redis.Redis:
    cfg = _redis_config()
    return redis.Redis(
        host=cfg.get("redisHost"),
        port=int(cfg.get("redisPort") or 6379),
        password=cfg.get("redisPassword") or None,
        db=int(cfg.get("redisDb") or 0),
        decode_responses=True,
    )
```

新的 live-crawler 模块必须暴露这些名称，因为测试和路由会使用它们：

```python
COLLECTIONS_KEY = "live:monitor:collections"
CONFIG_KEY_TEMPLATE = "live:collection:{collection_id}:config"
STATUS_KEY_TEMPLATE = "live:collection:{collection_id}:status"
DEFAULT_LIVE_STATUS_TTL_SECONDS = 900

def config_key(collection_id: str) -> str:
    return CONFIG_KEY_TEMPLATE.format(collection_id=collection_id)


def status_key(collection_id: str) -> str:
    return STATUS_KEY_TEMPLATE.format(collection_id=collection_id)

class LiveRedisRepository:
    def __init__(self, redis_client: object | None = None, *, status_ttl_seconds: int | None = None):
        self.redis = redis_client or self._create_default_client()
        self.status_ttl_seconds = int(status_ttl_seconds or DEFAULT_LIVE_STATUS_TTL_SECONDS)

    def list_live_status(self, collection_ids: list[str], *, now: int | None = None) -> list[dict[str, object]]:
        current_time = int(now if now is not None else time.time())
        rows = []
        for collection_id in collection_ids:
            config = _decode_hash(self.redis.hgetall(config_key(collection_id)))
            if not _is_config_enabled(config):
                rows.append({"collectionId": collection_id, "isLive": False, "roomId": "", "flvUrl": ""})
                continue
            raw = _decode_hash(self.redis.hgetall(status_key(collection_id)))
            if not raw:
                rows.append({"collectionId": collection_id, "isLive": False, "roomId": "", "flvUrl": ""})
                continue
            rows.append(_status_to_batch_item(collection_id, raw, current_time))
        return rows
```

`config_key`、`status_key`、`_decode`、`_decode_hash`、`_status_to_batch_item`、`_is_config_enabled`、`__init__` 和 `list_live_status` 的实际函数体应与 `services/live-monitor/utils/redis_bridge.py` 保持一致，确保 live-monitor 写入与 live-crawler 读取保持 byte-compatible。

- [x] **步骤 4：运行 Redis bridge 测试**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/utils/test_redis_bridge.py -v
```

预期：通过。

## 任务 2：在 live-crawler 中添加带鉴权的 live-status 路由

**文件：**
- 新建：`services/live-crawler/monitor/api/auth.py`
- 新建：`services/live-crawler/monitor/api/live_status_routes.py`
- 新建：`services/live-crawler/tests/monitor/test_live_status_batch.py`

- [x] **步骤 1：编写 live-status 路由测试**

创建 `services/live-crawler/tests/monitor/test_live_status_batch.py`：

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from monitor.api import live_status_routes


class FakeRepository:
    def __init__(self, rows=None, should_fail=False):
        self.rows = rows or {}
        self.should_fail = should_fail
        self.seen_collection_ids = []

    def list_live_status(self, collection_ids):
        self.seen_collection_ids = list(collection_ids)
        if self.should_fail:
            raise RuntimeError("redis down")
        return [
            self.rows.get(
                collection_id,
                {"collectionId": collection_id, "isLive": False, "roomId": "", "flvUrl": ""},
            )
            for collection_id in collection_ids
        ]


def make_client(repo, monkeypatch):
    app = FastAPI()
    monkeypatch.setattr(live_status_routes, "get_repository", lambda: repo)
    app.include_router(live_status_routes.router)
    return TestClient(app)


def test_batch_live_status_requires_token(monkeypatch):
    client = make_client(FakeRepository(), monkeypatch)

    response = client.post("/api/v1/tiktok/live-status/batch", json={"collectionIds": ["coll_1"]})

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API token"


def test_batch_live_status_rejects_wrong_token(monkeypatch):
    client = make_client(FakeRepository(), monkeypatch)

    response = client.post(
        "/api/v1/tiktok/live-status/batch",
        headers={"X-API-Token": "wrong"},
        json={"collectionIds": ["coll_1"]},
    )

    assert response.status_code == 403


def test_batch_live_status_keeps_request_order_and_casts_ids(monkeypatch):
    repo = FakeRepository(
        {
            "coll_1": {
                "collectionId": "coll_1",
                "isLive": True,
                "roomId": "7544720840995162887",
                "flvUrl": "https://pull-flv.example/live.flv",
            },
            "2": {"collectionId": "2", "isLive": False, "roomId": "", "flvUrl": ""},
        }
    )
    client = make_client(repo, monkeypatch)

    response = client.post(
        "/api/v1/tiktok/live-status/batch",
        headers={"X-API-Token": live_status_routes.API_TOKEN},
        json={"collectionIds": [2, "coll_1"]},
    )

    assert response.status_code == 200
    assert repo.seen_collection_ids == ["2", "coll_1"]
    assert response.json()["data"] == [
        {"collectionId": "2", "isLive": False, "roomId": "", "flvUrl": ""},
        {
            "collectionId": "coll_1",
            "isLive": True,
            "roomId": "7544720840995162887",
            "flvUrl": "https://pull-flv.example/live.flv",
        },
    ]


def test_batch_live_status_missing_collection_ids_returns_empty_data(monkeypatch):
    repo = FakeRepository()
    client = make_client(repo, monkeypatch)

    response = client.post(
        "/api/v1/tiktok/live-status/batch",
        headers={"X-API-Token": live_status_routes.API_TOKEN},
        json={},
    )

    assert response.status_code == 200
    assert repo.seen_collection_ids == []
    assert response.json() == {"code": 200, "message": "success", "data": []}


def test_batch_live_status_redis_failure_returns_5099(monkeypatch):
    client = make_client(FakeRepository(should_fail=True), monkeypatch)

    response = client.post(
        "/api/v1/tiktok/live-status/batch",
        headers={"X-API-Token": live_status_routes.API_TOKEN},
        json={"collectionIds": ["coll_1"]},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 5099
    assert response.json()["message"] == "Redis unavailable: redis down"
    assert response.json()["data"] is None
```

- [x] **步骤 2：运行路由测试并确认失败**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/monitor/test_live_status_batch.py -v
```

预期：失败，因为 `monitor.api.live_status_routes` 不存在。

- [x] **步骤 3：实现共享 API token 依赖**

创建 `services/live-crawler/monitor/api/auth.py`：

```python
"""共享 API 鉴权依赖。"""

from fastapi import Header, HTTPException

from core.config import Settings


API_TOKEN = Settings.COOKIE_API_CONFIG.get("token", "")


def require_cookie_api_token(x_api_token: str = Header(default="")) -> None:
    """校验下游内网接口的 X-API-Token。"""
    if x_api_token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid API token")
```

- [x] **步骤 4：实现 live-status 路由**

创建 `services/live-crawler/monitor/api/live_status_routes.py`：

```python
"""TikTok 批量开播状态 API。"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from monitor.api.auth import API_TOKEN, require_cookie_api_token
from utils.redis_bridge import LiveRedisRepository


router = APIRouter(tags=["live-status"])
_repository = None


class BatchLiveStatusRequest(BaseModel):
    collectionIds: list[object] = Field(default_factory=list)


def get_repository() -> LiveRedisRepository:
    global _repository
    if _repository is None:
        _repository = LiveRedisRepository()
    return _repository


@router.post("/api/v1/tiktok/live-status/batch")
def batch_live_status(req: BatchLiveStatusRequest, _: None = Depends(require_cookie_api_token)):
    collection_ids = [str(collection_id) for collection_id in req.collectionIds]

    try:
        data = get_repository().list_live_status(collection_ids)
    except Exception as e:
        return JSONResponse(content={"code": 5099, "message": f"Redis unavailable: {e}", "data": None})

    return JSONResponse(content={"code": 200, "message": "success", "data": data})
```

- [x] **步骤 5：运行 live-status 测试**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/monitor/test_live_status_batch.py tests/utils/test_redis_bridge.py -v
```

预期：通过。

## 任务 3：在 real_collector.py 中添加大屏 fetcher

**文件：**
- 新建：`services/live-crawler/crawlers/http/tiktok/real_collector.py`
- 新建：`services/live-crawler/tests/crawlers/http/test_tiktok_dashboard_fetchers.py`
- 读取：`docs/research/tiktok-live-dashboard-apis/API-inventory.md`
- 复用：`services/live-crawler/crawlers/http/tiktok/collector.py`

- [x] **步骤 1：编写大屏 fetcher 测试**

创建 `services/live-crawler/tests/crawlers/http/test_tiktok_dashboard_fetchers.py`：

```python
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from crawlers.http.tiktok import collector, real_collector
from utils.credentials import Credentials


class FakeResponse:
    status_code = 200

    def __init__(self, data: dict[str, Any]):
        self._data = data
        self.text = json.dumps(data)

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, response_data: dict[str, Any] | None = None):
        self.response_data = response_data or {"code": 0, "message": "success", "data": {"ok": True}}
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.posts.append({"url": url, "kwargs": kwargs})
        return FakeResponse(self.response_data)


def _cred() -> Credentials:
    query_string = (
        "app_name=i18n_ecom_alliance&device_id=0&fp=verify_test&device_platform=web"
        "&cookie_enabled=true&screen_width=1920&screen_height=1080"
        "&browser_language=vi-VN&browser_platform=Win32&browser_name=Mozilla"
        "&browser_version=5.0&browser_online=true&timezone_name=Asia%2FHo_Chi_Minh"
        "&vertical=1&msToken=dirty-token&X-Bogus=dirty-sign"
    )
    return Credentials(
        account_id="k19f2q44",
        platform="tiktok",
        group_name="越南团队-tiktok",
        token="{}",
        region="VN",
        proxy="",
        ext_json=json.dumps(
            {
                "query_string": query_string,
                "creator_id": "7158775580024210437",
                "user_agent": "Mozilla/5.0",
            }
        ),
        extra="{}",
    )


def _last_payload(session: FakeSession) -> dict[str, Any]:
    return session.posts[-1]["kwargs"]["json"]


def _last_query(session: FakeSession) -> dict[str, list[str]]:
    return parse_qs(urlparse(session.posts[-1]["url"]).query, keep_blank_values=True)


def test_core_stats_uses_dashboard_full_stats_creator_and_country():
    session = FakeSession()

    result = real_collector.fetch_dashboard_core_stats(session, _cred(), "7651420995556182804")

    payload = _last_payload(session)
    room_filter = payload["request"]["room_filter"]
    assert result["ok"] is True
    assert "/api/v1/insights/workbench/live/detail/core/stats" in result["url"]
    assert room_filter == {
        "room_id": "7651420995556182804",
        "is_content_type": 1,
        "creator_id": "7158775580024210437",
        "country": "VN",
    }
    assert payload["request"]["stats_types"] == real_collector.DASHBOARD_CORE_STATS_TYPES
    assert len(payload["request"]["stats_types"]) == 55
    assert -344 in payload["request"]["stats_types"]


def test_dashboard_urls_filter_dirty_query_keys_and_override_app_name():
    session = FakeSession()

    real_collector.fetch_dashboard_room_info(session, _cred(), "room-1")

    query = _last_query(session)
    assert query["app_name"] == ["i18n_ecom_shop"]
    assert query["vertical"] == ["3"]
    assert query["fp"] == ["verify_test"]
    assert "msToken" not in query
    assert "X-Bogus" not in query


def test_trend_chart_uses_independent_27_ids_and_optional_start_time():
    session = FakeSession()

    real_collector.fetch_dashboard_trend_chart(session, _cred(), "room-1", start_time=1782211225)

    payload = _last_payload(session)
    assert payload["request"]["stats_types"] == real_collector.DASHBOARD_TREND_CHART_TYPES
    assert len(payload["request"]["stats_types"]) == 27
    assert payload["request"]["stats_types"] != collector.CORE_STATS_TYPES
    assert payload["request"]["start_time"] == 1782211225


def test_trend_chart_full_range_omits_start_time():
    session = FakeSession()

    real_collector.fetch_dashboard_trend_chart(session, _cred(), "room-1")

    assert "start_time" not in _last_payload(session)["request"]


def test_source_new_uses_v3_room_filter_payload():
    session = FakeSession()

    real_collector.fetch_dashboard_source_new(session, _cred(), "room-1")

    payload = _last_payload(session)
    assert "/api/v3/insights/workbench/live/detail/source/new" in session.posts[-1]["url"]
    assert payload == {
        "request": {"stats_types": [100], "room_filter": {"room_id": "room-1", "is_content_type": 1}},
        "version": 3,
    }


def test_user_portrait_product_list_and_room_info_payloads():
    cred = _cred()

    portrait_session = FakeSession()
    real_collector.fetch_dashboard_user_portrait(portrait_session, cred, "room-1")
    assert _last_payload(portrait_session)["request"]["stats_types"] == real_collector.USER_PORTRAIT_TYPES

    product_session = FakeSession()
    real_collector.fetch_dashboard_product_list(product_session, cred, "room-1")
    product_payload = _last_payload(product_session)
    assert product_payload["request"]["sorting_type"] == 1
    assert product_payload["request"]["stats_types"] == real_collector.PRODUCT_LIST_TYPES

    room_session = FakeSession()
    real_collector.fetch_dashboard_room_info(room_session, cred, "room-1")
    room_payload = _last_payload(room_session)
    assert room_payload["request"] == {"room_filter": {"room_id": "room-1", "is_content_type": 1}}


def test_tiktok_business_code_is_preserved_as_successful_fetch_result():
    session = FakeSession({"code": 98001021, "message": "call downstream server error", "data": {}})

    result = real_collector.fetch_dashboard_trend_chart(session, _cred(), "room-1")

    assert result["ok"] is True
    assert json.loads(result["response_body"])["code"] == 98001021
```

- [x] **步骤 2：运行 fetcher 测试并确认失败**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/crawlers/http/test_tiktok_dashboard_fetchers.py -v
```

预期：失败，因为 `crawlers.http.tiktok.real_collector` 不存在。

- [x] **步骤 3：实现大屏常量和共享 POST helper**

创建 `services/live-crawler/crawlers/http/tiktok/real_collector.py`，并加入 `API-inventory.md` 中的这些常量：

```python
"""TikTok 直播大屏实时查询 fetchers。"""

from __future__ import annotations

from typing import Any

from crawlers.http.tiktok.collector import (
    CORE_STATS_QUERY_KEYS,
    _api_label,
    _build_filtered_url,
    _build_tiktok_headers,
    _json_dumps,
    _make_result,
    _parse_ext,
    _response_json,
)
from utils.credentials import Credentials
from utils.http_session import DEFAULT_RETRY_EXCEPTIONS, sync_retry
from utils.logger import logger
from utils.types import FetchResult


DASHBOARD_QUERY_KEYS = CORE_STATS_QUERY_KEYS
DASHBOARD_FIXED_QUERY = {"app_name": "i18n_ecom_shop", "vertical": "3"}

DASHBOARD_CORE_STATS_TYPES = [
    15, 27, 7, 344, 50, 346, 348,
    71, 10, 20, 330, 29, 70, 11, 39, 43, 343, 23, 310, 325, 130, 30, 332, 323, 349,
    62, 61, 60, 331, 312, 313, 314, 315,
    241, 283,
    3, 2, 5, 18, 17,
    290, 291, 292,
    -3, -2, -7, -344, -23, -20, -18, -39, -10, -11, -70, -71,
]
DASHBOARD_TREND_CHART_TYPES = [
    3, 52, 82, 41, 344,
    20, 11, 50, 14, 84, 51, 92,
    23, 13, 12, 16, 312, 313, 314, 315,
    401, 15, 91, 343, 350, 81, 323,
]
USER_PORTRAIT_TYPES = [80, 81, 82, 83, 90, 85, 86, 87, 88, 350, 351, 352, 353]
PRODUCT_LIST_TYPES = [4, 5, 6, 7, 10, 15, 17, 18, 21, 30, 35, 41, 48, 51, 55, 64, 120, 301, 345]


def _dashboard_url(path: str, cred: Credentials) -> str:
    ext = _parse_ext(cred)
    return _build_filtered_url(path, ext["query_string"], DASHBOARD_QUERY_KEYS, DASHBOARD_FIXED_QUERY)


@sync_retry(retries=2, delay=1.0, retry_exceptions=DEFAULT_RETRY_EXCEPTIONS)
def _post_dashboard_api(session: Any, cred: Credentials, endpoint: str, path: str, payload: dict[str, Any]) -> FetchResult:
    url = _dashboard_url(path, cred)
    resp = session.post(url, headers=_build_tiktok_headers(cred), json=payload, timeout=15)
    resp.raise_for_status()
    data = _response_json(resp)
    logger.info(
        f"[{cred.account_id}/{_api_label(endpoint)}] dashboard HTTP {resp.status_code} "
        f"code={data.get('code')} len={len(resp.text)}"
    )
    return _make_result(ok=True, url=url, request_body=_json_dumps(payload), response_body=resp.text, data=data)
```

- [x] **步骤 4：实现这六个 fetcher**

向 `real_collector.py` 添加以下函数：

```python
def fetch_dashboard_core_stats(session: Any, cred: Credentials, room_id: str) -> FetchResult:
    ext = _parse_ext(cred)
    creator_id = str(ext.get("creator_id") or "")
    if not creator_id:
        logger.warning(f"[{cred.account_id}/dashboard_core_stats] creator_id 缺失，继续请求并保留 TikTok 原始响应")
    payload = {
        "request": {
            "room_filter": {
                "room_id": room_id,
                "is_content_type": 1,
                "creator_id": creator_id,
                "country": cred.region.upper(),
            },
            "stats_types": DASHBOARD_CORE_STATS_TYPES,
        }
    }
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_core_stats",
        "/api/v1/insights/workbench/live/detail/core/stats",
        payload,
    )


def fetch_dashboard_trend_chart(
    session: Any,
    cred: Credentials,
    room_id: str,
    start_time: int | None = None,
) -> FetchResult:
    request: dict[str, Any] = {
        "room_filter": {"room_id": room_id, "is_content_type": 1},
        "stats_types": DASHBOARD_TREND_CHART_TYPES,
    }
    if start_time is not None:
        request["start_time"] = int(start_time)
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_trend_chart",
        "/api/v1/insights/workbench/live/detail/trend/chart",
        {"request": request},
    )


def fetch_dashboard_source_new(session: Any, cred: Credentials, room_id: str) -> FetchResult:
    payload = {
        "request": {
            "stats_types": [100],
            "room_filter": {"room_id": room_id, "is_content_type": 1},
        },
        "version": 3,
    }
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_source_new",
        "/api/v3/insights/workbench/live/detail/source/new",
        payload,
    )


def fetch_dashboard_user_portrait(session: Any, cred: Credentials, room_id: str) -> FetchResult:
    payload = {
        "request": {
            "room_filter": {"room_id": room_id, "is_content_type": 1},
            "stats_types": USER_PORTRAIT_TYPES,
        }
    }
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_user_portrait",
        "/api/v1/insights/workbench/live/detail/user/portrait",
        payload,
    )


def fetch_dashboard_product_list(session: Any, cred: Credentials, room_id: str) -> FetchResult:
    payload = {
        "request": {
            "room_filter": {"room_id": room_id, "is_content_type": 1},
            "sorting_type": 1,
            "stats_types": PRODUCT_LIST_TYPES,
        }
    }
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_product_list",
        "/api/v1/insights/workbench/live/detail/product/list",
        payload,
    )


def fetch_dashboard_room_info(session: Any, cred: Credentials, room_id: str) -> FetchResult:
    payload = {"request": {"room_filter": {"room_id": room_id, "is_content_type": 1}}}
    return _post_dashboard_api(
        session,
        cred,
        "dashboard_room_info",
        "/api/v1/insights/workbench/live/detail/room/info",
        payload,
    )
```

- [x] **步骤 5：运行 fetcher 测试和 collector 回归测试**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/crawlers/http/test_tiktok_dashboard_fetchers.py tests/crawlers/http/test_tiktok_collector_query_params.py tests/crawlers/http/test_tiktok_collector_business_retry.py -v
```

预期：通过。回归测试证明 `real_collector.py` 没有改变定时 `collector.py::collect_tiktok()` 的语义。

## 任务 4：添加大屏服务、schema 和路由

**文件：**
- 新建：`services/live-crawler/monitor/schemas/dashboard.py`
- 新建：`services/live-crawler/services/dashboard_data.py`
- 新建：`services/live-crawler/monitor/api/dashboard_routes.py`
- 新建：`services/live-crawler/tests/services/test_dashboard_data.py`
- 新建：`services/live-crawler/tests/monitor/test_tiktok_dashboard_routes.py`

- [x] **步骤 1：编写大屏服务测试**

创建 `services/live-crawler/tests/services/test_dashboard_data.py`：

```python
from __future__ import annotations

import json

import pytest

from monitor.schemas.dashboard import DashboardDataRequest, DashboardDataType, DashboardTimeRange
from services import dashboard_data
from utils.credentials import Credentials
from utils.types import FatalError, LoginRequired


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _cred() -> Credentials:
    return Credentials(
        account_id="k19f2q44",
        platform="tiktok",
        group_name="越南团队-tiktok",
        token='{"sessionid":"x"}',
        region="VN",
        proxy="",
        ext_json='{"query_string":"device_id=1&fp=x","creator_id":"creator-1"}',
        extra="{}",
    )


def _fetch_result(request_body=None):
    return {
        "ok": True,
        "url": "https://shop.tiktok.com/api/v1/insights/workbench/live/detail/core/stats?device_id=1",
        "request_body": request_body or {"request": {"room_filter": {"room_id": "room-1"}}},
        "response_body": '{"code":0,"data":{"ok":true}}',
        "data": {"code": 0, "data": {"ok": True}},
    }


def test_fetch_dashboard_data_success_adds_envelope_fields(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(dashboard_data, "setup_session", lambda collection_id: (_cred(), session, _fetch_result()))
    monkeypatch.setitem(
        dashboard_data.DASHBOARD_FETCHERS,
        DashboardDataType.core_stats,
        lambda _session, _cred_obj, room_id: _fetch_result({"request": {"room_filter": {"room_id": room_id}}}),
    )

    req = DashboardDataRequest(dataType="core_stats", roomId="room-1", collectionId="k19f2q44")

    result = dashboard_data.fetch_dashboard_data(req, now_func=lambda: 1782211525)

    assert result["code"] == 200
    assert result["message"] == "success"
    assert result["data"]["dataSource"] == "live_crawler_tiktok_http"
    assert result["data"]["dataType"] == "core_stats"
    assert result["data"]["roomId"] == "room-1"
    assert result["data"]["socketUserId"] == "k19f2q44"
    assert json.loads(result["data"]["request"]["response"])["code"] == 0
    assert session.closed is True


def test_trend_chart_time_range_last_5m_maps_to_start_time(monkeypatch):
    session = FakeSession()
    seen = {}
    monkeypatch.setattr(dashboard_data, "setup_session", lambda collection_id: (_cred(), session, _fetch_result()))

    def fake_trend(_session, _cred_obj, room_id, start_time=None):
        seen["room_id"] = room_id
        seen["start_time"] = start_time
        return _fetch_result({"request": {"room_filter": {"room_id": room_id}, "start_time": start_time}})

    monkeypatch.setitem(dashboard_data.DASHBOARD_FETCHERS, DashboardDataType.trend_chart, fake_trend)
    req = DashboardDataRequest(
        dataType="trend_chart",
        roomId="room-1",
        collectionId="k19f2q44",
        timeRange="last_5m",
    )

    dashboard_data.fetch_dashboard_data(req, now_func=lambda: 1782211525)

    assert seen == {"room_id": "room-1", "start_time": 1782211225}
    assert session.closed is True


def test_trend_chart_full_range_passes_no_start_time(monkeypatch):
    session = FakeSession()
    seen = {}
    monkeypatch.setattr(dashboard_data, "setup_session", lambda collection_id: (_cred(), session, _fetch_result()))

    def fake_trend(_session, _cred_obj, room_id, start_time=None):
        seen["start_time"] = start_time
        return _fetch_result()

    monkeypatch.setitem(dashboard_data.DASHBOARD_FETCHERS, DashboardDataType.trend_chart, fake_trend)
    req = DashboardDataRequest(dataType="trend_chart", roomId="room-1", collectionId="k19f2q44")

    dashboard_data.fetch_dashboard_data(req, now_func=lambda: 1782211525)

    assert seen["start_time"] is None
    assert session.closed is True


def test_setup_session_login_required_maps_to_api_error(monkeypatch):
    monkeypatch.setattr(dashboard_data, "setup_session", lambda collection_id: (_ for _ in ()).throw(LoginRequired("expired")))
    req = DashboardDataRequest(dataType="core_stats", roomId="room-1", collectionId="k19f2q44")

    with pytest.raises(dashboard_data.DashboardApiError) as exc_info:
        dashboard_data.fetch_dashboard_data(req)

    assert exc_info.value.code == 5001
    assert exc_info.value.reason == "login_required"
    assert exc_info.value.detail == "expired"


def test_setup_session_fatal_error_maps_to_session_not_found(monkeypatch):
    monkeypatch.setattr(dashboard_data, "setup_session", lambda collection_id: (_ for _ in ()).throw(FatalError("凭据缺失")))
    req = DashboardDataRequest(dataType="core_stats", roomId="room-1", collectionId="k19f2q44")

    with pytest.raises(dashboard_data.DashboardApiError) as exc_info:
        dashboard_data.fetch_dashboard_data(req)

    assert exc_info.value.code == 4041
    assert exc_info.value.reason == "session_not_found"


def test_session_closes_when_fetcher_raises(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(dashboard_data, "setup_session", lambda collection_id: (_cred(), session, _fetch_result()))

    def fail_fetcher(_session, _cred_obj, _room_id):
        raise RuntimeError("boom")

    monkeypatch.setitem(dashboard_data.DASHBOARD_FETCHERS, DashboardDataType.core_stats, fail_fetcher)
    req = DashboardDataRequest(dataType="core_stats", roomId="room-1", collectionId="k19f2q44")

    with pytest.raises(dashboard_data.DashboardApiError) as exc_info:
        dashboard_data.fetch_dashboard_data(req)

    assert exc_info.value.code == 5099
    assert exc_info.value.reason == "internal_error"
    assert session.closed is True


def test_json_decode_style_value_error_maps_to_upstream_error(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(dashboard_data, "setup_session", lambda collection_id: (_cred(), session, _fetch_result()))

    def fail_fetcher(_session, _cred_obj, _room_id):
        raise ValueError("unexpected json")

    monkeypatch.setitem(dashboard_data.DASHBOARD_FETCHERS, DashboardDataType.core_stats, fail_fetcher)
    req = DashboardDataRequest(dataType="core_stats", roomId="room-1", collectionId="k19f2q44")

    with pytest.raises(dashboard_data.DashboardApiError) as exc_info:
        dashboard_data.fetch_dashboard_data(req)

    assert exc_info.value.code == 5001
    assert exc_info.value.reason == "upstream_error"
    assert session.closed is True
```

- [x] **步骤 2：编写大屏路由测试**

创建 `services/live-crawler/tests/monitor/test_tiktok_dashboard_routes.py`：

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from monitor.api import dashboard_routes
from services.dashboard_data import DashboardApiError


def make_client(monkeypatch, service_result=None, service_error=None):
    app = FastAPI()

    def fake_fetch(req):
        if service_error is not None:
            raise service_error
        return service_result or {
            "code": 200,
            "message": "success",
            "data": {"dataType": req.dataType.value, "roomId": req.roomId},
        }

    monkeypatch.setattr(dashboard_routes, "fetch_dashboard_data", fake_fetch)
    app.include_router(dashboard_routes.router)
    return TestClient(app)


def _body():
    return {"dataType": "core_stats", "roomId": "room-1", "collectionId": "k19f2q44"}


def test_dashboard_route_requires_token(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post("/api/v1/tiktok/dashboard/data", json=_body())

    assert response.status_code == 403


def test_dashboard_route_rejects_wrong_token(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post(
        "/api/v1/tiktok/dashboard/data",
        headers={"X-API-Token": "wrong"},
        json=_body(),
    )

    assert response.status_code == 403


def test_dashboard_route_validates_data_type(monkeypatch):
    client = make_client(monkeypatch)
    body = _body()
    body["dataType"] = "bad"

    response = client.post(
        "/api/v1/tiktok/dashboard/data",
        headers={"X-API-Token": dashboard_routes.API_TOKEN},
        json=body,
    )

    assert response.status_code == 422


def test_dashboard_route_returns_service_success(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post(
        "/api/v1/tiktok/dashboard/data",
        headers={"X-API-Token": dashboard_routes.API_TOKEN},
        json=_body(),
    )

    assert response.status_code == 200
    assert response.json()["code"] == 200
    assert response.json()["data"]["dataType"] == "core_stats"


def test_dashboard_route_maps_api_error_to_response_body(monkeypatch):
    client = make_client(
        monkeypatch,
        service_error=DashboardApiError(5001, "login_required", "expired"),
    )

    response = client.post(
        "/api/v1/tiktok/dashboard/data",
        headers={"X-API-Token": dashboard_routes.API_TOKEN},
        json=_body(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 5001,
        "message": "上游请求失败",
        "dataType": "core_stats",
        "roomId": "room-1",
        "error": {"reason": "login_required", "detail": "expired"},
    }
```

- [x] **步骤 3：运行服务和路由测试，确认 import 失败**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/services/test_dashboard_data.py tests/monitor/test_tiktok_dashboard_routes.py -v
```

预期：失败，因为 `monitor.schemas.dashboard`、`services.dashboard_data` 和 `monitor.api.dashboard_routes` 都不存在。

- [x] **步骤 4：实现大屏 schemas**

创建 `services/live-crawler/monitor/schemas/dashboard.py`：

```python
"""TikTok 大屏 API schema。"""

from enum import StrEnum

from pydantic import BaseModel, Field


class DashboardDataType(StrEnum):
    core_stats = "core_stats"
    trend_chart = "trend_chart"
    source_new = "source_new"
    user_portrait = "user_portrait"
    product_list = "product_list"
    room_info = "room_info"


class DashboardTimeRange(StrEnum):
    full = "full"
    last_5m = "last_5m"
    last_30m = "last_30m"


class DashboardDataRequest(BaseModel):
    dataType: DashboardDataType
    roomId: str = Field(min_length=1)
    collectionId: str = Field(min_length=1)
    timeRange: DashboardTimeRange = DashboardTimeRange.full
```

- [x] **步骤 5：实现大屏服务**

创建 `services/live-crawler/services/dashboard_data.py`：

```python
"""TikTok 大屏实时查询编排。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from crawlers.http.tiktok.collector import _format_message, setup_session
from crawlers.http.tiktok.real_collector import (
    fetch_dashboard_core_stats,
    fetch_dashboard_product_list,
    fetch_dashboard_room_info,
    fetch_dashboard_source_new,
    fetch_dashboard_trend_chart,
    fetch_dashboard_user_portrait,
)
from monitor.schemas.dashboard import DashboardDataRequest, DashboardDataType, DashboardTimeRange
from utils.http_session import DEFAULT_RETRY_EXCEPTIONS
from utils.types import FatalError, LoginRequired


class DashboardApiError(Exception):
    def __init__(self, code: int, reason: str, detail: str):
        self.code = code
        self.reason = reason
        self.detail = detail
        super().__init__(detail)


DASHBOARD_FETCHERS = {
    DashboardDataType.core_stats: fetch_dashboard_core_stats,
    DashboardDataType.trend_chart: fetch_dashboard_trend_chart,
    DashboardDataType.source_new: fetch_dashboard_source_new,
    DashboardDataType.user_portrait: fetch_dashboard_user_portrait,
    DashboardDataType.product_list: fetch_dashboard_product_list,
    DashboardDataType.room_info: fetch_dashboard_room_info,
}


def _start_time_for(time_range: DashboardTimeRange, now_func: Callable[[], float]) -> int | None:
    now = int(now_func())
    if time_range == DashboardTimeRange.last_5m:
        return now - 300
    if time_range == DashboardTimeRange.last_30m:
        return now - 1800
    return None


def _upstream_reason(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return "upstream_timeout"
    return "upstream_error"


def fetch_dashboard_data(
    req: DashboardDataRequest,
    *,
    now_func: Callable[[], float] = time.time,
) -> dict[str, Any]:
    session = None
    try:
        cred, session, _login_result = setup_session(req.collectionId)
        fetcher = DASHBOARD_FETCHERS[req.dataType]
        if req.dataType == DashboardDataType.trend_chart:
            result = fetcher(session, cred, req.roomId, _start_time_for(req.timeRange, now_func))
        else:
            result = fetcher(session, cred, req.roomId)

        message = _format_message(
            result["url"],
            result["request_body"],
            result["response_body"],
            cred.token_data,
            req.collectionId,
        )
        message["dataSource"] = "live_crawler_tiktok_http"
        message["dataType"] = req.dataType.value
        message["roomId"] = req.roomId
        message["socketUserId"] = req.collectionId
        return {"code": 200, "message": "success", "data": message}
    except LoginRequired as e:
        raise DashboardApiError(5001, "login_required", str(e)) from e
    except FatalError as e:
        raise DashboardApiError(4041, "session_not_found", str(e)) from e
    except DEFAULT_RETRY_EXCEPTIONS as e:
        raise DashboardApiError(5001, _upstream_reason(e), str(e)) from e
    except ValueError as e:
        raise DashboardApiError(5001, "upstream_error", str(e)) from e
    except DashboardApiError:
        raise
    except Exception as e:
        raise DashboardApiError(5099, "internal_error", str(e)) from e
    finally:
        if session is not None:
            session.close()
```

- [x] **步骤 6：实现大屏路由**

创建 `services/live-crawler/monitor/api/dashboard_routes.py`：

```python
"""TikTok 大屏数据 API。"""

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from monitor.api.auth import API_TOKEN, require_cookie_api_token
from monitor.schemas.dashboard import DashboardDataRequest
from services.dashboard_data import DashboardApiError, fetch_dashboard_data


router = APIRouter(tags=["tiktok-dashboard"])


@router.post("/api/v1/tiktok/dashboard/data")
async def dashboard_data(req: DashboardDataRequest, _: None = Depends(require_cookie_api_token)):
    try:
        return await run_in_threadpool(fetch_dashboard_data, req)
    except DashboardApiError as e:
        message = "上游请求失败" if e.code == 5001 else "API request failed"
        return JSONResponse(
            content={
                "code": e.code,
                "message": message,
                "dataType": req.dataType.value,
                "roomId": req.roomId,
                "error": {"reason": e.reason, "detail": e.detail},
            }
        )
```

- [x] **步骤 7：运行大屏服务和路由测试**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/services/test_dashboard_data.py tests/monitor/test_tiktok_dashboard_routes.py -v
```

预期：通过。

## 任务 5：注册新路由并移除 live-monitor 查询路由

**文件：**
- 修改：`services/live-crawler/monitor/server.py`
- 修改：`services/live-monitor/main.py`
- 删除：`services/live-monitor/routes/live_status.py`
- 删除：`services/live-monitor/tests/test_live_status_batch.py`
- 新建或扩展：`services/live-crawler/tests/monitor/test_server_routes.py`

- [x] **步骤 1：添加 server 路由注册测试**

创建 `services/live-crawler/tests/monitor/test_server_routes.py`：

```python
from monitor.server import app


def test_monitor_server_registers_dashboard_and_live_status_routes():
    paths = {route.path for route in app.routes}

    assert "/api/v1/tiktok/live-status/batch" in paths
    assert "/api/v1/tiktok/dashboard/data" in paths
    assert "/api/cookies/{account_id}" in paths
    assert "/api/refresh_tiktok_credential" in paths
```

- [x] **步骤 2：运行注册测试并确认失败**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/monitor/test_server_routes.py -v
```

预期：失败，因为新路由尚未注册。

- [x] **步骤 3：在 live-crawler server 中注册路由**

修改 `services/live-crawler/monitor/server.py`：

```python
from monitor.api.cookie_routes import router as cookie_router
from monitor.api.dashboard_routes import router as dashboard_router
from monitor.api.live_status_routes import router as live_status_router
from monitor.api.tiktok_refresh_routes import router as tiktok_refresh_router
from monitor import get_db_connection, init_db


app = FastAPI(title="Live Crawler API", version="1.0")

init_db(get_db_connection())
app.include_router(cookie_router)
app.include_router(tiktok_refresh_router)
app.include_router(live_status_router)
app.include_router(dashboard_router)
```

保持 `python -m monitor.server` 和端口 `8777` 不变。

- [x] **步骤 4：移除旧的 live-monitor 路由注册**

修改 `services/live-monitor/main.py`：

```python
# Remove this import:
# from routes.live_status import router as live_status_router

# Remove this include:
# app.include_router(live_status_router)
```

然后删除：

```text
services/live-monitor/routes/live_status.py
services/live-monitor/tests/test_live_status_batch.py
```

- [x] **步骤 5：运行 server 和路由测试**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/monitor/test_server_routes.py tests/monitor/test_live_status_batch.py tests/monitor/test_tiktok_dashboard_routes.py -v
```

预期：通过。

运行：

```bash
cd services/live-monitor
uv run --python 3.12 pytest tests/test_redis_bridge.py tests/test_api_response.py -v
```

预期：通过。`tests/test_live_status_batch.py` 已不再存在于 live-monitor 中。

## 任务 6：同步文档与 Roadmap

**文件：**
- 修改：`services/live-crawler/README.md`
- 修改：`services/live-monitor/README.md`
- 修改：`docs/ROADMAP.md`

- [x] **步骤 1：更新 live-crawler README 的 API 职责**

在 `services/live-crawler/README.md` 中，更新 `live-crawler cookie-api` 这一行：

```markdown
| `live-crawler api` | `python -m monitor.server` | Cookie API + TikTok 凭据刷新 API + TikTok live-status/dashboard API，监听 `8777` |
```

在模块总览里，更新 `monitor/`：

```markdown
| `monitor/` | Cookie API、TikTok 刷新 API、TikTok live-status/dashboard API、登录状态兼容层 |
```

在启动表后补一段简短的 API 说明：

```markdown
`python -m monitor.server` 现在也是 TikTok 直播大屏查询入口：

- `POST /api/v1/tiktok/live-status/batch`：读取 Redis 中的轻量开播状态，需 `X-API-Token`
- `POST /api/v1/tiktok/dashboard/data`：按 `dataType + roomId + collectionId` 拉取 TikTok 大屏原始响应信封，需 `X-API-Token`
```

- [x] **步骤 2：更新 live-monitor README 的归属说明**

在 `services/live-monitor/README.md` 中，移除 `routes/live_status.py` 的模块树条目，并从 API 列表中删除 `/api/v1/tiktok/live-status/batch`。

在 Redis bridge 小节附近加上这段说明：

```markdown
live-monitor 只负责写入 Redis 状态；下游查询入口已迁移到 `services/live-crawler/monitor/api/live_status_routes.py`。
```

- [x] **步骤 3：在开始执行时更新 ROADMAP**

如果这个 plan 现在就要执行，在 `docs/ROADMAP.md` 中新增一条 `进行中` 项：

```markdown
- [ ] **TikTok 直播大屏数据 API 服务**(live-crawler live-status/dashboard 查询入口) → [superpowers/plans/2026-06-24-tiktok-live-dashboard-data-api-service.md](superpowers/plans/2026-06-24-tiktok-live-dashboard-data-api-service.md)
```

当所有验收标准都通过后，把该项移到 `最近完成`，日期写 `2026-06-24`。

## 任务 7：最终验证

**文件：**
- 验证：本计划触及的所有文件

- [x] **步骤 1：运行新的 live-crawler 测试**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/utils/test_redis_bridge.py tests/crawlers/http/test_tiktok_dashboard_fetchers.py tests/services/test_dashboard_data.py tests/monitor/test_live_status_batch.py tests/monitor/test_tiktok_dashboard_routes.py tests/monitor/test_server_routes.py -v
```

预期：通过。

- [x] **步骤 2：运行 TikTok HTTP 回归测试**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 pytest tests/crawlers/http/test_tiktok_collector_query_params.py tests/crawlers/http/test_tiktok_collector_credential_validation.py tests/crawlers/http/test_tiktok_collector_business_retry.py tests/crawlers/http/test_tiktok_adapter_recovery.py -v
```

预期：通过。

- [x] **步骤 3：运行 live-monitor 剩余的 Redis 测试**

运行：

```bash
cd services/live-monitor
uv run --python 3.12 pytest tests/test_redis_bridge.py tests/test_api_response.py -v
```

预期：通过。

- [x] **步骤 4：确认旧的 live-monitor 查询路由已删除**

运行：

```bash
rg -n "routes.live_status|live_status_router|/api/v1/tiktok/live-status/batch" services/live-monitor
```

预期：没有 `routes.live_status` 或 `live_status_router` 的引用。README 里说明查询入口已迁移到 live-crawler 也可以接受。

- [x] **步骤 5：确认新的 live-crawler endpoint 可发现**

运行：

```bash
cd services/live-crawler
uv run --python 3.12 python - <<'PY'
from monitor.server import app
for route in app.routes:
    if "tiktok" in route.path or "cookies" in route.path:
        print(route.path)
PY
```

预期输出包含：

```text
/api/cookies/{account_id}
/api/refresh_tiktok_credential
/api/v1/tiktok/live-status/batch
/api/v1/tiktok/dashboard/data
```

- [ ] **步骤 6：使用真实 token 和账号做手工 smoke test**

启动 API：

```bash
cd services/live-crawler
APP_ENV=pro uv run --python 3.12 python -m monitor.server
```

在另一个终端里调用 live-status：

```bash
TOKEN="$(uv run --python 3.12 python - <<'PY'
from core.config import Settings
print(Settings.COOKIE_API_CONFIG["token"])
PY
)"
ACCOUNT_ID="k19f2q44"
curl -X POST http://127.0.0.1:8777/api/v1/tiktok/live-status/batch \
  -H "Content-Type: application/json" \
  -H "X-API-Token: ${TOKEN}" \
  -d "{\"collectionIds\":[\"${ACCOUNT_ID}\"]}"
```

预期：JSON body 的 `code=200`，且 `data[0]` 包含 `collectionId`、`isLive`、`roomId` 和 `flvUrl`。

调用 dashboard data：

```bash
ROOM_ID="7651420995556182804"
curl -X POST http://127.0.0.1:8777/api/v1/tiktok/dashboard/data \
  -H "Content-Type: application/json" \
  -H "X-API-Token: ${TOKEN}" \
  -d "{\"dataType\":\"trend_chart\",\"roomId\":\"${ROOM_ID}\",\"collectionId\":\"${ACCOUNT_ID}\",\"timeRange\":\"last_5m\"}"
```

预期：JSON body 的 `code=200`，`data.dataType="trend_chart"`，`data.roomId` 等于 `${ROOM_ID}`，并且 `data.request.response` 是 TikTok 原始 JSON 字符串。

## 验收标准

- `POST /api/v1/tiktok/live-status/batch` 可从 `services/live-crawler/monitor/server.py` 访问。
- `POST /api/v1/tiktok/live-status/batch` 返回的 `collectionId/isLive/roomId/flvUrl` 结构与旧的 live-monitor 路由一致。
- 两个新 endpoint 都会对缺失或错误的 `X-API-Token` 返回 HTTP 403。
- `services/live-monitor/routes/live_status.py` 和 `services/live-monitor/tests/test_live_status_batch.py` 已删除。
- `POST /api/v1/tiktok/dashboard/data` 支持 `core_stats`、`trend_chart`、`source_new`、`user_portrait`、`product_list` 和 `room_info`。
- `trend_chart` 支持 `timeRange=full|last_5m|last_30m`；只有 `last_5m` 和 `last_30m` 会向上游发送 `start_time`。
- `real_collector.py` 只包含大屏 fetcher，不会把定时 `collect_tiktok()` 的行为混进实时查询流。
- `real_collector.py` 使用 `API-inventory.md` 里的 55-ID core stats 集合，以及独立的 27-ID trend chart 集合。
- 对这六个 business endpoint，大屏 fetcher 不会调用 `_check_code()`。
- `setup_session(collectionId)` 仍然是 TikTok 大屏凭据/session 的唯一入口。
- 新增的聚焦测试和现有的 TikTok HTTP 回归测试都通过。
- README 和 ROADMAP 体现了新的归属关系：live-monitor 写 Redis；live-crawler 暴露下游查询 API。
