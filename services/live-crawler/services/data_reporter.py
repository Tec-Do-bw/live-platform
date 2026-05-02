"""数据上报共享模块。

从 BaseLiveCrawler.send_api_request 抽取，供浏览器采集器和 HTTP 采集器共用。
包含重试、落盘、日志记录逻辑。
"""

import json
import time
from pathlib import Path

import requests

from core.config import Settings
from utils.logger import logger


def send_api_request(message: dict, *, platform: str = '',
                     socket_user_id: str = '',
                     timestamp: int = 0) -> bool:
    """通过 API 请求发送数据（与原 BaseLiveCrawler.send_api_request 行为一致）

    Args:
        message: 消息数据（含 fromUrl、request 等字段）
        platform: 平台标识，用于落盘文件名
        socket_user_id: 用户 ID，用于落盘文件名
        timestamp: 时间戳，用于落盘文件名

    Returns:
        bool: 是否发送成功
    """
    # 检查是否启用数据上报
    if not Settings.DATA_SERVER_CONFIG.get("enabled", True):
        logger.debug('数据上报已禁用，跳过发送')
        file_path = Settings.ROOT_DIR / 'resource'
        if not file_path.exists():
            file_path.mkdir(parents=True)

        # 强制 UTF-8 编码，避免 Windows 下 GBK 编码问题
        with open(file_path / f"{platform}_{socket_user_id}_{timestamp}.json",
                  "a", encoding="utf-8") as f:
            line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
            f.write(line + "\n")

        msg_copy = dict(message)
        msg_copy.pop('request', None)
        with open(file_path / f"{platform}_{socket_user_id}.json",
                  "a", encoding="utf-8") as f:
            line = json.dumps(msg_copy, ensure_ascii=False, separators=(",", ":"))
            f.write(line + "\n")

        return False

    try:
        # 获取服务器配置
        api_url = Settings.DATA_SERVER_CONFIG.get("api_url")
        endpoint = Settings.DATA_SERVER_CONFIG.get("send_endpoint", "/data/info/send")
        access_token = Settings.DATA_SERVER_CONFIG.get("access_token")
        timeout = Settings.DATA_SERVER_CONFIG.get("timeout", 30)
        retries = Settings.DATA_SERVER_CONFIG.get("retries", 3)
        retry_delay = Settings.DATA_SERVER_CONFIG.get("retry_delay", 1)

        if not api_url:
            logger.error('未配置API服务器地址，无法发送数据')
            return False

        full_url = f"{api_url}{endpoint}"
        headers = {
            "accessToken": access_token,
            "Content-Type": "application/json"
        }

        # 重试逻辑
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                response = requests.post(
                    full_url, headers=headers, json=message, timeout=timeout
                )
                if response.status_code == 200:
                    logger.info(f'数据已成功上报到API服务器: {message["fromUrl"][:80]}...')
                    logger.debug(f'数据上报格式数据为:{message["request"]["response"][:200]}')
                    return True
                else:
                    logger.warning(f'API响应状态码异常 {response.status_code}: {response.text[:200]}')
                    last_error = f'HTTP {response.status_code}'

            except requests.Timeout:
                last_error = '请求超时'
                logger.warning(f'[第{attempt}/{retries}次] API请求超时，将在{retry_delay}秒后重试')
            except requests.ConnectionError as e:
                last_error = f'连接失败: {str(e)}'
                logger.warning(f'[第{attempt}/{retries}次] API连接失败，将在{retry_delay}秒后重试')
            except Exception as e:
                last_error = str(e)
                logger.warning(f'[第{attempt}/{retries}次] API请求异常: {e}')

            if attempt < retries:
                time.sleep(retry_delay)

        logger.error(f'API数据发送失败（已重试{retries}次），最后错误: {last_error}')
        return False

    except Exception as e:
        logger.error(f'发送API请求异常: {e}')
        return False
