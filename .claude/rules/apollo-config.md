---
paths:
  - "services/live-stream/core/apollo/**"
  - "services/live-stream/config.py"
  - "services/live-stream/TT_client.py"
  - "services/live-stream/redis_room_source.py"
  - "services/live-stream/scripts/seed_apollo_config.py"
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
  `kafka.servers`（逗号分隔字符串,取出即用,**不再 eval**）`kafka.topic`
  `oss.endpoint` `oss.bucket_name` `oss.access_key_id` `oss.access_key_secret` `oss.region`
- **服务特有配置**（加服务前缀）: `live_stream.primary_node_url` `live_stream.max_retries` …

## 消费方式：读取点实时调用 get_value

- 流控参数、节点 URL、超时 → 每次使用处经 `config.py` 门面调 `APOLLO.get_value`,
  天然享热更新（客户端后台长轮询自动刷新内存缓存）,**禁止存模块级常量**
- 连接类配置（Redis/Kafka/OSS client）→ 启动读一次建立连接,变更需重启生效
- 每服务用 `config.py`（live-crawler 为 `core/config_base.py`）门面集中封装
  「key ↔ 默认值 ↔ 类型转换」,禁止散乱直接调 `get_value`

## 每服务独立 core/apollo/ 副本

apollo 客户端模板（读取 + 热更新 + 缓存 + OpenAPI 写入）在每个服务下各有一份
`core/apollo/`,独立演进。新增写入能力见 `core/apollo/openapi_writer.py`。

## 写配置到 Apollo：OpenAPI

- 写入走 `openapi_writer.py`（PUT items + POST releases）,OpenAPI env 用小写 `dev`
- **token 从环境变量 `APOLLO_OPENAPI_TOKEN` 读取,绝不硬编码或提交**
- 改通用 key 影响多个服务: 重命名通用 key 时需在所有 cluster 同步,
  并用 codegraph 定位全部引用点与配置改名同时上线;旧 key 删除前先确认无服务再读
