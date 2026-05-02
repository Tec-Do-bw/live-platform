# tests/monitor/test_api_registry.py

from fastapi.testclient import TestClient
from monitor.server import app


client = TestClient(app)


def test_registry_endpoint_returns_platform_structure():
    """/api/registry 应返回按平台分组的注册表"""
    resp = client.get('/api/registry')
    assert resp.status_code == 200
    data = resp.json()
    # 新格式：{platform: {account_types, daily_types, room_types}}
    assert 'tiktok' in data
    assert 'shopee' in data
    for platform in ('tiktok', 'shopee'):
        assert 'account_types' in data[platform]
        assert 'daily_types' in data[platform]
        assert 'room_types' in data[platform]


def test_registry_endpoint_items_have_key_and_label():
    """每项应包含 key 和 label"""
    resp = client.get('/api/registry')
    data = resp.json()
    for platform in data.values():
        for item in platform['account_types']:
            assert 'key' in item
            assert 'label' in item
