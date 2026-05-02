"""默认配置常量：请求头、代理、并发与重试参数。"""

# Chrome 143 / Windows 默认请求头
# 注意：当 impersonate="chrome_143" 时 never_primp 会自动注入 TLS/JA3/H2 指纹，
# 这里的 headers 仅作为应用层补充（impersonate 不覆盖的部分）
DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8,"
              "application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Chromium";v="143", "Not(A:Brand";v="24", "Google Chrome";v="143"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# 代理配置（专有网络环境使用，开发环境传 None 即可）
DEFAULT_PROXY: None = None

# --- 并发参数 ---
DEFAULT_WORKERS: int = 1          # 线程池大小
DEFAULT_TIMEOUT: float = 30.0      # 请求超时（秒）

# --- 重试参数（应用层 L2） ---
DEFAULT_MAX_RETRIES: int = 3       # 应用层最大重试次数（不含 never_primp L1 内置重试）
RETRY_BACKOFF_BASE: float = 1.0    # 指数退避基数（秒）
RETRY_BACKOFF_MAX: float = 30.0    # 最大退避时间（秒）
RETRY_STATUS_CODES: set[int] = {429, 500, 502, 503, 504}  # 触发应用层重试的状态码

# --- never_primp L1 内置重试 ---
NP_MAX_RETRIES: int = 2            # never_primp 底层网络重试次数
