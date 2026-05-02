"""API 类型注册表测试 — 验证平台化结构"""

from monitor.registry import (
    get_expected_account_types,
    get_expected_room_types,
    get_expected_daily_types,
    get_registry_for_api,
    detect_platform,
    API_TYPE_REGISTRY,
)


class TestRegistryStructure:
    """注册表结构测试"""

    def test_registry_has_platform_keys(self):
        """注册表应包含 tiktok 和 shopee 两个平台"""
        assert 'tiktok' in API_TYPE_REGISTRY
        assert 'shopee' in API_TYPE_REGISTRY

    def test_each_platform_has_three_levels(self):
        """每个平台应包含 account / daily / room 三层"""
        for platform in ('tiktok', 'shopee'):
            assert 'account' in API_TYPE_REGISTRY[platform]
            assert 'daily' in API_TYPE_REGISTRY[platform]
            assert 'room' in API_TYPE_REGISTRY[platform]

    def test_each_item_has_key_and_label(self):
        """每项应包含 key 和 label"""
        for platform in API_TYPE_REGISTRY:
            for level in API_TYPE_REGISTRY[platform]:
                for item in API_TYPE_REGISTRY[platform][level]:
                    assert 'key' in item
                    assert 'label' in item


class TestTikTokTypes:
    """TikTok 平台类型测试"""

    def test_account_types(self):
        types = get_expected_account_types('tiktok')
        assert 'live_list' in types
        assert 'replay_info' in types

    def test_room_types(self):
        types = get_expected_room_types('tiktok')
        assert 'trend_gmv' in types
        assert 'trend_stats' in types

    def test_daily_types(self):
        types = get_expected_daily_types('tiktok')
        assert 'live_stats' in types

    def test_default_platform_is_tiktok(self):
        """默认参数应返回 tiktok 的类型（向后兼容）"""
        assert get_expected_account_types() == get_expected_account_types('tiktok')
        assert get_expected_room_types() == get_expected_room_types('tiktok')
        assert get_expected_daily_types() == get_expected_daily_types('tiktok')


class TestShopeeTypes:
    """Shopee 平台类型测试"""

    def test_account_types(self):
        types = get_expected_account_types('shopee')
        assert 'session_list' in types
        assert 'live_list' in types

    def test_room_types(self):
        types = get_expected_room_types('shopee')
        assert 'session_detail' in types
        assert 'replay_detail' in types

    def test_daily_types(self):
        types = get_expected_daily_types('shopee')
        assert 'overview' in types
        assert 'metric_trend' in types


class TestDetectPlatform:
    """平台识别测试"""

    def test_known_platform_names(self):
        """已知平台名应直接返回"""
        assert detect_platform('tiktok') == 'tiktok'
        assert detect_platform('shopee') == 'shopee'

    def test_default_is_tiktok(self):
        """未知字符串应默认为 tiktok"""
        assert detect_platform('团队A') == 'tiktok'
        assert detect_platform('') == 'tiktok'
        assert detect_platform('unknown') == 'tiktok'


class TestGetRegistryForApi:
    """前端 API 返回格式测试"""

    def test_returns_platform_structure(self):
        result = get_registry_for_api()
        assert 'tiktok' in result
        assert 'shopee' in result
        for platform in result:
            assert 'account_types' in result[platform]
            assert 'daily_types' in result[platform]
            assert 'room_types' in result[platform]


class TestHelperFunctionsReturnStrings:
    """辅助函数返回类型测试"""

    def test_all_return_list_of_strings(self):
        for platform in ('tiktok', 'shopee'):
            for func in [get_expected_account_types, get_expected_room_types, get_expected_daily_types]:
                result = func(platform)
                assert isinstance(result, list)
                for item in result:
                    assert isinstance(item, str)
