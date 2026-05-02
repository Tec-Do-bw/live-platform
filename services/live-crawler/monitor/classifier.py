"""API 分类器 — 根据 URL + 请求参数判断 api_type

后续新增 API 类型时，在此文件添加匹配规则即可。
"""

import json


def extract_stats_types(request_body) -> list[int]:
    """从请求体中提取 stats_types 列表"""
    if not request_body:
        return []
    if isinstance(request_body, str):
        try:
            request_body = json.loads(request_body)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(request_body, dict):
        return []

    req = request_body.get('request', request_body)

    # trend/chart 格式：request.stats_types
    if 'stats_types' in req:
        return req['stats_types']

    # live/list 和 live/stats 格式：request.params[0].stats_types
    params = req.get('params', [])
    if params and isinstance(params, list):
        return params[0].get('stats_types', [])

    return []


def classify_api(url: str, request_body=None) -> str | None:
    """根据 URL + 请求参数判断 api_type

    Args:
        url: API URL
        request_body: 请求体（dict 或 JSON 字符串）

    Returns:
        api_type 字符串，无法识别返回 None
    """
    if not url:
        return None

    # 账号级 API — URL 直接匹配
    if 'live/list' in url:
        return 'live_list'
    if 'replay/info' in url:
        return 'replay_info'
    if 'account_info/get' in url:
        return 'account_info'

    # 直播间级 API — URL 直接匹配
    if 'recap/core/stats' in url:
        return 'room_core_stats'
    if 'recap/product/list' in url:
        return 'room_product_list'
    if 'workbench/live/detail/core/stats' in url:
        return 'room_traffic_conversion'
    if 'recap/viewer/source/stats' in url:
        return 'room_viewer_portrait'
    if 'detail/source/new' in url:
        return 'room_traffic_source'

    # trend/chart — 需要通过 stats_types 区分
    if 'recap/trend/chart' in url:
        stats_types = extract_stats_types(request_body)
        if 52 in stats_types:
            return 'trend_gmv'
        if 60 in stats_types or 61 in stats_types:
            return 'trend_traffic'
        if stats_types == [3]:
            return 'trend_gmv'
        return 'trend_stats'

    # live/stats — 需要通过 stats_types 区分
    if 'live/stats' in url:
        stats_types = extract_stats_types(request_body)
        if any(t in stats_types for t in [100, 101, 121]):
            return 'data_overview'
        return 'live_stats_7d'

    return None
