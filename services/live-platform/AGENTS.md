# AGENTS.md - live-platform 开发约束

## 核心约束

### 1. 配置管理：统一走 Apollo

**硬性要求：所有配置必须且只能通过 Apollo 读取，禁止使用其他配置来源。**

**禁止的配置来源：**
- ❌ 环境变量（除 Apollo 连接参数外）
- ❌ .env 文件
- ❌ config.json / settings.ini 等配置文件
- ❌ 硬编码在代码中的配置值
- ❌ 命令行参数

**允许的唯一例外：Apollo 连接参数**
只有以下 3 个环境变量允许用于 Apollo 客户端初始化：
- `APOLLOID` - Apollo App ID（默认 `'live-spider'`）
- `APOLLO_URL` - Apollo 配置中心地址（默认 `'http://dev-apollo.tec-develop.com'`）
- `DEPLOY_ENV` - 集群/环境（默认 `'default'`）

**Apollo 配置读取规范：**

```python
# ✅ 正确：通过 shared.config.settings 读取
from shared.config import settings

db_host = settings.mysql.host
redis_host = settings.redis.host
```

```python
# ❌ 错误：直接读环境变量
import os
db_host = os.environ.get('DB_HOST')  # 禁止
```

```python
# ❌ 错误：读 .env 文件
from dotenv import load_dotenv
load_dotenv()  # 禁止
```

```python
# ❌ 错误：硬编码配置
API_TIMEOUT = 30  # 禁止，应该从 Apollo 读取
```

### 2. Apollo 标准模板

**使用团队标准 Apollo 客户端：**
- 位置：`core/apollo/` 目录
- 来源：`D:\SpiderCode\prod\spider-back-end\core\apollo`（团队标准模板）
- 组成：`apollo_client.py` / `util.py` / `setting.py` / `__init__.py`

**禁止：**
- ❌ 自行实现 Apollo 客户端
- ❌ 使用第三方 Apollo SDK（如 pyapolloconfig 等）
- ❌ 修改 `core/apollo/` 模板代码（除非全团队同步更新）

### 3. 配置定义规范

**所有新增配置必须：**
1. 在 `shared/config.py` 中定义对应的 dataclass
2. 在 `load_settings()` 中添加读取逻辑
3. 在 Apollo 配置中心补充对应的 key-value
4. 更新 `.agents.md` 的配置清单

**示例：新增超时配置**

```python
# shared/config.py
@dataclass(frozen=True)
class ServiceConfig:
    api_timeout: int  # 新增字段

def load_settings(apollo_config: dict[str, Any] | None = None) -> Settings:
    config = fetch_apollo_config() if apollo_config is None else apollo_config
    return Settings(
        service=ServiceConfig(
            api_timeout=_config_int(config, "apiTimeout"),  # 新增读取
        ),
        # ...
    )
```

然后在 Apollo 配置中心补充 `apiTimeout` key。

### 4. 禁止的反模式

**❌ 反模式 1：配置降级到环境变量**
```python
# 错误示例
timeout = os.environ.get('API_TIMEOUT', '30')  # 禁止
```

**❌ 反模式 2：配置硬编码**
```python
# 错误示例
RETRY_COUNT = 3  # 禁止，应该从 Apollo 读取
```

**❌ 反模式 3：运行时动态修改配置**
```python
# 错误示例
settings.mysql.host = "new-host"  # Settings 是 frozen dataclass，禁止修改
```

**❌ 反模式 4：多套配置系统并存**
```python
# 错误示例
from some_other_config import config  # 禁止引入其他配置体系
```

## 当前 Apollo 配置清单

### 必填配置（33 个 key）

#### Server 配置（5 个）
- `livePlatformHost` - 服务监听地址
- `livePlatformPort` - 服务监听端口
- `livePlatformDetectIntervalSeconds` - 房间检测周期（秒）
- `livePlatformAccessToken` - API 鉴权 token
- `cutliveNumber` - 最大并发录制数

#### MediaMTX 配置（4 个）
- `mediaMtxApiBaseUrl` - MediaMTX API 地址
- `mediaMtxRtmpBaseUrl` - MediaMTX RTMP 推流地址
- `mediaMtxRecordRoot` - MediaMTX 录制文件根目录
- `segmentTimeoutSeconds` - 切片超时判定（秒）

#### Redis 配置（4 个）
- `redisHost` - Redis 地址
- `redisPort` - Redis 端口
- `redisPassword` - Redis 密码
- `redisDb` - Redis 数据库编号

#### OSS 配置（6 个）
- `endpoint` - 阿里云 OSS endpoint
- `bucket_name` - OSS bucket 名称
- `access_key_id` - OSS access key
- `access_key_secret` - OSS secret key
- `ossPrefix` - OSS 对象 key 前缀
- `ossSignedUrlTtlSeconds` - OSS 签名 URL 有效期（秒）

#### Kafka 配置（2 个）
- `kafkaPro` 或 `kafkaAddress` - Kafka bootstrap servers（支持数组或逗号分隔字符串）
- `topic_name` - Kafka topic 名称

#### Upload 配置（1 个）
- `uploadWorkerCount` - 上传并发 worker 数

#### MySQL 配置（5 个）
- `devSqlHost` - MySQL 地址
- `devSqlPort` - MySQL 端口
- `devSqlUser` - MySQL 用户名
- `devSqlPassword` - MySQL 密码
- `database` - MySQL 数据库名

#### Log 配置（1 个）
- `livePlatformLogDir` - 日志目录路径

### 可选配置（1 个）
- `mysqlSyncIntervalSeconds` - MySQL → Redis 种子同步周期（秒），默认 300

---

## 配置变更流程

**新增/修改配置时，必须按以下顺序操作：**

1. **Apollo 配置中心**：先在 Apollo 补充 key-value
2. **代码定义**：在 `shared/config.py` 添加 dataclass 字段和读取逻辑
3. **文档更新**：更新本文档（AGENTS.md）的配置清单
4. **验证**：本地/测试环境验证配置读取正常

**❌ 禁止：代码先行，Apollo 后补**
- 不允许代码中引用 Apollo 尚未配置的 key
- 不允许配置项"先上线再补 Apollo"

---

## 多环境配置管理

### 环境区分
- **dev**: 开发/测试环境（Zadig dev）
- **prod**: 生产环境（Zadig prod）

### 配置隔离
- **同一 Apollo App ID**: `live-spider`
- **不同 cluster**: 通过 `DEPLOY_ENV` 环境变量区分
  - dev: `DEPLOY_ENV=default`
  - prod: `DEPLOY_ENV=<prod-cluster>`（待补充）

### 部署配置（Zadig）

**dev 环境变量：**
```yaml
APOLLOID: live-spider
APOLLO_URL: http://dev-apollo.tec-develop.com
DEPLOY_ENV: default
```

**prod 环境变量：**
```yaml
APOLLOID: live-spider
APOLLO_URL: <prod-apollo-url>  # 由运维提供
DEPLOY_ENV: <prod-cluster>     # 由运维提供
```

**禁止：**
- ❌ 在 docker-compose.yml 或 Dockerfile 中硬编码配置值
- ❌ 在代码中用 `if env == 'prod'` 分支读取不同配置来源

---

## 配置安全规范

### 敏感配置处理
- **密码/密钥类配置必须存储在 Apollo**
- **禁止在日志中打印敏感配置**
- **禁止在代码注释中写入敏感配置示例**

```python
# ✅ 正确：不打印敏感配置
logger.info(f"MySQL 连接初始化 | host={settings.mysql.host}")

# ❌ 错误：泄露密码
logger.info(f"MySQL 连接初始化 | password={settings.mysql.password}")
```

---

## 检查清单

**PR 提交前自查：**
- [ ] 所有新增配置已在 Apollo 配置中心补充
- [ ] 配置读取统一走 `shared.config.settings`
- [ ] 代码中无 `os.environ.get()` 读取业务配置
- [ ] 代码中无硬编码配置值（魔法数字/字符串）
- [ ] 已更新 AGENTS.md 配置清单
- [ ] 本地/dev 环境验证配置读取正常

---

## 违规处理

**发现以下行为将要求整改：**
1. 在代码中读取环境变量（Apollo 连接参数除外）
2. 引入 .env 文件或其他配置文件
3. 硬编码配置值
4. 使用非团队标准的 Apollo 客户端
5. 配置未在 Apollo 配置中心维护

**整改要求：**
- 立即修改代码，移除非 Apollo 配置来源
- 补充 Apollo 配置
- 更新文档

---

## FAQ

**Q: 为什么不用 .env 文件？**
A: .env 文件需要手工维护、多环境同步困难、无版本管理、无审计日志。Apollo 统一管理配置，支持热更新、权限控制、审计追踪。

**Q: 本地开发时如何调试配置？**
A: 本地启动时仍走 Apollo dev 集群。如需临时修改配置，在 Apollo dev 命名空间修改即可（会自动热更新）。

**Q: 紧急情况下能否临时用环境变量覆盖配置？**
A: 不允许。紧急情况应直接修改 Apollo 配置（生效速度更快，且有审计记录）。

**Q: 第三方库需要的配置（如 requests timeout）怎么办？**
A: 也必须从 Apollo 读取，然后传给第三方库：
```python
import requests
timeout = settings.service.api_timeout  # 从 Apollo 读取
requests.get(url, timeout=timeout)
```

**Q: 单元测试中如何 mock 配置？**
A: 使用 `settings.override()` 或直接传入 mock 的 Settings 对象：
```python
from shared.config import settings, Settings, ServerConfig

# 测试时覆盖配置
test_settings = Settings(
    server=ServerConfig(host="test-host", ...),
    # ...
)
settings.override(test_settings)
```

---

**最后更新：2026-06-23**
**维护者：开发团队**
