"""Shopee 登录监听单元测试"""
import pytest
from unittest.mock import MagicMock, patch
from app.services.login_monitor import LoginMonitorService
from app.services.session import Session


@pytest.fixture
def service():
    """LoginMonitorService 实例"""
    return LoginMonitorService()


@pytest.fixture
def mock_tab():
    """Mock DrissionPage tab"""
    tab = MagicMock()
    tab.url = "https://seller.shopee.com.my/"
    tab.run_js = MagicMock(return_value=None)
    return tab


@pytest.fixture
def session_cn(mock_tab):
    """跨境店 session"""
    session = Session(
        session_id="test-cn",
        profile_id="profile-cn",
        country="MY",
        media="shopee",
        validate_id="123456",
        cb_option=1,
        drissionpage_tab=mock_tab,
    )
    return session


@pytest.fixture
def session_local(mock_tab):
    """本土店 session"""
    session = Session(
        session_id="test-local",
        profile_id="profile-local",
        country="MY",
        media="shopee",
        validate_id="789012",
        cb_option=0,
        drissionpage_tab=mock_tab,
    )
    return session


def test_fetch_cn_shop_ids_success(service, mock_tab):
    """跨境店主动验证成功，get_session + get_merchant_shop_list 都返回"""
    with patch.object(service, '_inject_js_with_retry'):
        with patch.object(service, '_poll_window_var') as mock_poll:
            mock_poll.side_effect = [
                {'status': 200, 'response': {'code': 0, 'sub_account_info': {'current_shop_id': 123456}}},
                {'status': 200, 'response': {'code': 0, 'data': {'shops': [{'shop_id': 123456}, {'shop_id': 789012}]}}},
            ]
            login_ok, shop_ids = service._fetch_cn_shop_ids(mock_tab)
            assert login_ok is True
            assert shop_ids == {123456, 789012}


def test_fetch_cn_shop_ids_only_current(service, mock_tab):
    """跨境店 get_merchant_shop_list 无权限，仅 current_shop_id 可用"""
    with patch.object(service, '_inject_js_with_retry'):
        with patch.object(service, '_poll_window_var') as mock_poll:
            mock_poll.side_effect = [
                {'status': 200, 'response': {'code': 0, 'sub_account_info': {'current_shop_id': 123456}}},
                {'error': 'NetworkError'},
            ]
            login_ok, shop_ids = service._fetch_cn_shop_ids(mock_tab)
            assert login_ok is True
            assert shop_ids == {123456}


def test_fetch_cn_shop_ids_logout(service, mock_tab):
    """跨境店未登录"""
    with patch.object(service, '_inject_js_with_retry'):
        with patch.object(service, '_poll_window_var') as mock_poll:
            mock_poll.side_effect = [
                {'status': 200, 'response': {'code': 2, 'message': 'token not found'}},
                None,
            ]
            login_ok, shop_ids = service._fetch_cn_shop_ids(mock_tab)
            assert login_ok is False
            assert shop_ids == set()


def test_fetch_local_shop_ids_success(service, mock_tab):
    """本土店主动验证成功"""
    with patch.object(service, '_inject_js_with_retry'):
        with patch.object(service, '_poll_window_var') as mock_poll:
            mock_poll.side_effect = [
                {'status': 200, 'response': {'errcode': 0, 'shopid': 789012}},
                {'status': 200, 'response': {'code': 0, 'shops': [{'shop_id': 789012}, {'shop_id': 111111}]}},
            ]
            login_ok, shop_ids = service._fetch_local_shop_ids(mock_tab, "MY")
            assert login_ok is True
            assert shop_ids == {789012, 111111}


def test_fetch_local_shop_ids_logout(service, mock_tab):
    """本土店未登录"""
    with patch.object(service, '_inject_js_with_retry'):
        with patch.object(service, '_poll_window_var') as mock_poll:
            mock_poll.side_effect = [
                {'status': 200, 'response': {'errcode': 1, 'fields': None}},
                None,
            ]
            login_ok, shop_ids = service._fetch_local_shop_ids(mock_tab, "MY")
            assert login_ok is False
            assert shop_ids == set()


def test_poll_window_var_success(service, mock_tab):
    """poll 成功获取值"""
    mock_tab.run_js.return_value = {'key': 'value'}
    result = service._poll_window_var(mock_tab, "__test_var", timeout=2.0)
    assert result == {'key': 'value'}


def test_poll_window_var_timeout(service, mock_tab):
    """poll 超时返回 None"""
    mock_tab.run_js.return_value = None
    result = service._poll_window_var(mock_tab, "__test_var", timeout=0.5)
    assert result is None


def test_listen_once_false_positive_blocked(service, session_local, mock_tab):
    """被动监听误报，最终 API 验证拦截"""
    # Mock 被动监听返回 shop_id（误报）
    mock_packet = type('Packet', (), {
        'url': 'https://seller.shopee.com.my/api/v2/login',
        'response': type('Response', (), {
            'body': '{"errcode": 0, "shopid": 789012}'
        })()
    })()
    
    mock_tab.listen.start = lambda x: None
    mock_tab.listen.wait = lambda timeout: mock_packet
    mock_tab.listen.stop = lambda: None
    mock_tab.url = "https://seller.shopee.com.my/"
    
    # 最终 API 验证返回未登录
    with patch.object(service, '_fetch_shopee_shop_ids') as mock_final:
        mock_final.return_value = (False, set())  # 最终验证失败
        
        result = service._listen_once(session_local)
        
        # 应该被最终验证拦截，返回 None
        assert result is None
        assert mock_final.call_count >= 1  # 主动验证 + 最终验证


def test_listen_once_final_verify_pass(service, session_local, mock_tab):
    """被动监听 + 最终 API 验证都通过"""
    mock_packet = type('Packet', (), {
        'url': 'https://seller.shopee.com.my/api/v2/login',
        'response': type('Response', (), {
            'body': '{"errcode": 0, "shopid": 789012}'
        })()
    })()
    
    mock_tab.listen.start = lambda x: None
    mock_tab.listen.wait = lambda timeout: mock_packet
    mock_tab.listen.stop = lambda: None
    mock_tab.url = "https://seller.shopee.com.my/"
    
    # 最终 API 验证返回成功
    with patch.object(service, '_fetch_shopee_shop_ids') as mock_final:
        mock_final.return_value = (True, {789012, 111111})  # 最终验证成功
        
        result = service._listen_once(session_local)
        
        # 应该合并最终验证结果
        assert result is not None
        assert result['login_ok'] is True
        assert 789012 in result['shop_ids']
        assert 111111 in result['shop_ids']
