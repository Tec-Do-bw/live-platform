from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from loguru import logger


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    profile_id: str = ""
    debug_port: int = 0
    ws_url: str = ""
    country: str = ""
    media: str = ""
    advertiser_name: str = ""
    validate_id: Optional[str] = None
    target_group_id: Optional[str] = None  # 登录成功后移动到的目标分组ID
    cb_option: Optional[int] = None  # 0=本土店, 1=跨境店
    drissionpage_tab: Any = None
    cdp_connection: Any = None
    cdp_session_id: Optional[str] = None
    pending_frame_session_id: Optional[int] = None  # 待前端确认的帧 session ID
    frontend_ws: Any = None
    login_status: Optional[str] = None
    login_reason: Optional[str] = None
    login_shop_id: Optional[int] = None
    login_callback_sent: bool = False  # 回调是否已发送
    login_task: Any = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: datetime = field(default_factory=datetime.utcnow)
    status: str = "active"
    cleanup_started: bool = False
    cleanup_owner: str = ""


class SessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}

    def create(
        self,
        profile_id: str,
        debug_port: int,
        ws_url: str,
        country: str,
        media: str,
        advertiser_name: str,
        validate_id: Optional[str] = None,
        target_group_id: Optional[str] = None,
        cb_option: Optional[int] = None,
        drissionpage_tab: Any = None,
    ) -> Session:
        session = Session(
            profile_id=profile_id,
            debug_port=debug_port,
            ws_url=ws_url,
            country=country,
            media=media,
            advertiser_name=advertiser_name,
            validate_id=validate_id,
            target_group_id=target_group_id,
            cb_option=cb_option,
            drissionpage_tab=drissionpage_tab,
        )
        self._sessions[session.session_id] = session
        logger.info("创建 Session: {}", session.session_id)
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def begin_cleanup(self, session_id: str, owner: str) -> Tuple[Optional[Session], bool]:
        session = self.get(session_id)
        if not session:
            return None, False
        if session.cleanup_started:
            return session, False
        session.cleanup_started = True
        session.cleanup_owner = owner
        return session, True

    def update_activity(self, session_id: str) -> None:
        session = self.get(session_id)
        if not session:
            return
        session.last_active = datetime.utcnow()

    async def close(self, session_id: str) -> bool:
        """关闭会话并清理资源"""
        session = self.get(session_id)
        if not session:
            return False
        session.status = "closed"
        session.last_active = datetime.utcnow()
        # 取消登录监听任务
        self._safe_cancel(session.login_task, "登录监听任务")
        # 关闭 WebSocket 连接
        await self._safe_close_ws(session.frontend_ws, "前端 WebSocket")
        await self._safe_close_ws(session.cdp_connection, "CDP WebSocket")
        # 关闭 DrissionPage 标签页
        self._safe_call(session.drissionpage_tab, "close", "DrissionPage 标签页")
        return True

    def _safe_cancel(self, task: Any, name: str) -> None:
        """安全取消异步任务"""
        if task is None:
            return
        cancel_method = getattr(task, "cancel", None)
        if callable(cancel_method):
            try:
                cancel_method()
            except Exception as exc:
                logger.debug("取消 {} 失败: {}", name, exc)

    def _safe_call(self, obj: Any, method_name: str, name: str) -> None:
        """安全调用对象方法"""
        if obj is None:
            return
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                method()
            except Exception as exc:
                logger.warning("关闭 {} 失败: {}", name, exc)

    def remove(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions.pop(session_id, None)
            logger.info("移除 Session: {}", session_id)

    def get_all_active(self) -> List[Session]:
        return [session for session in self._sessions.values() if session.status == "active"]

    async def _safe_close_ws(self, ws: Any, name: str) -> None:
        if ws is None:
            return
        close_method = getattr(ws, "close", None)
        if not callable(close_method):
            return
        try:
            result = close_method()
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            logger.warning("关闭 {} 失败: {}", name, exc)


session_manager = SessionManager()
