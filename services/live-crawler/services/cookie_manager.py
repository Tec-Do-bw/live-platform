"""Cookie 统一管理模块，提供 Lazada 双端口 Cookie 的 CRUD 接口"""

import json
from datetime import datetime, timezone

from monitor.db import get_connection


def get_cookies(account_id: str, platform: str, endpoint: str = '') -> dict | None:
    """获取指定账号的有效 Cookie，失效或不存在返回 None"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT cookies, is_valid FROM cookies "
            "WHERE account_id=? AND platform=? AND endpoint=?",
            (account_id, platform, endpoint)
        ).fetchone()
    if row is None or row['is_valid'] == 0:
        return None
    return json.loads(row['cookies'])


def save_cookies(account_id: str, platform: str, endpoint: str = '',
                 cookies: dict | None = None,
                 extra: dict | None = None) -> None:
    """写入或更新 Cookie（upsert），自动标记 is_valid=1"""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO cookies (account_id, platform, endpoint, cookies, is_valid, extra, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)
               ON CONFLICT(account_id, platform, endpoint) DO UPDATE SET
                   cookies=excluded.cookies,
                   is_valid=1,
                   extra=CASE WHEN excluded.extra != '{}' THEN excluded.extra ELSE extra END,
                   updated_at=excluded.updated_at""",
            (account_id, platform, endpoint,
             json.dumps(cookies or {}),
             json.dumps(extra or {}),
             now)
        )
        conn.commit()


def get_cookie_extra(account_id: str, platform: str, endpoint: str = '') -> dict:
    """获取 Cookie 记录的 extra 字段（seller_id、venture 等元数据）"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT extra FROM cookies WHERE account_id=? AND platform=? AND endpoint=?",
            (account_id, platform, endpoint)
        ).fetchone()
    if row is None:
        return {}
    return json.loads(row['extra'])


def get_account_credentials(account_id: str, platform: str, endpoint: str = '') -> dict | None:
    """从 extra 字段提取账号密码，不存在或为空返回 None"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT extra FROM cookies WHERE account_id=? AND platform=? AND endpoint=?",
            (account_id, platform, endpoint)
        ).fetchone()
    if row is None:
        return None
    extra = json.loads(row['extra'])
    if not extra.get('username') or not extra.get('password'):
        return None
    return {'username': extra['username'], 'password': extra['password']}
