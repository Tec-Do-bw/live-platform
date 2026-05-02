"""API 类型注册表 — 定义完整性监控的期望 API 列表（按平台）

扩展方式：在对应平台的层级中添加 {'key': '...', 'label': '...'} 即可。
前端通过 /api/registry 获取注册表，动态渲染列头，无需改前端代码。
"""

API_TYPE_REGISTRY: dict[str, dict[str, list[dict]]] = {
    'tiktok': {
        # 账号级（每个账号采集一次）
        'account': [
            {'key': 'live_list', 'label': '直播间列表'},
            {'key': 'replay_info', 'label': '直播回放列表'},
        ],
        # 日期级（每个账号 × 每天一条）
        'daily': [
            {'key': 'live_stats', 'label': '关键指标(按天)'},
        ],
        # 直播间级（每个 room_id 都需要）
        'room': [
            {'key': 'trend_gmv', 'label': 'GMV趋势'},
            {'key': 'trend_stats', 'label': '直播趋势'},
        ],
    },
    'shopee': {
        'account': [
            {'key': 'session_list', 'label': '实时直播间列表'},
            {'key': 'live_list', 'label': '历史直播间列表'},
        ],
        'daily': [
            {'key': 'overview', 'label': '概览数据'},
            {'key': 'metric_trend', 'label': '指标趋势'},
        ],
        'room': [
            {'key': 'session_detail', 'label': '实时直播详情'},
            {'key': 'replay_detail', 'label': '回放详情'},
        ],
    },
    'lazada': {
        # 账号级（每个账号采集一次）
        'account': [
            {'key': 'lazada_realtime_trend', 'label': '实时趋势'},
            {'key': 'lazada_realtime_detail', 'label': '实时详情'},
        ],
        # 日期级（每个账号 × 每天一条）
        'daily': [
            {'key': 'lazada_seller_metrics', 'label': '卖家指标'},
            {'key': 'lazada_seller_product_rooms', 'label': '商品直播间'},
            {'key': 'lazada_seller_products', 'label': '商品列表'},
            {'key': 'lazada_ba_key_overview', 'label': '关键指标概览'},
            {'key': 'lazada_ba_key_trend', 'label': '关键指标趋势'},
            {'key': 'lazada_ba_traffic_overall', 'label': '流量整体'},
            {'key': 'lazada_ba_traffic_source', 'label': '流量来源'},
            {'key': 'lazada_ba_traffic_search', 'label': '流量搜索'},
            {'key': 'lazada_ba_product_overview', 'label': '商品概览'},
            {'key': 'lazada_ba_product_diagnosis', 'label': '商品诊断'},
            {'key': 'lazada_ba_product_perf_revenue', 'label': '商品营收'},
            {'key': 'lazada_ba_product_perf_visitor', 'label': '商品访客'},
            {'key': 'lazada_ba_promo_overview', 'label': '促销概览'},
            {'key': 'lazada_ba_promo_trend', 'label': '促销趋势'},
            {'key': 'lazada_ba_promo_category', 'label': '促销分类'},
        ],
        # 直播间级（每个 room_id 都需要）
        'room': [
            {'key': 'lazada_live_list', 'label': '直播列表'},
            {'key': 'lazada_room_metrics', 'label': '直播间指标'},
        ],
    },
}


def detect_platform(group_name_or_platform: str) -> str:
    """识别平台，优先匹配已知平台名，否则默认 tiktok

    Args:
        group_name_or_platform: 平台名（如 'shopee'）或分组名
    """
    if group_name_or_platform in API_TYPE_REGISTRY:
        return group_name_or_platform
    return 'tiktok'


def get_expected_account_types(platform: str = 'tiktok', crawl_type: str = '') -> list[str]:
    """返回账号级期望 api_type 列表"""
    return [item['key'] for item in API_TYPE_REGISTRY[platform]['account']]


def get_expected_daily_types(platform: str = 'tiktok', crawl_type: str = '') -> list[str]:
    """返回日期级期望 api_type 列表"""
    return [item['key'] for item in API_TYPE_REGISTRY[platform]['daily']]


def get_expected_room_types(platform: str = 'tiktok', crawl_type: str = '') -> list[str]:
    """返回直播间级期望 api_type 列表"""
    return [item['key'] for item in API_TYPE_REGISTRY[platform]['room']]


def get_room_types_for_completion(platform: str = 'tiktok', crawl_type: str = '') -> list[str]:
    """返回用于完整率计算的直播间级 api_type 列表

    Shopee 当前版本只关注回放采集完整性，排除 session_detail。
    """
    all_types = get_expected_room_types(platform)
    if platform == 'shopee':
        return [t for t in all_types if t != 'session_detail']
    return all_types


def get_registry_for_api() -> dict:
    """返回完整注册表供前端 /api/registry 使用（按平台）"""
    result = {}
    for platform, levels in API_TYPE_REGISTRY.items():
        result[platform] = {
            'account_types': levels['account'],
            'daily_types': levels['daily'],
            'room_types': levels['room'],
        }
    return result
