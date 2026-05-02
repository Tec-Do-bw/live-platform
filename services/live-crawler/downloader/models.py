"""数据模型定义：Task（采集任务）和 DownloadResult（采集结果）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Task:
    """单个采集任务的描述。

    Attributes:
        url: 目标 URL
        task_id: 业务 ID，不设则由 Downloader 自动分配序号
        method: HTTP 方法，默认 GET
        headers: 请求级别的额外 headers（会与 Client 级别合并）
        params: URL 查询参数
        json_data: JSON 请求体（自动序列化）
        data: 表单 / 原始请求体
        timeout: 请求级别超时（秒），覆盖 Downloader 默认值
        meta: 业务附加数据，原样透传到 DownloadResult
    """

    url: str
    task_id: str | None = None
    method: str = "GET"
    headers: dict[str, str] | None = None
    params: dict[str, str] | None = None
    json_data: Any = None
    data: Any = None
    timeout: float | None = None
    meta: dict[str, Any] | None = None


@dataclass
class DownloadResult:
    """单个采集任务的执行结果。

    Attributes:
        task: 原始任务对象（含 meta 透传数据）
        success: 是否成功（HTTP 2xx 且无异常）
        status_code: HTTP 状态码（请求未到达服务器时为 None）
        text: 响应文本（成功时填充）
        content: 响应原始字节（成功时填充）
        url: 最终 URL（可能经过重定向）
        headers: 响应头
        error: 失败原因描述
        attempts: 总尝试次数（含首次 + 所有重试）
        elapsed_ms: 总耗时（毫秒），含重试等待
    """

    task: Task
    success: bool
    status_code: int | None = None
    text: str | None = None
    content: bytes | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    error: str | None = None
    attempts: int = 0
    elapsed_ms: float = 0
