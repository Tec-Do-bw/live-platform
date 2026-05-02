import asyncio
import sys
import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.append("..")
from app.api import browser as browser_router
from app.api import websocket as websocket_router
from app.config import settings
from app.models.response import ApiResponse, CODE_FAILED, CODE_PARAM_ERROR
from app.services.adspower import AdsPowerService
from app.services.login_monitor import login_monitor_service
from app.services.session import session_manager
from loguru import logger

# 导入以初始化日志配置
import app.utils.logger  # noqa: F401


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


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用"""
    app = FastAPI(title="AdsPower 投屏服务", version="0.1.0")

    # 配置跨域中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(browser_router.router)
    app.include_router(websocket_router.router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """处理请求参数验证错误"""
        logger.warning("参数验证失败: {}", exc)
        return JSONResponse(status_code=422, content=ApiResponse(code=CODE_PARAM_ERROR, msg="参数错误").dict())

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """处理未捕获的异常"""
        logger.exception("未处理异常: {}", exc)
        return JSONResponse(status_code=500, content=ApiResponse(code=CODE_FAILED, msg="服务器异常").dict())

    @app.on_event("shutdown")
    async def shutdown_event():
        """服务关闭时清理所有活跃会话"""
        logger.info("服务关闭，开始清理 Session")
        adspower_service = AdsPowerService()
        for session in session_manager.get_all_active():
            # 应用关闭时触发回调通知后端
            await login_monitor_service.callback_close(session, reason="app_shutdown")
            await session_manager.close(session.session_id)
            # 先关闭所有 tab 窗口
            await _close_all_tabs(session)
            await adspower_service.stop_browser(session.profile_id)  # 只关闭浏览器，不删除环境
            session_manager.remove(session.session_id)

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.SERVER_PORT)
