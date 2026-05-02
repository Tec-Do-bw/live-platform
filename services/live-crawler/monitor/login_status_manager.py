"""账号登录状态管理器。

负责维护账号当前登录快照，以及基于事件的登录状态历史。
"""

import json
import sqlite3
from datetime import datetime
from utils.logger import logger


class LoginStatusManager:
    """账号登录状态管理器。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def append_event(
        self,
        account_id: str,
        platform: str,
        group_name: str,
        event_type: str,
        batch_id: str = '',
        detail: dict | None = None,
        event_time: str | None = None,
        commit: bool = True,
    ) -> None:
        """写入登录状态历史事件。"""
        try:
            self._conn.execute(
                """INSERT INTO account_login_events
                   (account_id, platform, group_name, event_type, event_time, batch_id, detail)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    account_id,
                    platform,
                    group_name,
                    event_type,
                    event_time or datetime.now().isoformat(),
                    batch_id,
                    json.dumps(detail or {}, ensure_ascii=False),
                ),
            )
            if commit:
                self._conn.commit()
        except Exception as e:
            if commit:
                self._conn.rollback()
            logger.error(f'写入登录状态历史事件失败: {e}')
            raise

    def list_events(self, account_id: str, limit: int = 100) -> list[dict]:
        """按时间倒序列出账号登录状态历史事件。"""
        try:
            rows = self._conn.execute(
                """SELECT * FROM account_login_events
                   WHERE account_id = ?
                   ORDER BY event_time DESC, id DESC
                   LIMIT ?""",
                (account_id, limit),
            ).fetchall()
            return [self._event_row_to_dict(row) for row in rows]
        except Exception as e:
            logger.error(f'查询登录状态历史事件失败: {e}')
            return []

    def get_recent_events(self, account_id: str, limit: int = 2) -> list[dict]:
        """查询账号最近 N 条事件。"""
        return self.list_events(account_id, limit=limit)

    def record_login_status(
        self,
        account_id: str,
        platform: str,
        group_name: str,
        login_status: str,
        reason: str = '',
    ) -> None:
        """根据登录回调刷新状态快照并写入 logout/login 事件。"""
        now = datetime.now().isoformat()
        is_logout = login_status == 'logout'
        event_type = 'logout' if is_logout else 'login'

        try:
            current_status = self.get_account_status(account_id)
            if is_logout:
                self._conn.execute(
                    """INSERT INTO account_login_status
                       (account_id, platform, group_name, status, logout_at, login_at,
                        logout_reason, recovery_batch_id, updated_at)
                       VALUES (?, ?, ?, 'logout', ?, NULL, ?, '', ?)
                       ON CONFLICT(account_id)
                       DO UPDATE SET platform=excluded.platform,
                                     group_name=excluded.group_name,
                                     status='logout',
                                     logout_at=excluded.logout_at,
                                     login_at=NULL,
                                     logout_reason=excluded.logout_reason,
                                     recovery_batch_id='',
                                     updated_at=excluded.updated_at""",
                    (account_id, platform, group_name, now, reason, now),
                )
            elif current_status:
                self._conn.execute(
                    """UPDATE account_login_status
                       SET platform=?, group_name=?, status='online',
                           login_at=?, logout_reason='', recovery_batch_id='', updated_at=?
                       WHERE account_id=?""",
                    (platform, group_name, now, now, account_id),
                )
            else:
                self._conn.execute(
                    """INSERT INTO account_login_status
                       (account_id, platform, group_name, status, login_at,
                        logout_reason, recovery_batch_id, updated_at)
                       VALUES (?, ?, ?, 'online', ?, '', '', ?)""",
                    (account_id, platform, group_name, now, now),
                )

            detail = {'reason': reason} if reason else None
            self.append_event(
                account_id=account_id,
                platform=platform,
                group_name=group_name,
                event_type=event_type,
                detail=detail,
                event_time=now,
                commit=False,
            )
            self._conn.commit()
            logger.info(f'账号 {account_id} 登录状态已更新: {event_type}')
        except Exception as e:
            self._conn.rollback()
            logger.error(f'更新账号登录状态失败: {e}')
            raise

    def mark_logout(
        self,
        account_id: str,
        platform: str,
        group_name: str,
        reason: str,
    ) -> None:
        """兼容旧调用：记录账号登出。"""
        self.record_login_status(
            account_id=account_id,
            platform=platform,
            group_name=group_name,
            login_status='logout',
            reason=reason,
        )

    def mark_login(
        self,
        account_id: str,
        platform: str,
        group_name: str,
    ) -> None:
        """兼容旧调用：记录账号登录。"""
        self.record_login_status(
            account_id=account_id,
            platform=platform,
            group_name=group_name,
            login_status='success',
        )

    def mark_full_recovery_pending(
        self,
        account_id: str,
        platform: str,
        group_name: str,
    ) -> None:
        """记录手动恢复请求事件。"""
        now = datetime.now().isoformat()
        try:
            current_status = self.get_account_status(account_id)
            if current_status:
                self._conn.execute(
                    """UPDATE account_login_status
                       SET platform=?, group_name=?, updated_at=?
                       WHERE account_id=?""",
                    (platform, group_name, now, account_id),
                )
            else:
                self._conn.execute(
                    """INSERT INTO account_login_status
                       (account_id, platform, group_name, status, login_at,
                        logout_reason, recovery_batch_id, updated_at)
                       VALUES (?, ?, ?, 'online', ?, '', '', ?)""",
                    (account_id, platform, group_name, now, now),
                )

            self.append_event(
                account_id=account_id,
                platform=platform,
                group_name=group_name,
                event_type='full_recovery_marked',
                detail={'source': 'manual_trigger'},
                event_time=now,
                commit=False,
            )
            self._conn.commit()
            logger.info(f'账号 {account_id} 已记录手动恢复请求事件')
        except Exception as e:
            self._conn.rollback()
            logger.error(f'记录手动恢复请求事件失败: {e}')
            raise

    def get_account_status(self, account_id: str) -> dict | None:
        """获取账号当前状态。"""
        try:
            row = self._conn.execute(
                "SELECT * FROM account_login_status WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f'获取账号状态失败: {e}')
            return None

    def list_logout_accounts(self, platform: str | None = None) -> list[dict]:
        """列出所有登出状态的账号。"""
        try:
            sql = "SELECT * FROM account_login_status WHERE status = 'logout'"
            params: list = []
            if platform:
                sql += " AND platform = ?"
                params.append(platform)
            sql += " ORDER BY logout_at DESC"

            rows = self._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f'列出登出账号失败: {e}')
            return []

    @staticmethod
    def _event_row_to_dict(row: sqlite3.Row) -> dict:
        """将事件记录转为 API 友好的字典。"""
        item = dict(row)
        detail = item.get('detail') or '{}'
        try:
            item['detail'] = json.loads(detail)
        except json.JSONDecodeError:
            item['detail'] = {'raw': detail}
        return item
