#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从旧 cookies 表迁移到 account_credentials 表。

默认只做 dry-run，打印建表 SQL、迁移条数和重复 endpoint 舍弃清单；
传入 --execute 才会写入 SQLite。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from monitor import get_connection
from utils.adspower_client import AdsPowerApiError, AdsPowerRateLimitError, get_adspower_client
from utils.adspower_proxy import build_proxy_url
from utils.logger import logger


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
class MigrationCandidate:
    """单个账号迁移候选。"""

    account_id: str
    platform: str
    endpoint: str
    token: str
    extra: str
    updated_at: str
    group_name: str
    proxy: str
    discarded_endpoints: list[str]
    blockers: list[str]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="迁移 cookies 表到 account_credentials 表")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只打印迁移计划，不写库（默认）")
    mode.add_argument("--execute", action="store_true", help="执行迁移写入")
    parser.add_argument("--db-path", default=None, help="SQLite 数据库路径，默认使用 monitor/data/monitor.db")
    parser.add_argument(
        "--skip-adspower",
        action="store_true",
        help="跳过 AdsPower enrichment，group_name/proxy 留空",
    )
    return parser.parse_args()


def _safe_json_text(value: str | None, default: str) -> str:
    """确保字段是合法 JSON 文本，不合法时保留默认值。"""
    if not value:
        return default
    try:
        json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
    return value


def _row_time_key(row: Any) -> tuple[str, str, int]:
    """按 updated_at DESC、created_at DESC、id DESC 选最新行。"""
    return (
        row["updated_at"] or "",
        row["created_at"] or "",
        int(row["id"] or 0),
    )


def _fetch_profile(account_id: str) -> tuple[str, str, str | None]:
    """从 AdsPower 拉取 group_name 和 proxy。

    Returns:
        (group_name, proxy, blocker)
    """
    try:
        client = get_adspower_client()
        data = client.post("/api/v2/browser-profile/list", json={"profile_id": [account_id]})
        profiles = data.get("data", {}).get("list", [])
        if not profiles:
            return "", "", f"账号 {account_id} 未在 AdsPower browser-profile/list 找到"

        profile = profiles[0]
        group_name = (
            profile.get("group_name")
            or profile.get("group", {}).get("group_name")
            or profile.get("groupName")
            or ""
        )
        proxy = build_proxy_url(profile.get("user_proxy_config", {}) or {}) or ""
        return str(group_name or ""), proxy, None
    except (AdsPowerRateLimitError, AdsPowerApiError) as e:
        return "", "", f"账号 {account_id} AdsPower enrichment 失败: {e}"
    except Exception as e:
        return "", "", f"账号 {account_id} AdsPower enrichment 异常: {type(e).__name__}: {e}"


def _load_candidates(conn: Any, skip_adspower: bool) -> list[MigrationCandidate]:
    rows = conn.execute(
        """
        SELECT id, account_id, platform, endpoint, cookies, extra, updated_at, created_at
        FROM cookies
        WHERE is_valid = 1
        ORDER BY account_id, updated_at DESC, created_at DESC, id DESC
        """
    ).fetchall()

    grouped: dict[str, list[Any]] = {}
    for row in rows:
        grouped.setdefault(row["account_id"], []).append(row)

    candidates: list[MigrationCandidate] = []
    for account_id, account_rows in grouped.items():
        sorted_rows = sorted(account_rows, key=_row_time_key, reverse=True)
        selected = sorted_rows[0]
        discarded = [
            f"{row['platform']}:{row['endpoint'] or '<empty>'}"
            for row in sorted_rows[1:]
        ]

        blockers: list[str] = []
        group_name = ""
        proxy = ""
        if skip_adspower:
            blockers.append(f"账号 {account_id} 跳过 AdsPower enrichment，group_name/proxy 留空")
        else:
            group_name, proxy, blocker = _fetch_profile(account_id)
            if blocker:
                blockers.append(blocker)

        token = _safe_json_text(selected["cookies"], "{}")
        extra = _safe_json_text(selected["extra"], "{}")

        candidates.append(
            MigrationCandidate(
                account_id=account_id,
                platform=selected["platform"],
                endpoint=selected["endpoint"] or "",
                token=token,
                extra=extra,
                updated_at=selected["updated_at"] or selected["created_at"] or "",
                group_name=group_name,
                proxy=proxy,
                discarded_endpoints=discarded,
                blockers=blockers,
            )
        )

    return candidates


def _execute_migration(conn: Any, candidates: list[MigrationCandidate]) -> None:
    conn.executescript(CREATE_TABLE_SQL)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(account_credentials)").fetchall()}
    if "crawler_mode" not in columns:
        conn.execute("ALTER TABLE account_credentials ADD COLUMN crawler_mode TEXT DEFAULT NULL")
    for item in candidates:
        conn.execute(
            """
            INSERT INTO account_credentials (
                account_id, platform, group_name, token, region, proxy,
                ext_json, extra, crawler_mode, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, COALESCE(NULLIF(?, ''), CURRENT_TIMESTAMP))
            ON CONFLICT(account_id) DO UPDATE SET
                platform=excluded.platform,
                group_name=excluded.group_name,
                token=excluded.token,
                region=excluded.region,
                proxy=excluded.proxy,
                ext_json=excluded.ext_json,
                extra=excluded.extra,
                crawler_mode=COALESCE(excluded.crawler_mode, account_credentials.crawler_mode),
                updated_at=excluded.updated_at
            """,
            (
                item.account_id,
                item.platform,
                item.group_name,
                item.token,
                "",
                item.proxy,
                "{}",
                item.extra,
                item.updated_at,
            ),
        )
    conn.commit()


def _print_summary(candidates: list[MigrationCandidate], execute: bool) -> None:
    print("=== account_credentials migration ===")
    print(f"mode={'execute' if execute else 'dry-run'}")
    print("SQL:")
    print(CREATE_TABLE_SQL.strip())
    print(f"候选迁移账号数: {len(candidates)}")
    discarded_count = sum(len(item.discarded_endpoints) for item in candidates)
    print(f"重复 endpoint 舍弃行数: {discarded_count}")

    for item in candidates:
        print(
            f"- {item.account_id} platform={item.platform} "
            f"endpoint={item.endpoint or '<empty>'} group_name={item.group_name or '<empty>'} "
            f"proxy={'yes' if item.proxy else 'no'}"
        )
        if item.discarded_endpoints:
            print(f"  discarded={', '.join(item.discarded_endpoints)}")
        for blocker in item.blockers:
            print(f"  BLOCKER: {blocker}")


def main() -> int:
    args = _parse_args()
    execute = bool(args.execute)
    if not execute:
        args.dry_run = True

    conn = get_connection(args.db_path)
    try:
        candidates = _load_candidates(conn, args.skip_adspower)
        _print_summary(candidates, execute=execute)
        if execute:
            _execute_migration(conn, candidates)
            logger.info(f"account_credentials 迁移完成，写入账号数={len(candidates)}")
        else:
            logger.info(f"account_credentials dry-run 完成，候选账号数={len(candidates)}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
