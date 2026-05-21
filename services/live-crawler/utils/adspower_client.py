"""AdsPower API 统一客户端，内置限流重试机制"""

import time
import requests
from utils.logger import logger


class AdsPowerRateLimitError(Exception):
    """AdsPower 限流异常"""
    pass


class AdsPowerApiError(Exception):
    """AdsPower 业务异常（非限流）"""
    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"AdsPower API error: code={code}, msg={msg}")


class AdsPowerClient:
    """AdsPower API 统一客户端

    内置限流识别与指数退避重试，所有 AdsPower API 调用应通过此客户端发起。
    限流特征：返回 code=-1 且 msg 含 "too many" 或 "rate"。
    """

    def __init__(self, base_url: str, timeout: int = 10,
                 max_retries: int = 5, initial_delay: float = 3.0,
                 backoff_factor: float = 1.5):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.session = requests.Session()

    def get(self, path: str, params: dict = None) -> dict:
        return self._request('GET', path, params=params)

    def post(self, path: str, json: dict = None) -> dict:
        return self._request('POST', path, json=json)

    def _is_rate_limited(self, data: dict) -> bool:
        """判断响应是否为限流"""
        if data.get('code') != -1:
            return False
        msg = data.get('msg', '').lower()
        return 'too many' in msg or 'rate' in msg

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        kwargs.setdefault('timeout', self.timeout)
        delay = self.initial_delay

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.request(method, url, **kwargs)
                resp.raise_for_status()
                data = resp.json()

                if data.get('code') == 0:
                    return data

                if self._is_rate_limited(data):
                    if attempt < self.max_retries:
                        logger.warning(
                            f"AdsPower 限流 [{path}]，{delay:.1f}s 后重试"
                            f"（第{attempt}/{self.max_retries}次）"
                        )
                        time.sleep(delay)
                        delay *= self.backoff_factor
                        continue
                    raise AdsPowerRateLimitError(
                        f"AdsPower 限流重试耗尽 [{path}]: {data.get('msg')}"
                    )

                raise AdsPowerApiError(data.get('code', -1), data.get('msg', ''))

            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < self.max_retries:
                    logger.warning(
                        f"AdsPower 连接异常 [{path}]: {e}，"
                        f"{delay:.1f}s 后重试（第{attempt}/{self.max_retries}次）"
                    )
                    time.sleep(delay)
                    delay *= self.backoff_factor
                    continue
                raise

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_adspower_client() -> AdsPowerClient:
    """获取使用默认配置的 AdsPowerClient 实例"""
    from core.config import Settings
    return AdsPowerClient(base_url=Settings.ADSPOWER_CONFIG["api_url"])
