"""AdsPower 代理 IP 获取工具。"""

import time

from utils.adspower_client import (
    AdsPowerApiError,
    AdsPowerClient,
    AdsPowerRateLimitError,
    get_adspower_client,
)
from utils.logger import logger


def sync_retry(retries=3, delay=0.1, backoff_factor=1.5, no_retry_exceptions=()):
    """同步重试装饰器。"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            current_delay = delay

            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if no_retry_exceptions and isinstance(e, no_retry_exceptions):
                        raise
                    if attempt < retries:
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        return None

        return wrapper

    return decorator


def build_proxy_url(proxy_config: dict) -> str | None:
    """将 AdsPower user_proxy_config 转为 requests 代理 URL。"""
    if proxy_config.get('proxy_soft') == 'no_proxy':
        return None

    proxy_type = proxy_config.get('proxy_type', 'http')
    host = proxy_config.get('proxy_host', '')
    port = proxy_config.get('proxy_port', '')

    if not host or not port:
        return None

    user = proxy_config.get('proxy_user', '')
    password = proxy_config.get('proxy_password', '')

    if user and password:
        return f'{proxy_type}://{user}:{password}@{host}:{port}'
    return f'{proxy_type}://{host}:{port}'


def get_proxy_for_account(account_id: str, api_url: str | None = None) -> dict | None:
    """通过 AdsPower V2 API 获取账号对应的代理配置。

    Returns:
        {'http': 'socks5://...', 'https': 'socks5://...'} 或 None
    """
    try:
        if api_url is None:
            client = get_adspower_client()
        else:
            client = AdsPowerClient(base_url=api_url)

        data = client.post('/api/v2/browser-profile/list', json={'profile_id': [account_id]})

        profiles = data.get('data', {}).get('list', [])
        if not profiles:
            logger.warning(f'未找到账号 {account_id} 的 AdsPower 环境')
            return None

        proxy_config = profiles[0].get('user_proxy_config', {})
        proxy_url = build_proxy_url(proxy_config)

        if proxy_url is None:
            logger.info(f'账号 {account_id} 未配置代理（no_proxy）')
            return None

        return {'http': proxy_url, 'https': proxy_url}

    except (AdsPowerRateLimitError, AdsPowerApiError) as e:
        logger.warning(f'AdsPower 查询代理失败: {e}')
        return None
    except Exception as e:
        logger.warning(f'AdsPower 查询代理异常: {e}')
        return None


if __name__ == '__main__':
    for _ in range(3):
        print(get_proxy_for_account('k1c04gom'))
