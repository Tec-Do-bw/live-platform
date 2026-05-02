import asyncio
from typing import Optional

from fastapi import APIRouter, Request

from app.config import get_group_config, get_login_url, get_proxy_by_country, settings
from app.models.request import CloseBrowserRequest, CreateBrowserRequest
from app.models.response import (
    ApiResponse,
    CODE_ADSPOWER_API_FAILED,
    CODE_FAILED,
    CODE_SESSION_NOT_FOUND,
    CODE_UNSUPPORTED,
    CreateBrowserData,
)
# 注意：AdsPowerApiError, AdsPowerConnectionError 仍用于 create_browser 的异常捕获
from app.services.adspower import AdsPowerApiError, AdsPowerConnectionError, AdsPowerService
from app.services.dynamic_proxy import dynamic_proxy_service
from app.services.login_monitor import login_monitor_service
from app.services.notification import notification_service
from app.services.session import session_manager
from app.services.shopee_api import shopee_api_service
from loguru import logger
router = APIRouter(prefix="/api/browser", tags=["browser"])

_adspower_service = AdsPowerService()


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


async def _connect_and_navigate(debug_port: int, login_url: str):
    def _sync_connect():
        from DrissionPage import Chromium

        browser = Chromium(addr_or_opts=f"127.0.0.1:{debug_port}")
        tab = getattr(browser, "latest_tab", None) or browser.new_tab()
        if login_url:
            tab.get(login_url)
        return tab

    return await asyncio.to_thread(_sync_connect)


def _parse_remark_cb(remark: str) -> int | None:
    """从 remark 中解析 cb 字段值"""
    if not remark or not remark.startswith('vid:'):
        return None
    for part in remark.split('|'):
        part = part.strip()
        if part.startswith('cb:'):
            try:
                return int(part[3:].strip())
            except ValueError:
                return None
    return None


def _build_remark(advertiser_name: str, media: str, validate_id: str, cb_option: int = None) -> str:
    """构建环境备注，Shopee 多店铺场景下设置 validate_id 和 cb_option"""
    if media.lower() == "shopee" and validate_id:
        parts = [f"vid:{validate_id}"]
        if cb_option is not None:
            parts.append(f"cb:{cb_option}")
        return "|".join(parts)
    return advertiser_name or ""


@router.post("/profile/create", response_model=ApiResponse)
async def create_browser(request: Request, payload: CreateBrowserRequest):
    """创建并启动浏览器"""
    profile_id: Optional[str] = payload.collection_id or None
    created_new_profile = False
    is_dynamic_proxy = False  # 标记是否使用动态代理
    group_id = None  # 目标分组ID（登录成功后移动分组用）
    cb_option = None  # Shopee 店铺类型（0=本土，1=跨境）
    try:
        # 查询 Shopee cb_option（本土/跨境标记）
        if payload.media.lower() == "shopee" and payload.validate_id:
            cb_option = await shopee_api_service.get_shop_cb_option(
                country=payload.country,
                shop_id=payload.validate_id
            )

        # 无论新建还是已有环境，登录成功后都需要移动到对应分组
        group_config = get_group_config(payload.country, payload.media)
        if group_config and group_config.get("group_id"):
            group_id = group_config["group_id"]
        else:
            group_id = await _adspower_service.get_or_create_group(
                country=payload.country,
                media=payload.media
            )

        if not profile_id:
            # 创建新环境前，先检查并清理旧环境
            await _adspower_service.cleanup_old_profiles(
                threshold=settings.PROFILE_CLEANUP_THRESHOLD,
                cleanup_count=settings.PROFILE_CLEANUP_COUNT,
                group_id="0"  # 只清理未分组的环境
            )

            # 1. 先从 _PROXY_MAP 获取代理
            proxy = get_proxy_by_country(payload.country)
            if not proxy:
                # 代理不存在，尝试动态代理
                logger.info("国家 {} 无静态代理配置，尝试获取动态代理", payload.country)
                proxy = await dynamic_proxy_service.get_proxy(payload.country)
                if not proxy:
                    return ApiResponse(code=CODE_UNSUPPORTED, msg="不支持的国家")
                is_dynamic_proxy = True

            create_data = await _adspower_service.create_browser(
                group_id=str(0),
                proxy=proxy,
                remark=_build_remark(payload.advertiser_name, payload.media, payload.validate_id, cb_option),
                live_account=payload.live_account,
                country=payload.country,
            )
            profile_id = create_data.get("profile_id") or ""
            if not profile_id:
                return ApiResponse(code=CODE_FAILED, msg="创建浏览器失败：未返回 profile_id")
            created_new_profile = True

            # 浏览器创建成功后，若使用动态代理则发送飞书通知
            if is_dynamic_proxy:
                # 异步发送，不阻塞主流程
                asyncio.create_task(
                    notification_service.notify_unsupported_country(
                        country=payload.country,
                        media=payload.media,
                        profile_id=profile_id
                    )
                )

        try:
            start_data = await _adspower_service.start_browser(profile_id)
        except AdsPowerApiError as exc:
            # 检查是否为 "Profile does not exist" 错误
            if "does not exist" in str(exc).lower() or "不存在" in str(exc):
                logger.warning("Profile {} 不存在，自动创建新环境", profile_id)

                # 获取代理配置
                proxy = get_proxy_by_country(payload.country)
                if not proxy:
                    # 尝试获取动态代理
                    proxy = await dynamic_proxy_service.get_proxy(payload.country)
                    if not proxy:
                        return ApiResponse(code=CODE_UNSUPPORTED, msg="Profile不存在且无法获取代理配置")
                    is_dynamic_proxy = True

                # 创建新环境
                create_data = await _adspower_service.create_browser(
                    group_id=str(0),
                    proxy=proxy,
                    remark=_build_remark(payload.advertiser_name, payload.media, payload.validate_id, cb_option),
                    live_account=payload.live_account,
                    country=payload.country,
                )
                profile_id = create_data.get("profile_id") or ""
                if not profile_id:
                    return ApiResponse(code=CODE_FAILED, msg="自动创建浏览器失败")
                created_new_profile = True

                # 重新启动新创建的浏览器
                start_data = await _adspower_service.start_browser(profile_id)
            else:
                # 其他 API 错误，继续抛出
                raise

        debug_port = start_data.get("debug_port")
        ws_info = start_data.get("ws", {})
        cdp_ws_url = ws_info.get("puppeteer") or ""
        if not debug_port or not cdp_ws_url:
            return ApiResponse(code=CODE_FAILED, msg="启动浏览器失败：缺少调试信息")

        # 已有环境复用时更新环境名和备注（新建环境在 create_browser 时已设置）
        if not created_new_profile and payload.live_account:
            # 如果 cb_option 查询失败（None），尝试从现有 remark 中保留已有的 cb 值
            effective_cb_option = cb_option
            if cb_option is None and payload.media.lower() == "shopee" and payload.validate_id:
                existing_remark = start_data.get("remark", "")
                existing_cb = _parse_remark_cb(existing_remark)
                if existing_cb is not None:
                    effective_cb_option = existing_cb
                    logger.info("cb_option 查询失败，保留现有 remark 中的 cb:{}", existing_cb)

            remark = _build_remark(payload.advertiser_name, payload.media, payload.validate_id, effective_cb_option)
            await _adspower_service.update_browser_name(profile_id, payload.live_account, remark=remark)

        login_url = get_login_url(payload.media, payload.country, cb_option)
        tab = await _connect_and_navigate(int(debug_port), login_url)

        session = session_manager.create(
            profile_id=profile_id,
            debug_port=int(debug_port),
            ws_url=cdp_ws_url,
            country=payload.country,
            media=payload.media,
            advertiser_name=payload.advertiser_name,
            validate_id=payload.validate_id,
            target_group_id=str(group_id) if group_id else None,
            cb_option=cb_option,
            drissionpage_tab=tab,
        )
        login_monitor_service.start(session)

        server_host = request.url.hostname or "localhost"
        ws_port = request.url.port or settings.SERVER_PORT
        ws_url = f"ws://{server_host}:{ws_port}/ws/remote/{session.session_id}"
        data = CreateBrowserData(
            session_id=session.session_id,
            ws_url=ws_url,
            debug_port=str(debug_port),
            collection_id=profile_id
        )
        return ApiResponse(code=0, msg="success", data=data)
    except (AdsPowerConnectionError, AdsPowerApiError) as exc:
        logger.error("AdsPower 调用失败: {}", exc)
        return ApiResponse(code=CODE_ADSPOWER_API_FAILED, msg=str(exc))
    except Exception as exc:
        logger.exception("创建浏览器异常: {}", exc)
        if created_new_profile and profile_id:
            await _adspower_service.cleanup_browser(profile_id)
        return ApiResponse(code=CODE_FAILED, msg="创建浏览器异常")


@router.post("/profile/close", response_model=ApiResponse)
async def close_browser(payload: CloseBrowserRequest):
    session, is_owner = session_manager.begin_cleanup(payload.session_id, owner="api")
    if not session:
        return ApiResponse(code=CODE_SESSION_NOT_FOUND, msg="Session 不存在")

    profile_id = payload.collection_id or session.profile_id

    if is_owner:
        # 关闭前触发回调通知后端
        await login_monitor_service.callback_close(session, reason="api_close")
        await session_manager.close(payload.session_id)
        # 先关闭所有 tab 窗口
        await _close_all_tabs(session)
        await _adspower_service.stop_browser(profile_id)  # 只关闭浏览器，不删除环境
        session_manager.remove(payload.session_id)
    return ApiResponse(code=0, msg="success")
