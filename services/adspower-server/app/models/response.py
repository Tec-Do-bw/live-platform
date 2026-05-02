from typing import Any, Optional

from pydantic import BaseModel


CODE_SUCCESS = 0
CODE_FAILED = -1
CODE_PARAM_ERROR = -2
CODE_UNSUPPORTED = -3
CODE_ADSPOWER_API_FAILED = -4
CODE_CDP_CONNECT_FAILED = -5
CODE_SESSION_NOT_FOUND = -6

# 错误码描述映射
CODE_DESCRIPTIONS = {
    CODE_SUCCESS: "成功",
    CODE_FAILED: "通用失败",
    CODE_PARAM_ERROR: "参数错误",
    CODE_UNSUPPORTED: "不支持的国家/媒体组合",
    CODE_ADSPOWER_API_FAILED: "AdsPower API 调用失败",
    CODE_CDP_CONNECT_FAILED: "CDP 连接失败",
    CODE_SESSION_NOT_FOUND: "Session 不存在或已过期",
}


class ApiResponse(BaseModel):
    code: int = CODE_SUCCESS
    msg: str = "success"
    data: Optional[Any] = None


class CreateBrowserData(BaseModel):
    session_id: str
    ws_url: str
    debug_port: str
    collection_id: str
