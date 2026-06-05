"""HTTP 采集器抽象基类。

与 BaseLiveCrawler（浏览器采集）平级，提供纯 HTTP 请求的标准采集流程。
不依赖 AdsPower / DrissionPage，通过 downloader 批量发送 HTTP 请求。

采用 API 序列驱动模式：子类通过 build_api_sequence() 定义 API 类型的执行顺序，
基类按序列逐个执行（初始请求 → 翻页循环 → 依赖任务），确保每个 API 类型
完整完成后再进入下一个。

典型子类用法::

    class LazadaHttpCrawler(BaseHttpCrawler):
        def get_platform_name(self) -> str:
            return 'lazada'

        def build_api_sequence(self, cookies, is_full):
            return [
                ApiSequence(
                    api_type='lazada_seller_metrics',
                    build_initial_tasks=lambda: self._build_metrics_tasks(cookies, is_full),
                ),
            ]

        def parse_response(self, result):
            data = result.text and json.loads(result.text)
            return {'api_type': 'lazada_live_list', 'data': data}
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from core.config import Settings
from core.collection_tracker import CollectionTracker
from downloader import Downloader, Task, DownloadResult
from monitor import get_monitor
from monitor.login_status_manager import LoginStatusManager
from core.collection_mode import resolve_collection_mode
from services.cookie_manager import get_cookies as _get_cookies
from utils.alert import alert_manager
from utils.kafka_client import producer_client
from utils.logger import logger


@dataclass
class ApiSequence:
    """单个 API 类型的采集序列配置。

    Attributes:
        api_type: API 类型标识（如 'lazada_seller_metrics'）
        build_initial_tasks: 构造首页任务，签名 () -> list[Task]。
                             cookies/is_full 等参数由子类在构造 ApiSequence 时通过闭包捕获。
        build_next_page: 构造下一页任务，签名 (last_results, page) -> list[Task]，
                         返回空列表表示无需续页。None 表示该 API 类型不支持分页。
        on_completed: API 类型完成后的回调，签名 (all_results) -> list[Task]，
                      可返回依赖任务（如 3.1 完成后构造 3.2 Task）。None 表示无依赖。
        max_pages: 分页保护上限，防止无限翻页
    """
    api_type: str
    build_initial_tasks: Callable[[], list[Task]]
    build_next_page: Callable[[list[dict], int], list[Task]] | None = None
    on_completed: Callable[[list[dict]], list[Task]] | None = None
    max_pages: int = 10


class BaseHttpCrawler(ABC):
    """HTTP 采集器抽象基类。

    职责边界：
    - 负责通过 HTTP 请求采集数据、解析上报、监控记录
    - 不判断登录状态，不发送 send_login_callback
    - Cookie 管理和登录态判定由养号服务负责
    """

    def __init__(self, browser_id: str = '', full_collection: bool = False,
                 group_name: str = '', batch_id: str = ''):
        self.browser_id = browser_id
        self.full_collection = full_collection
        self.group_name = group_name
        self.batch_id = batch_id
        self.socket_user_id = browser_id

        self.platform = self.get_platform_name()
        if self.platform not in Settings.PLATFORM_CONFIG:
            raise ValueError(f"不支持的平台: {self.platform}")
        self.config = Settings.PLATFORM_CONFIG[self.platform]

        self.timestamp = int(time.time() * 1000)
        logger.info(f'初始化 {self.platform} HTTP 采集器，browser_id: {browser_id}')

    # ------------------------------------------------------------------
    # 抽象方法（子类必须实现）
    # ------------------------------------------------------------------

    @abstractmethod
    def get_platform_name(self) -> str:
        """返回平台标识（如 'lazada'）"""

    @abstractmethod
    def get_data_source(self) -> str:
        """返回数据源标识（子类必须实现）

        Returns:
            str: 数据源标识（如 'live_crawler_lazada_http'）
        """

    @abstractmethod
    def build_api_sequence(self, cookies: dict, is_full: bool) -> list[ApiSequence]:
        """构造 API 序列列表（按执行顺序）。

        基类按序列逐个执行：初始请求 → 翻页循环 → 依赖任务。
        每个 API 类型完整完成后再进入下一个。

        Args:
            cookies: CookieManager 返回的 Cookie 字典
            is_full: 是否全量采集

        Returns:
            ApiSequence 列表，按执行顺序排列
        """

    @abstractmethod
    def parse_response(self, result: DownloadResult) -> dict | None:
        """解析单个下载结果。

        Returns:
            解析后的字典（至少含 api_type 字段），解析失败返回 None
        """

    # ------------------------------------------------------------------
    # 可选钩子（子类按需覆写）
    # ------------------------------------------------------------------

    def get_proxy(self) -> str | None:
        """获取代理地址，子类可覆写。默认不使用代理。

        Returns:
            代理 URL 字符串（如 'socks5://user:pass@host:port'），或 None

        Raises:
            Exception: 子类可在代理获取失败时抛出异常，终止采集
        """
        return None

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _get_kafka_topic(self) -> str:
        """获取当前平台对应的 Kafka topic（优先从平台配置读取）"""
        platform_cfg = Settings.PLATFORM_CONFIG.get(self.platform, {})
        topic = platform_cfg.get('topic_name')
        if topic:
            return topic
        return Settings.KAFKA_CONFIG.get('platform_topics', {}).get(self.platform, '')

    def get_cookies(self) -> dict | None:
        """获取采集所需 Cookie，子类可覆写以支持多端口。

        基类默认实现获取空 endpoint 的 Cookie。
        子类（如 LazadaHttpCrawler）可覆写此方法以获取多端口 Cookie。

        Returns:
            Cookie 字典，无有效 Cookie 返回 None

        Example:
            # 子类覆写示例（Lazada 多端口）
            def get_cookies(self):
                sc = _get_cookies(self.browser_id, 'lazada', 'sellercenter')
                live = _get_cookies(self.browser_id, 'lazada', 'live')
                if sc is None and live is None:
                    return None
                return {'sellercenter': sc or {}, 'live': live or {}}
        """
        return _get_cookies(self.browser_id, self.platform)

    @staticmethod
    def _cookie_header(cookies: dict) -> str:
        """将 Cookie 字典拼接为 HTTP Cookie 头格式"""
        return '; '.join(f'{k}={v}' for k, v in cookies.items())

    def format_message(self, url: str, response_text: str,
                       cookies: dict | None = None,
                       extra: str | None = None,
                       task: 'Task | None' = None) -> dict:
        """构造数据上报消息体（与浏览器采集器格式兼容，支持 GET/POST）。

        Args:
            url: 请求 URL
            response_text: 响应文本
            cookies: Cookie 字典（未使用，子类可覆写）
            extra: 额外信息（未使用，子类可覆写）
            task: Task 对象（用于获取 method 和 POST body）
        """
        method = task.method if task else 'GET'
        if method == 'POST' and task and task.data:
            if isinstance(task.data, dict):
                body = json.dumps(task.data, ensure_ascii=False)
            else:
                body = ''
        else:
            body = ''

        return {
            "params": '',
            "method": method,
            "body": body,
            "cookies": json.dumps(cookies or {}, ensure_ascii=False),
            "fromUrl": url,
            "extra": extra,
            "sign": Settings.DATA_SERVER_CONFIG['api_sign'],
            "userType": 6.0,
            "dataSource": self.get_data_source(),
            "updateTime": int(time.time() * 1000),
            "request": {"response": response_text, "url": url},
            "socketUserId": self.socket_user_id,
        }

    # ------------------------------------------------------------------
    # 核心采集流程
    # ------------------------------------------------------------------

    def start_crawl(self) -> dict[str, Any]:
        """标准 HTTP 采集流程（API 序列驱动）。

        1. 获取 Cookie → 2. 判断全量/增量 → 3. 构造 API 序列 →
        4. 逐个执行序列（初始请求 + 翻页 + 依赖任务） → 5. 监控记录
        """
        monitor = get_monitor()
        if self.batch_id:
            try:
                monitor.start_account(
                    self.batch_id, self.browser_id,
                    self.group_name, self.platform,
                    getattr(self, 'crawl_type', ''),
                )
            except Exception as e:
                logger.error(f'监控 start_account 失败: {e}')

        result: dict[str, Any] = {
            'platform': self.platform,
            'browser_id': self.browser_id,
            'success': False,
            'sequences_completed': 0,
            'tasks_total': 0,
            'tasks_success': 0,
            'data_sent': 0,
            'error': None,
            'start_time': datetime.now().isoformat(),
        }

        try:
            # 1. 获取 Cookie（子类可覆写 get_cookies 支持多端口）
            cookies = self.get_cookies()
            if cookies is None:
                logger.warning(
                    f'账号 {self.browser_id} 无有效 Cookie，跳过采集'
                )
                result['error'] = 'no_cookies'
                return result

            # 2. 判断全量/增量
            tracker = CollectionTracker()
            status_mgr = LoginStatusManager(monitor.conn)
            is_full, mode_reason = resolve_collection_mode(
                platform=self.platform,
                user_id=self.browser_id,
                tracker=tracker,
                status_mgr=status_mgr,
                force_full_collection=self.full_collection,
            )
            logger.info(
                f'采集模式: {"全量" if is_full else "增量"} ({mode_reason})'
            )

            # 3. 获取代理配置（子类可覆写）
            proxy = self.get_proxy()
            if proxy:
                logger.info(f'使用代理: {proxy[:30]}...')

            # 4. 构造 API 序列
            sequences = self.build_api_sequence(cookies, is_full)
            logger.info(f'构造 API 序列完成，共 {len(sequences)} 个')

            # 5. 逐个执行序列
            for seq in sequences:
                self._execute_sequence(seq, proxy, result)
                result['sequences_completed'] += 1

            result['success'] = result['error'] is None

            # 确保所有 Kafka 消息发送完成
            try:
                producer_client.flush()
            except Exception as e:
                logger.error(f'Kafka flush 失败: {e}')

        except Exception as e:
            logger.exception(f'HTTP 采集过程异常: {e}')
            result['error'] = str(e)

        finally:
            result['end_time'] = datetime.now().isoformat()
            if self.batch_id:
                try:
                    status = 'success' if result.get('success') else 'error'
                    monitor.finish_account(
                        self.batch_id, self.browser_id, status
                    )
                except Exception as e:
                    logger.error(f'监控 finish_account 失败: {e}')

        return result

    def _execute_sequence(self, seq: ApiSequence, proxy: str | None,
                          result: dict) -> None:
        """执行单个 API 序列（初始请求 + 翻页循环 + 依赖任务）。

        单个序列失败不阻塞后续序列的执行。
        """
        logger.info(f'[{seq.api_type}] 开始执行')

        try:
            # 1. 执行初始任务
            tasks = seq.build_initial_tasks()
            if not tasks:
                logger.info(f'[{seq.api_type}] 无初始任务，跳过')
                return

            all_parsed: list[dict] = []
            page = 1

            while tasks:
                logger.info(
                    f'[{seq.api_type}] 第 {page} 轮，执行 {len(tasks)} 个 Task'
                )
                result['tasks_total'] += len(tasks)

                dl = Downloader(proxy=proxy)
                dl_results = dl.run(tasks)
                parsed = self._process_results(dl_results, result)
                all_parsed.extend(parsed)

                # 检查翻页
                if not seq.build_next_page or page >= seq.max_pages:
                    break
                page += 1
                tasks = seq.build_next_page(parsed, page)
                if not tasks:
                    break

            # 2. 执行依赖任务（如 3.1→3.2）
            if seq.on_completed and all_parsed:
                dep_tasks = seq.on_completed(all_parsed)
                if dep_tasks:
                    logger.info(
                        f'[{seq.api_type}] 执行 {len(dep_tasks)} 个依赖任务'
                    )
                    result['tasks_total'] += len(dep_tasks)
                    dl = Downloader(proxy=proxy)
                    dl_results = dl.run(dep_tasks)
                    self._process_results(dl_results, result)

        except Exception as e:
            logger.error(f'[{seq.api_type}] 执行异常: {e}')

        logger.info(f'[{seq.api_type}] 完成')

    def _process_results(self, dl_results: list[DownloadResult],
                         result: dict) -> list[dict]:
        """处理一个阶段的下载结果：解析、上报、监控记录。

        返回本阶段成功解析的结果列表。
        """
        monitor = get_monitor()
        parsed_list: list[dict] = []

        for dr in dl_results:
            if not dr.success:
                msg = (
                    f'[{self.platform}] 账号 {self.browser_id} '
                    f'任务 {dr.task.task_id or dr.task.url[:60]} '
                    f'重试 {dr.attempts} 次仍失败: {dr.error}'
                )
                logger.warning(msg)
                alert_manager.send_alert('crawl_failed', '采集任务重试失败', msg)
                continue

            parsed = self.parse_response(dr)
            if parsed is None:
                continue

            result['tasks_success'] += 1
            parsed_list.append(parsed)

            # 数据上报（Kafka）
            api_type = parsed.get('api_type', 'unknown')
            # Token 重试成功时使用重试后的响应体
            response_text = parsed.pop('_retried_text', None) or dr.text or ''
            message = self.format_message(
                url=dr.task.url,
                response_text=response_text,
                extra=dr.task.meta.get('extra') if dr.task.meta else None,
                task=dr.task,
            )
            topic = self._get_kafka_topic()
            if producer_client.send_to_topic(topic, message):
                result['data_sent'] += 1

            # 监控记录
            if self.batch_id:
                try:
                    monitor.record(
                        self.batch_id, self.browser_id,
                        api_type=api_type,
                        room_id=parsed.get('room_id', ''),
                        status='success',
                        response_size=len(response_text),
                    )
                except Exception as e:
                    logger.error(f'监控 record 失败: {e}')

        return parsed_list
