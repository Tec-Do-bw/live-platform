"""CollectionMonitor — 采集完整性监控器

通过钩子方法在爬虫关键路径记录采集状态到 SQLite。
"""

import json
from datetime import datetime, timedelta, timezone

from monitor.db import get_connection, init_db


class CollectionMonitor:
    """采集完整性监控器"""

    def __init__(self, db_path: str | None = None):
        self._conn = get_connection(db_path)
        init_db(self._conn)

    @property
    def conn(self):
        """暴露数据库连接供补采模块使用"""
        return self._conn

    def start_batch(self, batch_id: str, mode: str):
        """记录采集批次开始"""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO collection_batches (batch_id, mode, started_at) VALUES (?, ?, ?)",
                (batch_id, mode, datetime.now().isoformat())
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录批次开始失败: {e}')

    def finish_batch(self, batch_id: str):
        """记录采集批次结束，自动统计账号数"""
        try:
            row = self._conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success "
                "FROM account_sessions WHERE batch_id=?",
                (batch_id,)
            ).fetchone()
            total = row['total'] if row else 0
            success = row['success'] if row else 0

            self._conn.execute(
                "UPDATE collection_batches SET finished_at=?, total_accounts=?, success_accounts=? WHERE batch_id=?",
                (datetime.now().isoformat(), total, success, batch_id)
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录批次结束失败: {e}')

    def start_account(self, batch_id: str, account_id: str, group_name: str = '',
                      platform: str = 'tiktok', crawl_type: str = ''):
        """记录账号采集开始"""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO account_sessions (batch_id, account_id, group_name, platform, crawl_type, started_at) VALUES (?, ?, ?, ?, ?, ?)",
                (batch_id, account_id, group_name, platform, crawl_type, datetime.now().isoformat())
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录账号开始失败: {e}')

    def finish_account(self, batch_id: str, account_id: str, status: str = 'success'):
        """记录账号采集结束，自动统计 room 数"""
        try:
            row = self._conn.execute(
                "SELECT COUNT(DISTINCT room_id) as cnt FROM collection_records "
                "WHERE batch_id=? AND account_id=? AND room_id != ''",
                (batch_id, account_id)
            ).fetchone()
            total_rooms = row['cnt'] if row else 0

            self._conn.execute(
                "UPDATE account_sessions SET status=?, total_rooms=?, finished_at=? "
                "WHERE batch_id=? AND account_id=?",
                (status, total_rooms, datetime.now().isoformat(), batch_id, account_id)
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录账号结束失败: {e}')

    def record(self, batch_id: str, account_id: str, api_type: str,
               room_id: str = '', status: str = 'success',
               response_size: int = 0, extra_data: dict | None = None):
        """通用记录方法 — 记录一次 API 采集结果"""
        try:
            extra_json = json.dumps(extra_data, ensure_ascii=False) if extra_data else ''
            self._conn.execute(
                "INSERT OR REPLACE INTO collection_records "
                "(batch_id, account_id, room_id, api_type, status, response_size, extra_data, collected_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (batch_id, account_id, room_id, api_type, status, response_size, extra_json,
                 datetime.now().isoformat())
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录采集数据失败: {e}')

    def record_rooms(self, batch_id: str, account_id: str, rooms_data: list[dict]):
        """记录 live_list 响应，解析直播场次写入 room_sessions

        即使 rooms_data 为空列表，也记录 live_list 的采集状态为 success。
        """
        # 1. 记录 live_list API 本身的采集状态
        self.record(batch_id=batch_id, account_id=account_id,
                    api_type='live_list', status='success',
                    response_size=len(rooms_data),
                    extra_data={'rooms': rooms_data})

        # 2. 解析每个 room，写入 room_sessions
        for room in rooms_data:
            self._insert_room_session(
                batch_id, account_id,
                room_id=str(room.get('room_id', '')),
                start_time=room.get('live_start_ts', 0),
                end_time=room.get('live_end_ts', 0),
            )

    def record_daily_stats(self, batch_id: str, account_id: str,
                           target_date: str, api_type: str = 'live_stats',
                           status: str = 'success'):
        """记录按天采集的指标状态

        Args:
            batch_id: 批次 ID
            account_id: 账号 ID
            target_date: 目标日期，格式 'YYYY-MM-DD'
            api_type: 日期级 api_type，默认 'live_stats'
            status: 采集状态（success / failed / empty）
        """
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO daily_collection_status "
                "(batch_id, account_id, target_date, api_type, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (batch_id, account_id, target_date, api_type, status)
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'记录日期级采集状态失败: {e}')

    def _insert_room_session(self, batch_id: str, account_id: str,
                             room_id: str, start_time: int = 0,
                             end_time: int = 0):
        """写入直播场次到 room_sessions 表"""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO room_sessions "
                "(batch_id, account_id, room_id, start_time, end_time) "
                "VALUES (?, ?, ?, ?, ?)",
                (batch_id, account_id, room_id, start_time, end_time)
            )
            self._conn.commit()
        except Exception as e:
            self._log_error(f'写入直播场次失败: {e}')

    def save_request_context(
        self, account_id: str, context_type: str,
        api_base_url: str = '', query_string: str = '',
        headers: str = '{}', cookies: str = '[]',
        payload_template: str = '{}',
    ) -> None:
        """保存请求上下文到数据库，供补采模块复用"""
        try:
            from monitor.recrawl.models import save_request_context as _save
            _save(
                self._conn, account_id, context_type,
                api_base_url, query_string, headers, cookies, payload_template,
            )
        except Exception as e:
            self._log_error(f'保存请求上下文失败: {e}')

    @staticmethod
    def _log_error(msg: str):
        """静默日志，避免 import logger 在测试中报错"""
        try:
            from utils.logger import logger
            logger.error(msg)
        except ImportError:
            print(f'[MONITOR ERROR] {msg}')


def extract_target_date(request_body: dict) -> str | None:
    """从 live/stats 请求体中提取目标日期

    payload 结构：request.params[0].time_selector.start_timestamp
    target_date = start + 1天（因为 start 是 D-1 的 UTC 00:00）
    """
    try:
        params = request_body.get('request', {}).get('params', [])
        if not params:
            return None
        time_selector = params[0].get('time_selector', {})
        start_ts = time_selector.get('start_timestamp', 0)
        if not start_ts:
            return None
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        target_dt = start_dt + timedelta(days=1)
        return target_dt.strftime('%Y-%m-%d')
    except Exception:
        return None
