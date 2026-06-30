"""时间解析工具。"""

from datetime import datetime, timezone


def extract_target_date(request_body: dict) -> str | None:
    """从 live/stats 请求体中提取目标日期。"""
    try:
        params = request_body.get("request", {}).get("params", [])
        if not params:
            return None
        time_selector = params[0].get("time_selector", {})
        start_ts = time_selector.get("start_timestamp", 0)
        if not start_ts:
            return None
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        return start_dt.strftime("%Y-%m-%d")
    except Exception:
        return None
