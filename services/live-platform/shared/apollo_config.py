from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

APOLLO_URL = "http://dev-apollo.tec-develop.com"
APOLLO_APP_ID = "live-spider"
APOLLO_CLUSTER = "dev"
APOLLO_NAMESPACE = "application"


def fetch_apollo_config(
    *,
    retries: int = 5,
    timeout_seconds: float = 1,
    retry_interval_seconds: float = 0.2,
    namespace: str = APOLLO_NAMESPACE,
) -> dict[str, Any]:
    """从固定 Apollo dev 读取配置。"""
    url = f"{APOLLO_URL}/configs/{APOLLO_APP_ID}/{APOLLO_CLUSTER}/{namespace}"

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            configurations = payload.get("configurations", {})
            if isinstance(configurations, dict):
                return configurations
            logger.warning(f"Apollo 配置格式异常 | cluster={APOLLO_CLUSTER} namespace={namespace}")
            return {}
        except Exception as exc:
            logger.warning(
                f"Apollo 配置获取失败 | cluster={APOLLO_CLUSTER} namespace={namespace} "
                f"attempt={attempt}/{retries} error={exc}"
            )
            if attempt < retries:
                time.sleep(retry_interval_seconds)
    return {}
