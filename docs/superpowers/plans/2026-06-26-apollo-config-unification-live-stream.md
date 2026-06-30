# Apollo 配置统一改造实施计划（live-stream）

> **For agentic workers:** Execute task-by-task with checkbox (`- [x]`) tracking. Use `subagent-driven-development` only when tasks are independent and risk/scale justifies review overhead; otherwise use `executing-plans` or inline execution with checkpoints.

**Goal:** 把 live-stream 的全部业务配置从环境变量/裸 requests 拉取/硬编码,统一收敛到 Apollo（共享 app_id=live-spider、application namespace、小写点分 key）。Apollo 配置值由 Portal 人工维护,禁止代码自动写入/发布。

**Architecture:** 从 live-crawler 拷贝成熟 Apollo 客户端（含热更新/缓存/容灾）到 live-stream 的 `core/apollo/`;新建 `config.py` 门面集中封装「点分 key ↔ 默认值 ↔ 类型转换」;`TT_client.py` 与 `redis_room_source.py` 改为从 `config.py` 读取。

**Tech Stack:** Python 3.12 · Apollo 配置中心 · redis · kafka-python · oss2 · pytest

**2026-06-29 策略变更:** 公司 Apollo 禁止代码、脚本或 OpenAPI 自动写入/发布配置。Task 2 与 Task 6 的写入能力已撤销,相关文件已从当前实现移除。后续配置变更必须由有权限的人在 Apollo Portal 人工维护。

**本次范围（重要）:** 只彻底做 live-stream。旧 key 保留不删,其他 3 服务（live-crawler/live-monitor/adspower-server）读旧 key 不会断,本次一行不动,留待用户后续连同它们的特有 key 一起迁移。

**关键约定:**
- 仅 3 个引导参数走环境变量:`APOLLO_URL`、`APOLLOID`（默认 live-spider）、`DEPLOY_ENV`（cluster）
- 禁止代码、脚本或 OpenAPI 自动写入/发布 Apollo 配置
- 新旧 key 并存,旧 key 由用户后续自行清理
- `kafka.servers` 取出即用,移除 `eval()`;loguru 用 f-string

---

## Task 1: 拷贝 Apollo 客户端模块到 live-stream

把 live-crawler 成熟的 Apollo 客户端（读取 + 热更新 + 缓存 + 容灾）拷贝到 live-stream,建立 `core/apollo/` 结构。引导参数从环境变量读取。

**Files:**
- Create: `services/live-stream/core/__init__.py`
- Create: `services/live-stream/core/apollo/__init__.py`
- Create: `services/live-stream/core/apollo/apollo_client.py`
- Create: `services/live-stream/core/apollo/util.py`

- [x] **Step 1: 创建 core 包**

创建空文件 `services/live-stream/core/__init__.py`（内容为空)。

- [x] **Step 2: 拷贝 apollo_client.py 和 util.py**

把 `services/live-crawler/core/apollo/apollo_client.py` 与 `services/live-crawler/core/apollo/util.py` 原样拷贝到 `services/live-stream/core/apollo/`。

```bash
mkdir -p services/live-stream/core/apollo
cp services/live-crawler/core/apollo/apollo_client.py services/live-stream/core/apollo/apollo_client.py
cp services/live-crawler/core/apollo/util.py services/live-stream/core/apollo/util.py
```

- [x] **Step 3: 写 core/apollo/__init__.py（全局单例 APOLLO）**

不拷贝 live-crawler 的 `__init__.py`,而是新写——保持引导参数从环境变量读取,APOLLOID 默认 `live-spider`。注意:不拷贝 live-crawler 的 `setting.py`（那是 live-crawler 特有的 KAFKA_HOSTS 旧用法,live-stream 不需要)。

```python
import os

from core.apollo.apollo_client import ApolloClient


# Apollo 引导参数（唯一允许走环境变量的配置,鸡生蛋问题）
apollo_id = os.environ.get("APOLLOID", "live-spider")
config_url = os.environ.get("APOLLO_URL", "http://dev-apollo.tec-develop.com")
cluster = os.environ.get("DEPLOY_ENV", "dev01")


APOLLO = ApolloClient(
    app_id=apollo_id,
    cluster=cluster,
    config_url=config_url,
)
```

- [x] **Step 4: 验证模块可导入**

Run: `cd services/live-stream && python -c "from core.apollo import APOLLO; print(type(APOLLO).__name__)"`
Expected: 打印 `ApolloClient`（若网络不通仍应能实例化,客户端构造不阻塞）

- [x] **Step 5: 提交**

```bash
git add services/live-stream/core/
git commit -m "feat: live-stream 新增 core/apollo 模块（拷贝自 live-crawler）"
```

---

## Task 2: 给 apollo 模板新增 OpenAPI 写入/发布能力（已撤销）

> 2026-06-29 撤销说明: 公司 Apollo 禁止代码、脚本或 OpenAPI 自动写入/发布配置。本任务历史上已执行,但相关实现已从当前代码中移除。后续不得恢复 `openapi_writer.py` 或同类写入入口。

**原计划文件（已删除）:**
- Delete: `services/live-crawler/core/apollo/openapi_writer.py`
- Delete: `services/live-stream/core/apollo/openapi_writer.py`

- [x] **Step 1: 撤销 OpenAPI writer 实现**

删除 Apollo 写入/发布 helper,不再保留可执行写入入口。

- [x] **Step 2: 撤销导入验证与提交指引**

不再提供 `update_apollo_item` / `publish_namespace` 导入命令、OpenAPI token 说明或提交指引。配置维护统一改为 Apollo Portal 人工操作。

---
## Task 3: 新建 config.py 配置访问层（门面）

集中封装「点分 key ↔ 默认值 ↔ 类型转换」。所有配置以函数形式暴露,每次调 `APOLLO.get_value`,流控参数天然享热更新。连接类配置也走函数,由调用方在启动时读一次。

**Files:**
- Create: `services/live-stream/config.py`
- Test: `services/live-stream/tests/test_config.py`

- [x] **Step 1: 写失败测试**

测试类型转换与默认值回退。用 monkeypatch 替换 `APOLLO.get_value`,避免依赖真实 Apollo。

```python
# services/live-stream/tests/test_config.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg


class FakeApollo:
    def __init__(self, store):
        self.store = store

    def get_value(self, key, default_val=None, namespace="application"):
        return self.store.get(key, default_val)


def test_stream_int_with_minimum(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.max_retries": "3"}))
    assert cfg.stream_max_retries() == 3


def test_stream_int_falls_back_to_default_on_garbage(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.max_retries": "abc"}))
    assert cfg.stream_max_retries() == 12


def test_stream_int_minimum_clamp(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.heartbeat_interval_seconds": "1"}))
    assert cfg.stream_heartbeat_interval_seconds() == 5  # minimum=5


def test_redis_config_types(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({
        "redis.host": "10.0.0.1", "redis.port": "6380",
        "redis.password": "pw", "redis.db": "2",
    }))
    rc = cfg.redis_config()
    assert rc == {"host": "10.0.0.1", "port": 6380, "password": "pw", "db": 2}


def test_kafka_servers_no_eval(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({
        "kafka.servers": "10.0.0.1:9092,10.0.0.2:9092",
    }))
    assert cfg.kafka_servers() == ["10.0.0.1:9092", "10.0.0.2:9092"]


def test_room_source_is_redis(monkeypatch):
    monkeypatch.setattr(cfg, "APOLLO", FakeApollo({"live_stream.room_source": "redis"}))
    assert cfg.is_redis_room_source() is True
```

- [x] **Step 2: 运行测试确认失败**

Run: `cd services/live-stream && python -m pytest tests/test_config.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'config'`

- [x] **Step 3: 写 config.py**

```python
"""live-stream 配置访问层（门面）。

所有业务配置统一从 Apollo 读取（唯一权威源）。
- 流控参数/节点 URL: 读取点实时调用,享热更新,禁止存模块级常量
- 连接类配置（Redis/Kafka/OSS）: 由调用方启动时读一次
仅 APOLLO_URL/APOLLOID/DEPLOY_ENV 走环境变量（见 core/apollo/__init__.py）。
"""
from __future__ import annotations

import socket
import os

from core.apollo import APOLLO


def _get_str(key: str, default: str = "") -> str:
    val = APOLLO.get_value(key, default_val=default)
    return default if val is None else str(val)


def _get_int(key: str, default: int, minimum: int | None = None) -> int:
    raw = APOLLO.get_value(key, default_val=str(default))
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = default
    return max(val, minimum) if minimum is not None else val


def _get_float(key: str, default: float, minimum: float | None = None) -> float:
    raw = APOLLO.get_value(key, default_val=str(default))
    try:
        val = float(raw)
    except (TypeError, ValueError):
        val = default
    return max(val, minimum) if minimum is not None else val


# ========== 连接类配置（启动读一次）==========
def redis_config() -> dict:
    """Redis 连接参数。"""
    return {
        "host": _get_str("redis.host"),
        "port": _get_int("redis.port", 6379),
        "password": _get_str("redis.password") or None,
        "db": _get_int("redis.db", 0),
    }


def kafka_servers() -> list[str]:
    """Kafka broker 列表。值为逗号分隔字符串,取出即用,不再 eval。"""
    raw = _get_str("kafka.servers")
    return [s.strip() for s in raw.split(",") if s.strip()]


def kafka_topic() -> str:
    return _get_str("live_stream.kafka.topic", "liveTs")


def oss_config() -> dict:
    """阿里云 OSS 连接参数。"""
    return {
        "endpoint": _get_str("oss.endpoint"),
        "bucket_name": _get_str("oss.bucket_name"),
        "access_key_id": _get_str("oss.access_key_id"),
        "access_key_secret": _get_str("oss.access_key_secret"),
    }


def cut_live_number() -> int:
    """单房间切片积压阈值（原 cutliveNumber 通用 key,保留原名）。"""
    return _get_int("cutliveNumber", 4)


# ========== 主备节点（实时,热更新）==========
def primary_node_url() -> str:
    return _get_str("live_stream.primary_node_url", "http://192.168.46.39:8080")


def backup_node_url() -> str:
    return _get_str("live_stream.backup_node_url", "http://192.168.46.39:8080")


# ========== 房间来源 / worker（实时）==========
def is_redis_room_source() -> bool:
    return _get_str("live_stream.room_source", "http").lower() == "redis"


def worker_id() -> str:
    configured = _get_str("live_stream.worker_id")
    if configured:
        return configured
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "unknown"
    return f"{socket.gethostname()}:{local_ip}:{os.getpid()}"


def stream_lease_ttl_seconds() -> int:
    return _get_int("live_stream.lease_ttl_seconds", 360)


# ========== FFmpeg 流控参数（实时,热更新）==========
def stream_max_retries() -> int:
    return _get_int("live_stream.max_retries", 12, minimum=1)


def stream_retry_interval_seconds() -> int:
    return _get_int("live_stream.retry_interval_seconds", 1, minimum=1)


def stream_retry_backoff() -> float:
    return _get_float("live_stream.retry_backoff", 1.5, minimum=1.0)


def stream_max_retry_interval_seconds() -> int:
    return _get_int("live_stream.max_retry_interval_seconds", 30, minimum=1)


def stream_analyze_duration_us() -> int:
    return _get_int("live_stream.analyze_duration_us", 5000000, minimum=1000000)


def stream_probe_size_bytes() -> int:
    return _get_int("live_stream.probe_size_bytes", 10000000, minimum=1000000)


def stream_heartbeat_interval_seconds() -> int:
    return _get_int("live_stream.heartbeat_interval_seconds", 10, minimum=5)


def stream_no_data_timeout_seconds() -> int:
    return _get_int("live_stream.no_data_timeout_seconds", 25, minimum=10)
```

- [x] **Step 4: 运行测试确认通过**

Run: `cd services/live-stream && python -m pytest tests/test_config.py -v`
Expected: PASS（6 passed）

- [x] **Step 5: 提交**

```bash
git add services/live-stream/config.py services/live-stream/tests/test_config.py
git commit -m "feat: live-stream 新增 config.py 配置访问层（点分 key 门面）"
```

---

## Task 4: 改造 redis_room_source.py 走 config.py

移除裸 requests 的 `_fetch_apollo_config` 和环境变量兜底 `_redis_config_from_env_or_apollo`,Redis 连接与 lease TTL 改走 `config.py`。

**Files:**
- Modify: `services/live-stream/redis_room_source.py:78-127`
- Test: `services/live-stream/tests/test_redis_room_source.py`（已存在,验证不回归）

- [x] **Step 1: 删除旧的 Apollo/env 读取函数**

删除 `redis_room_source.py` 第 78-108 行的 `_fetch_apollo_config` 和 `_redis_config_from_env_or_apollo` 两个函数（整段)。

- [x] **Step 2: 改造 RedisRoomSource 构造与默认客户端**

把第 111-127 行替换为从 `config.py` 读取:

```python
class RedisRoomSource:
    def __init__(self, redis_client: Any | None = None):
        self.redis = redis_client or self._create_default_client()
        self.lease_ttl_seconds = config.stream_lease_ttl_seconds()

    @staticmethod
    def _create_default_client() -> redis.Redis:
        cfg = config.redis_config()
        return redis.Redis(
            host=cfg["host"],
            port=cfg["port"],
            password=cfg["password"],
            db=cfg["db"],
            decode_responses=True,
        )
```

- [x] **Step 3: 调整 import,移除不再需要的 requests/os 依赖**

文件顶部（第 1-9 行）原有 `import os` / `import requests`。改为:
- 删除 `import requests`（已无裸 HTTP 调用)
- 保留 `import os`（其他地方可能用到;若 lint 报未使用再删)
- 新增 `import config`

确认改后顶部为:

```python
from __future__ import annotations

import json
import time
from typing import Any

import redis

import config
```

同时删除文件中已无引用的 `DEFAULT_STREAM_LEASE_TTL_SECONDS` 常量（第 17 行)——它的职责已移到 `config.stream_lease_ttl_seconds()` 的默认值 360。

- [x] **Step 4: 隔离既有测试的 Apollo 依赖**

改造后 `__init__` 会调用 `config.stream_lease_ttl_seconds()` → `APOLLO.get_value`,
既有测试虽注入了 FakeRedis,这一步仍会触达真实 Apollo（无网络时 fallback 有数秒超时）。
在 `tests/test_redis_room_source.py` 顶部（第 6 行 import 之后）加一个 autouse fixture 隔离:

```python
import pytest
import redis_room_source as rrs


@pytest.fixture(autouse=True)
def _stub_lease_ttl(monkeypatch):
    # 隔离 Apollo: lease ttl 用固定值,避免测试触达配置中心
    monkeypatch.setattr(rrs.config, "stream_lease_ttl_seconds", lambda: 360)
```

- [x] **Step 5: 运行既有测试确认不回归**

Run: `cd services/live-stream && python -m pytest tests/test_redis_room_source.py -v`
Expected: PASS（既有测试通过 FakeRedis 注入,lease ttl 被 stub,不触达 Apollo)

- [x] **Step 6: 提交**

```bash
git add services/live-stream/redis_room_source.py services/live-stream/tests/test_redis_room_source.py
git commit -m "refactor: redis_room_source 配置读取改走 config.py 点分 key"
```

---

## Task 5: 改造 TT_client.py 走 config.py

移除 `_env_int`/`_env_float`、裸 requests 的 `fetch_apollo_config`、Windows 硬编码 URL 与 istest 判断;KafkaHelper/AiyunOBSHelper、流控参数、主备节点、主入口全部改走 `config.py`。

**Files:**
- Modify: `services/live-stream/TT_client.py`（多处,见下)

- [x] **Step 1: 顶部新增 import config**

在 `TT_client.py` 顶部 import 区（第 19 行 `import re` 后）新增:

```python
import config
```

- [x] **Step 2: 删除 _env_int / _env_float 辅助函数**

删除第 39-56 行 `_env_int` 和 `_env_float` 两个函数（整段)。它们的职责已由 `config._get_int/_get_float` 承担。

- [x] **Step 3: 删除模块级 LIVE_STREAM_ROOM_SOURCE 常量**

删除第 33 行:

```python
LIVE_STREAM_ROOM_SOURCE = os.environ.get("LIVE_STREAM_ROOM_SOURCE", "http").lower()
```

（房间来源判断改用 `config.is_redis_room_source()`,见 Step 8)

- [x] **Step 4: 改造主备节点 URL（第 502-503 行）**

把模块级常量改为不在导入期读取。删除第 502-503 行的 `PRIMARY_NODE_URL`/`BACKUP_NODE_URL` 常量定义,并修改 `request_with_fallback`（第 534-535 行）为运行时读取:

```python
def request_with_fallback(method, endpoint, json_data=None, timeout=5):
    nodes = [config.primary_node_url()]
    backup = config.backup_node_url()
    if backup and backup != nodes[0]:
        nodes.append(backup)
    # ... 其余逻辑不变
```

- [x] **Step 5: 删除 fetch_apollo_config（第 561-600 行）**

删除整个 `fetch_apollo_config` 函数（含 Windows 硬编码 URL、istest/develop 判断、`APOLLOID='live-spider'` 硬编码)。

- [x] **Step 6: 改造 KafkaHelper（第 673-680 行）**

```python
class KafkaHelper:
    def __init__(self):
        kafka_server = config.kafka_servers()  # 取出即用,不再 eval
        self.producer = KafkaProducer(
            bootstrap_servers=kafka_server,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
```

注意:`KafkaHelper.__init__` 原签名带 `istest=1`,现移除。检查所有实例化处（见 Step 9 的 MainHelper)。

- [x] **Step 7: 改造 AiyunOBSHelper（第 689-700 行）**

```python
class AiyunOBSHelper:
    def __init__(self):
        oss_cfg = config.oss_config()
        self.endpoint = oss_cfg["endpoint"]
        self.bucket_name = oss_cfg["bucket_name"]
        self.access_key_id = oss_cfg["access_key_id"]
        self.access_key_secret = oss_cfg["access_key_secret"]

        self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)
        self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)
```

原签名带 `istest=1`,移除。

- [x] **Step 8: 改造 MainHelper（第 928-932 行）**

```python
class MainHelper:
    def __init__(self, topic_name='liveTs'):
        self.FileHelperObj = FileHelper()
        self.AliYOBSHelperObj = AiyunOBSHelper()
        self.KafkaHelperObj = KafkaHelper()
        self.topic_name = topic_name
        # ... 其余不变
```

- [x] **Step 9: 改造 StreamConfig 实例化（第 1241-1250 行）**

把 `_env_int`/`_env_float` 调用改为 `config.*`,变量名沿用真实代码的 `stream_config`（与 `import config` 模块名不冲突,后续第 1253 行 `FFmpegStreamManager(config=stream_config)` 继续引用):

```python
    # 创建推流配置
    stream_config = StreamConfig(
        max_retries=config.stream_max_retries(),
        retry_interval=config.stream_retry_interval_seconds(),
        retry_backoff=config.stream_retry_backoff(),
        max_retry_interval=config.stream_max_retry_interval_seconds(),
        analyzeduration=config.stream_analyze_duration_us(),
        probesize=config.stream_probe_size_bytes(),
        heartbeat_interval=config.stream_heartbeat_interval_seconds(),
        no_data_timeout=config.stream_no_data_timeout_seconds(),
    )
```

- [x] **Step 10: 改造 is_redis_room_source_enabled / get_worker_id（第 1127-1139 行）**

```python
def is_redis_room_source_enabled():
    return config.is_redis_room_source()


def get_worker_id():
    return config.worker_id()
```

- [x] **Step 11: 改造主入口（第 1567-1571 行）**

```python
    topic_name = config.kafka_topic()
    liveRoomNumber = config.cut_live_number()
    MainHelperObj = MainHelper(topic_name=topic_name)
```

删除 `istest = 0` 和 `config_apollo = fetch_apollo_config(istest)` 两行。

- [x] **Step 12: 全文件搜残留,确认无遗漏**

Run: `cd services/live-stream && grep -nE "os\.environ\.get|fetch_apollo_config|_env_int|_env_float|eval\(|istest" TT_client.py`
Expected: 无输出（或仅剩与配置无关的合理用法,逐条确认)

- [x] **Step 13: 编译检查**

Run: `cd services/live-stream && python -m py_compile TT_client.py && echo OK`
Expected: 打印 `OK`

- [x] **Step 14: 运行既有 ffmpeg 命令测试确认不回归**

Run: `cd services/live-stream && python -m pytest tests/test_ffmpeg_command.py -v`
Expected: PASS

- [x] **Step 15: 提交**

```bash
git add services/live-stream/TT_client.py
git commit -m "refactor: TT_client 配置读取统一收敛到 config.py 点分 key"
```

---

## Task 6: 生成 Apollo 写入脚本（已撤销）

> 2026-06-29 撤销说明: 公司 Apollo 禁止代码、脚本或 OpenAPI 自动写入/发布配置。本任务历史上已执行,但 `services/live-stream/scripts/seed_apollo_config.py` 已从当前代码中移除。Apollo 配置只能通过 Portal 人工维护。

**原计划文件（已删除）:**
- Delete: `services/live-stream/scripts/seed_apollo_config.py`

- [x] **Step 1: 撤销写入脚本**

删除一次性 seed 脚本,不再在仓库中保存 Apollo 写入代码、OpenAPI token 使用方式或可执行发布命令。

- [x] **Step 2: 改为 Portal 人工配置**

由有权限的人在 Apollo Portal 手工新增/更新 DEV/dev01 点分 key,新旧 key 并存,旧 key 后续确认无服务读取后再人工清理。

---
## Task 7: 沉淀 apollo-config 规则 + 文档指针

新建 `.claude/rules/apollo-config.md`（paths 自动触发),根 CLAUDE.md 与 AGENTS.md 各加一行指针引用。

**Files:**
- Create: `.claude/rules/apollo-config.md`
- Modify: `CLAUDE.md`（rules 表格追加一行)
- Modify: `AGENTS.md`（追加一行指针)

- [x] **Step 1: 写规则文件**

```markdown
---
paths:
  - "services/live-stream/core/apollo/**"
  - "services/live-stream/config.py"
  - "services/live-stream/TT_client.py"
  - "services/live-stream/redis_room_source.py"
  - "services/live-crawler/core/apollo/**"
---

# Apollo 配置中心：唯一配置权威源

## 核心约定

所有业务配置统一收敛到 Apollo,**Apollo 是唯一权威源**。
禁止从环境变量、.env、硬编码常量读取业务配置。

- **app_id**: 所有服务共享 `live-spider`
- **namespace**: 统一 `application`
- **cluster**: 由环境变量 `DEPLOY_ENV` 决定（dev01 / PRO 等）,
  禁止用 `istest` / `os.name=='nt'` / `'develop' in url` 硬编码判断环境

## 唯一例外：Apollo 引导参数走环境变量

鸡生蛋问题,以下 3 个参数必须从环境变量读取:
`APOLLO_URL`、`APOLLOID`（默认 `live-spider`）、`DEPLOY_ENV`（cluster）

## key 命名：小写点分（dot.case）

- **通用配置**（跨服务共享,不加服务前缀）:
  `redis.host` `redis.port` `redis.password` `redis.db`
  `kafka.servers`（逗号分隔字符串,取出即用,**不再 eval**）
  `oss.endpoint` `oss.bucket_name` `oss.access_key_id` `oss.access_key_secret` `oss.region`
- **服务特有配置**（加服务前缀）: `live_stream.primary_node_url` `live_stream.kafka.topic` `live_stream.max_retries` …

## 消费方式：读取点实时调用 get_value

- 流控参数、节点 URL、超时 → 每次使用处经 `config.py` 门面调 `APOLLO.get_value`,
  天然享热更新（客户端后台长轮询自动刷新内存缓存）,**禁止存模块级常量**
- 连接类配置（Redis/Kafka/OSS client）→ 启动读一次建立连接,变更需重启生效
- 每服务用 `config.py`（live-crawler 为 `core/config_base.py`）门面集中封装
  「key ↔ 默认值 ↔ 类型转换」,禁止散乱直接调 `get_value`

## 每服务独立 core/apollo/ 副本

apollo 客户端模板（读取 + 热更新 + 缓存）在每个服务下各有一份
`core/apollo/`,独立演进。

## 禁止代码写入 Apollo

- 公司 Apollo 禁止代码、脚本或 OpenAPI 自动写入/发布配置。
- 配置变更必须由有权限的人在 Apollo Portal 人工维护与发布。
- 改通用 key 影响多个服务: 重命名通用 key 时需在所有 cluster 同步,
  并用 codegraph 定位全部引用点与配置改名同时上线;旧 key 删除前先确认无服务再读
```

- [x] **Step 2: CLAUDE.md rules 表格追加一行**

在根 `CLAUDE.md` 的 rules 表格（`tiktok-http-lifecycle.md` 行之后）追加:

```markdown
| `apollo-config.md` | 编辑各服务 core/apollo、config.py 或配置读取代码 | Apollo 唯一权威源、点分命名、引导参数例外、禁止代码写入 Apollo |
```

- [x] **Step 3: AGENTS.md 追加指针**

在 `AGENTS.md` 第 8 行（"遵循 CLAUDE.md..."）之后追加一行:

```markdown

配置相关改动遵循 `.claude/rules/apollo-config.md`（Apollo 为唯一配置权威源,小写点分 key,引导参数走环境变量）。
```

- [x] **Step 4: 提交**

```bash
git add .claude/rules/apollo-config.md CLAUDE.md AGENTS.md
git commit -m "docs: 新增 apollo-config 规则并在 CLAUDE.md/AGENTS.md 加指针"
```

---

## Task 8: 端到端验证 live-stream 无回归

确认改造后 live-stream 能正常导入、编译、跑通既有测试,且无残留环境变量/裸 Apollo 读取。

- [x] **Step 1: 全量编译检查**

Run: `cd services/live-stream && python -m py_compile TT_client.py redis_room_source.py config.py core/apollo/__init__.py core/apollo/apollo_client.py core/apollo/util.py && echo OK`
Expected: 打印 `OK`

- [x] **Step 2: 跑全部单测**

Run: `cd services/live-stream && python -m pytest tests/ -v`
Expected: 全部 PASS（test_config / test_redis_room_source / test_ffmpeg_command）

- [x] **Step 3: 确认无残留旧配置读取方式**

Run: `cd services/live-stream && grep -rnE "os\.environ\.get\(['\"](REDIS_|STREAM_|PRIMARY_|BACKUP_|LIVE_STREAM_|APOLLOID|ISTEST)|kafkaPro|fetch_apollo_config|_env_int|_env_float" --include=*.py . | grep -v core/apollo`
Expected: 无输出（引导参数 APOLLO_URL/APOLLOID/DEPLOY_ENV 仅允许出现在 core/apollo/__init__.py)

- [x] **Step 4: 更新子项目 README 目录树**

按 `update-docs-on-structure-change.md`,在 `services/live-stream/README.md` 项目结构里补充新增文件: `core/apollo/`、`config.py`,并明确配置值由 Apollo Portal 人工维护。

- [x] **Step 5: 提交**

```bash
git add services/live-stream/README.md
git commit -m "docs: live-stream README 补充 apollo 配置相关目录结构"
```

---

## 人工执行 / 本地无法验证

以下事项需要在有 Apollo 权限、DEV 环境和真实运行节点的上下文中执行；本轮只完成代码、文档和本地测试验证。

- [x] 在 Apollo Portal 人工维护 DEV/dev01 的新点分 key,尤其是 Redis/Kafka/OSS 凭据与节点 URL。
- [x] 在 Apollo Portal 确认新点分 key 已发布,旧 key 保留不删除。
- [x] 部署或重启 DEV live-stream 节点,确认 `APOLLO_URL` / `APOLLOID` / `DEPLOY_ENV` 引导参数正确。
- [x] 做 live-stream smoke test:`TT_client.py` 能启动,Kafka / OSS / Redis 初始化成功,`/check_status` 正常。
- [x] 如启用 Redis 房间源,在 Apollo 设置 `live_stream.room_source=redis`,观察抢占 lease、续租、断流刷新 `flvUrl`。
- [x] 观察真实日志与链路:FFmpeg 切片、OSS 上传、Kafka 推送、主备 fallback 都正常。
- [x] 后续其他服务完成迁移后,再统一评估并清理 Apollo 旧 key。

---
