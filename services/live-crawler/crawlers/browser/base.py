#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time       : 2025/11/12
# @Author     : XBW
# @File       : base.py
# @Description: 直播数据采集爬虫基类

import json
import time
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from core.config import Settings
from webdriver.browserapi import BrowserApi
from utils.logger import logger
from urllib.parse import urlparse


class BaseLiveCrawler(ABC):
    """直播数据采集爬虫基类
    
    提供通用的采集流程和方法，子类需要实现平台特定的逻辑
    """
    
    def __init__(self, browser_id: str = None, full_collection: bool = False, group_name: str = '', batch_id: str = ''):
        """初始化爬虫基类

        Args:
            browser_id: 指纹浏览器ID（同时作为socketUserId）
            full_collection: 是否全量采集模式
            group_name: AdsPower分组名称（用于多国域名识别）
        """
        self.browser_id = browser_id
        self.full_collection = full_collection
        self.group_name = group_name
        self.socket_user_id = browser_id
        self._login_recovery = False  # 标记本轮是否触发了登出即时恢复

        # 平台标识（子类必须设置）
        self.platform = self.get_platform_name()
        
        # 加载平台配置
        if self.platform not in Settings.PLATFORM_CONFIG:
            raise ValueError(f"不支持的平台: {self.platform}")
        
        self.config = Settings.PLATFORM_CONFIG[self.platform]
        logger.info(f'初始化 {self.platform} 平台爬虫，browser_id: {browser_id}')
        
        # 初始化浏览器API
        self.browser_api = BrowserApi()
        self.driver = None
        
        # 数据存储
        self.collected_data = []
        self.login_status = True  # 登录状态标记
        self._login_recovery = False  # 标记本轮是否触发了登出即时恢复
        self.timestamp = int(time.time() * 1000)
        self.batch_id = batch_id  # 采集监控批次ID
    
    @abstractmethod
    def get_platform_name(self) -> str:
        """获取平台标识名称（子类必须实现）
        
        Returns:
            str: 平台标识（如 'tiktok', 'shopee'）
        """
        pass
    
    @abstractmethod
    def handle_special_logic(self, url: str, response: Any, **kwargs) -> None:
        """处理平台特殊逻辑（子类必须实现）
        
        Args:
            url: API URL
            response: 响应数据
        """
        pass
    
    @abstractmethod
    def visit_page_and_collect(self, url: str) -> Dict[str, Any]:
        """访问单个页面并收集数据（子类必须实现）
        
        Args:
            url: 页面URL
            
        Returns:
            Dict: 页面采集结果，包含 {'url': str, 'apis_count': int, 'data_sent': int}
        """
        pass
        
    def start_crawl(self) -> Dict[str, Any]:
        """开始采集流程
        
        Returns:
            Dict: 采集结果统计
        """
        # 采集监控：记录账号开始
        from monitor import get_monitor
        monitor = get_monitor()
        if self.batch_id:
            monitor.start_account(self.batch_id, self.browser_id, self.group_name, self.platform)

        result = {
            'platform': self.platform,
            'browser_id': self.browser_id,
            'success': False,
            'pages_visited': 0,
            'apis_collected': 0,
            'data_sent': 0,
            'login_status': True,
            'error': None,
            'start_time': datetime.now().isoformat(),
            'login_recovery': False,
        }
        
        try:
            # 1. 获取浏览器驱动
            logger.info(f'========== 开始 {self.platform} 平台采集 ==========')
            self.driver = self.browser_api.get_driver(self.browser_id)

            self.tab = self.driver.latest_tab

            # 2. 启动API监听
            self.browser_api.listen_api(self.tab, self.config['listen_urls'])
            
            # 3. 循环访问页面并采集
            for i, page_url in enumerate(self.config['page_urls'], 1):
                logger.info(f'[{i}/{len(self.config["page_urls"])}] 开始访问页面: {page_url}')
                
                try:
                    page_result = self.visit_page_and_collect(page_url)
                    result['pages_visited'] += 1
                    result['apis_collected'] += page_result['apis_count']
                    result['data_sent'] += page_result['data_sent']
                    
                    # 检查登录状态
                    if not self.login_status:
                        logger.error('检测到账号登出 | 采集无权限，停止采集')
                        result['login_status'] = False
                        break
                        
                except Exception as e:
                    logger.error(f'访问页面失败: {page_url}, 错误: {e}')
                    continue
            
            result['success'] = self.login_status

            logger.info(f'========== {self.platform} 平台采集完成 ==========')
            logger.info(f'访问页面数: {result["pages_visited"]}, '
                       f'拦截API数: {result["apis_collected"]}, '
                       f'发送数据数: {result["data_sent"]}')
            
        except Exception as e:
            logger.exception(f'采集过程异常: {e}')
            result['error'] = str(e)
            
        finally:
            # 清理资源
            if self.driver:
                try:
                    self.browser_api.close_driver(self.driver)
                except Exception as e:
                    logger.error(f'关闭浏览器失败: {e}')
            
            result['end_time'] = datetime.now().isoformat()
            result['login_recovery'] = self._login_recovery

            # 采集监控：记录账号结束
            if self.batch_id:
                acct_status = 'success' if result.get('success') else ('login_failed' if not result.get('login_status', True) else 'failed')
                monitor.finish_account(self.batch_id, self.browser_id, acct_status)

        return result
    
    def format_api_message(self, url: str, request_body: Any, 
                          response_body: Any, cookies: List[Dict]) -> Dict[str, Any]:
        """格式化API上报消息（参考插件中的sendRequest格式）
        
        Args:
            url: API URL
            request_body: 请求体
            response_body: 响应体
            cookies: cookies列表
            
        Returns:
            Dict: 格式化后的消息
        """
        # 处理请求体
        if request_body == "No request body" or not request_body:
            extra = None
        else:
            extra = request_body if isinstance(request_body, str) else json.dumps(request_body)
        
        # 格式化响应体
        if isinstance(response_body, dict):
            response_str = json.dumps(response_body, ensure_ascii=False)
        else:
            response_str = str(response_body)
        
        # 构造消息体（与插件格式保持一致）
        message = {
            "params": '',
            "cookies": json.dumps(cookies, ensure_ascii=False),
            "fromUrl": url,
            "extra": extra,
            "sign": Settings.DATA_SERVER_CONFIG['api_sign'],
            "userType": 6.0,
            "updateTime": int(time.time() * 1000),
            "request": {
                "response": response_str,
                "url": url
            },
            # 添加socketUserId字段（参考插件的sendRequest）
            "socketUserId": self.socket_user_id,
        }
        
        return message
    
    def send_api_request(self, message: Dict[str, Any]) -> bool:
        """通过API请求发送数据（委托给共享模块 services.data_reporter）

        Args:
            message: 消息数据

        Returns:
            bool: 是否发送成功
        """
        from services.data_reporter import send_api_request as _send
        return _send(
            message,
            platform=self.platform,
            socket_user_id=self.socket_user_id,
            timestamp=self.timestamp,
        )
    
    def check_login_status(self, api_data: Dict[str, Any]) -> bool:
        """检测账号登录状态
        
        Args:
            api_data: API数据
            
        Returns:
            bool: True表示已登录，False表示已登出
        """
        try:
            response_body = api_data.get('response', '')
            
            # 尝试解析响应
            if isinstance(response_body, str):
                try:
                    response_json = json.loads(response_body)
                except:
                    return True  # 无法解析时默认登录状态正常
            else:
                response_json = response_body
            
            # 检查常见的登出错误码
            error_codes = [401, 403, 10001, 10002]  # 根据实际平台调整
            code = response_json.get('code') or response_json.get('status_code')
            
            if code in error_codes:
                logger.warning(f'检测到登出错误码: {code}')
                return False
            
            # 检查错误消息
            message = response_json.get('message', '').lower()
            error_keywords = ['unauthorized', 'not logged', 'login', 'token expired']
            if any(keyword in message for keyword in error_keywords):
                logger.warning(f'检测到登出关键词: {message}')
                return False
            
            return True
            
        except Exception as e:
            logger.debug(f'登录状态检测异常: {e}')
            return True  # 异常时默认登录正常
    
    def _extract_domain(self, url: str) -> str:
        """从URL提取域名

        Args:
            url: 完整URL

        Returns:
            str: 域名
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return ''

    def send_login_callback(self, login_status: str, reason: str = "") -> bool:
        """发送登录状态回调

        Args:
            login_status: 登录状态，"success" 或 "logout"
            reason: 失败/登出原因（可选）

        Returns:
            bool: 是否发送成功
        """
        callback_sent = False
        callback_config = Settings.LOGIN_CALLBACK_CONFIG
        if not callback_config.get("enabled", True):
            logger.debug('登录回调已禁用，跳过发送')
        else:
            try:
                # 获取回调配置
                callback_url = callback_config.get("url")
                access_token = callback_config.get("access_token", "")
                timeout = callback_config.get("timeout", 10)

                if not callback_url:
                    logger.warning('未配置登录回调URL，无法发送回调')
                else:
                    # 构造回调参数
                    payload = {
                        "login_status": login_status,
                        "media": self.get_platform_name(),
                        "collection_id": self.browser_id,
                        "reason": reason,
                    }

                    # 构造请求头
                    headers = {
                        "Content-Type": "application/json",
                    }
                    if access_token:
                        headers["accessToken"] = access_token

                    # 发送回调请求
                    logger.info(f'发送登录回调: status={login_status}, platform={self.platform}, browser_id={self.browser_id}')
                    response = requests.post(
                        callback_url,
                        headers=headers,
                        json=payload,
                        timeout=timeout
                    )

                    if response.status_code == 200:
                        logger.info(f'登录回调发送成功: {login_status}')
                        callback_sent = True
                    else:
                        logger.warning(f'登录回调响应异常 {response.status_code}: {response.text[:200]}')

            except requests.Timeout:
                logger.warning('登录回调请求超时')
            except requests.ConnectionError as e:
                logger.warning(f'登录回调连接失败: {e}')
            except Exception as e:
                logger.error(f'发送登录回调异常: {e}')

        try:
            from monitor import get_monitor
            from monitor.login_status_manager import LoginStatusManager

            status_mgr = LoginStatusManager(get_monitor().conn)

            # 检测登出→登录恢复：在写入 login 事件前查询当前状态
            if login_status == "success":
                current_status = status_mgr.get_account_status(self.browser_id)
                if current_status and current_status['status'] == 'logout':
                    self.full_collection = True
                    self._login_recovery = True
                    logger.info(
                        f'[登出即时恢复] 账号 {self.browser_id} 从 logout 恢复登录，'
                        f'当轮切换为全量采集模式'
                    )

            status_mgr.record_login_status(
                account_id=self.browser_id,
                platform=self.platform,
                group_name=self.group_name,
                login_status=login_status,
                reason=reason,
            )
        except Exception as e:
            logger.error(f'写入登录状态事件失败: {e}')

        return callback_sent

