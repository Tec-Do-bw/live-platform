import asyncio
import json
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.response import CODE_CDP_CONNECT_FAILED
from app.services.adspower import AdsPowerService
from app.services.login_monitor import login_monitor_service
from app.services.screencast import ScreencastService
from app.services.session import session_manager
from loguru import logger
router = APIRouter(tags=["websocket"])

_adspower_service = AdsPowerService()
FRONTEND_CLOSE_GRACE_SECONDS = 0.3


async def _close_all_tabs(session):
    """关闭浏览器中所有 tab 窗口"""
    def _sync_close_tabs():
        try:
            tab = session.drissionpage_tab
            if tab:
                # 先关闭其他 tab
                tab.close(others=True)

        except Exception as e:
            logger.warning("关闭 tab 失败: {}", e)

    await asyncio.to_thread(_sync_close_tabs)


@router.websocket("/ws/remote/{session_id}")
async def remote_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = session_manager.get(session_id)
    if not session or session.status != "active":
        await websocket.close(code=1008)
        return

    session.frontend_ws = websocket
    screencast_service = ScreencastService()

    # WebSocket 连接成功后，检查登录状态，如果已有结果则补发通知
    # 解决：复用已登录环境时，Cookie 已存在导致登录监听在 WebSocket 连接前就完成的问题
    if session.login_status in ["success", "error"]:
        await _send_login_status(websocket, session)

    async def _cdp_to_frontend():
        try:
            await screencast_service.run_screencast_loop(session, websocket)
        except Exception as exc:
            logger.error("CDP 转发异常: {}", exc)
            await _send_error(websocket, "cdp_error")

    async def _frontend_to_cdp():
        try:
            while True:
                message = await websocket.receive_text()
                session_manager.update_activity(session_id)
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue

                msg_type = payload.get("type")
                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "ts": payload.get("ts")}))
                    continue

                if msg_type == "frameAck":
                    # 前端确认已渲染帧（仅用于日志，非阻塞模式下不影响帧处理）
                    screencast_service.ack_pending_frame(payload.get("frameId"))
                    continue
                if msg_type == "frameRequest":
                    # 前端请求重发最后一帧（兜底）
                    await screencast_service.resend_last_frame(websocket)
                    continue

                if msg_type == "input":
                    await _handle_input_event(screencast_service, session, payload)
                    continue

                if msg_type == "resize":
                    continue
        except WebSocketDisconnect:
            logger.info("前端断开: {}", session_id)
        except Exception as exc:
            logger.warning("前端消息异常: {}", exc)

    cdp_task = asyncio.create_task(_cdp_to_frontend())
    frontend_task = asyncio.create_task(_frontend_to_cdp())
    tasks = [cdp_task, frontend_task]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    if cdp_task in done:
        # CDP 先结束时，补发最后一帧并给前端留出处理时间
        await screencast_service.resend_last_frame(websocket)
        try:
            await websocket.send_text(json.dumps({"type": "stream_end"}))
        except Exception:
            pass
        await asyncio.sleep(FRONTEND_CLOSE_GRACE_SECONDS)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    await _cleanup_session(session_id)


async def _handle_input_event(screencast_service: ScreencastService, session, payload: Dict[str, Any]) -> None:
    """处理输入事件（鼠标、键盘、文本）"""
    if not session.cdp_connection:
        await asyncio.sleep(0.1)
    if not session.cdp_connection:
        return

    event_type = payload.get("event")
    cdp_session_id = session.cdp_session_id

    # 事件处理器映射
    handlers = {
        "mouse": screencast_service.handle_mouse_event,
        "key": screencast_service.handle_key_event,
        "text": screencast_service.handle_text_input,
        "clipboard": screencast_service.handle_clipboard_paste,  # 剪贴板粘贴
    }
    handler = handlers.get(event_type)
    if handler:
        await handler(session.cdp_connection, payload, cdp_session_id=cdp_session_id)


async def _send_error(websocket: WebSocket, reason: str) -> None:
    try:
        await websocket.send_text(json.dumps({"type": "error", "reason": reason, "code": CODE_CDP_CONNECT_FAILED}))
    except Exception:
        return


async def _send_login_status(websocket: WebSocket, session) -> None:
    """补发登录状态通知（用于 WebSocket 连接时登录已完成的情况）"""
    try:
        status = session.login_status
        reason = session.login_reason or ""
        shop_id = session.login_shop_id

        if status == "success":
            payload = {
                "type": "login_success",
                "data": {
                    "shop_id": shop_id,
                    "validate_id": session.validate_id,
                    "profile_id": session.profile_id,
                },
            }
        elif reason == "timeout":
            payload = {"type": "login_timeout"}
        else:
            payload = {"type": "login_failed", "reason": reason}
            if shop_id is not None:
                payload["shop_id"] = shop_id

        await websocket.send_text(json.dumps(payload))
        logger.info("补发登录状态通知: session_id={}, status={}", session.session_id, status)
    except Exception as exc:
        logger.warning("补发登录状态通知失败: {}", exc)


async def _cleanup_session(session_id: str) -> None:
    """清理 Session 及关联的浏览器"""
    session, is_owner = session_manager.begin_cleanup(session_id, owner="ws")
    if not session:
        return
    if is_owner:
        # WebSocket 断开时触发回调通知后端
        await login_monitor_service.callback_close(session, reason="ws_disconnect")
        await session_manager.close(session_id)
        # 先关闭所有 tab 窗口
        await _close_all_tabs(session)
        await _adspower_service.stop_browser(session.profile_id)  # 只关闭浏览器，不删除环境
        session_manager.remove(session_id)
