---
name: simplify-proxy-strategy-static-first-ipbiubiu-retry
description: 默认静态池，重试切 ipbiubiu。删除 kkoip 和所有国家代理逻辑
created: 2026-05-27
status: confirmed
---

# 代理策略极简化：静态优先 + ipbiubiu 重试

## Context

### 第一性原理

**目标：请求能完成**。其他都是手段。

### 当前过度设计

代码里有一整套"短响应 → 国家代理切换 → MX/ID/BR 并发轮询 → 多轮重试"的复杂逻辑，绑死 kkoip 动态代理（密码段 `-XX@` 模式）。

测试数据（`tests/proxy_stability/`）显示这套逻辑：
- 420 账号测试期间触发次数 = 0
- 即便触发也未必命中正确国家
- 完全锁定 kkoip 一种代理形态

### 三方代理实测对比

| 代理 | TikTok 成功率 | P50 | P95 | 评价 |
|------|---------------|-----|-----|------|
| 静态池（300 个） | 100% | 1250ms | 1688ms | **最快最稳** |
| kkoip 动态 | 90% | 1812ms | 3748ms | 慢、国家不纯（混入 PK/SY）、HTTP 451 |
| ipbiubiu 动态 | 96.7% | 1516ms | 2009ms | **每次换 IP、100% US、延迟低** |

### 决策

- **默认走静态池**：300 个 IP 随机，最快最稳
- **重试切 ipbiubiu**：自动换 IP（一次一换），相当于天然的"换代理重试"
- **删除 kkoip**：性能差、国家不纯，没用
- **删除所有国家切换逻辑**：用不上，删掉减负

## 设计

### 路径（一图看懂）

```
首次请求 ───────► 静态池随机
   │
   ├─ 成功 → 完成
   │
   └─ 失败（HTTP 5xx/异常/短响应）
        ↓
        重试（最多 N 次）─► ipbiubiu（每次自动换 IP）
           │
           ├─ 成功 → 完成
           │
           └─ 全部失败 → 终结失败
```

### 改动清单

#### 1. `utils/downloader/config.py`

```python
# 之前
DEFAULT_PROXY: str = "http://7758105-0c83c22f:26394524-US@gate-hk.kkoip.com:19187"

# 之后
DEFAULT_PROXY: str = "http://w8a3gsvcnv3y_c_US:EYaCbD1o3qMrneUm@dp1.ipbiubiu.com:10769"
```

`DEFAULT_PROXY` 含义从"kkoip 动态代理"变为"重试用代理（ipbiubiu）"。

#### 2. `utils/downloader/core.py`

**改动 1：`__init__` 构造时缓存重试用代理 + 静态池**

```python
self._merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
self._impersonate = impersonate

# 主代理选择（首次请求用）
if proxy is DEFAULT_PROXY:
    # 调用方未显式传 proxy → 走静态池随机
    self._primary_proxy = "http://" + random.choice(self.ip_list)
    self._retry_proxy = DEFAULT_PROXY  # 重试时切到 ipbiubiu
else:
    # 调用方显式传入（含 None）→ 全程用它，重试也不换
    self._primary_proxy = proxy
    self._retry_proxy = proxy

self._client = self._build_client(self._primary_proxy)
```

**改动 2：抽出 `_build_client(proxy)` 辅助方法**

```python
def _build_client(self, proxy: str | None) -> never_primp.Client:
    """根据代理构造 never_primp Client"""
    return never_primp.Client(
        impersonate=self._impersonate,
        impersonate_os="windows",
        proxy=proxy,
        timeout=self._timeout,
        headers=self._merged_headers,
        max_retries=NP_MAX_RETRIES,
    )
```

**改动 3：`_execute_task` 重试时切到 `_retry_proxy`**

```python
for attempt in range(1, self._max_retries + 2):
    try:
        # 第一次用 primary，从第二次开始用 retry（ipbiubiu）
        if attempt == 2:
            self._client = self._build_client(self._retry_proxy)
            logger.debug("[%s] 切换到重试代理（ipbiubiu）", task.task_id)

        resp = method_fn(task.url, **kwargs)
        text_len = len(resp.text or "")

        # 短响应判定：HTTP 200 但内容过短 → 视为失败重试
        if (task.min_content_length is not None
                and resp.status_code == 200
                and text_len < task.min_content_length):
            last_status = resp.status_code
            last_error = f"短响应 {text_len} < {task.min_content_length}"
            if attempt <= self._max_retries:
                continue  # 短响应不退避，立即换代理重试
            return DownloadResult(success=False, error=last_error, ...)

        if resp.status_code in RETRY_STATUS_CODES:
            ...  # 原逻辑保持不变
```

> 注意：`attempt == 2` 而不是 `> 1` —— 第三次及以后已经在 ipbiubiu 上了（一次一换会自动换 IP），不需要重新构造 client。

#### 3. `utils/downloader/models.py`

新增 `Task.min_content_length` 字段：

```python
@dataclass
class Task:
    ...
    min_content_length: int | None = None  # 响应文本最少字节数，低于则视为失败重试
```

#### 4. `utils/TiktokTool.py`

**删除**：

```python
# 删除常量
_LIVE_RETRY_COUNTRIES = ("MX", "ID", "BR")
_LIVE_RETRY_ROUNDS = 2
_PROXY_COUNTRY_RE = re.compile(r"-[A-Z]{2}@")

# 删除方法
def _build_country_proxy(self, country): ...
def _fetch_live_with_country(self, live_url, country): ...
def _retry_live_with_country_proxy(self, live_url): ...

# 删除 import
from utils.downloader.config import DEFAULT_PROXY
```

**修改** `get_tiktok_stream_data_requests`：

```python
# 之前
tasks = [
    Task(url=profile_url, task_id="profile", headers=...),
    Task(url=live_url, task_id="live", headers=...),
]
results = self._downloader.run(tasks)
profile_result, live_result = results[0], results[1]
...
# 短响应风控兜底：依次换代理重试，命中即用新结果继续解析
if live_result.text and len(live_result.text) < _LIVE_HTML_MIN_LEN:
    good = self._retry_live_with_country_proxy(live_url)
    if good is not None:
        live_result = good

# 之后
tasks = [
    Task(url=profile_url, task_id="profile", headers=...),
    Task(url=live_url, task_id="live", headers=...,
         min_content_length=_LIVE_HTML_MIN_LEN),  # ← Downloader 自动处理
]
results = self._downloader.run(tasks)
profile_result, live_result = results[0], results[1]
# 短响应兜底完全删除
```

保留 `_LIVE_HTML_MIN_LEN = 2000` 作为 Task 字段值。

## 实施步骤

### Step 1：换 `DEFAULT_PROXY` 到 ipbiubiu

文件：`utils/downloader/config.py`

```python
DEFAULT_PROXY: str = "http://w8a3gsvcnv3y_c_US:EYaCbD1o3qMrneUm@dp1.ipbiubiu.com:10769"
```

### Step 2：扩展 Task 模型

文件：`utils/downloader/models.py`

新增 `min_content_length: int | None = None` 字段。

### Step 3：重构 Downloader

文件：`utils/downloader/core.py`

1. `__init__` 缓存 `_primary_proxy` / `_retry_proxy` / `_merged_headers` / `_impersonate`
2. 抽出 `_build_client(proxy)` 方法
3. `_execute_task` 在 `attempt == 2` 时切换 client 到 `_retry_proxy`
4. `_execute_task` 增加短响应判定（`task.min_content_length`）
5. 更新文件顶部 docstring，简化"三层重试机制"说明

### Step 4：清理 TiktokTool

文件：`utils/TiktokTool.py`

删除 3 个常量 + 3 个方法 + 1 个 import，简化 `get_tiktok_stream_data_requests` 主流程。

### Step 5：清理测试套件 patch

文件：`tests/proxy_stability/scenario_runner.py`

删除对 `_retry_live_with_country_proxy` 和 `_fetch_live_with_country` 的 monkey-patch（这两个方法已不存在）。

`scenario_config.py` 把"国家兜底"维度从场景定义里移除（场景 3/4 改为静态/动态对比）。

### Step 6：更新 CLAUDE.md

文件：`services/live-monitor/CLAUDE.md`

把"直播流采集架构"段落里 kkoip 和国家代理相关描述改成新策略：

```markdown
- TikTok 实时路由（`/route/tiktok`）走 HTTP Downloader 路径：
  utils/TiktokTool.py 通过 utils/downloader/ 完成抓取，
  默认使用静态代理池（300 IP 随机），重试时切换到 ipbiubiu 动态代理（每次换 IP）
```

### Step 7：验证

1. **API 契约测试**：`pytest tests/test_api_response.py -v` 全过（17 用例）
2. **端到端**：跑 3 个真实账号（TH/MY/US 各一个），确认 flv_url、uniqueId、region 正常
3. **重试路径**：构造一个会短响应的请求，观察日志确认切到了 ipbiubiu

## 关键文件清单

| 文件 | 改动 | 行数变化 |
|------|------|---------|
| `utils/downloader/config.py` | 改 1 行（DEFAULT_PROXY） | ±1 |
| `utils/downloader/models.py` | 加 1 字段 | +2 |
| `utils/downloader/core.py` | 重构 _execute_task | +30 / -10 |
| `utils/TiktokTool.py` | 删 3 方法 + 3 常量 + 1 import | **-70** |
| `tests/proxy_stability/scenario_runner.py` | 删 patch | -30 |
| `services/live-monitor/CLAUDE.md` | 改 2 段 | ±5 |

净代码量：**-75 行左右**（核心是 TiktokTool 减负 70 行）。

## 验证清单

- [ ] `DEFAULT_PROXY` 已换为 ipbiubiu
- [ ] kkoip 字符串在仓库中已无残留：`grep -r "kkoip" services/live-monitor/`
- [ ] `_PROXY_COUNTRY_RE` / `_build_country_proxy` / `_fetch_live_with_country` / `_retry_live_with_country_proxy` 全部删除
- [ ] Downloader `_execute_task` 第二次重试时使用 `_retry_proxy`
- [ ] live Task 带 `min_content_length=2000`
- [ ] `pytest tests/test_api_response.py -v` 17 用例全过
- [ ] 端到端 3 账号验证（TH/MY/US 各一）拿到完整 flv_url + region
- [ ] CLAUDE.md "直播流采集架构"段落已更新
- [ ] commit message 反映"简化"语义（如"refactor(tiktok): 简化代理策略，默认静态池 + 重试切 ipbiubiu，删除 kkoip 和国家代理逻辑"）

## 回退

所有改动集中在 6 个文件，单次 commit。回退命令 `git revert HEAD`。

测试数据 `tests/proxy_stability/results/*.json` 保留作历史快照。

## 不做的事（明确边界）

- ❌ 不引入 ipbiubiu 失败再切第三种代理（YAGNI，请求已尽力）
- ❌ 不按 country_code 智能匹配代理（ipbiubiu 是单一 US，无意义）
- ❌ 不引入代理质量监控/黑名单（300 静态池实测全健康）
- ❌ 不动 Lazada/Shopee（它们用各自的代理逻辑，本次不波及）
