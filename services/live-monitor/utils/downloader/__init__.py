"""downloader —— 基于 never_primp 的稳定批量采集下载器。

用法：
    from downloader import Downloader, Task

    dl = Downloader(workers=10)
    results = dl.run(["https://example.com/1", "https://example.com/2"])
    print(dl.summary)
"""

from .config import (
    DEFAULT_HEADERS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PROXY,
    DEFAULT_TIMEOUT,
    DEFAULT_WORKERS,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_MAX,
    RETRY_STATUS_CODES,
)
from .core import Downloader
from .models import DownloadResult, Task

__all__ = [
    "Downloader",
    "Task",
    "DownloadResult",
    "DEFAULT_HEADERS",
    "DEFAULT_PROXY",
    "DEFAULT_WORKERS",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
    "RETRY_BACKOFF_BASE",
    "RETRY_BACKOFF_MAX",
    "RETRY_STATUS_CODES",
]
