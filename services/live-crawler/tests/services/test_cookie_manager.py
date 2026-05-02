"""Cookie 管理模块单元测试"""

import json
import pytest
from services.cookie_manager import get_cookies, save_cookies, get_account_credentials
from monitor.db import get_connection, init_db


@pytest.fixture
def db_factory(monkeypatch):
    """创建内存测试数据库，并 patch get_connection 返回同一连接"""
    conn = get_connection(':memory:')
    init_db(conn)
    monkeypatch.setattr('services.cookie_manager.get_connection', lambda: conn)
    yield conn
    conn.close()


def test_save_and_get_cookies(db_factory):
    """测试首次保存和查询 Cookie"""
    cookies = {'token': 'abc123', 'session': 'xyz'}
    save_cookies('a1', 'lazada', 'sellercenter', cookies)
    result = get_cookies('a1', 'lazada', 'sellercenter')
    assert result == cookies


def test_update_existing_cookies(db_factory):
    """测试更新已有 Cookie"""
    save_cookies('a1', 'lazada', 'sellercenter', {'token': 'old'})
    new_cookies = {'token': 'new', 'extra_field': 'value'}
    save_cookies('a1', 'lazada', 'sellercenter', new_cookies)
    result = get_cookies('a1', 'lazada', 'sellercenter')
    assert result == new_cookies


def test_get_nonexistent_cookies(db_factory):
    """测试查询不存在的 Cookie 返回 None"""
    result = get_cookies('nonexistent', 'lazada', 'sellercenter')
    assert result is None


def test_save_with_extra(db_factory):
    """测试保存 extra 字段（账号密码）"""
    extra = {'username': 'user@example.com', 'password': 'pass123'}
    save_cookies('a1', 'lazada', 'sellercenter', {'token': 'abc'}, extra)
    row = db_factory.execute(
        "SELECT extra FROM cookies WHERE account_id='a1' AND platform='lazada' AND endpoint='sellercenter'"
    ).fetchone()
    assert json.loads(row['extra']) == extra


def test_get_account_credentials(db_factory):
    """测试提取账号凭证"""
    extra = {'username': 'user@test.com', 'password': 'secret'}
    save_cookies('a1', 'lazada', 'sellercenter', {'token': 'x'}, extra)
    result = get_account_credentials('a1', 'lazada', 'sellercenter')
    assert result == {'username': 'user@test.com', 'password': 'secret'}


def test_get_credentials_empty_extra(db_factory):
    """测试 extra 为空时返回 None"""
    save_cookies('a1', 'lazada', 'sellercenter', {'token': 'x'})
    result = get_account_credentials('a1', 'lazada', 'sellercenter')
    assert result is None
