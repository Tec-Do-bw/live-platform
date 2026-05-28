"""curl_cffi Session 工厂与同步重试装饰器。"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

from curl_cffi.requests import RetryStrategy, Session
from curl_cffi.requests.errors import RequestsError

from utils.logger import logger


DEFAULT_TIMEOUT = 30
DEFAULT_RETRY_EXCEPTIONS = (RequestsError, TimeoutError, ConnectionError)
F = TypeVar("F", bound=Callable[..., Any])


def _normalize_proxy(proxy: str | dict[str, str] | None) -> dict[str, str] | None:
    """统一代理配置为 curl_cffi proxies dict。"""
    if not proxy:
        return None
    if isinstance(proxy, dict):
        return proxy
    return {"http": proxy, "https": proxy}


def get_session(
    fingerprint_spec: dict[str, Any] | None = None,
    *,
    proxy: str | dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    retry_count: int = 3,
) -> Session:
    """创建 curl_cffi 同步 Session。

    Context7 与本地规范确认：Session 支持 impersonate、timeout、proxies，
    retry 可传入 RetryStrategy。
    """
    spec = fingerprint_spec or {}
    strategy = RetryStrategy(count=retry_count, delay=0.3, jitter=0.1, backoff="exponential")
    session = Session(
        impersonate=spec.get("impersonate") or "chrome",
        default_headers=True,
        timeout=timeout,
        proxies=_normalize_proxy(proxy),
        retry=strategy,
    )
    return session


def sync_retry(
    retries: int = 2,
    delay: float = 0.5,
    backoff_factor: float = 2.0,
    retry_exceptions: tuple[type[BaseException], ...] = DEFAULT_RETRY_EXCEPTIONS,
) -> Callable[[F], F]:
    """同步业务重试装饰器，只重试显式列出的异常。"""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay
            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except retry_exceptions as e:
                    if attempt >= retries:
                        raise
                    logger.warning(
                        f"{func.__name__} 请求异常，{current_delay:.1f}s 后重试"
                        f"（第{attempt + 1}/{retries}次）: {e}"
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff_factor

        return wrapper  # type: ignore[return-value]

    return decorator
