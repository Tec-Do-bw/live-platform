# Downloader — 基于 never_primp 的稳定批量采集下载器

基于 [never_primp](https://github.com/neverl805/never_primp)（Rust/wreq）构建的批量 HTTP 采集工具，专为 500~1000+ 请求的稳定采集场景设计。

## 特性

- **浏览器指纹伪装** — 默认模拟 Chrome 143，完整 TLS/JA3/H2 指纹
- **线程池并发** — `ThreadPoolExecutor` + never_primp 无锁共享 Client
- **三层重试机制** — 网络层自动重试 → 应用层指数退避 → 失败队列追踪
- **业务回调** — `on_success` / `on_failure` 实时通知
- **失败可重跑** — `failed_tasks()` 提取失败任务，直接传入下一次 `run()`

## 安装

```bash
pip install never_primp
```

## 快速开始

```python
from downloader import Downloader

dl = Downloader(workers=10)
results = dl.run([
    "https://httpbin.org/get?id=1",
    "https://httpbin.org/get?id=2",
    "https://httpbin.org/get?id=3",
])

for r in results:
    print(f"[{'成功' if r.success else '失败'}] {r.task.task_id}: HTTP {r.status_code}")

print(dl.summary)
```

## API 参考

### Downloader

```python
Downloader(
    proxy=DEFAULT_PROXY,     # 代理地址，传 None 禁用代理
    workers=10,              # 线程池并发数
    timeout=30.0,            # 请求超时（秒）
    max_retries=3,           # 应用层重试次数
    headers=None,            # 自定义请求头（与默认 Chrome 143 headers 合并）
    on_success=None,         # 成功回调: (DownloadResult) -> Any
    on_failure=None,         # 失败回调: (DownloadResult) -> Any
    impersonate="chrome_143" # 浏览器指纹
)
```

#### `run(tasks) -> list[DownloadResult]`

批量执行采集。`tasks` 可以是 URL 字符串列表或 `Task` 对象列表，返回全部结果（成功 + 失败），顺序与输入一致。

#### `summary -> dict`

采集摘要统计，包含 `total` / `success` / `failed` / `elapsed` / `failures` 字段。

#### `failed_tasks() -> list[Task]`

提取失败的 Task 列表，可直接传给另一次 `run()` 重跑。

### Task

```python
Task(
    url="https://example.com",   # 目标 URL（必填）
    task_id="order_001",         # 业务 ID，不设则自动分配序号
    method="GET",                # HTTP 方法
    headers=None,                # 请求级别额外 headers
    params=None,                 # URL 查询参数
    json_data=None,              # JSON 请求体
    data=None,                   # 表单/原始请求体
    timeout=None,                # 请求级别超时（覆盖 Downloader 默认值）
    meta=None,                   # 业务附加数据，透传到结果中
)
```

### DownloadResult

| 字段 | 类型 | 说明 |
|------|------|------|
| `task` | `Task` | 原始任务（含 `meta` 透传数据） |
| `success` | `bool` | 是否成功 |
| `status_code` | `int \| None` | HTTP 状态码 |
| `text` | `str \| None` | 响应文本 |
| `content` | `bytes \| None` | 响应原始字节 |
| `url` | `str \| None` | 最终 URL（重定向后） |
| `headers` | `dict \| None` | 响应头 |
| `error` | `str \| None` | 失败原因 |
| `attempts` | `int` | 总尝试次数 |
| `elapsed_ms` | `float` | 总耗时（毫秒） |

## 使用示例

### 自定义 Task + 回调

```python
from downloader import Downloader, Task

def on_fail(result):
    print(f"[失败] {result.task.task_id}: {result.error}")

dl = Downloader(workers=20, on_failure=on_fail)

tasks = [
    Task(url="https://api.example.com/data", task_id="001", params={"id": "1"}),
    Task(url="https://api.example.com/data", task_id="002", method="POST", json_data={"q": "test"}),
]
results = dl.run(tasks)
print(dl.summary)
```

### 失败重跑

```python
dl = Downloader(workers=10)
results = dl.run(url_list)

# 第一轮失败的任务，换更大超时重跑
if dl.failed_tasks():
    dl2 = Downloader(workers=5, timeout=60, max_retries=5)
    retry_results = dl2.run(dl.failed_tasks())
```

### 不使用代理（本地开发）

```python
dl = Downloader(proxy=None, workers=5)
```

## 三层重试机制

| 层级 | 责任方 | 触发条件 | 策略 |
|------|--------|----------|------|
| **L1** | never_primp 内置 | 网络连接失败、DNS 解析失败 | 自动重试 2 次 |
| **L2** | 应用层指数退避 | HTTP 429 / 500 / 502 / 503 / 504 | 退避 1s → 2s → 4s（上限 30s），最多 3 次 |
| **L3** | 最终失败队列 | L1 + L2 全部耗尽 | 记录到 `failed_tasks()`，触发 `on_failure` 回调 |

## 配置修改

编辑 `downloader/config.py` 可调整默认值：

```python
DEFAULT_PROXY          # 代理地址
DEFAULT_WORKERS = 10   # 并发数
DEFAULT_TIMEOUT = 30.0 # 超时
DEFAULT_MAX_RETRIES = 3    # 应用层重试次数
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}  # 触发重试的状态码
```
