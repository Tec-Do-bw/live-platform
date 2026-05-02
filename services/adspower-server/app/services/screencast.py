from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

import websockets

from app.config import settings
from loguru import logger

# 无新帧时的最后一帧兜底重发间隔（秒）
FRAME_KEEPALIVE_INTERVAL = 2.0
FRAME_KEEPALIVE_IDLE_THRESHOLD = 1.5
FOCUS_THROTTLE_SECONDS = 0.5

SPECIAL_KEY_CODES = {
    "Control": ("ControlLeft", 17),
    "Shift": ("ShiftLeft", 16),
    "Alt": ("AltLeft", 18),
    "Meta": ("MetaLeft", 91),
    "Backspace": ("Backspace", 8),
    "Delete": ("Delete", 46),
    "Enter": ("Enter", 13),
    "Tab": ("Tab", 9),
    "Escape": ("Escape", 27),
    "ArrowLeft": ("ArrowLeft", 37),
    "ArrowUp": ("ArrowUp", 38),
    "ArrowRight": ("ArrowRight", 39),
    "ArrowDown": ("ArrowDown", 40),
    "Home": ("Home", 36),
    "End": ("End", 35),
    "PageUp": ("PageUp", 33),
    "PageDown": ("PageDown", 34),
    "Insert": ("Insert", 45),
}


class ScreencastService:
    def __init__(self) -> None:
        self._command_id = 0
        self._current_target_id: Optional[str] = None
        self._frame_seq: int = 0
        self._last_frame_payload: Optional[Dict[str, Any]] = None
        self._last_frame_sent_at: float = 0.0
        self._last_frame_received_at: float = 0.0
        self._last_focus_time: float = 0.0
        self._frontend_send_lock = asyncio.Lock()

    async def connect_cdp(self, ws_url: str):
        return await websockets.connect(ws_url, max_size=10 * 1024 * 1024)

    async def start_screencast(self, cdp_ws, cdp_session_id: Optional[str] = None) -> None:
        # 使用配置化的分辨率，确保投屏与浏览器窗口大小一致
        await self._send_command(
            cdp_ws,
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": 80,
                "maxWidth": settings.BROWSER_WIDTH,
                "maxHeight": settings.BROWSER_HEIGHT,
            },
            cdp_session_id=cdp_session_id,
        )

    async def stop_screencast(self, cdp_ws, cdp_session_id: Optional[str] = None) -> None:
        await self._send_command(cdp_ws, "Page.stopScreencast", {}, cdp_session_id=cdp_session_id)

    async def send_frame_ack(
        self, cdp_ws, frame_session_id: int, cdp_session_id: Optional[str] = None
    ) -> None:
        await self._send_command(
            cdp_ws,
            "Page.screencastFrameAck",
            {"sessionId": frame_session_id},
            cdp_session_id=cdp_session_id,
        )

    async def _attach_to_page(
        self, cdp_ws, preferred_url: Optional[str] = None
    ) -> Optional[str]:
        try:
            await self._send_command_and_wait(
                cdp_ws, "Target.setDiscoverTargets", {"discover": True}
            )
        except Exception as exc:
            logger.debug("Target.setDiscoverTargets failed: {}", exc)

        response = await self._send_command_and_wait(cdp_ws, "Target.getTargets", {})
        targets = response.get("result", {}).get("targetInfos", [])
        page_targets = [target for target in targets if target.get("type") == "page"]
        if not page_targets:
            logger.warning("No page targets found for screencast.")
            return None

        def _is_real_page(target: Dict[str, Any]) -> bool:
            url = (target.get("url") or "").lower()
            if not url:
                return False
            if url == "about:blank" or url.startswith("about:"):
                return False
            return not url.startswith(
                ("chrome://", "devtools://", "chrome-extension://", "edge://")
            )

        def _normalize_url(url: str) -> str:
            return url.strip().rstrip("/")

        real_page_targets = [target for target in page_targets if _is_real_page(target)]
        candidate_targets = real_page_targets or page_targets

        target: Optional[Dict[str, Any]] = None
        if preferred_url:
            preferred = _normalize_url(preferred_url)
            target = next(
                (
                    t
                    for t in candidate_targets
                    if _normalize_url(str(t.get("url") or "")) == preferred
                ),
                None,
            )

        if not target:
            attached_targets = [t for t in candidate_targets if t.get("attached")]
            if attached_targets:
                target = attached_targets[-1]

        if not target:
            target = candidate_targets[-1]

        logger.info(
            "选择投屏 Target: id={} url={} attached={}",
            target.get("targetId"),
            target.get("url"),
            target.get("attached"),
        )
        target_id = target.get("targetId")
        if not target_id:
            logger.warning("No targetId found for page target.")
            return None
        self._current_target_id = target_id

        attach_response = await self._send_command_and_wait(
            cdp_ws, "Target.attachToTarget", {"targetId": target_id, "flatten": True}
        )
        session_id = attach_response.get("result", {}).get("sessionId")
        if not session_id:
            logger.warning("Failed to attach to target: {}", attach_response)
            return None
        return session_id

    async def run_screencast_loop(self, session, frontend_ws) -> None:
        try:
            cdp_ws = await self.connect_cdp(session.ws_url)
        except Exception as exc:
            logger.error("CDP 连接失败: {}", exc)
            raise

        session.cdp_connection = cdp_ws
        preferred_url = self._get_preferred_tab_url(session)
        session.cdp_session_id = await self._attach_to_page(cdp_ws, preferred_url=preferred_url)
        if session.cdp_session_id:
            await self._send_command(cdp_ws, "Page.enable", {}, cdp_session_id=session.cdp_session_id)
            await self._ensure_target_active(cdp_ws, session.cdp_session_id)
        await self.start_screencast(cdp_ws, cdp_session_id=session.cdp_session_id)
        logger.info("开始投屏: {}", session.session_id)

        keepalive_task = asyncio.create_task(self._frame_keepalive_loop(frontend_ws))

        try:
            async for message in cdp_ws:
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue

                if payload.get("method") != "Page.screencastFrame":
                    continue

                if (
                    session.cdp_session_id
                    and payload.get("sessionId")
                    and payload.get("sessionId") != session.cdp_session_id
                ):
                    continue

                params = payload.get("params", {})
                frame_data = params.get("data")
                metadata = params.get("metadata", {})
                frame_session_id = params.get("sessionId")
                width = metadata.get("deviceWidth") or metadata.get("width") or 0
                height = metadata.get("deviceHeight") or metadata.get("height") or 0

                if frame_data:
                    # 递增帧序号
                    self._frame_seq += 1
                    frontend_frame_id = self._frame_seq

                    msg = {
                        "type": "frame",
                        "data": frame_data,
                        "width": width,
                        "height": height,
                        "ts": int(time.time() * 1000),
                        "frameId": frontend_frame_id,
                    }
                    if frame_session_id is not None:
                        msg["cdpFrameId"] = frame_session_id
                    self._last_frame_payload = msg
                    self._last_frame_sent_at = time.time()
                    self._last_frame_received_at = self._last_frame_sent_at

                    # 发送帧给前端（非阻塞）
                    await self._send_frontend_message(frontend_ws, msg)

                    # 立即发送 ACK 给 CDP，不等待前端确认（非阻塞式）
                    if frame_session_id is not None:
                        await self.send_frame_ack(
                            cdp_ws, frame_session_id, cdp_session_id=session.cdp_session_id
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("投屏循环异常: {}", exc)
        finally:
            if keepalive_task:
                keepalive_task.cancel()
                await asyncio.gather(keepalive_task, return_exceptions=True)
            try:
                await self.stop_screencast(cdp_ws, cdp_session_id=session.cdp_session_id)
            except Exception as exc:
                logger.debug("停止投屏失败: {}", exc)
            try:
                await cdp_ws.close()
            except Exception as exc:
                logger.debug("关闭 CDP 连接失败: {}", exc)
            logger.info("投屏结束: {}", session.session_id)

    def ack_pending_frame(self, frame_id: Optional[int] = None) -> None:
        """前端确认已渲染帧（仅用于日志/统计，不影响帧处理流程）"""
        # 非阻塞模式下，前端 ACK 仅用于可选的调试日志
        logger.debug("收到前端帧确认: frameId={}", frame_id)

    async def resend_last_frame(self, frontend_ws) -> bool:
        """兜底重发最后一帧（用于前端主动请求或连接关闭前补发）"""
        if not self._last_frame_payload:
            return False
        try:
            await self._send_frontend_message(frontend_ws, self._last_frame_payload, swallow=True)
            self._last_frame_sent_at = time.time()
            return True
        except Exception as exc:
            logger.debug("重发最后一帧失败: {}", exc)
            return False

    async def _frame_keepalive_loop(self, frontend_ws) -> None:
        """无新帧时定时重发最后一帧，避免最后一帧丢失"""
        try:
            while True:
                await asyncio.sleep(FRAME_KEEPALIVE_INTERVAL)
                if not self._last_frame_payload:
                    continue
                now = time.time()
                # 如果最近有新帧到达，不需要 keepalive
                if now - self._last_frame_received_at < FRAME_KEEPALIVE_IDLE_THRESHOLD:
                    continue
                # 如果最近已经发送过，不需要重复发送
                if now - self._last_frame_sent_at < FRAME_KEEPALIVE_INTERVAL:
                    continue
                # 构造新的 keepalive 帧：更新 frameId 和 ts，保留图片数据
                self._frame_seq += 1
                keepalive_frame = {
                    "type": "frame",
                    "data": self._last_frame_payload.get("data"),
                    "width": self._last_frame_payload.get("width", 0),
                    "height": self._last_frame_payload.get("height", 0),
                    "ts": int(now * 1000),
                    "frameId": self._frame_seq,
                    "keepalive": True,  # 标记为 keepalive 帧，便于调试
                }
                if self._last_frame_payload.get("cdpFrameId") is not None:
                    keepalive_frame["cdpFrameId"] = self._last_frame_payload.get("cdpFrameId")
                self._last_frame_payload = keepalive_frame
                self._last_frame_sent_at = now
                await self._send_frontend_message(frontend_ws, keepalive_frame, swallow=True)
                logger.debug("发送 keepalive 帧: frameId={}", self._frame_seq)
        except asyncio.CancelledError:
            raise

    async def _send_frontend_message(
        self, frontend_ws, payload: Dict[str, Any], swallow: bool = False
    ) -> bool:
        try:
            async with self._frontend_send_lock:
                await frontend_ws.send_text(json.dumps(payload))
            return True
        except Exception as exc:
            if swallow:
                logger.debug("发送前端消息失败: {}", exc)
                return False
            raise

    async def _ensure_target_active(self, cdp_ws, cdp_session_id: Optional[str]) -> None:
        if not cdp_session_id:
            return
        now = time.time()
        if now - self._last_focus_time < FOCUS_THROTTLE_SECONDS:
            return
        self._last_focus_time = now
        if self._current_target_id:
            await self._send_command(
                cdp_ws, "Target.activateTarget", {"targetId": self._current_target_id}
            )
        await self._send_command(
            cdp_ws, "Page.bringToFront", {}, cdp_session_id=cdp_session_id
        )

    def _get_preferred_tab_url(self, session: Any) -> Optional[str]:
        tab = getattr(session, "drissionpage_tab", None)
        if not tab:
            return None
        url_value = getattr(tab, "url", None)
        if callable(url_value):
            try:
                url_value = url_value()
            except Exception:
                url_value = None
        if not url_value:
            url_value = getattr(tab, "current_url", None)
            if callable(url_value):
                try:
                    url_value = url_value()
                except Exception:
                    url_value = None
        if isinstance(url_value, str) and url_value:
            return url_value
        return None

    async def handle_mouse_event(
        self, cdp_ws, event: Dict[str, Any], cdp_session_id: Optional[str] = None
    ) -> None:
        action = event.get("action")

        # 处理滚轮事件
        if action == "wheel":
            await self._ensure_target_active(cdp_ws, cdp_session_id)
            await self._handle_wheel_event(cdp_ws, event, cdp_session_id)
            return

        event_type_map = {
            "down": "mousePressed",
            "up": "mouseReleased",
            "move": "mouseMoved",
        }
        cdp_type = event_type_map.get(action)
        if not cdp_type:
            return

        await self._ensure_target_active(cdp_ws, cdp_session_id)
        payload = {
            "type": cdp_type,
            "x": event.get("x", 0),
            "y": event.get("y", 0),
            "button": event.get("button", "left"),
            "clickCount": 1,
        }
        await self._send_command(
            cdp_ws, "Input.dispatchMouseEvent", payload, cdp_session_id=cdp_session_id
        )

    async def _handle_wheel_event(
        self, cdp_ws, event: Dict[str, Any], cdp_session_id: Optional[str] = None
    ) -> None:
        """处理鼠标滚轮事件"""
        payload = {
            "type": "mouseWheel",
            "x": event.get("x", 0),
            "y": event.get("y", 0),
            "deltaX": event.get("deltaX", 0),
            "deltaY": event.get("deltaY", 0),
        }
        await self._send_command(
            cdp_ws, "Input.dispatchMouseEvent", payload, cdp_session_id=cdp_session_id
        )

    async def handle_key_event(
        self, cdp_ws, event: Dict[str, Any], cdp_session_id: Optional[str] = None
    ) -> None:
        """处理键盘事件"""
        action = event.get("action")
        if action not in ("down", "up"):
            return
        await self._ensure_target_active(cdp_ws, cdp_session_id)

        key = event.get("key", "")
        is_single_char = isinstance(key, str) and len(key) == 1
        modifiers = _get_modifiers(event.get("modifiers"))
        has_shortcut_modifier = bool(modifiers & 0b111)

        # 确定文本内容
        text = event.get("text")
        if text is None and is_single_char:
            text = key
        if has_shortcut_modifier:
            text = ""

        # 确定事件类型
        if action == "up":
            cdp_type = "keyUp"
        elif has_shortcut_modifier:
            cdp_type = "rawKeyDown"
        else:
            cdp_type = "keyDown"

        payload = {
            "type": cdp_type,
            "key": key,
            "text": text or "",
            "unmodifiedText": text or "",
            "modifiers": modifiers,
        }

        # 添加键码信息
        code, key_code = self._get_key_code(key, is_single_char)
        if code and key_code is not None:
            payload.update({
                "code": code,
                "keyCode": key_code,
                "windowsVirtualKeyCode": key_code,
                "nativeVirtualKeyCode": key_code,
            })

        await self._send_command(
            cdp_ws, "Input.dispatchKeyEvent", payload, cdp_session_id=cdp_session_id
        )

    def _get_key_code(self, key: str, is_single_char: bool) -> tuple:
        """获取键码信息"""
        special = SPECIAL_KEY_CODES.get(key)
        if special:
            return special
        if is_single_char:
            upper = key.upper()
            if "A" <= upper <= "Z":
                return f"Key{upper}", ord(upper)
            if "0" <= key <= "9":
                return f"Digit{key}", ord(key)
        return None, None

    async def handle_text_input(
        self, cdp_ws, event: Dict[str, Any], cdp_session_id: Optional[str] = None
    ) -> None:
        text = event.get("text", "")
        if not text:
            return
        await self._ensure_target_active(cdp_ws, cdp_session_id)
        await self._send_command(
            cdp_ws, "Input.insertText", {"text": text}, cdp_session_id=cdp_session_id
        )

    async def handle_clipboard_paste(
        self, cdp_ws, event: Dict[str, Any], cdp_session_id: Optional[str] = None
    ) -> None:
        """处理剪贴板粘贴事件 - 将前端传来的剪贴板文本插入到远程浏览器"""
        text = event.get("text", "")
        if not text:
            return
        await self._ensure_target_active(cdp_ws, cdp_session_id)
        # 直接使用 Input.insertText 插入文本
        await self._send_command(
            cdp_ws, "Input.insertText", {"text": text}, cdp_session_id=cdp_session_id
        )

    async def _send_command(
        self, cdp_ws, method: str, params: Dict[str, Any], cdp_session_id: Optional[str] = None
    ) -> int:
        self._command_id += 1
        payload = {
            "id": self._command_id,
            "method": method,
            "params": params,
        }
        if cdp_session_id:
            payload["sessionId"] = cdp_session_id
        await cdp_ws.send(json.dumps(payload))
        return self._command_id

    async def _send_command_and_wait(
        self,
        cdp_ws,
        method: str,
        params: Dict[str, Any],
        cdp_session_id: Optional[str] = None,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        command_id = await self._send_command(
            cdp_ws, method, params, cdp_session_id=cdp_session_id
        )
        while True:
            message = await asyncio.wait_for(cdp_ws.recv(), timeout=timeout)
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue
            if payload.get("id") == command_id:
                if payload.get("error"):
                    logger.warning("CDP command error: {}", payload)
                return payload


def _get_modifiers(modifiers: Optional[Any]) -> int:
    if not modifiers:
        return 0
    if isinstance(modifiers, str):
        modifiers = [modifiers]
    mapping = {
        "alt": 1,
        "ctrl": 2,
        "meta": 4,
        "shift": 8,
    }
    value = 0
    for item in modifiers:
        key = str(item).lower()
        value |= mapping.get(key, 0)
    return value
