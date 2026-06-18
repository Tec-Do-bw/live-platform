"""API 响应翻译层：将 Tool 返回值映射为标准化响应结构"""
from dataclasses import dataclass


@dataclass
class ApiOutcome:
    """Tool 返回值翻译后的统一结构"""
    code: int
    port_info: dict | None
    error_reason: str | None
    error_detail: str | None


CODE_MESSAGES = {
    200:  "success",
    2001: "当前未开播",
    2002: "历史直播已结束",
    401:  "Unauthorized",
    4001: "入参缺失",
    4002: "入参格式错误",
    4041: "直播间不存在",
    4042: "短链已失效",
    5001: "上游请求失败",
    5002: "上游响应解析失败",
    5003: "上游限流或风控",
    5099: "采集内部异常",
}


class ErrorReason:
    INVALID_PARAM = "INVALID_PARAM"
    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"
    SHORT_URL_EXPIRED = "SHORT_URL_EXPIRED"
    UPSTREAM_REQUEST_FAILED = "UPSTREAM_REQUEST_FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def classify_tiktok_result(raw: dict | None, mate_url: str) -> ApiOutcome:
    """将 TikTok Tool 返回值翻译为 ApiOutcome"""
    if raw is None:
        return ApiOutcome(5099, None, ErrorReason.INTERNAL_ERROR, "Tool 返回 None")

    flv_url = raw.get("flv_url", "")
    message = raw.get("message", "")

    # 直播中
    if flv_url and flv_url not in ("", "error"):
        clean_info = {k: v for k, v in raw.items() if k != "message"}
        return ApiOutcome(200, clean_info, None, None)

    # 未开播（有用户信息）
    if flv_url == "" and raw.get("uniqueId"):
        clean_info = {
            k: v for k, v in raw.items()
            if k not in ("flv_url", "message") and v != ""
        }
        return ApiOutcome(2001, clean_info, None, None)

    # flv_url="" 且 message 指示错误
    if flv_url == "":
        if "页面解析失败" in message:
            return ApiOutcome(5002, None, ErrorReason.PARSE_FAILED, message)
        if "用户信息不存在" in message or "直播间不存在" in message:
            return ApiOutcome(4041, None, ErrorReason.ROOM_NOT_FOUND, message)

    # flv_url="error"
    if flv_url == "error":
        if "请求直播页失败" in message or "请求个人页失败" in message:
            return ApiOutcome(5001, None, ErrorReason.UPSTREAM_REQUEST_FAILED, message)
        if "采集内部异常" in message or "tk采集异常" in message:
            return ApiOutcome(5099, None, ErrorReason.INTERNAL_ERROR, message)
        return ApiOutcome(5002, None, ErrorReason.PARSE_FAILED, message or "解析失败")

    return ApiOutcome(5099, None, ErrorReason.INTERNAL_ERROR, "未识别的返回格式")


def classify_shopee_result(raw: dict | None, mate_url: str) -> ApiOutcome:
    """将 Shopee Tool 返回值翻译为 ApiOutcome"""
    if raw is None:
        return ApiOutcome(5099, None, ErrorReason.INTERNAL_ERROR, "Shopee 采集失败")

    flv_url = raw.get("flv_url", "")

    # 直播中
    if flv_url and flv_url not in ("", "error"):
        return ApiOutcome(200, raw, None, None)

    # 未开播（有 session 或 filePath）
    if raw.get("session") or raw.get("filePath"):
        clean_info = {
            k: v for k, v in raw.items()
            if k not in ("flv_url", "play_urls", "startTime") and v != ""
        }
        return ApiOutcome(2001, clean_info, None, None)

    return ApiOutcome(5002, None, ErrorReason.PARSE_FAILED, "Shopee 数据不完整")


def classify_lazada_result(raw: dict | None, mate_url: str) -> ApiOutcome:
    """将 Lazada Tool 返回值翻译为 ApiOutcome"""
    if raw is None:
        return ApiOutcome(5099, None, ErrorReason.INTERNAL_ERROR, "Tool 返回 None")

    flv_url = raw.get("flv_url", "")
    message = raw.get("message", "")

    # 直播中
    if flv_url and flv_url not in ("", "error"):
        clean_info = {k: v for k, v in raw.items() if k != "message"}
        return ApiOutcome(200, clean_info, None, None)

    # flv_url="error"
    if flv_url == "error":
        if "直播间不存在" in message:
            return ApiOutcome(4041, None, ErrorReason.ROOM_NOT_FOUND, message)
        if "当前暂无直播" in message:
            clean_info = {
                k: v for k, v in raw.items()
                if k not in ("flv_url", "message", "play_urls", "startTime",
                             "liveUuid", "roomStatus", "title") and v != ""
            }
            return ApiOutcome(2002, clean_info, None, None)
        if "lazada数据为空" in message:
            return ApiOutcome(5002, None, ErrorReason.PARSE_FAILED, message)
        if "lazada采集异常" in message:
            return ApiOutcome(5099, None, ErrorReason.INTERNAL_ERROR, message)

    return ApiOutcome(5099, None, ErrorReason.INTERNAL_ERROR, "未识别的返回格式")


def success_response(code: int, port_info: dict | None, mate_url: str) -> dict:
    """成功响应包装（code=200 或 2xxx）"""
    return {
        "code": code,
        "message": CODE_MESSAGES[code],
        "data": {"mateUrl": mate_url, "port_info": port_info},
    }


def error_response(
    code: int, reason: str, detail: str, platform: str, mate_url: str
) -> dict:
    """失败响应包装（code=4xxx 或 5xxx）"""
    safe_detail = detail[:200] if detail else ""
    return {
        "code": code,
        "message": CODE_MESSAGES[code],
        "data": {"mateUrl": mate_url, "port_info": None},
        "error": {"platform": platform, "reason": reason, "detail": safe_detail},
    }
