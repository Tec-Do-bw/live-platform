# Lazada HTTP 采集系统 — 清晰分层架构 Spec

> 版本: v1.1 | 日期: 2026-04-14 | 作者: XBW

---

## Why

### 背景

当前 live_dp 的采集架构基于 AdsPower + DrissionPage 浏览器自动化，所有平台（TikTok、Shopee）都依赖浏览器实例运行。随着业务发展，出现了以下问题：

1. **请求频率无法灵活控制** — 浏览器模式串行访问页面，无法实现高频采集（如 10 分钟一次实时数据）
2. **资源开销大** — 每个账号需要一个 AdsPower 浏览器实例，内存和 CPU 占用高
3. **耦合严重** — 采集逻辑与浏览器生命周期深度绑定，无法独立扩展
4. **新平台接入困难** — Lazada 可通过纯 HTTP 请求采集，不需要浏览器渲染

### 目标

以 Lazada 为试点，建立独立于浏览器采集的 **HTTP 采集体系**，为后续 TikTok/Shopee 迁移铺路。

核心原则：
- **模块解耦**：HTTP 采集（模块 B）与养号续 Cookie（模块 A）完全分离
- **统一抽象**：定义 `BaseHttpCrawler` 基类，未来所有 HTTP 平台继承此基类
- **渐进迁移**：现有浏览器采集保持运行，两套系统并行

---

## Lazada 双端口架构

Lazada 有两个独立的端口，Cookie 体系完全独立：

| 端口 | 域名 | 用途 | Cookie 特征 |
|------|------|------|-------------|
| **sellercenter**（卖家中心） | `sellercenter.lazada.{country}` | 数据洞察、场次/商品列表、实时大屏 | `asc_uid`、`_tb_token_`、`epssw` |
| **live**（LazLive 直播后台） | `acs-m.lazada.{country}` / `live.lazada.{country}` | 直播列表、直播详情 | `_m_h5_tk`（mtop 签名用）、`lwrid`、`lwrtk` |

### 登录流程

```
用户通过 adspower-server 投屏登录 sellercenter
    ↓
JS Hook 拦截 DOM 获取账号密码 → 存入 cookies 表 extra 字段
    ↓
sellercenter 登录成功 → 提取 Cookie → 写入 cookies 表 (endpoint='sellercenter')
    ↓
程序自动用相同账密登录 live 端口
    ↓
live 登录成功 → 提取 Cookie → 写入 cookies 表 (endpoint='live')
```

**关键点**：两个端口使用相同的账号密码，但 Cookie 完全独立，需要分别登录、分别存储。

---

## What Changes

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    现有系统（迁移到新目录）                     │
│  crawlers/browser/  →  BaseLiveCrawler                      │
│    ├── tiktok.py       AdsPower + DrissionPage               │
│    └── shopee.py       浏览器拦截 + JS 注入                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    新增系统                                   │
│                                                              │
│  模块 A: cookie_keeper/        模块 B: crawlers/http/        │
│  ┌─────────────────────┐      ┌───────────────────────────┐ │
│  │ 养号服务（独立进程）  │      │ HTTP 采集（独立基类）      │ │
│  │ - 定时刷新 Cookie    │      │ - BaseHttpCrawler         │ │
│  │ - AdsPower 浏览器    │  CK  │ - LazadaHttpCrawler       │ │
│  │ - 自动登录续 Cookie  │──────│ - 使用 downloader/ 请求   │ │
│  │ - Cookie → SQLite   │      │ - 复用 monitor 监控钩子    │ │
│  └─────────────────────┘      └───────────────────────────┘ │
│                                                              │
│  Cookie 管理: services/cookie_manager.py                     │
│  共享上报:    services/data_reporter.py                      │
│  共享回调:    services/login_callback.py                     │
│  Cookie API:  monitor/api/cookie_routes.py                   │
│  Cookie 表:   monitor/db.py (cookies 表, 按 endpoint 区分)   │
└─────────────────────────────────────────────────────────────┘
```

### 目录结构（含架构重构）

本次 Lazada 接入同步进行目录结构优化，将 `core/` 拆分为 `config/` + `services/`，
采集器统一到 `crawlers/` 下，浏览器驱动重命名为 `browser/`。

```
live_dp/
├── main.py                                 # 入口（不变）
├── conftest.py                             # pytest 配置（不变）
│
├── config/                                 # ← 原 core/ 中的配置部分
│   ├── __init__.py                         #   导出 Settings 单例
│   ├── base.py                             #   ← 原 core/config_base.py
│   ├── config.py                           #   ← 原 core/config.py
│   └── apollo/                             #   ← 原 core/apollo/（整体搬过来）
│       ├── __init__.py
│       ├── apollo_client.py
│       ├── setting.py
│       └── util.py
│
├── crawlers/                               # ← 统一采集器入口
│   ├── __init__.py
│   ├── factory.py                          #   ← 原 spiders/live_crawler.py（工厂类）
│   ├── browser/                            #   浏览器采集体系
│   │   ├── __init__.py
│   │   ├── base.py                         #   ← 原 spiders/base.py
│   │   ├── tiktok.py                       #   ← 原 spiders/tiktok.py
│   │   ├── mx_tiktok.py                    #   ← 原 spiders/mx_tiktok.py
│   │   └── shopee.py                       #   ← 原 spiders/shopee.py
│   └── http/                               #   HTTP 采集体系（新增）
│       ├── __init__.py
│       ├── base.py                         #   BaseHttpCrawler（多阶段执行支持）
│       └── lazada.py                       #   LazadaHttpCrawler
│
├── services/                               # ← 采集流程共享业务组件
│   ├── __init__.py
│   ├── collection_mode.py                  #   ← 原 core/collection_mode.py
│   ├── collection_tracker.py               #   ← 原 core/collection_tracker.py
│   ├── data_reporter.py                    #   新增（从 base.py 抽取 send_api_request）
│   ├── login_callback.py                   #   新增（从 base.py 抽取 send_login_callback）
│   └── cookie_manager.py                   #   新增（Cookie 统一管理）
│
├── cookie_keeper/                          # 新增：养号服务（模块 A，独立进程）
│   ├── __init__.py
│   ├── keeper.py                           #   养号调度器（APScheduler），直接使用 CookieManager
│   └── browser_refresher.py                #   AdsPower 浏览器自动登录 + Cookie 提取
│
├── browser/                                # ← 原 webdriver/
│   ├── __init__.py
│   └── adspower.py                         #   ← 原 webdriver/browserapi.py
│
├── downloader/                             # HTTP 客户端（不变）
│   ├── __init__.py
│   ├── config.py
│   ├── core.py
│   └── models.py
│
├── monitor/                                # 采集监控系统（结构不变，新增文件）
│   ├── __init__.py
│   ├── db.py                               #   修改：新增 cookies 表
│   ├── tracker.py
│   ├── classifier.py
│   ├── registry.py                         #   修改：新增 lazada（含 daily 层级）
│   ├── server.py                           #   修改：注册 cookie_routes
│   ├── login_status_manager.py
│   ├── recovery_events.py
│   ├── invalid_marker.py
│   ├── api/
│   │   ├── accounts.py
│   │   ├── batches.py
│   │   ├── overview.py
│   │   ├── login_status_routes.py
│   │   ├── recrawl_routes.py
│   │   ├── registry_routes.py
│   │   └── cookie_routes.py                #   新增：Cookie CRUD API（Header sign 鉴权）
│   ├── recrawl/
│   │   ├── executor.py
│   │   ├── gap_detector.py
│   │   ├── models.py
│   │   ├── proxy.py
│   │   └── recovery_detector.py
│   ├── frontend/                           #   Vue3 前端（不变）
│   └── data/                               #   SQLite 数据库（运行时）
│
├── scheduler/                              # 定时调度（不变）
│   ├── __init__.py
│   └── task_scheduler.py
│
├── utils/                                  # 纯工具函数（精简）
│   ├── __init__.py
│   ├── logger.py
│   ├── request.py
│   ├── async_request.py
│   └── Params.py
│
├── infra/                                  # ← 业务级外部服务客户端
│   ├── __init__.py
│   ├── kafka_client.py                     #   ← 原 utils/kafka_client.py
│   ├── kafka_push_file.py                  #   ← 原 utils/kafka_push_file.py
│   └── alert.py                            #   ← 原 utils/alert.py
│
├── scripts/                                # 脚本（不变）
├── resource/                               # 运行时资源（不变）
├── demo/                                   # 示例代码（不变）
├── doc/                                    # 文档（不变）
│
└── tests/                                  # 测试目录（对齐源码结构）
    ├── crawlers/                            #   ← 原 tests/spiders/
    │   ├── browser/
    │   │   ├── test_browserapi_shopee_headers.py
    │   │   └── test_shopee_js_injection.py
    │   └── http/
    │       └── lazda/
    ├── monitor/                            #   不变
    ├── e2e/                                #   不变
    ├── test_daily_payloads.py
    └── test_recovery_full_collection_flow.py
```

### 目录迁移映射表

| 原路径 | 新路径 | 类型 |
|--------|--------|------|
| `core/config.py` + `core/config_base.py` + `core/apollo/` | `config/` | 移动 |
| `core/collection_mode.py`, `core/collection_tracker.py` | `services/` | 移动 |
| `spiders/base.py`, `tiktok.py`, `mx_tiktok.py`, `shopee.py` | `crawlers/browser/` | 移动 |
| `spiders/live_crawler.py` | `crawlers/factory.py` | 移动+重命名 |
| `webdriver/browserapi.py` | `browser/adspower.py` | 移动+重命名 |
| `utils/kafka_client.py`, `kafka_push_file.py`, `alert.py` | `infra/` | 移动 |
| `tests/spiders/` | `tests/crawlers/browser/` | 移动 |
| 无 | `crawlers/http/base.py`, `lazada.py` | 新增 |
| 无 | `services/data_reporter.py`, `login_callback.py`, `cookie_manager.py` | 新增 |
| 无 | `cookie_keeper/` | 新增 |
| 无 | `monitor/api/cookie_routes.py` | 新增 |

### 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| HTTP 客户端 | `live_dp/downloader/`（never_primp） | 已有浏览器指纹伪装、三层重试、线程池并发 |
| Cookie 存储 | monitor.db 新增 cookies 表，按 endpoint 区分 | 两个端口 Cookie 独立，每个账号两条记录 |
| Cookie 表设计 | `UNIQUE(account_id, platform, endpoint)` | sellercenter 和 live 各一条记录 |
| 账密存储 | 明文存入 cookies 表 extra 字段 | 仅用于养号服务自动登录续 Cookie |
| BaseHttpCrawler 继承 | **不继承** BaseLiveCrawler | 避免浏览器依赖，干净的接口定义 |
| 养号服务 | 独立子模块（cookie_keeper/） | 与采集解耦，独立进程运行 |
| 养号自动登录 | AdsPower 浏览器 + 自动填写账密 | 首次需验证码（用户手动），后续自动 |
| 数据上报 | 抽到 `services/data_reporter.py` 共享模块，两个基类共用 | 避免 150+ 行复杂逻辑（重试、落盘、登录事件写入）代码复制 |
| 登录回调 | 抽到 `services/login_callback.py` 共享模块，两个基类共用 | 避免回调逻辑 + 登出恢复检测代码复制 |
| 工厂类路由 | 在 LiveCrawler 中新增 http 分支 | main.py 统一调度，无需感知差异 |

---

## Phase 总览

| Phase | 名称 | 依赖 | 核心产出 |
|-------|------|------|----------|
| Phase 1 | Cookie 基础设施 | 无 | cookies 表 + CookieManager + Cookie API |
| Phase 2 | BaseHttpCrawler 基类 | Phase 1 | HTTP 采集基类 + 监控集成 + 数据上报 |
| Phase 3 | LazadaHttpCrawler 实现 | Phase 2 | Lazada 全部接口采集 + mtop 签名 |
| Phase 4 | 平台注册与调度集成 | Phase 3 | 工厂类注册 + config + main.py 调度 |
| Phase 5 | 养号服务（cookie_keeper） | Phase 1 | 定时刷新 Cookie + AdsPower 浏览器登录 |
| Phase 6 | adspower-server Lazada 登录 | Phase 1 | 投屏登录监听 + Cookie 写入 |

---

## Phase 1: Cookie 基础设施

### Why

HTTP 采集的核心前提是拥有有效的 Cookie。Lazada 有两个独立端口（sellercenter / live），Cookie 体系完全独立，每个账号需要存储两份 Cookie。同时需要存储账号密码（明文），供养号服务自动登录续 Cookie。

### What Changes

#### 1.1 cookies 表（monitor/db.py）

在 `init_db()` 中新增表。每个 Lazada 账号对应两条记录（sellercenter + live）：

```sql
CREATE TABLE IF NOT EXISTS cookies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    TEXT NOT NULL,                -- AdsPower profile_id / browser_id
    platform      TEXT NOT NULL,                -- 平台标识：lazada / tiktok / shopee
    endpoint      TEXT NOT NULL DEFAULT '',     -- 端口标识：sellercenter / live（同平台多端口场景）
    cookies       TEXT NOT NULL DEFAULT '{}',   -- JSON: {"cookie_name": "value", ...}
    is_valid      INTEGER NOT NULL DEFAULT 1,   -- 1=有效, 0=失效
    seller_id     TEXT DEFAULT '',              -- 平台卖家 ID（Lazada: asc_uid）
    venture       TEXT DEFAULT '',              -- 国家/区域代码（TH/MY/ID/VN/SG/PH）
    extra         TEXT DEFAULT '{}',            -- JSON 扩展字段，含账密等信息
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, platform, endpoint)
);
CREATE INDEX IF NOT EXISTS idx_cookies_platform_valid
    ON cookies(platform, is_valid);
```

**Lazada 账号数据示例**（每个账号两条记录）：

| account_id | platform | endpoint | cookies | is_valid | extra |
|------------|----------|----------|---------|----------|-------|
| profile_01 | lazada | sellercenter | `{"asc_uid":"101...", "_tb_token_":"5df...", ...}` | 1 | `{"username":"xxx@email.com", "password":"xxx123"}` |
| profile_01 | lazada | live | `{"_m_h5_tk":"6a4d...", "lwrid":"AgG...", ...}` | 1 | `{"username":"xxx@email.com", "password":"xxx123"}` |

**extra 字段说明**：

```json
{
    "username": "xxx@email.com",   // Lazada 登录账号（明文）
    "password": "xxx123"           // Lazada 登录密码（明文）
}
```

- 账密由 adspower-server 登录时 JS Hook 获取并写入
- 两条记录（sellercenter / live）都存储相同的账密
- 仅用于养号服务（cookie_keeper）自动登录续 Cookie

#### 1.2 CookieManager（services/cookie_manager.py）

```python
class CookieManager:
    """统一 Cookie 管理器（单例）"""

    def get_cookies(account_id, platform, endpoint='') -> dict | None
        """获取指定端口的有效 Cookie，无效返回 None
        
        Lazada 示例：
            get_cookies('profile_01', 'lazada', 'sellercenter')
            get_cookies('profile_01', 'lazada', 'live')
        TikTok/Shopee（无 endpoint 区分）：
            get_cookies('profile_01', 'tiktok')
        """

    def set_cookies(account_id, platform, cookies, endpoint='',
                    seller_id='', venture='', extra=None)
        """写入/更新 Cookie，自动标记 is_valid=1"""

    def invalidate(account_id, platform, endpoint='')
        """标记 Cookie 失效（is_valid=0）"""

    def is_valid(account_id, platform, endpoint='') -> bool
        """检查 Cookie 是否有效"""

    def get_credentials(account_id, platform) -> dict | None
        """获取账号密码（从任一 endpoint 的 extra 中读取）
        
        返回: {"username": "xxx", "password": "xxx"} 或 None
        """

    def list_accounts(platform, valid_only=True) -> list[dict]
        """列出平台下所有账号及 Cookie 状态（按 account_id 聚合）"""

    def check_validity(account_id, platform, endpoint='') -> bool
        """验证 Cookie 有效性（通过 HTTP 请求验证）
        
        TODO: 具体验证逻辑待实现
        """
```

#### 1.3 Cookie API（monitor/api/cookie_routes.py）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/cookies/{account_id}?platform=lazada&endpoint=sellercenter` | Header sign | 获取指定端口 Cookie |
| PUT | `/api/cookies/{account_id}` | Header sign | 写入/更新 Cookie（body 含 endpoint） |
| DELETE | `/api/cookies/{account_id}?platform=lazada&endpoint=live` | Header sign | 标记指定端口 Cookie 失效 |
| GET | `/api/cookies/list?platform=lazada` | Header sign | 列出平台所有账号（聚合两端口状态） |

**鉴权方式**：通过 HTTP Header 携带 sign，所有端口（sellercenter / live）使用统一的验证逻辑：

```
Header: X-Sign: <sign_value>
sign = md5(secret_key)
```

`secret_key` 配置在 `config/base.py` 的 `COOKIE_API_CONFIG` 中。服务端校验 Header 中的 `X-Sign` 值是否匹配即可，无需区分端口或账号。

**PUT 请求体示例**：

```json
{
    "platform": "lazada",
    "endpoint": "sellercenter",
    "cookies": {"asc_uid": "101...", "_tb_token_": "5df..."},
    "seller_id": "101007760547",
    "venture": "TH",
    "extra": {"username": "xxx@email.com", "password": "xxx123"}
}
```

#### 1.4 server.py 修改

注册 cookie_routes router：

```python
from monitor.api.cookie_routes import router as cookie_router
app.include_router(cookie_router)
```

### 产出文件

| 文件 | 操作 |
|------|------|
| `live_dp/services/cookie_manager.py` | 新增 |
| `live_dp/monitor/db.py` | 修改（新增 cookies 表） |
| `live_dp/monitor/api/cookie_routes.py` | 新增 |
| `live_dp/monitor/server.py` | 修改（注册路由） |
| `live_dp/config/base.py` | 修改（新增 COOKIE_API_CONFIG） |

---

## Phase 2: BaseHttpCrawler 基类

### Why

需要一个独立于浏览器的采集基类，定义 HTTP 采集的标准流程。与 `BaseLiveCrawler` 完全解耦，但复用监控钩子、数据上报格式、登录状态事件系统。

### What Changes

#### 2.1 BaseHttpCrawler（crawlers/http/base.py）

**核心流程**（与 BaseLiveCrawler 对比）：

```
BaseLiveCrawler.start_crawl()           BaseHttpCrawler.start_crawl()
─────────────────────────────           ─────────────────────────────
1. get_driver()（开浏览器）              1. cookie_manager.get_cookies() → self.cookies
2. listen_api()（网络监听）              2. Cookie 无效 → 跳过 + 回调 logout
3. visit_page_and_collect()             3. build_tasks(self.cookies)（构造第一阶段 Task）
   └─ 被动拦截 API 响应                  4. downloader.run(tasks)（批量请求）
4. format_api_message()                  5. parse_and_report(results)
5. send_api_request()                       └─ format_message() + send_request()
6. send_login_callback()                 6. build_next_tasks(results)?（多阶段钩子）
7. monitor.record()                      7. 重复 4~6 直到无后续阶段
                                         8. send_login_callback()
                                         9. monitor.record()
```

**接口定义**：

```python
class BaseHttpCrawler(ABC):
    """HTTP 采集爬虫基类（不依赖浏览器）"""

    def __init__(self,
                 account_id: str,
                 full_collection: bool = False,
                 group_name: str = '',
                 batch_id: str = ''):
        ...

    # ─── 子类必须实现 ───
    @abstractmethod
    def get_platform_name(self) -> str: ...

    @abstractmethod
    def build_tasks(self, cookies: dict[str, dict]) -> list[Task]: ...
        """构造第一阶段采集任务列表
        
        Args:
            cookies: 基类从 CookieManager 获取的 Cookie 字典
                     Lazada 示例: {'sellercenter': {...}, 'live': {...}}
                     单端口平台: {'': {...}}
        """

    def build_next_tasks(self, phase: int, results: list[DownloadResult]) -> list[Task]: ...
        """多阶段采集钩子（可选覆写）
        
        基类默认返回空列表（单阶段）。子类覆写此方法实现多阶段依赖。
        例如 Lazada 3.2 直播详情依赖 3.1 直播列表的 liveUuid。
        
        Args:
            phase: 当前阶段编号（从 2 开始，build_tasks 为阶段 1）
            results: 上一阶段的执行结果
            
        Returns:
            下一阶段的 Task 列表，空列表表示采集结束
        """
        return []

    @abstractmethod
    def parse_response(self, result: DownloadResult) -> dict | None: ...
        """解析单个响应，返回标准上报消息体或 None"""

    @abstractmethod
    def check_login_from_response(self, result: DownloadResult) -> bool: ...
        """从响应判断登录状态，True=正常，False=登出"""

    # ─── 基类提供 ───
    def start_crawl(self) -> dict: ...
        """标准采集流程（多阶段支持）
        
        流程：
            1. CookieManager 获取各端口 Cookie → self.cookies
            2. 调用 build_tasks(self.cookies) 构造第一阶段任务
            3. downloader.run(tasks) 执行请求
            4. parse_and_report(results) 解析上报
            5. 调用 build_next_tasks(phase, results)，若返回非空则回到步骤 3
            6. send_login_callback() 登录回调
            7. monitor.record() 监控记录
        """

    def format_message(self, url, method, body, response, cookies, extra) -> dict: ...
        """构造标准上报消息体（与 BaseLiveCrawler.format_api_message 格式一致）"""

    def send_request(self, message: dict) -> bool: ...
        """上报数据到 livelabstar.com（调用 services/data_reporter.py 共享模块）"""

    def send_login_callback(self, status, reason) -> bool: ...
        """登录状态回调（调用 services/login_callback.py 共享模块）"""
```

**Downloader 集成方式**：

```python
from live_dp.downloader import Downloader, Task

# 在 start_crawl() 中初始化
self.downloader = Downloader(
    proxy=self._get_proxy(),
    workers=self.config.get('http_workers', 5),
    headers=self._build_default_headers(),
)

# 子类在 build_tasks() 中构造任务
# Cookie 通过 Task.headers 中的 Cookie 字段传递（手动拼接）
def _cookie_header(self, cookies: dict) -> str:
    """将 Cookie dict 拼接为 HTTP Cookie 头"""
    return '; '.join(f'{k}={v}' for k, v in cookies.items())

tasks = [
    Task(
        url="https://acs-m.lazada.co.th/h5/mtop...",
        method="POST",
        headers={
            'Cookie': self._cookie_header(self.sc_cookies),
            ...
        },
        data={...},          # POST body
        meta={'api_type': 'live_list', 'room_id': ''},  # 业务元数据
    ),
    ...
]

# 批量执行
results = self.downloader.run(tasks)
```

**Cookie 传递说明**：Downloader 的 `Task.headers` 会与 Client 级别 headers 合并（Task 级别优先），因此在每个 Task 的 `headers` 中手动拼接 `Cookie: k1=v1; k2=v2` 即可。不同端口（sellercenter / live）的 Task 使用各自的 Cookie。

**监控钩子集成**：

```python
# start_crawl() 中
monitor = get_monitor()
monitor.start_account(batch_id, account_id, group_name, platform)

# 每个成功响应
monitor.record(batch_id, account_id, api_type, room_id, 'success', response_size)

# 结束
monitor.finish_account(batch_id, account_id, status)
```

#### 2.2 工厂类扩展（crawlers/factory.py）

新增 HTTP 爬虫路由：

```python
from crawlers.http.lazada import LazadaHttpCrawler

class LiveCrawler:
    PLATFORM_CRAWLERS = {
        'tiktok': TikTokLiveCrawler,
        'shopee': ShopeeLiveCrawler,
    }

    # 新增：HTTP 采集平台
    HTTP_CRAWLERS = {
        'lazada': LazadaHttpCrawler,
    }

    def __new__(cls, platform, browser_id, full_collection, group_name, batch_id):
        # 优先检查 HTTP 爬虫
        if platform in cls.HTTP_CRAWLERS:
            crawler_class = cls.HTTP_CRAWLERS[platform]
            return crawler_class(
                account_id=browser_id,
                full_collection=full_collection,
                group_name=group_name,
                batch_id=batch_id,
            )
        # 否则走浏览器爬虫
        ...

    @classmethod
    def get_supported_platforms(cls) -> list[str]:
        """返回所有支持的平台（浏览器 + HTTP）"""
        return list(cls.PLATFORM_CRAWLERS.keys()) + list(cls.HTTP_CRAWLERS.keys())
```

### 产出文件

| 文件 | 操作 |
|------|------|
| `live_dp/crawlers/http/__init__.py` | 新增 |
| `live_dp/crawlers/http/base.py` | 新增 |
| `live_dp/services/data_reporter.py` | 新增（从 BaseLiveCrawler.send_api_request 抽取） |
| `live_dp/services/login_callback.py` | 新增（从 BaseLiveCrawler.send_login_callback 抽取） |
| `live_dp/crawlers/browser/base.py` | 修改（send_api_request / send_login_callback 改为调用 services/ 共享模块） |
| `live_dp/crawlers/factory.py` | 修改（新增 HTTP_CRAWLERS 路由 + get_supported_platforms） |

---

## Phase 3: LazadaHttpCrawler 实现

### Why

实现 Lazada 平台全部 18 个采集接口，包括卖家中心（直播概览、场次详情、商品详情、实时数据）、数据洞察（关键指标、流量、商品、营销）、LazLive 直播后台（直播列表、直播详情）。

### What Changes

#### 3.1 接口清单与采集策略

| 编号 | 接口 | 采集模式         | 频率 |
|------|------|--------------|------|
| **卖家中心 - 营销中心** | |              | |
| 1.1 | mtop.lazada.live.data.seller.metrics | by day 逐日    | 每天 2 次 |
| 1.2 | mtop.lazada.live.data.seller.productRooms | 通用（l7d/l30d） | 每天 2 次 |
| 1.3 | mtop.lazada.live.data.seller.products | 通用（l7d/l30d） | 每天 2 次 |
| 1.4 | realtime/key/detail/trend/accumulationV2 | -            |  每天 2 次 |
| 1.5 | realtime/key/detailV2 | -            |  每天 2 次 |
| **卖家中心 - 数据洞察** | |              | |
| 2.1.1 | dashboard/key/overviewV2 | by day 逐日    | 每天 2 次 |
| 2.1.2 | dashboard/key/trendV2 | by day 逐日    | 每天 2 次 |
| 2.2.1 | dashboard/traffic/overall | by day 逐日    | 每天 2 次 |
| 2.2.2 | dashboard/traffic/source/ranking | by day 逐日    | 每天 2 次 |
| 2.2.3 | dashboard/traffic/search/ranking | by day 逐日    | 每天 2 次 |
| 2.3.1 | dashboard/product/overview | by day 逐日    | 每天 2 次 |
| 2.3.2 | product/diagnosis/overview | by day 逐日    | 每天 2 次 |
| 2.3.3 | product/performance/batch/itemV2（按营收） | by day 逐日    | 每天 2 次 |
| 2.3.4 | product/performance/batch/itemV2（按访客） | by day 逐日    | 每天 2 次 |
| 2.4.1 | promotion/board/overview | by day 逐日    | 每天 2 次 |
| 2.4.2 | promotion/board/trend | by day 逐日    | 每天 2 次 |
| 2.4.3 | promotion/board/category/ratio | by day 逐日    | 每天 2 次 |
| **LazLive 直播后台** | |              | |
| roomStatus 有四种状态  "Notice,Online,End,History"
| 对于 End,History 执行以下模式
| 3.1 | mtop.lazada.live.querylivesbystatus | 全量/增量分页      | 每天 2 次 |
| 3.2 | mtop.lazada.live.data.presenter.room.metrics | 逐场次          | 每天 2 次 |
| 对于 Online 执行以下模式
| 3.1 | mtop.lazada.live.querylivesbystatus | 实时           | 每 10min 1 次 |
| 3.2 | mtop.lazada.live.data.presenter.room.metrics | 对于Online场次实时 | 每 10min 1 次 |


#### 3.2 两种采集域

Lazada 接口分布在两个域：

| 域 | Base URL | Cookie 体系 | 签名方式 |
|-----|----------|-------------|----------|
| 卖家中心主站 (sellercenter) | `https://sellercenter.lazada.{country}/` | sellercenter Cookie | 无需额外签名 |
| acs-m mtop 网关 | `https://acs-m.lazada.{country}/` | mtop Cookie (`_m_h5_tk`) | md5(token + t + appKey + data) |

#### 3.3 mtop 签名计算

```python
def _calc_mtop_sign(self, token: str, timestamp: str, app_key: str, data: str) -> str:
    """Lazada mtop 接口签名：md5(token + '&' + t + '&' + appKey + '&' + data)"""
    raw = f"{token}&{timestamp}&{app_key}&{data}"
    return hashlib.md5(raw.encode()).hexdigest()
```

- `token` 取自 Cookie `_m_h5_tk` 的前 32 位（`_m_h5_tk.split('_')[0]`）
- `t` 为当前时间戳（毫秒）
- `appKey` 固定为 `"4272"`
- `data` 为请求参数的 JSON 字符串

#### 3.4 国家域名与时区映射

```python
LAZADA_COUNTRY_MAP = {
    "泰国": "co.th",   "马来": "com.my",  "印尼": "co.id",
    "越南": "vn",       "新加坡": "sg",    "菲律宾": "com.ph",
}

LAZADA_TIMEZONE_MAP = {
    "co.th": 7,  "com.my": 8, "co.id": 7,
    "vn": 7,     "sg": 8,     "com.ph": 8,
}
```

#### 3.5 build_tasks() 逻辑概览

```python
def build_tasks(self, cookies: dict[str, dict]) -> list[Task]:
    tasks = []

    # Cookie 由基类 start_crawl() 获取并传入
    # cookies = {'sellercenter': {...}, 'live': {...}}
    self.sc_cookies = cookies.get('sellercenter')
    self.live_cookies = cookies.get('live')

    # 1. 卖家中心 mtop 接口（1.1~1.3）— 使用 sellercenter Cookie + mtop 签名
    #    增量: 7 天逐日 / l7d
    #    全量: 30 天逐日 / l30d
    if self.sc_cookies:
        tasks += self._build_sellercenter_mtop_tasks()

    # 2. 卖家中心 sellercenter 接口（1.4~1.5, 2.x）— 使用 sellercenter Cookie，无需签名
    #    实时接口: 无日期参数
    #    by day 接口: 逐日生成 Task
    if self.sc_cookies:
        tasks += self._build_sellercenter_ba_tasks()

    # 3. LazLive 直播后台（3.1~3.2）— 使用 live Cookie + mtop 签名
    #    3.1 获取直播列表
    #    3.2 根据列表中的 liveUuid 逐个请求详情
    if self.live_cookies:
        tasks += self._build_lazlive_tasks()

    return tasks
```

**注意**：3.2 直播详情依赖 3.1 的结果，通过基类的多阶段机制处理：
- `build_tasks()` 阶段 1：构造 1.x + 2.x + 3.1 的 Task
- `build_next_tasks(phase=2, results)` 阶段 2：从 3.1 结果中解析 liveUuid 列表，为每个 liveUuid 构造 3.2 Task

---

#### 3.6 接口分组与约束条件

按请求特征将 18 个接口分为 5 组：

| 分组 | 接口编号 | Cookie 端口 | 日期格式 | 采集模式 | mtop 签名 | 分页 |
|------|---------|-------------|----------|----------|----------|------|
| **Group A: mtop by-day** | 1.1 | live | `YYYYMMDD\|YYYYMMDD` | 逐日采集 | 是 | 否 |
| **Group B: mtop range** | 1.2~1.3 | live | `YYYYMMDD\|YYYYMMDD` | 范围采集（l7d/l30d） | 是 | 是（pageNum, pageSize=100） |
| **Group C: BA 实时** | 1.4~1.5 | sellercenter | 无日期参数 | 实时 | 否 | 否 |
| **Group D: BA by-day** | 2.1~2.4 | sellercenter | `YYYY-MM-DD\|YYYY-MM-DD` | 逐日采集 | 否 | 部分（page, pageSize=5） |
| **Group E: LazLive** | 3.1~3.2 | live | `YYYYMMDD\|YYYYMMDD` | 3.1 分页 + 3.2 逐场次 | 是 | 3.1 分页（pageNum, pageSize=100） |

**关键差异**：
- **Cookie 端口**：1.1~1.3 和 3.x 使用 live Cookie（`_m_h5_tk`），1.4~1.5 和 2.x 使用 sellercenter Cookie
- **日期格式**：mtop 接口（1.x, 3.x）无分隔符，BA 接口（2.x）有分隔符
- **mtop 签名**：仅 mtop 网关接口（1.1~1.3, 3.1~3.2）需要签名，BA 接口无需签名

---

#### 3.7 关键约束条件

##### 3.7.1 日期参数计算规则

| 模式 | 天数 | 日期范围 | 生成方式 |
|------|------|----------|----------|
| **增量** | 7 天 | T-7 ~ T-1 | by day: 7 个 `(Di, Di)` 对<br>range: 1 个 `(T-7, T-1)` 对 |
| **全量** | 30 天 | T-30 ~ T-1 | by day: 30 个 `(Di, Di)` 对<br>range: 1 个 `(T-30, T-1)` 对 |

**日期格式约束**：
- mtop 接口（1.x, 3.x）：`YYYYMMDD|YYYYMMDD`（无分隔符）
- BA 接口（2.x）：`YYYY-MM-DD|YYYY-MM-DD`（有分隔符）

**示例**（假设 T = 2026-04-09）：
- 增量 by day：`20260408|20260408`, `20260407|20260407`, ..., `20260402|20260402`（7 个请求）
- 增量 range：`20260402|20260408`（1 个请求）
- 全量 by day：`20260408|20260408`, ..., `20260310|20260310`（30 个请求）

##### 3.7.2 时区转换逻辑

**规则**：所有日期参数必须使用对应国家时区的日期，不能硬编码。

```python
# 时区映射
LAZADA_TIMEZONE_MAP = {
    "co.th": 7,   # 泰国 UTC+7
    "com.my": 8,  # 马来 UTC+8
    "co.id": 7,   # 印尼 UTC+7
    "vn": 7,      # 越南 UTC+7
    "sg": 8,      # 新加坡 UTC+8
    "com.ph": 8,  # 菲律宾 UTC+8
}

# 计算流程
country_domain → LAZADA_TIMEZONE_MAP → UTC offset → 当地日期 - offset_days
```

**示例**：
- 泰国账号（co.th）：UTC+7，当前 UTC 时间 2026-04-09 10:00 → 当地时间 2026-04-09 17:00 → T = 2026-04-09
- 马来账号（com.my）：UTC+8，当前 UTC 时间 2026-04-09 10:00 → 当地时间 2026-04-09 18:00 → T = 2026-04-09

##### 3.7.3 mtop 签名计算

**适用接口**：1.1~1.3（卖家中心 mtop）、3.1~3.2（LazLive mtop）

**签名公式**：
```python
token = _m_h5_tk.split('_')[0]  # Cookie 前 32 位
t = str(int(time.time() * 1000))  # 毫秒时间戳
appKey = "4272"  # 固定值
data = json.dumps(data_dict, separators=(',', ':'))  # 紧凑 JSON（无空格）
sign = md5(f"{token}&{t}&{appKey}&{data}")
```

**关键点**：
- `token` 从 live Cookie 的 `_m_h5_tk` 字段提取（格式：`{32位token}_{timestamp}`）
- `data` 必须是紧凑 JSON（`separators=(',', ':')`），否则签名不匹配
- `t` 和 `sign` 必须同时作为 URL query string 参数传递

##### 3.7.4 Cookie 独立性

| 接口组 | Cookie 端口 | 获取方式 | 关键 Cookie 字段 |
|--------|-------------|----------|------------------|
| 1.1~1.3 (mtop) | `live` | `_get_cookies(browser_id, 'lazada', 'live')` | `_m_h5_tk`（签名用） |
| 1.4~1.5, 2.x (BA) | `sellercenter` | `_get_cookies(browser_id, 'lazada', 'sellercenter')` | `asc_uid`, `_tb_token_` |
| 3.1~3.2 (LazLive) | `live` | 同 1.1~1.3 | `_m_h5_tk`, `lwrid`, `lwrtk` |

**注意**：
- 1.1~1.3 虽然是"卖家中心-营销中心"的接口，但走的是 acs-m mtop 网关，使用 live Cookie
- 两个端口 Cookie 完全独立，不可混用，每个账号需要分别登录、分别存储

##### 3.7.5 分页处理规则

| 接口组 | 分页参数 | 起始值 | 页大小 | 终止条件 |
|--------|---------|--------|--------|----------|
| **mtop 分页**（1.2, 1.3, 3.1） | `pageNum` | 1 | 100 | 返回条数 < 100 |
| **BA 分页**（2.2.2, 2.2.3, 2.3.3, 2.3.4） | `page` | 1 | 5 | 返回条数 < 5 |

**实现方式**：
- 初始请求：`pageNum=1` 或 `page=1`
- 检查响应：如果返回数据条数 < pageSize，停止翻页
- 继续翻页：`pageNum += 1` 或 `page += 1`，重复请求

**增量模式优化**（仅 3.1 直播列表）：
- 除了检查返回条数，还需检查最后一条数据的时间戳
- 如果最后一条数据超出时间范围（早于 T-7），提前终止翻页

---

#### 3.8 多阶段依赖处理

**职责**：3.2 直播详情依赖 3.1 直播列表返回的 `liveUuid`

**实现方式**：

```python
def build_tasks(self, cookies, is_full) -> list[Task]:
    """阶段 1：构造所有非依赖接口的 Task"""
    tasks = []
    # 1.x + 2.x + 3.1
    return tasks

def build_next_tasks(self, phase: int, results: list[dict]) -> list[Task]:
    """阶段 2：从 3.1 结果提取 liveUuid，构造 3.2 Task"""
    if phase == 2:
        live_uuids = []
        for r in results:
            if r.get('api_type') == 'lazada_live_list':
                # 从响应中提取 rooms[*].liveUuid
                rooms = r.get('rooms', [])
                live_uuids.extend(room['liveUuid'] for room in rooms)
        
        if not live_uuids:
            return []  # 无直播间，终止
        
        # 为每个 liveUuid 构造 3.2 详情 Task
        return [self._build_room_metrics_task(uuid) for uuid in live_uuids]
    
    return []  # 无更多阶段
```

**关键点**：
- `build_next_tasks` 返回空列表时，基类终止多阶段循环
- 3.2 任务数量 = 3.1 返回的直播间数量（可能为 0）
- 如果 3.1 失败或返回空，3.2 不会执行

---

#### 3.9 错误处理约定

| 场景 | 检测方式 | 处理 |
|------|----------|------|
| **Cookie 过期** | HTTP 302 或 `ret` 含 `TOKEN_EXOIRED` | 标记 `cookie_expired=True`，终止当前账号采集 |
| **mtop 签名错误** | `ret` 含 `ILLEGAL_ACCESS` | 记录日志，由 Downloader 自动重试（L2 重试） |
| **接口限流** | HTTP 429 或 `ret` 含 `FLOW_LIMIT` | Downloader 指数退避重试（L2 重试） |
| **数据为空** | `data.model` 为 null 或空数组 | 正常情况（该日无数据），上报空结果，不中断 |
| **网络超时** | Downloader 超时 | 三层重试（L1 底层 + L2 应用层 + L3 最终失败） |
| **分页终止** | 返回条数 < pageSize | 停止翻页，合并已有数据，继续下一接口 |
| **阶段全部失败** | `_process_results` 返回空 | 基类终止采集 + 告警（通过 `alert.py`） |

**Cookie 过期检测逻辑**：

```python
def _check_cookie_expired(self, result: DownloadResult) -> bool:
    """检测 Cookie 是否过期"""
    # HTTP 302 重定向到登录页
    if result.status_code == 302:
        return True
    
    # mtop 接口：检查 ret 字段
    if 'ret' in result.text:
        ret = json.loads(result.text).get('ret', [])
        if any('TOKEN_EXOIRED' in r or 'SESSION_EXPIRED' in r for r in ret):
            return True
    
    # BA 接口：检查 code 字段
    if 'code' in result.text:
        code = json.loads(result.text).get('code')
        if code == 401 or code == 403:
            return True
    
    return False
```

---

#### 3.10 上报消息格式

与现有 TikTok/Shopee 保持一致：

```json
{
    "params": "",
    "method": "GET",
    "body": "",
    "cookies": "{...}",
    "fromUrl": "https://sellercenter.lazada.co.th/...",
    "extra": {"seller_id": "101007760547", "venture": "TH"},
    "sign": "4fk0050d4c9c2c7ba8efc59684acf",
    "socketUserId": "<account_id>",
    "userType": 6.0,
    "updateTime": 1776066687292,
    "request": {
        "response": "<API 原始 JSON 响应>",
        "url": "<请求的完整 URL>"
    }
}
```

### 产出文件

| 文件 | 操作 |
|------|------|
| `live_dp/crawlers/http/lazada.py` | 新增 |

---

## Phase 4: 平台注册与调度集成

### Why

将 LazadaHttpCrawler 接入现有的调度系统，使 `main.py` 和 `TaskScheduler` 能够统一调度浏览器采集和 HTTP 采集。同时在监控系统中注册 Lazada 的 API 类型。

### What Changes

#### 4.1 config/base.py 新增 lazada 配置

```python
PLATFORM_CONFIG["lazada"] = {
    # 账号获取方式（复用 AdsPower 分组）
    "use_dynamic_users": True,
    "use_dynamic_groups": True,
    "group_names": [],
    "user_ids": [],

    # HTTP 采集专用配置
    "crawler_type": "http",       # 标识为 HTTP 采集（区分浏览器采集）
    "http_workers": 5,            # Downloader 并发线程数
    "proxy": None,                # 采集代理（None 则从 AdsPower 获取）

    # 页面/监听 URL（HTTP 模式不使用，保留空值兼容）
    "page_urls": [],
    "listen_urls": [],

    # 调度配置：两种采集模式
    "realtime_interval_minutes": 10,   # 实时接口采集间隔（分钟）
    "history_cron": [                  # 历史数据采集时间（每天 2 次）
        {"hour": "4", "minute": "0"},
        {"hour": "20", "minute": "0"},
    ],
}
```

**调度说明**：
- `main.py` 根据配置创建两个独立的调度任务：
  - 实时任务：每 10 分钟调用 `LazadaHttpCrawler(crawl_type='realtime')`
  - 历史任务：每天 2 次调用 `LazadaHttpCrawler(crawl_type='history')`
- `LazadaHttpCrawler.build_tasks()` 根据 `self.crawl_type` 决定构造哪些 Task：
  - `'realtime'`：只构造 2.1 实时趋势、2.2 实时大屏
  - `'history'`：构造 1.x 卖家中心、3.x 直播后台
  - `None` 或 `'full'`：构造所有接口（手动全量采集）
```

#### 4.2 Cookie API 鉴权配置

```python
COOKIE_API_CONFIG = {
    "secret_key": "your_secret_key_here",  # sign 计算密钥
}
```

#### 4.3 monitor/registry.py 新增 lazada API 类型

```python
API_TYPE_REGISTRY["lazada"] = {
    "account": [
        {"key": "realtime_trend",      "label": "实时趋势"},
        {"key": "realtime_dashboard",  "label": "实时大屏"},
    ],
    "daily": [
        {"key": "seller_metrics",      "label": "直播概览"},
        {"key": "product_rooms",       "label": "场次详情"},
        {"key": "seller_products",     "label": "商品详情"},
        {"key": "key_overview",        "label": "关键指标概览"},
        {"key": "key_trend",           "label": "关键指标趋势"},
        {"key": "traffic_overall",     "label": "流量概览"},
        {"key": "traffic_source",      "label": "流量来源"},
        {"key": "traffic_search",      "label": "搜索关键词"},
        {"key": "product_overview",    "label": "商品概览"},
        {"key": "product_diagnosis",   "label": "商品诊断"},
        {"key": "product_revenue",     "label": "商品排名-营收"},
        {"key": "product_ipvuv",       "label": "商品排名-访客"},
        {"key": "promotion_overview",  "label": "营销概览"},
        {"key": "promotion_trend",     "label": "营销趋势"},
        {"key": "promotion_ratio",     "label": "营销分类"},
    ],
    "room": [
        {"key": "live_list",           "label": "直播场次列表"},
        {"key": "room_metrics",        "label": "直播间详情"},
    ],
}
```

#### 4.4 live_crawler.py 工厂类修改

新增 `HTTP_CRAWLERS` 字典和路由逻辑。

#### 4.5 main.py 调度兼容

**关键点**：HTTP 爬虫的 `start_crawl()` 返回格式与浏览器爬虫一致，`main.py` 中的 `run_once()` 和 `crawl_single_account()` 无需修改核心逻辑。

需要适配的地方：
- HTTP 爬虫不需要 `BrowserApi.close_driver()`
- HTTP 爬虫的参数名为 `account_id`（非 `browser_id`），工厂类做映射

### 产出文件

| 文件 | 操作 |
|------|------|
| `live_dp/config/base.py` | 修改（新增 lazada 配置 + COOKIE_API_CONFIG） |
| `live_dp/monitor/registry.py` | 修改（新增 lazada API 类型） |
| `live_dp/crawlers/factory.py` | 修改（新增 HTTP_CRAWLERS 路由） |
| `live_dp/main.py` | 修改（适配 HTTP 爬虫调度） |

---

## Phase 5: 养号服务（cookie_keeper）

### Why

Lazada Cookie 有效期较短，需要定期通过 AdsPower 浏览器自动登录来刷新 Cookie。养号服务作为独立进程运行，是 HTTP 采集体系中唯一负责登录态管理的模块。

**职责边界**：采集器（BaseHttpCrawler）只管拿 Cookie 采集数据，不判断登录状态、不发送登录回调。以下职责全部由养号服务承担：

| 职责 | 说明                                                                                                |
|------|---------------------------------------------------------------------------------------------------|
| Cookie 刷新 | 定时为每个账号的两个端口（sellercenter / live）刷新 Cookie                                                        |
| Cookie 有效性判定 | 通过 HTTP 请求验证 Cookie 是否有效，失效时标记 `is_valid=0`                                                       |
| 登录态事件记录 | 调用 `services/login_callback.py` 共享模块，发送 `send_login_callback` 记录登录/登出事件                           |
| 登出恢复触发 | 刷新失败（登出）→ 记录 logout 事件；刷新成功（恢复）→ 记录 login 事件。采集器下次启动时通过 `resolve_collection_mode()` 读取事件序列，自动切换全量采集 |

**与采集器的协作流程**：
```
养号服务（cookie_keeper）                    采集器（BaseHttpCrawler）
─────────────────────────                   ─────────────────────────
1. 定时刷新 Cookie                           
2. 刷新成功 → set_cookies() + send_login_callback('login')
   刷新失败 → invalidate() + send_login_callback('logout')
                                            3. start_crawl()
                                            4. cookie_manager.get_cookies() → 拿 Cookie
                                            5. resolve_collection_mode() → 读登录态事件判断全量/增量
                                            6. build_tasks() → 采集 → 上报
```

### What Changes

#### 5.1 keeper.py 养号调度器

```python
class CookieKeeperScheduler:
    """养号服务调度器
    
    职责约束：
    - 是 HTTP 采集体系中唯一负责登录态管理的模块
    - 必须在 Cookie 刷新后调用 send_login_callback 记录登录态事件
    - 采集器不发送 send_login_callback，完全依赖本服务记录的事件
    """

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.cookie_mgr = CookieManager()       # 直接使用 CookieManager
        self.refresher = BrowserRefresher()      # AdsPower 浏览器操作

    def start(self):
        """启动定时任务（每天 2 次：02:00 和 14:00）"""
        self.scheduler.add_job(
            self.refresh_all_accounts,
            CronTrigger(hour='2,14', minute='0'),
            id='cookie_refresh',
        )
        self.scheduler.start()

    def refresh_all_accounts(self):
        """刷新所有 Lazada 账号的 Cookie（两个端口）"""
        accounts = self.cookie_mgr.list_accounts('lazada')
        for account in accounts:
            account_id = account['account_id']
            credentials = self.cookie_mgr.get_credentials(account_id, 'lazada')
            if not credentials:
                logger.warning(f'账号 {account_id} 无账密信息，跳过自动登录')
                continue

            # 刷新 sellercenter 端口
            self._refresh_endpoint(account_id, 'sellercenter', credentials)
            # 刷新 live 端口
            self._refresh_endpoint(account_id, 'live', credentials)

    def _refresh_endpoint(self, account_id, endpoint, credentials):
        """刷新单个端口的 Cookie，并记录登录态事件"""
        try:
            cookies = self.refresher.refresh(account_id, endpoint, credentials)
            if cookies:
                self.cookie_mgr.set_cookies(account_id, 'lazada', cookies, endpoint=endpoint)
                # 刷新成功 → 记录 login 事件（供采集器 resolve_collection_mode 读取）
                send_login_callback(account_id, 'lazada', 'login', reason='cookie_refreshed')
                logger.info(f'刷新成功: {account_id}/{endpoint}')
            else:
                self.cookie_mgr.invalidate(account_id, 'lazada', endpoint=endpoint)
                # 刷新失败 → 记录 logout 事件
                send_login_callback(account_id, 'lazada', 'logout', reason='cookie_refresh_failed')
                logger.warning(f'刷新失败: {account_id}/{endpoint}')
        except Exception as e:
            logger.error(f'刷新异常: {account_id}/{endpoint}: {e}')
```

#### 5.2 browser_refresher.py 浏览器自动登录

```python
class BrowserRefresher:
    """通过 AdsPower 浏览器自动登录并提取 Cookie
    
    整体架构：
    - refresh() 为入口方法，根据 endpoint 分发到对应的登录流程
    - 每个端口的具体登录逻辑（页面导航、元素定位、账密填写）由调用方补充
    - 本类只提供浏览器生命周期管理和 Cookie 提取的骨架
    """

    def refresh(self, account_id: str, endpoint: str,
                credentials: dict) -> dict | None:
        """自动登录并提取 Cookie
        
        Args:
            account_id: AdsPower profile_id
            endpoint: 'sellercenter' 或 'live'
            credentials: {"username": "xxx", "password": "xxx"}
            
        Returns:
            Cookie dict 或 None（登录失败）
            
        流程：
            1. BrowserApi.get_driver(account_id)
            2. 根据 endpoint 导航到对应登录页
            3. 自动填写账密并提交
            4. 等待登录完成（检测特定元素或 Cookie）
            5. 提取 driver.cookies()
            6. BrowserApi.close_driver()
        """
        driver = None
        try:
            driver = BrowserApi().get_driver(account_id)
            tab = driver.latest_tab

            if endpoint == 'sellercenter':
                cookies = self._login_sellercenter(tab, credentials)
            elif endpoint == 'live':
                cookies = self._login_live(tab, credentials)
            else:
                return None

            return cookies
        except Exception as e:
            logger.error(f'自动登录失败 {account_id}/{endpoint}: {e}')
            return None
        finally:
            if driver:
                BrowserApi().close_driver(driver)

    def _login_sellercenter(self, tab, credentials: dict) -> dict | None:
        """sellercenter 端口自动登录
        
        TODO: 具体实现（页面导航、元素定位、账密填写、登录验证）
        
        预期流程：
            1. tab.get('https://sellercenter.lazada.{country}/')
            2. 检测是否需要登录（是否跳转到登录页）
            3. 如果需要登录：
               a. 定位账号输入框，填写 credentials['username']
               b. 定位密码输入框，填写 credentials['password']
               c. 点击登录按钮
               d. 等待登录完成
            4. 提取并返回 Cookie
        """
        raise NotImplementedError('待实现：sellercenter 自动登录逻辑')

    def _login_live(self, tab, credentials: dict) -> dict | None:
        """live 端口自动登录
        
        TODO: 具体实现（页面导航、元素定位、账密填写、登录验证）
        
        预期流程：
            1. tab.get('https://live.lazada.{country}/app/live-list')
            2. 检测是否需要登录
            3. 如果需要登录：
               a. 填写相同的 credentials
               b. 提交登录
               c. 等待登录完成
            4. 提取并返回 Cookie
        """
        raise NotImplementedError('待实现：live 自动登录逻辑')
```

#### 5.3 启动命令

```bash
# 启动养号服务（独立进程）
cd live_dp && python -m cookie_keeper
```

**注意**：养号服务直接使用 `CookieManager` 操作数据库，不再需要额外的 `CookieStorage` 封装层。

**职责约束**：
- 养号服务必须在 Cookie 刷新后调用 `services/login_callback.py` 的 `send_login_callback()` 记录登录态事件
- 采集器（BaseHttpCrawler）不发送 `send_login_callback`，完全依赖养号服务记录的事件
- 采集器通过 `resolve_collection_mode()` 读取事件序列，自动判断全量/增量

### 产出文件

| 文件 | 操作 |
|------|------|
| `live_dp/cookie_keeper/__init__.py` | 新增 |
| `live_dp/cookie_keeper/keeper.py` | 新增（必须调用 send_login_callback） |
| `live_dp/cookie_keeper/browser_refresher.py` | 新增（骨架，具体登录逻辑待补充） |

---

## Phase 6: adspower-server Lazada 登录监听

### Why

用户首次登录 Lazada 时，需要通过 adspower-server 投屏监控登录过程，完成以下任务：
1. **JS Hook 拦截账号密码**（从 DOM 输入框获取）
2. **提取 sellercenter 端口 Cookie**（用户手动登录后）
3. **自动登录 live 端口**（使用相同账密）
4. **提取 live 端口 Cookie**
5. **将两份 Cookie + 账密写入 monitor.db**

### What Changes

#### 6.1 login_monitor.py 新增 Lazada 分支

```python
class LoginMonitorService:
    # 现有 Shopee/TikTok 监听模式保持不变
    SHOPEE_PATTERN = [...]
    TIKTOK_COOKIE_KEY = "multi_sids"

    # 新增 Lazada 监听模式
    LAZADA_SELLERCENTER_PATTERN = ["login.json", "passport/login"]
    LAZADA_LIVE_PATTERN = ["mtop.member.tokenlogin"]

    def start(self, session: Session) -> None:
        media = session.media.lower()
        if media == "lazada":
            session.login_status = "pending"
            session.login_task = asyncio.create_task(self._run_lazada(session))
        ...

    async def _run_lazada(self, session: Session) -> None:
        """Lazada 双端口登录监听流程

        流程：
            1. 注入 JS Hook 监听账号密码输入
            2. 用户手动登录 sellercenter（首次需验证码）
            3. 提取 sellercenter Cookie + 账密 → 写入 monitor.db
            4. 程序自动用相同账密登录 live 端口
            5. 提取 live Cookie → 写入 monitor.db
            6. 回调通知后端登录成功
        """
```

#### 6.2 双端口登录流程

```
用户通过投屏页面打开 sellercenter.lazada.{country}
    ↓
JS Hook 注入：监听 input 事件，拦截账号密码
    ↓
用户手动输入账密并登录（首次需验证码）
    ↓
login_monitor 检测到 sellercenter 登录成功
    ↓
提取 sellercenter Cookie + 账密
    ↓
PUT /api/cookies/{account_id}
    body: {platform: "lazada", endpoint: "sellercenter",
           cookies: {...}, extra: {"username":"xxx","password":"xxx"}}
    ↓
程序自动导航到 live.lazada.{country}
    ↓
自动填写相同账密并登录（后续无需验证码）
    ↓
提取 live Cookie
    ↓
PUT /api/cookies/{account_id}
    body: {platform: "lazada", endpoint: "live",
           cookies: {...}, extra: {"username":"xxx","password":"xxx"}}
    ↓
回调通知后端登录成功
```

#### 6.3 核心方法骨架

```python
def _hook_lazada_credentials(self, session) -> dict | None:
    """JS Hook 拦截账号密码
    TODO: 具体实现（注入 JS 监听 input 事件，读取 window.__lazada_credentials）
    返回: {"username": "xxx", "password": "xxx"} 或 None
    """

def _listen_sellercenter_login(self, session) -> dict | None:
    """监听 sellercenter 登录接口响应
    TODO: 具体实现（DrissionPage listen + 超时 120 秒）
    """

def _auto_login_live(self, session, credentials, venture) -> dict | None:
    """自动登录 live 端口
    TODO: 具体实现（导航到 live 页面 → 填写账密 → 提交 → 提取 Cookie）
    """

async def _save_cookies(self, account_id, platform, endpoint,
                        cookies, seller_id, venture, credentials):
    """调用 Cookie API 写入 Cookie + 账密"""

def _extract_cookies(self, tab) -> dict:
    """从 DrissionPage tab 提取 Cookie"""
    cookies = tab.cookies()
    return {c['name']: c['value'] for c in cookies}
```

### 产出文件

| 文件 | 操作 |
|------|------|
| `adspower-server/app/services/login_monitor.py` | 修改（新增 `_run_lazada` 分支，骨架方法待补充） |
| `adspower-server/app/config.py` | 修改（新增 MONITOR_API_URL 配置） |

---

## 附录 A: 数据流全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     用户操作（首次登录）                              │
│  1. 通过 adspower-server 投屏登录 sellercenter                      │
│  2. JS Hook 拦截账号密码                                             │
│  3. 程序自动用相同账密登录 live                                       │
│  4. 两份 Cookie + 账密 → monitor.db                                 │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  monitor.db cookies 表（每个 Lazada 账号两条记录）                    │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ account_id | platform | endpoint      | cookies | extra       │ │
│  │ profile_01 | lazada   | sellercenter  | {...}   | {user,pass} │ │
│  │ profile_01 | lazada   | live          | {...}   | {user,pass} │ │
│  └────────────────────────────────────────────────────────────────┘ │
└───────┬──────────────────────────────────┬──────────────────────────┘
        │ 读取 Cookie                       │ 自动登录续 Cookie
        ▼                                  ▼
┌────────────────────┐         ┌──────────────────────────────┐
│ 模块 B: HTTP 采集   │         │ 模块 A: 养号服务              │
│ crawlers/http/       │         │ cookie_keeper/                │
│                     │         │                               │
│ LazadaHttpCrawler   │         │ 每天 2 次：                   │
│ ├─ sc_cookies       │         │ 1. 读取账密（extra 字段）      │
│ │  → sellercenter   │         │ 2. 开 AdsPower 浏览器         │
│ ├─ live_cookies     │         │ 3. 自动登录 sellercenter      │
│ │  → live/acs-m     │         │ 4. 提取 Cookie → 更新 DB      │
│ ├─ downloader.run() │         │ 5. 自动登录 live              │
│ └─ send_request()   │         │ 6. 提取 Cookie → 更新 DB      │
│        │             │         └──────────────────────────────┘
│        ▼             │
│  livelabstar.com     │
│  (数据上报)           │
└────────────────────┘
```

## 附录 B: 与现有系统的兼容性

| 现有组件 | 影响 | 说明 |
|----------|------|------|
| BaseLiveCrawler | 无改动 | HTTP 体系完全独立 |
| TikTokLiveCrawler | 无改动 | 继续浏览器采集 |
| ShopeeLiveCrawler | 无改动 | 继续浏览器采集 |
| main.py | 轻微改动 | 工厂类自动路由，核心逻辑不变 |
| TaskScheduler | 轻微改动 | 新增 lazada 实时采集调度 |
| monitor 系统 | 新增表+路由 | 不影响现有功能 |
| downloader/ | 无改动 | 作为 HTTP 客户端被调用 |
| adspower-server | 新增分支 | 不影响 Shopee/TikTok 登录 |
