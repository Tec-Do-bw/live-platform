"""Downloader 主类：基于 never_primp 的稳定批量采集下载器。

代理策略：
  - 默认（调用方未显式传 proxy）：首次请求用静态池随机 IP，重试时切到 DEFAULT_PROXY（ipbiubiu，一次一换）
  - 调用方显式传入 proxy：全程使用该代理，重试不切换
  - 调用方传 None：禁用代理

三层重试机制：
  L1 - never_primp 内置：网络连接/DNS 失败时自动重试（max_retries=2）
  L2 - 应用层指数退避：HTTP 429/5xx/异常/短响应时退避重试（默认 3 次），重试时自动换代理
  L3 - 最终失败队列：全部耗尽后记录到 failed_results，回调通知业务

短响应判定：
  Task.min_content_length 不为 None 时，HTTP 200 但响应短于此值视为失败重试
  （用于 TikTok 直播页风控/简化页等场景）
"""

from __future__ import annotations

import time
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
from loguru import logger

import never_primp

from .config import (
    DEFAULT_HEADERS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PROXY,
    DEFAULT_TIMEOUT,
    DEFAULT_WORKERS,
    NP_MAX_RETRIES,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_MAX,
    RETRY_STATUS_CODES,
)
from .models import DownloadResult, Task



class Downloader:
    """稳定批量采集下载器。

    基于 never_primp（wreq/Rust）构建，支持浏览器指纹伪装、
    线程池并发、分层重试和业务回调。

    用法：
        dl = Downloader(workers=10)
        results = dl.run(["https://example.com/1", "https://example.com/2"])
        print(dl.summary)
    """

    def __init__(
        self,
        proxy: str | None = DEFAULT_PROXY,
        workers: int = DEFAULT_WORKERS,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        headers: dict[str, str] | None = None,
        on_success: Callable[[DownloadResult], Any] | None = None,
        on_failure: Callable[[DownloadResult], Any] | None = None,
        impersonate: str = "chrome_143",
    ) -> None:
        """初始化下载器。

        Args:
            proxy: 代理地址，默认使用 DEFAULT_PROXY，传 None 禁用代理
            workers: 线程池大小
            timeout: 请求超时（秒）
            max_retries: 应用层最大重试次数（L2）
            headers: 自定义请求头（与 DEFAULT_HEADERS 合并，自定义优先）
            on_success: 成功回调，签名 (DownloadResult) -> Any
            on_failure: 失败回调，签名 (DownloadResult) -> Any
            impersonate: 浏览器指纹，默认 chrome_143
        """
        self._workers = workers
        self._timeout = timeout
        self._max_retries = max_retries
        self._on_success = on_success
        self._on_failure = on_failure
        self._impersonate = impersonate
        _JS_DIR = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(_JS_DIR, "ip_list.txt"), "r", encoding="UTF-8") as _f:
            self.ip_list = [line.strip() for line in _f.readlines()]

        # 合并请求头：默认 + 自定义覆盖
        self._merged_headers = {**DEFAULT_HEADERS, **(headers or {})}

        # 代理选择策略（基于 tests/proxy_stability 实测数据）：
        # - 调用方未显式传 proxy（保留默认 DEFAULT_PROXY）→ 首次走静态池随机，重试切 ipbiubiu
        # - 调用方显式传入 proxy（含 None）→ 全程使用，重试不切换
        # 静态池：300 IP 实测成功率 100%、P95 1688ms
        # ipbiubiu：一次一换、100% US 纯度，作为重试代理
        if proxy is DEFAULT_PROXY:
            self._primary_proxy = "http://" + random.choice(self.ip_list)
            self._retry_proxy = DEFAULT_PROXY
        else:
            self._primary_proxy = proxy
            self._retry_proxy = proxy

        # 创建首次请求用的 Client
        self._client = self._build_client(self._primary_proxy)

        # 结果存储
        self._results: list[DownloadResult] = []
        self._total_elapsed: float = 0

    def _build_client(self, proxy: str | None) -> never_primp.Client:
        """根据代理构造 never_primp Client（线程安全、无锁 Arc clone）"""
        return never_primp.Client(
            impersonate=self._impersonate,
            impersonate_os="windows",
            proxy=proxy,
            timeout=self._timeout,
            headers=self._merged_headers,
            max_retries=NP_MAX_RETRIES,  # L1 底层网络重试
        )

    def run(self, tasks: list[Task | str]) -> list[DownloadResult]:
        """批量执行采集，返回全部结果（成功 + 失败）。

        Args:
            tasks: 任务列表，可以是 Task 对象或 URL 字符串

        Returns:
            全部 DownloadResult 列表，顺序与输入一致
        """
        # 标准化输入：str → Task
        normalized: list[Task] = []
        for i, t in enumerate(tasks):
            if isinstance(t, str):
                t = Task(url=t, task_id=str(i))
            elif t.task_id is None:
                t.task_id = str(i)
            normalized.append(t)

        total = len(normalized)
        start_time = time.monotonic()

        results: list[DownloadResult] = [None] * total  # type: ignore[list-item]

        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            # 提交所有任务，记录 future → 索引映射
            future_to_idx = {
                pool.submit(self._execute_task, task): idx
                for idx, task in enumerate(normalized)
            }

            done_count = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                result = future.result()  # _execute_task 内部已捕获所有异常
                results[idx] = result
                done_count += 1

                # 回调通知
                if result.success:
                    if self._on_success:
                        try:
                            self._on_success(result)
                        except Exception:
                            logger.exception("on_success 回调异常")
                else:
                    if self._on_failure:
                        try:
                            self._on_failure(result)
                        except Exception:
                            logger.exception("on_failure 回调异常")

        self._total_elapsed = (time.monotonic() - start_time) * 1000
        self._results = results
        return results

    def fetch_one(self, task: Task | str) -> DownloadResult:
        """执行单个采集任务并返回结果。"""
        results = self.run([task])
        return results[0]

    def _execute_task(self, task: Task) -> DownloadResult:
        """执行单个任务，含 L2 应用层指数退避重试。

        重试时自动切换到 _retry_proxy（默认 ipbiubiu，一次一换 IP）。
        若 task.min_content_length 不为 None，HTTP 200 但响应过短也视为失败重试。
        """
        last_error: str | None = None
        last_status: int | None = None
        task_start = time.monotonic()

        for attempt in range(1, self._max_retries + 2):  # +1 是首次尝试
            # 第二次尝试起切到重试代理（ipbiubiu 自带一次一换，后续重试不必再切）
            if attempt == 2 and self._retry_proxy != self._primary_proxy:
                self._client = self._build_client(self._retry_proxy)
                logger.debug("[%s] 切换到重试代理"% task.task_id)

            try:
                # 构造请求参数
                kwargs: dict[str, Any] = {}
                if task.params:
                    kwargs["params"] = task.params
                if task.headers:
                    kwargs["headers"] = task.headers
                if task.json_data is not None:
                    kwargs["json"] = task.json_data
                if task.data is not None:
                    kwargs["data"] = task.data
                if task.timeout is not None:
                    kwargs["timeout"] = task.timeout

                # 通过方法名分发（get/post/put/delete/patch/head/options）
                method_fn = getattr(self._client, task.method.lower())
                resp = method_fn(task.url, **kwargs)

                # 短响应判定（HTTP 200 但响应过短，视为风控/简化页 → 重试换代理）
                if (task.min_content_length is not None
                        and resp.status_code == 200
                        and len(resp.text or "") < task.min_content_length):
                    text_len = len(resp.text or "")
                    last_status = resp.status_code
                    last_error = f"短响应 {text_len} < {task.min_content_length}"
                    if attempt <= self._max_retries:
                        logger.debug(
                            "[%s] 短响应 %d 字节 < %d，重试 (%d/%d)"%
                            (task.task_id, text_len, task.min_content_length,
                            attempt, self._max_retries)
                        )
                        # 短响应不退避：风控页响应已经很快，立即换代理重试更高效
                        continue
                    elapsed = (time.monotonic() - task_start) * 1000
                    return DownloadResult(
                        task=task,
                        success=False,
                        status_code=resp.status_code,
                        text=resp.text,
                        error=f"重试耗尽: {last_error}",
                        attempts=attempt,
                        elapsed_ms=elapsed,
                    )

                # 检查是否需要 L2 重试
                if resp.status_code in RETRY_STATUS_CODES:
                    last_status = resp.status_code
                    last_error = f"HTTP {resp.status_code}"
                    if attempt <= self._max_retries:
                        backoff = min(
                            RETRY_BACKOFF_BASE * (2 ** (attempt - 1)),
                            RETRY_BACKOFF_MAX,
                        )
                        logger.debug(
                            "[%s] HTTP %d，%.1fs 后重试 (%d/%d)" %
                            (task.task_id, resp.status_code, backoff,
                            attempt, self._max_retries)
                        )
                        time.sleep(backoff)
                        continue

                    # 重试耗尽，仍返回可重试状态码 → 标记失败
                    elapsed = (time.monotonic() - task_start) * 1000
                    return DownloadResult(
                        task=task,
                        success=False,
                        status_code=resp.status_code,
                        error=f"重试耗尽: HTTP {resp.status_code}",
                        attempts=attempt,
                        elapsed_ms=elapsed,
                    )

                # 成功
                elapsed = (time.monotonic() - task_start) * 1000
                return DownloadResult(
                    task=task,
                    success=True,
                    status_code=resp.status_code,
                    text=resp.text,
                    content=resp.content,
                    url=resp.url,
                    headers=dict(resp.headers),
                    attempts=attempt,
                    elapsed_ms=elapsed,
                )

            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                last_status = None
                if attempt <= self._max_retries:
                    backoff = min(
                        RETRY_BACKOFF_BASE * (2 ** (attempt - 1)),
                        RETRY_BACKOFF_MAX,
                    )
                    logger.debug(
                        "[%s] 异常 %s，%.1fs 后重试 (%d/%d)" %
                        (task.task_id, last_error, backoff,
                        attempt, self._max_retries)
                    )
                    time.sleep(backoff)
                    continue

        # 全部重试耗尽（L3 最终失败）
        elapsed = (time.monotonic() - task_start) * 1000
        return DownloadResult(
            task=task,
            success=False,
            status_code=last_status,
            error=last_error,
            attempts=self._max_retries + 1,
            elapsed_ms=elapsed,
        )

    @property
    def summary(self) -> dict[str, Any]:
        """采集摘要统计。

        Returns:
            包含 total/success/failed/elapsed/failures 的字典
        """
        success_count = sum(1 for r in self._results if r.success)
        failed = [r for r in self._results if not r.success]
        return {
            "total": len(self._results),
            "success": success_count,
            "failed": len(failed),
            "elapsed": f"{self._total_elapsed / 1000:.1f}s",
            "failures": [
                {
                    "task_id": r.task.task_id,
                    "url": r.task.url,
                    "error": r.error,
                    "status_code": r.status_code,
                    "attempts": r.attempts,
                }
                for r in failed
            ],
        }

    def failed_tasks(self) -> list[Task]:
        """提取失败的 Task 列表，可直接传给另一次 run() 重跑。"""
        return [r.task for r in self._results if not r.success]
