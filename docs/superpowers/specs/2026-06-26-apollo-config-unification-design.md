# Apollo 配置统一改造设计

> 状态:已确认,写入方案已按公司 Apollo 策略调整为 Portal 人工维护
> 日期:2026-06-26
> 本次范围:彻底迁移 live-stream + 全局通用 key + apollo 模板改造分发到 4 服务

## 1. 背景与目标

### 现状问题

live-stream 当前配置散落在三处,方式各异:

1. **环境变量**(`os.environ.get`)—— 约 13 个:`PRIMARY_NODE_URL`、`BACKUP_NODE_URL`、
   `LIVE_STREAM_ROOM_SOURCE`、`LIVE_STREAM_WORKER_ID`、`STREAM_*` 系列流控参数、
   `REDIS_*`、`STREAM_LEASE_TTL_SECONDS` 等
2. **临时 Apollo 拉取**(裸 `requests.get` + `fetch_apollo_config`)—— Kafka/OSS 配置,
   **无缓存、无热更新、无容灾**,且 `APOLLOID` 被硬编码、Windows URL 被硬编码、
   用 `istest`/`develop`/`os.name=='nt'` 硬判断环境
3. **硬编码默认值** —— 散落各处(如 Kafka topic `liveTs`)

### 目标

所有业务配置收敛到 Apollo,**Apollo 是唯一权威源**,不从环境变量/.env/硬编码读取业务配置。
用 live-crawler 的成熟 Apollo 客户端(含热更新/缓存/容灾)替换临时实现。公司 Apollo 禁止代码自动写入/发布配置,配置值由 Apollo Portal 人工维护。

### 关键约束

- 4 服务共享 `app_id=live-spider`、`application` namespace
- cluster 由环境变量 `DEPLOY_ENV` 决定(dev01 / PRO 等)
- 仅 3 个 Apollo 引导参数走环境变量(鸡生蛋问题,无法避免):
  `APOLLO_URL`、`APOLLOID`(默认 `live-spider`)、`DEPLOY_ENV`
- key 命名统一小写点分(dot.case)
- 每个服务拥有独立的 `core/apollo/` 模板副本

## 2. 本次范围边界

| 项目 | 本次做 | 留待后续 |
|------|--------|----------|
| live-stream 全部配置迁移 | ✅ 彻底做(通用 + 特有 key) | — |
| 全局通用 key 写入 Apollo(DEV) | ❌ | 公司 Apollo 禁止代码写入,由 Apollo Portal 人工维护 |
| 4 服务通用 key 引用同步改名 | ✅ 必须(Apollo 改名后旧引用失效) | — |
| apollo 模板改造 + 分发到 4 服务 | ✅ | — |
| live-crawler/live-monitor/adspower 特有 key 迁移 | ❌ | 用户在本次所有 todo 完成后接着实现 |
| 删除旧 key | ❌ | 用户验证无回归后自行在 Portal 清理 |

## 3. Apollo 模板改造(基准)

以 `services/live-crawler/core/apollo` 为基准,仅保留读取能力:

| 能力 | 来源 | 说明 |
|------|------|------|
| 读取 `get_value` | 现有 apollo | 三级降级 + 热更新长轮询 + 本地缓存容灾,保留 |
| 写入/发布配置 | 不实现 | 公司 Apollo 禁止代码、脚本或 OpenAPI 自动写入/发布配置 |

- 改造后分发到 4 个服务各自独立的 `core/apollo/`,各服务独立演进
- 配置值由有权限的人在 Apollo Portal 人工维护和发布

## 4. 配置 Key 清单(全部小写点分)

### 通用配置(跨服务共享,不加服务前缀)

| 用途 | 旧 key | 新 key |
|------|--------|--------|
| Redis host | `redisHost` | `redis.host` |
| Redis port | `redisPort` | `redis.port` |
| Redis password | `redisPassword` | `redis.password` |
| Redis db | `redisDb` | `redis.db` |
| Kafka 服务器 | `kafkaPro` | `kafka.servers`(取出即用,不 eval) |
| Kafka topic | `topic_name` | `live_stream.kafka.topic` |
| OSS endpoint | `endpoint` | `oss.endpoint` |
| OSS bucket | `bucket_name` | `oss.bucket_name` |
| OSS key id | `access_key_id` | `oss.access_key_id` |
| OSS key secret | `access_key_secret` | `oss.access_key_secret` |
| OSS region | `oss_region` | `oss.region` |

### live-stream 特有(`live_stream.` 前缀)

| 用途 | 新 key | 默认值 | 消费方式 |
|------|--------|--------|---------|
| 主节点 URL | `live_stream.primary_node_url` | `http://192.168.46.39:8080` | 实时(热更新)|
| 备节点 URL | `live_stream.backup_node_url` | 同上 | 实时 |
| 房间来源模式 | `live_stream.room_source` | `http` | 实时 |
| 工作节点 ID | `live_stream.worker_id` | 自动生成 | 实时 |
| 最大重试次数 | `live_stream.max_retries` | `12` | 实时 |
| 重试初始间隔 | `live_stream.retry_interval_seconds` | `1` | 实时 |
| 重试退避因子 | `live_stream.retry_backoff` | `1.5` | 实时 |
| 最大重试间隔 | `live_stream.max_retry_interval_seconds` | `30` | 实时 |
| FFmpeg 分析时长 | `live_stream.analyze_duration_us` | `5000000` | 实时 |
| FFmpeg 探测大小 | `live_stream.probe_size_bytes` | `10000000` | 实时 |
| 心跳间隔 | `live_stream.heartbeat_interval_seconds` | `10` | 实时 |
| 无数据超时 | `live_stream.no_data_timeout_seconds` | `25` | 实时 |
| Redis 租约 TTL | `live_stream.lease_ttl_seconds` | `360` | 启动读一次 |

## 5. 模块架构

每个服务新增/对齐独立的 `core/apollo/` 模块。以 live-stream 为例:

```
services/live-stream/
├── core/
│   ├── __init__.py
│   └── apollo/
│       ├── __init__.py          # 全局单例 APOLLO,引导参数从环境变量读取
│       ├── apollo_client.py     # 读取+热更新+缓存
│       └── util.py
├── config.py                    # 【新增】集中配置访问层(门面)
├── TT_client.py                 # 改为从 config 读取
└── redis_room_source.py         # 改为从 config 读取
```

### config.py 门面设计

不让业务代码散乱直接调 `APOLLO.get_value(...)`,而是收敛到 `config.py`:

1. **单一映射源**:「点分 key ↔ 代码用法 ↔ 默认值」集中一处
2. **类型转换集中**:封装 int/float 转换(替代散落的 `_env_int`/`_env_float`/`eval`)
3. **热更新天然生效**:暴露的是**函数**(每次调 `get_value`),不是模块级常量

```python
from core.apollo import APOLLO

def _get_int(key: str, default: int, minimum: int | None = None) -> int:
    raw = APOLLO.get_value(key, default_val=str(default))
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = default
    return max(val, minimum) if minimum is not None else val

# 流控参数(热更新生效)
def stream_max_retries() -> int:
    return _get_int("live_stream.max_retries", 12, minimum=1)

# 连接类配置(启动读一次)
def redis_config() -> dict: ...
```

## 6. 消费方式

- 流控参数、节点 URL、超时等 → 读取点实时 `get_value`,享热更新,**禁止存模块级常量**
- 连接类配置(Redis/Kafka/OSS client)→ 启动读一次建立连接,变更需重启生效
- 移除所有 Windows 硬编码 URL、`istest`/`develop` 环境判断(环境由 cluster=`DEPLOY_ENV` 决定)
- `kafka.servers` 取出即用,移除 `eval()`;`live_stream.kafka.topic` 取代硬编码 `liveTs`

## 7. 配置维护策略

- 不生成写入脚本,不提供 `openapi_writer.py`,不通过代码、脚本、CI 或 OpenAPI 自动写入/发布 Apollo 配置
- 由有权限的人在 Apollo Portal 人工新增/更新全部通用点分 key + 全部 `live_stream.*` 特有 key(其余 3 服务特有 key 本次不写)
- **新 key 与旧 key 并存,不删旧 key**(用户后续自行在 Portal 清理)
- PRO 等生产集群用户确认后单独处理

## 8. 跨服务影响

通用 key 被 4 服务、21 个文件引用。本次 apollo 改名后:

1. 用 codegraph 精确定位每个 `get_value`/config 读取点(非纯字符串替换,避免误伤)
2. 4 服务通用 key 引用与 Apollo 改名**同时上线**,否则线上读不到配置
3. 重点文件:live-crawler `core/config_base.py`、`utils/redis_bridge.py`、`crawlers/http/base.py`;
   live-monitor `config.py`、`base.py`、`utils/Tools.py`、`utils/redis_bridge.py`、`tasks/scheduler_tasks.py`;
   adspower-server `app/services/login_monitor.py`;live-stream `TT_client.py`、`redis_room_source.py`

## 9. 长期规则沉淀

新建 `.claude/rules/apollo-config.md`(按 `paths` frontmatter 自动触发),记录:
Apollo 唯一权威源、共享 app_id/namespace、cluster 由 DEPLOY_ENV 决定、3 个引导参数例外、
小写点分命名、每服务独立 core/apollo、读取点实时 get_value、config.py 门面、
kafka.servers 取出即用、改通用 key 的连锁影响、禁止代码写入 Apollo。
在根 `CLAUDE.md` rules 表格和 `AGENTS.md` 各加一行指针引用(single-source-of-truth,不重复内容)。

## 10. 执行顺序

1. 分发 apollo 读取模板到 live-stream
2. live-stream 建 config.py → 改造 live-stream / codegraph 定位引用
3. 由 Apollo Portal 人工维护新点分 key
4. 同步改 4 服务通用 key 引用 → 写规则文件
5. 验证 4 服务无回归
