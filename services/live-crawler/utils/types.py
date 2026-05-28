"""HTTP 采集共享类型契约。"""

from typing import Any, TypedDict


class FatalError(Exception):
    """需要中止当前账号整轮采集的致命异常。"""


class LoginRequired(FatalError):
    """凭据失效或账号需要重新登录。"""


class FetchResult(TypedDict):
    """单个 fetch_* 接口的统一返回结构。"""

    ok: bool
    url: str
    request_body: str | dict[str, Any] | None
    response_body: str | dict[str, Any]
    data: dict[str, Any]
