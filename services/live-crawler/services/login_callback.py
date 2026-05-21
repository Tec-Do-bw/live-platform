"""登录回调共享模块。

从 BaseLiveCrawler.send_login_callback 抽取，供浏览器采集器和未来养号服务共用。
包含回调请求发送和登出恢复检测逻辑。
"""

import requests

from core.config import Settings
from utils.logger import logger


def send_login_callback(
    *,
    browser_id: str,
    platform: str,
    group_name: str = '',
    login_status: str,
    reason: str = '',
) -> dict:
    """发送登录状态回调并写入登录事件。

    Args:
        browser_id: 浏览器/账号 ID
        platform: 平台标识
        group_name: 分组名称
        login_status: 登录状态，"success" 或 "logout"
        reason: 失败/登出原因

    Returns:
        dict: 包含 callback_sent(bool) 和 login_recovery(bool) 两个标记
    """
    result = {'callback_sent': False, 'login_recovery': False}

    # --- 1. 发送 HTTP 回调 ---
    callback_config = Settings.LOGIN_CALLBACK_CONFIG
    if not callback_config.get("enabled", True):
        logger.debug('登录回调已禁用，跳过发送')
    else:
        try:
            callback_url = callback_config.get("url")
            access_token = callback_config.get("access_token", "")
            timeout = callback_config.get("timeout", 10)

            if not callback_url:
                logger.warning('未配置登录回调URL，无法发送回调')
            else:
                payload = {
                    "login_status": login_status,
                    "media": platform,
                    "collection_id": browser_id,
                    "reason": reason,
                }
                headers = {"Content-Type": "application/json"}
                if access_token:
                    headers["accessToken"] = access_token

                logger.info(
                    f'发送登录回调: status={login_status}, '
                    f'platform={platform}, browser_id={browser_id}, url={callback_url}'
                )
                response = requests.post(
                    callback_url, headers=headers, json=payload, timeout=timeout
                )
                if response.status_code == 200:
                    logger.info(f'登录回调发送成功: {login_status}')
                    result['callback_sent'] = True
                else:
                    logger.warning(
                        f'登录回调响应异常 {response.status_code}: '
                        f'{response.text[:200]}'
                    )
        except requests.Timeout:
            logger.warning('登录回调请求超时')
        except requests.ConnectionError as e:
            logger.warning(f'登录回调连接失败: {e}')
        except Exception as e:
            logger.error(f'发送登录回调异常: {e}')

    # --- 2. 写入登录事件 + 登出恢复检测 ---
    try:
        from monitor import get_monitor
        from monitor.login_status_manager import LoginStatusManager

        status_mgr = LoginStatusManager(get_monitor().conn)

        # 检测登出→登录恢复
        if login_status == "success":
            current_status = status_mgr.get_account_status(browser_id)
            if current_status and current_status['status'] == 'logout':
                result['login_recovery'] = True
                logger.info(
                    f'[登出即时恢复] 账号 {browser_id} 从 logout 恢复登录，'
                    f'当轮切换为全量采集模式'
                )

        status_mgr.record_login_status(
            account_id=browser_id,
            platform=platform,
            group_name=group_name,
            login_status=login_status,
            reason=reason,
        )
    except Exception as e:
        logger.error(f'写入登录状态事件失败: {e}')

    return result
