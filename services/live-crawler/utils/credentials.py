"""account_credentials 表读写工具。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from monitor import get_connection


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS account_credentials (
    account_id    TEXT PRIMARY KEY,
    platform      TEXT NOT NULL,
    group_name    TEXT NOT NULL,
    token         TEXT NOT NULL,
    region        TEXT NOT NULL,
    proxy         TEXT,
    ext_json      TEXT,
    extra         TEXT,
    crawler_mode  TEXT DEFAULT NULL,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_group_platform
    ON account_credentials(group_name, platform);
CREATE INDEX IF NOT EXISTS idx_platform_region
    ON account_credentials(platform, region);
"""


@dataclass
class Credentials:
    """HTTP 采集账号凭据。"""

    account_id: str
    platform: str
    group_name: str
    token: str
    region: str
    proxy: str
    ext_json: str
    extra: str
    crawler_mode: str | None = None
    updated_at: str = ""

    @property
    def token_data(self) -> dict[str, Any] | list[dict[str, Any]]:
        """解析 Cookie JSON，兼容 dict 与浏览器 cookie list。"""
        return _loads_json(self.token, {})

    @property
    def ext(self) -> dict[str, Any]:
        """解析平台扩展参数。"""
        data = _loads_json(self.ext_json, {})
        return data if isinstance(data, dict) else {}

    @property
    def extra_data(self) -> dict[str, Any]:
        """解析额外字段。"""
        data = _loads_json(self.extra, {})
        return data if isinstance(data, dict) else {}

    @property
    def fingerprint_spec(self) -> dict[str, Any]:
        """从 ext_json/extra 派生 curl_cffi 指纹配置。"""
        ext = self.ext
        extra = self.extra_data
        return {
            "impersonate": ext.get("impersonate") or extra.get("impersonate") or "chrome",
            "user_agent": ext.get("user_agent") or extra.get("user_agent") or "",
            "sec_ch_ua": ext.get("sec_ch_ua") or extra.get("sec_ch_ua") or "",
            "sec_ch_ua_mobile": ext.get("sec_ch_ua_mobile") or extra.get("sec_ch_ua_mobile") or "?0",
            "sec_ch_ua_platform": ext.get("sec_ch_ua_platform") or extra.get("sec_ch_ua_platform") or "",
            "accept_language": ext.get("accept_language") or extra.get("accept_language") or "en-US,en;q=0.9",
        }

    def save(self) -> None:
        """保存当前凭据对象。"""
        save_credentials(
            account_id=self.account_id,
            platform=self.platform,
            group_name=self.group_name,
            token=self.token,
            region=self.region,
            proxy=self.proxy,
            ext_json=self.ext_json,
            extra=self.extra,
            crawler_mode=self.crawler_mode,
        )


def _loads_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _dumps_json(value: Any, default: str = "{}") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default
        return value
    return json.dumps(value, ensure_ascii=False)


def ensure_table(conn: Any | None = None) -> None:
    """确保 account_credentials 表和索引存在。"""
    own_conn = conn is None
    conn = conn or get_connection()
    try:
        conn.executescript(CREATE_TABLE_SQL)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(account_credentials)").fetchall()}
        if "crawler_mode" not in columns:
            conn.execute("ALTER TABLE account_credentials ADD COLUMN crawler_mode TEXT DEFAULT NULL")
        conn.commit()
    finally:
        if own_conn:
            conn.close()


def load_credentials(account_id: str, platform: str = "tiktok") -> Credentials | None:
    """读取单个账号凭据。"""
    conn = get_connection()
    try:
        ensure_table(conn)
        row = conn.execute(
            """
            SELECT account_id, platform, group_name, token, region, proxy,
                   ext_json, extra, crawler_mode, updated_at
            FROM account_credentials
            WHERE account_id = ? AND platform = ?
            """,
            (account_id, platform),
        ).fetchone()
        if not row:
            return None
        return Credentials(
            account_id=row["account_id"],
            platform=row["platform"],
            group_name=row["group_name"] or "",
            token=row["token"] or "{}",
            region=row["region"] or "",
            proxy=row["proxy"] or "",
            ext_json=row["ext_json"] or "{}",
            extra=row["extra"] or "{}",
            crawler_mode=row["crawler_mode"],
            updated_at=row["updated_at"] or "",
        )
    finally:
        conn.close()


def save_credentials(
    account_id: str,
    platform: str,
    group_name: str = "",
    token: str | dict[str, Any] | list[dict[str, Any]] = "{}",
    region: str = "",
    proxy: str | None = "",
    ext_json: str | dict[str, Any] | None = "{}",
    extra: str | dict[str, Any] | None = "{}",
    crawler_mode: str | None = None,
) -> None:
    """写入或更新账号凭据。"""
    conn = get_connection()
    try:
        ensure_table(conn)
        conn.execute(
            """
            INSERT INTO account_credentials (
                account_id, platform, group_name, token, region, proxy,
                ext_json, extra, crawler_mode, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(account_id) DO UPDATE SET
                platform=excluded.platform,
                group_name=excluded.group_name,
                token=excluded.token,
                region=excluded.region,
                proxy=excluded.proxy,
                ext_json=excluded.ext_json,
                extra=excluded.extra,
                crawler_mode=COALESCE(excluded.crawler_mode, account_credentials.crawler_mode),
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                account_id,
                platform,
                group_name or "",
                _dumps_json(token),
                region or "",
                proxy or "",
                _dumps_json(ext_json),
                _dumps_json(extra),
                crawler_mode,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_accounts(platform: str = "tiktok", group_name: str | None = None) -> list[Credentials]:
    """按平台和可选分组列出账号凭据。"""
    conn = get_connection()
    try:
        ensure_table(conn)
        if group_name is None:
            rows = conn.execute(
                """
                SELECT account_id, platform, group_name, token, region, proxy,
                       ext_json, extra, crawler_mode, updated_at
                FROM account_credentials
                WHERE platform = ?
                ORDER BY updated_at DESC
                """,
                (platform,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT account_id, platform, group_name, token, region, proxy,
                       ext_json, extra, crawler_mode, updated_at
                FROM account_credentials
                WHERE platform = ? AND group_name = ?
                ORDER BY updated_at DESC
                """,
                (platform, group_name),
            ).fetchall()

        return [
            Credentials(
                account_id=row["account_id"],
                platform=row["platform"],
                group_name=row["group_name"] or "",
                token=row["token"] or "{}",
                region=row["region"] or "",
                proxy=row["proxy"] or "",
                ext_json=row["ext_json"] or "{}",
                extra=row["extra"] or "{}",
                crawler_mode=row["crawler_mode"],
                updated_at=row["updated_at"] or "",
            )
            for row in rows
        ]
    finally:
        conn.close()
